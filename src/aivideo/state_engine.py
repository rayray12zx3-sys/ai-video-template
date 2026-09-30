"""Single writer for canonical project state and append-only event history.

The project file is UTF-8 JSON (a YAML 1.2 subset). Hashes cover exact bytes.
"""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import tempfile

from .schema import (CURRENT_EVENT_SCHEMA, CURRENT_PROJECT_SCHEMA, MigrationRequired,
                     SchemaError, UnsupportedNewerSchema, schema_access, validate)


class StateConflict(RuntimeError):
    code = "STATE_CONFLICT"


class RecoveryConflict(RuntimeError):
    code = "RECOVERY_CONFLICT"


class RemoteStateConflict(StateConflict):
    code = "REMOTE_STATE_CONFLICT"


class WriterLockConflict(RuntimeError):
    code = "WRITER_LOCK_CONFLICT"


class DuplicateTransaction(StateConflict):
    code = "DUPLICATE_TRANSACTION"


class DuplicateImport(StateConflict):
    code = "DUPLICATE_IMPORT"


class PhaseI1Required(RuntimeError):
    """Retained for callers of the I0 stub API; I1 requires a new state."""


@dataclass(frozen=True)
class ProjectSnapshot:
    document: dict
    state_revision: int | None
    project_hash: str
    access: str
    next_action: str | None


@dataclass(frozen=True)
class TransactionRequest:
    expected_state_revision: int
    expected_project_hash: str
    transaction_id: str
    actor: str
    event_type: str
    handoff_base: dict | None = None


@dataclass(frozen=True)
class ImportAdoptionPlan:
    document: dict
    transition_metadata: dict


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _subject(document, ref):
    if not isinstance(ref, str) or ":" not in ref:
        return None
    kind, ident = ref.split(":", 1)
    if kind == "project":
        return document.get(ident)
    collection = {"asset": "assets", "shot": "shots"}.get(kind)
    if collection:
        return next((item for item in document.get(collection, [])
                     if isinstance(item, dict) and item.get("id") == ident), None)
    return None


def _check_dependency_transition(before, after, metadata):
    """Require auditable typed invalidation on canonical upstream edits."""
    impacts = {"IDENTITY", "APPEARANCE", "STRUCTURE", "COMPOSITION", "CAMERA", "MOTION",
               "TIMING", "SEMANTIC_CONTENT", "AUDIO", "BRAND", "TECHNICAL_FORMAT",
               "DELIVERY_ONLY", "GENERIC"}
    metadata = metadata if isinstance(metadata, dict) else {}
    def edge_set(document):
        result = set()
        for item in document.get("dependencies", []):
            if (not isinstance(item, dict) or not isinstance(item.get("source"), str)
                    or not isinstance(item.get("target"), str)
                    or not isinstance(item.get("impact", "GENERIC"), str)
                    or item.get("impact", "GENERIC") not in impacts):
                raise StateConflict("dependency edge has invalid source, target, or impact")
            result.add((item["source"], item["target"], item.get("impact", "GENERIC")))
        return result
    before_edges = edge_set(before)
    after_edges = edge_set(after)
    edge_changes = metadata.get("dependency_changes", [])
    if not isinstance(edge_changes, list):
        edge_changes = []
    for operation, changed_edges in (("ADDED", after_edges - before_edges),
                                     ("REMOVED", before_edges - after_edges)):
        for source, target, impact in changed_edges:
            if _subject(before, target) is None and operation == "ADDED":
                continue  # a new dependent has no prior approval to invalidate
            if not any(isinstance(item, dict) and item.get("operation") == operation
                       and item.get("source") == source and item.get("target") == target
                       and item.get("impact") == impact for item in edge_changes):
                raise StateConflict(f"dependency edge {operation} requires audited declaration")
            dependent = _subject(after, target)
            if isinstance(dependent, dict) and dependent.get("lifecycle", dependent.get("status")) not in {"STALE", "MISSING", "SUPERSEDED"}:
                raise StateConflict(f"changed dependency target {target} must be marked STALE")
    declarations = metadata.get("changes", [])
    if isinstance(metadata.get("change"), dict):
        declarations = [*declarations, metadata["change"]] if isinstance(declarations, list) else [metadata["change"]]
    if not isinstance(declarations, list):
        declarations = []
    edges = [edge for edge in before.get("dependencies", []) + after.get("dependencies", [])
             if isinstance(edge, dict) and isinstance(edge.get("source"), str)]
    seen = set()
    for edge in edges:
        source = edge["source"]
        if not isinstance(edge.get("target"), str) or edge.get("impact", "GENERIC") not in impacts:
            raise StateConflict("dependency edge has invalid target or impact")
        if (source, edge["target"], edge.get("impact")) in seen:
            continue
        seen.add((source, edge["target"], edge.get("impact")))
        if _subject(before, source) is None or _subject(before, source) == _subject(after, source):
            continue
        declaration = next((item for item in declarations if isinstance(item, dict)
                            and item.get("target") == source and isinstance(item.get("dimensions"), list)
                            and item["dimensions"] and all(isinstance(d, str) and d in impacts
                                                       for d in item["dimensions"])), None)
        if declaration is None:
            raise StateConflict(f"changed dependency source {source} requires change dimensions")
        impact = edge.get("impact", "GENERIC")
        if impact != "GENERIC" and "GENERIC" not in declaration["dimensions"] and impact not in declaration["dimensions"]:
            continue
        dependent = _subject(after, edge.get("target"))
        if not isinstance(dependent, dict) or dependent.get("lifecycle", dependent.get("status")) not in {"STALE", "MISSING", "SUPERSEDED"}:
            raise StateConflict(f"dependent {edge.get('target')} must be marked STALE")
    remediation = metadata.get("remediation")
    for edge in edges:
        target = edge.get("target")
        old = _subject(before, target)
        new = _subject(after, target)
        if not isinstance(old, dict) or not isinstance(new, dict):
            continue
        if old.get("lifecycle", old.get("status")) != "STALE" or new.get("lifecycle", new.get("status")) == "STALE":
            continue
        if (not isinstance(remediation, dict) or remediation.get("target") != target
                or not isinstance(remediation.get("evidence_id"), str)
                or new.get("remediated_after_revision") != after["state_revision"]
                or not any(isinstance(item, dict) and item.get("id") == remediation["evidence_id"]
                           and item.get("status") == "APPROVED" and item.get("subject") == target
                           for item in after.get("evidence", []))):
            raise StateConflict(f"remediation of {target} requires audited approval evidence")


def _sync_directory(path: Path) -> None:
    # Windows cannot portably fsync a directory with stdlib.
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _atomic_replace(path: Path, raw: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        _sync_directory(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class LocalWriterLock:
    """OS lock released on process exit; metadata is diagnostic, never authority."""

    def __init__(self, project_dir: Path):
        self.path = Path(project_dir) / ".state-engine.lock"
        self.previous_owner = None

    @contextmanager
    def acquire(self, transaction_id: str):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a+b", buffering=0) as stream:
            if self.path.stat().st_size == 0:
                stream.seek(0)
                stream.write(b"L")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise WriterLockConflict("another local writer owns the OS lock") from exc
            try:
                stream.seek(1)
                previous = stream.read().strip()
                try:
                    self.previous_owner = json.loads(previous) if previous else None
                except (ValueError, UnicodeError):
                    self.previous_owner = {"status": "UNREADABLE_METADATA"}
                metadata = {"pid": os.getpid(), "host": socket.gethostname(),
                            "acquired_at": datetime.now(timezone.utc).isoformat(),
                            "transaction_id": transaction_id, "status": "ACTIVE"}
                self._metadata(stream, metadata)
                yield self
                metadata["status"] = "RELEASED"
                self._metadata(stream, metadata)
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _metadata(stream, value):
        stream.seek(1)
        stream.truncate(1)
        stream.write(_json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


class PendingJournal:
    def __init__(self, project_dir: Path):
        self.path = Path(project_dir) / ".pending-transaction.json"

    def prepare(self, request: TransactionRequest, before: ProjectSnapshot, after: dict, event: dict):
        if self.path.exists():
            raise RecoveryConflict("pending journal already exists")
        after_raw = _json_bytes(after)
        record = {"journal_version": "1.0", "transaction_id": request.transaction_id,
                  "before_revision": before.state_revision, "before_hash": before.project_hash,
                  "after_revision": after["state_revision"], "after_hash": _hash(after_raw),
                  "after_text": after_raw.decode("utf-8"), "event": event}
        _atomic_replace(self.path, _json_bytes(record))
        return record

    def load(self):
        if not self.path.exists():
            return None
        try:
            record = json.loads(self.path.read_bytes())
            if not isinstance(record, dict) or record.get("journal_version") != "1.0":
                raise ValueError("journal version")
            raw = record["after_text"].encode("utf-8")
            after = json.loads(raw)
            validate(after, "project")
            event = record["event"]
            validate(event, "event")
            if (_hash(raw) != record["after_hash"] or
                    after["state_revision"] != record["after_revision"] or
                    record["after_revision"] != record["before_revision"] + 1 or
                    event["transaction_id"] != record["transaction_id"] or
                    event["state_revision_before"] != record["before_revision"] or
                    event["state_revision_after"] != record["after_revision"] or
                    event["project_hash_before"] != record["before_hash"] or
                    event["project_hash_after"] != record["after_hash"]):
                raise ValueError("journal binding mismatch")
            return record
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, SchemaError) as exc:
            raise RecoveryConflict("malformed or inconsistent pending journal") from exc

    def clear(self):
        self.path.unlink()
        _sync_directory(self.path.parent)


class StateEngine:
    def __init__(self, project_dir: Path, repo: Path | None = None):
        self.project_dir = Path(project_dir)
        self.project_path = self.project_dir / "project.yaml"
        self.events_path = self.project_dir / "events.jsonl"
        self.lock = LocalWriterLock(self.project_dir)
        self.journal = PendingJournal(self.project_dir)
        self.repo = Path(repo) if repo is not None else None

    def read(self) -> ProjectSnapshot:
        raw = self.project_path.read_bytes()
        try:
            document = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SchemaError("project.yaml must contain UTF-8 JSON/YAML-subset syntax") from exc
        access = schema_access(document, CURRENT_PROJECT_SCHEMA, "schema_version")
        if access == "WRITABLE_VERSION":
            validate(document, "project")
        revision = document.get("state_revision")
        next_action = document.get("next_action")
        if access != "WRITABLE_VERSION":
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
                revision = None
            if not isinstance(next_action, str) or not next_action:
                next_action = None
        return ProjectSnapshot(document, revision, _hash(raw), access, next_action)

    def inspect_consistency(self) -> ProjectSnapshot:
        """Read a committed snapshot/history without recovery or any canonical write."""
        if self.journal.path.exists():
            raise RecoveryConflict("pending transaction requires State Engine recovery")
        snapshot = self.read()
        if snapshot.access != "WRITABLE_VERSION":
            return snapshot
        self._check_consistency(snapshot, self._events())
        return snapshot

    def inspect_history(self) -> tuple[dict, ...]:
        """Return committed events only; pending work must be recovered explicitly."""
        if self.journal.path.exists():
            raise RecoveryConflict("pending transaction requires State Engine recovery")
        snapshot = self.read()
        if snapshot.access != "WRITABLE_VERSION":
            raise SchemaError("history inspection requires current project schema")
        events = self._events()
        self._check_consistency(snapshot, events)
        return tuple(events)

    def _events(self, pending_event=None):
        try:
            raw = self.events_path.read_bytes()
            tail = b""
            if raw and not raw.endswith(b"\n"):
                complete, separator, tail = raw.rpartition(b"\n")
                expected = _json_bytes(pending_event) if pending_event is not None else b""
                if not tail or not expected.startswith(tail):
                    raise ValueError("unrelated partial event tail")
                raw = complete + separator
            events = [json.loads(line) for line in raw.splitlines()]
            seen = set()
            for event in events:
                validate(event, "event")
                if (event["state_revision_after"] != event["state_revision_before"] + 1 or
                        not isinstance(event.get("project_hash_before"), str) or
                        not isinstance(event.get("project_hash_after"), str)):
                    raise ValueError("invalid event revision/hash binding")
                txid = event["transaction_id"]
                if txid in seen:
                    raise ValueError("duplicate transaction ID")
                seen.add(txid)
            if events and events[0]["state_revision_before"] != 0:
                raise ValueError("history must start at revision zero")
            for older, newer in zip(events, events[1:]):
                if (older["state_revision_after"] != newer["state_revision_before"] or
                        older.get("project_hash_after") != newer.get("project_hash_before")):
                    raise ValueError("broken event chain")
            return (events, tail) if pending_event is not None else events
        except (OSError, ValueError, UnicodeError, SchemaError, KeyError, TypeError) as exc:
            raise RecoveryConflict("event history is malformed or duplicated") from exc

    def _check_consistency(self, snapshot, events):
        if events:
            last = events[-1]
            if (last["state_revision_after"] != snapshot.state_revision or
                    last.get("project_hash_after") != snapshot.project_hash):
                raise RecoveryConflict("project does not match last event")
        elif snapshot.state_revision != 0:
            raise RecoveryConflict("nonzero project revision has no event")

    def _append_event(self, event):
        raw = _json_bytes(event)
        fd = os.open(self.events_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:])
                if written <= 0:
                    raise OSError("event append made no progress")
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        _sync_directory(self.project_dir)

    def _recover_locked(self):
        record = self.journal.load()
        snapshot = self.read()
        if record is None:
            self._check_consistency(snapshot, self._events())
            return "NO_PENDING"
        if record["event"].get("event_type") == "IMPORT_ADOPTION":
            self._verify_import_artifacts(record["event"].get("transition_metadata"))
        events, tail = self._events(record["event"])
        matches = [event for event in events if event["transaction_id"] == record["transaction_id"]]
        if matches and matches[0] != record["event"]:
            raise RecoveryConflict("transaction ID belongs to another event")
        has_event = bool(matches)
        before = (snapshot.state_revision == record["before_revision"] and
                  snapshot.project_hash == record["before_hash"])
        after = (snapshot.state_revision == record["after_revision"] and
                 snapshot.project_hash == record["after_hash"])
        if not (before or after):
            raise RecoveryConflict("canonical state changed outside the pending transaction")
        if tail and (has_event or before):
            raise RecoveryConflict("partial event tail conflicts with canonical state")
        if has_event:
            if events[-1]["transaction_id"] != record["transaction_id"]:
                raise RecoveryConflict("pending event is not the history tail")
            if before:
                self._check_consistency(snapshot, events[:-1])
                _atomic_replace(self.project_path, record["after_text"].encode("utf-8"))
                result = "STATE_REPLAYED"
            else:
                self._check_consistency(snapshot, events)
                result = "ALREADY_COMMITTED"
        elif before:
            self._check_consistency(snapshot, events)
            result = "ABORTED_PREPARED"
        else:
            if events:
                if (events[-1]["state_revision_after"] != record["before_revision"] or
                        events[-1].get("project_hash_after") != record["before_hash"]):
                    raise RecoveryConflict("history diverged before pending event")
            elif record["before_revision"] != 0:
                raise RecoveryConflict("history absent before pending event")
            if tail:
                self._append_event_suffix(record["event"], tail)
            else:
                self._append_event(record["event"])
            result = "EVENT_REPLAYED"
        self._check_consistency(self.read(), self._events())
        self.journal.clear()
        return result

    def _append_event_suffix(self, event, prefix):
        raw = self.events_path.read_bytes()
        if not raw.endswith(prefix) or not _json_bytes(event).startswith(prefix):
            raise RecoveryConflict("pending event tail changed during recovery")
        suffix = _json_bytes(event)[len(prefix):]
        fd = os.open(self.events_path, os.O_WRONLY | os.O_APPEND | getattr(os, "O_BINARY", 0))
        try:
            while suffix:
                written = os.write(fd, suffix)
                if written <= 0:
                    raise OSError("event append made no progress")
                suffix = suffix[written:]
            os.fsync(fd)
        finally:
            os.close(fd)

    def recover_pending(self):
        with self.lock.acquire("RECOVERY"):
            return self._recover_locked()

    def begin_transaction(self, request: TransactionRequest, after_document: dict | None = None,
                          *, transition_metadata: dict | None = None):
        if request.event_type == "IMPORT_ADOPTION":
            raise ValueError("IMPORT_ADOPTION requires the dedicated adoption path")
        with self.lock.acquire(request.transaction_id):
            return self._commit_locked(request, after_document, transition_metadata, None)

    def preview_import_adoption(self, request: TransactionRequest, source_fixture: dict,
                                candidate: dict, report: dict) -> ImportAdoptionPlan:
        """Plan a reviewed external import without writing canonical or audit files."""
        before = self.inspect_consistency()
        return self._plan_import_adoption(request, source_fixture, candidate, report,
                                          before, self._events())

    def commit_import_adoption(self, request: TransactionRequest, source_fixture: dict,
                               candidate: dict, report: dict) -> ProjectSnapshot:
        """Adopt an external candidate through the State Engine journal."""
        if request.event_type != "IMPORT_ADOPTION":
            raise ValueError("adoption requires IMPORT_ADOPTION event_type")
        with self.lock.acquire(request.transaction_id):
            self._recover_locked()
            before = self.read()
            events = self._events()
            self._check_consistency(before, events)
            plan = self._plan_import_adoption(request, source_fixture, candidate, report,
                                              before, events)
            source_raw = self.project_path.read_bytes()
            if _hash(source_raw) != before.project_hash:
                raise StateConflict("import source changed before checkpoint")
            metadata = plan.transition_metadata
            self._write_import_artifact(metadata["checkpoint_path"], source_raw)
            self._write_import_artifact(metadata["report_evidence_path"], _json_bytes(report))
            self._verify_import_artifacts(metadata)
            return self._write_transition_locked(request, before, plan.document, metadata)

    def _plan_import_adoption(self, request, source_fixture, candidate, report, before, events):
        from .legacy_import import LEGACY_FORMAT, import_legacy_project
        if request.event_type != "IMPORT_ADOPTION":
            raise ValueError("adoption requires IMPORT_ADOPTION event_type")
        if before.access == "UNSUPPORTED_NEWER_SCHEMA":
            raise UnsupportedNewerSchema("unknown newer project schema")
        if before.access != "WRITABLE_VERSION":
            raise MigrationRequired("current schema required before import adoption")
        if any(event["transaction_id"] == request.transaction_id for event in events):
            raise DuplicateTransaction("transaction ID already committed")
        if not isinstance(candidate, dict):
            raise SchemaError("import candidate must be an object")
        validate(candidate, "project")
        if candidate["project_id"] != before.document["project_id"]:
            raise StateConflict("project identity cannot change in import adoption")
        if (not isinstance(report, dict) or report.get("source_format") != LEGACY_FORMAT
                or report.get("target_schema_version") != CURRENT_PROJECT_SCHEMA
                or not isinstance(report.get("source_fingerprint"), str)
                or re.fullmatch(r"[0-9a-f]{64}", report["source_fingerprint"]) is None):
            raise StateConflict("import report format, schema, or fingerprint is invalid")
        unresolved = report.get("unresolved_items")
        if not isinstance(unresolved, list) or any(
                not isinstance(item, dict) or not isinstance(item.get("blocking"), bool)
                for item in unresolved):
            raise StateConflict("import report unresolved items are invalid")
        if any(item["blocking"] for item in unresolved):
            raise StateConflict("blocking unresolved import items prevent adoption")
        try:
            reproduced_candidate, reproduced_report = import_legacy_project(source_fixture)
        except (TypeError, ValueError) as exc:
            raise StateConflict("source fixture cannot reproduce the I6b dry-run") from exc
        if (_json_bytes(candidate) != _json_bytes(reproduced_candidate) or
                _json_bytes(report) != _json_bytes(reproduced_report)):
            raise StateConflict("candidate and report do not match the source dry-run")
        candidate_digest = _hash(_json_bytes(candidate))
        report_digest = _hash(_json_bytes(report))
        identity = _hash(_json_bytes({
            "source_fingerprint": report["source_fingerprint"],
            "candidate_sha256": candidate_digest, "report_sha256": report_digest,
            "project_id": before.document["project_id"],
            "expected_state_revision": request.expected_state_revision,
            "expected_project_hash": request.expected_project_hash}))
        if any(event.get("event_type") == "IMPORT_ADOPTION" and
               isinstance(event.get("transition_metadata"), dict) and
               event["transition_metadata"].get("import_identity") == identity
               for event in events):
            raise DuplicateImport("import identity already committed")
        if (before.state_revision != request.expected_state_revision or
                before.project_hash != request.expected_project_hash):
            raise StateConflict("expected state revision/hash does not match current state")
        self._check_handoff(request, before)
        after = deepcopy(candidate)
        after["state_revision"] = before.state_revision + 1
        validate(after, "project")
        artifact_id = _hash(_json_bytes({"transaction_id": request.transaction_id,
                                         "import_identity": identity}))
        metadata = {
            "adoption_mode": "EXTERNAL_IMPORT", "adoption_version": "1.0",
            "import_identity": identity, "source_format": report["source_format"],
            "source_fingerprint": report["source_fingerprint"],
            "candidate_sha256": candidate_digest, "report_sha256": report_digest,
            "candidate_source_revision": candidate["state_revision"],
            "checkpoint_path": f".import-backups/{artifact_id}.project.yaml",
            "checkpoint_sha256": before.project_hash,
            "report_evidence_path": f".import-evidence/{artifact_id}.report.json",
            "report_evidence_sha256": report_digest,
        }
        return ImportAdoptionPlan(after, metadata)

    def _write_import_artifact(self, relative_path, raw):
        path = self._import_artifact_path(relative_path)
        path.parent.mkdir(exist_ok=True)
        path = self._import_artifact_path(relative_path)
        if path.exists():
            if path.read_bytes() != raw:
                raise RecoveryConflict("import artifact identity collision")
        else:
            _atomic_replace(path, raw)

    def _import_artifact_path(self, relative_path):
        path = self.project_dir / relative_path
        root = self.project_dir.resolve()
        if (path.parent.is_symlink() or path.is_symlink() or
                not path.resolve().is_relative_to(root)):
            raise RecoveryConflict("import artifact path escapes the project")
        return path

    def _verify_import_artifacts(self, metadata):
        if not isinstance(metadata, dict):
            raise RecoveryConflict("import evidence metadata missing")
        for path_key, digest_key, folder, suffix in (
                ("checkpoint_path", "checkpoint_sha256", ".import-backups", ".project.yaml"),
                ("report_evidence_path", "report_evidence_sha256", ".import-evidence", ".report.json")):
            relative = metadata.get(path_key)
            if (not isinstance(relative, str) or
                    re.fullmatch(rf"{re.escape(folder)}/[0-9a-f]{{64}}{re.escape(suffix)}", relative) is None):
                raise RecoveryConflict("import checkpoint or evidence path is invalid")
            try:
                actual = _hash(self._import_artifact_path(relative).read_bytes())
            except OSError as exc:
                raise RecoveryConflict("import checkpoint or evidence is missing") from exc
            if actual != metadata.get(digest_key):
                raise RecoveryConflict("import checkpoint or evidence does not match event")

    def migrate(self, request: TransactionRequest, steps: tuple):
        """Commit an explicitly supplied migration chain as one audited event."""
        if request.event_type != "MIGRATION":
            raise ValueError("migration requires MIGRATION event_type")
        with self.lock.acquire(request.transaction_id):
            return self._commit_locked(request, None, None, steps)

    def _commit_locked(self, request, after_document, transition_metadata, migration_steps):
            self._recover_locked()
            before = self.read()
            if before.access == "UNSUPPORTED_NEWER_SCHEMA":
                raise UnsupportedNewerSchema("unknown newer project schema")
            events = self._events()
            if any(event["transaction_id"] == request.transaction_id for event in events):
                raise DuplicateTransaction("transaction ID already committed")
            if (before.state_revision != request.expected_state_revision or
                    before.project_hash != request.expected_project_hash):
                raise StateConflict("expected state revision/hash does not match current state")
            self._check_handoff(request, before)
            if migration_steps is None:
                if before.access == "MIGRATION_REQUIRED":
                    raise MigrationRequired("explicit migration required before ordinary writes")
                if after_document is None:
                    raise PhaseI1Required("provide the complete next canonical document")
                after = dict(after_document)
            else:
                from .migration import preview_migration
                after, transition_metadata = preview_migration(before.document, migration_steps)
                source_raw = self.project_path.read_bytes()
                if _hash(source_raw) != before.project_hash:
                    raise StateConflict("migration source changed before backup")
                backup_dir = self.project_dir / ".migration-backups"
                backup_dir.mkdir(exist_ok=True)
                backup_name = _hash(request.transaction_id.encode("utf-8")) + ".project.yaml"
                backup = backup_dir / backup_name
                if backup.exists():
                    if backup.read_bytes() != source_raw:
                        raise RecoveryConflict("migration backup identity collision")
                else:
                    _atomic_replace(backup, source_raw)
                transition_metadata = {**transition_metadata,
                                       "backup_path": f".migration-backups/{backup_name}",
                                       "backup_sha256": before.project_hash}
            if after.get("state_revision") != before.state_revision + 1:
                raise StateConflict("next state revision must increase by exactly one")
            if after.get("project_id") != before.document.get("project_id"):
                raise StateConflict("project identity cannot change in a state transition")
            validate(after, "project")
            if migration_steps is None:
                _check_dependency_transition(before.document, after, transition_metadata)
            return self._write_transition_locked(request, before, after, transition_metadata)

    def _write_transition_locked(self, request, before, after, transition_metadata):
            after_hash = _hash(_json_bytes(after))
            event = {"event_schema_version": CURRENT_EVENT_SCHEMA,
                     "transaction_id": request.transaction_id,
                     "state_revision_before": before.state_revision,
                     "state_revision_after": after["state_revision"],
                     "project_hash_before": before.project_hash,
                     "project_hash_after": after_hash,
                     "timestamp": datetime.now(timezone.utc).isoformat(),
                     "actor": request.actor, "event_type": request.event_type}
            if transition_metadata is not None:
                event["transition_metadata"] = transition_metadata
            validate(event, "event")
            self.journal.prepare(request, before, after, event)
            _atomic_replace(self.project_path, _json_bytes(after))
            self._append_event(event)
            self._check_consistency(self.read(), self._events())
            self.journal.clear()
            return self.read()

    def _check_handoff(self, request, snapshot):
        from .handoff import verify_handoff_base
        if self.repo is not None:
            if request.handoff_base is None:
                raise RemoteStateConflict("Git-backed writes require explicit handoff evidence")
            verify_handoff_base(self.repo, self.project_dir, request.handoff_base, snapshot)
        elif request.handoff_base is not None:
            raise RemoteStateConflict("handoff evidence requires a Git repository")
