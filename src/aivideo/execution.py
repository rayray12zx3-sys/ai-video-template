"""Local durable claim/submission protocol. No provider calls are made here."""

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Protocol

from .guards import ActionRequest, guard_action
from .qc import check_file_metadata, probe_media
from .state_engine import TransactionRequest
from .tickets import (AccountEntitlementSnapshot, GenerationTicket, ProviderRuntimeSnapshot,
                      SHA256, SURFACES, TechnicalCapabilitySnapshot, UNKNOWN, _digest, ticket_staleness)


class ExecutionConflict(RuntimeError):
    pass


class ApprovalVerifier(Protocol):
    def __call__(self, kind: str, subject: str, request: ActionRequest, snapshot) -> bool: ...


class PreflightVerifier(Protocol):
    def __call__(self, request: ActionRequest, snapshot, now: datetime) -> dict: ...


class ReconciliationVerifier(Protocol):
    def __call__(self, claim: dict, evidence: dict) -> str: ...


class WorkspaceReceiptVerifier(Protocol):
    def __call__(self, receipt: "ProviderReceipt", ticket: GenerationTicket) -> bool: ...


@dataclass(frozen=True)
class ExecutionClaim:
    id: int
    ticket_id: str
    project_id: str
    shot_id: str
    candidate_id: str
    provider: str
    workspace_id: str
    execution_surface: str
    actor: str
    state_revision: int
    project_hash: str
    claimed_at: str
    submission_state: str
    action: str
    backend: str


@dataclass(frozen=True)
class ProviderUpload:
    asset_id: str
    source_sha256: str
    upload_sha256: str
    provider_upload_id: str
    derivative_id: str | None = None

    def __post_init__(self):
        if (not self.asset_id or not self.provider_upload_id or self.provider_upload_id == UNKNOWN or
                not SHA256.fullmatch(self.source_sha256) or not SHA256.fullmatch(self.upload_sha256)):
            raise ValueError("provider upload identity/hash is invalid")


@dataclass(frozen=True)
class ProviderReceipt:
    ticket_id: str
    candidate_id: str
    claim_id: int
    provider: str
    workspace_id: str
    execution_surface: str
    submission_state: str
    runtime_snapshot_id: str
    provider_task_id: str | None
    quoted_cost: float | None
    charged_cost: float | None
    output_ids: tuple[str, ...]
    submitted_at: str | None
    completed_at: str | None
    provenance: str
    effective_prompt: str | None = None
    prompt_transform_version: str | None = None
    uploaded_inputs: tuple[ProviderUpload, ...] = ()
    observed_workspace_id: str | None = None
    workspace_evidence_ref: str | None = None

    def __post_init__(self):
        if self.execution_surface not in SURFACES or not all((self.ticket_id, self.candidate_id,
                                                              self.provider, self.workspace_id, self.provenance)):
            raise ValueError("receipt binding incomplete")
        if self.submission_state not in {"SUBMITTED", "COMPLETED", "FAILED", "UNKNOWN_SUBMISSION"}:
            raise ValueError("invalid receipt submission state")
        if not isinstance(self.output_ids, tuple) or not isinstance(self.uploaded_inputs, tuple):
            raise ValueError("receipt collections must be immutable tuples")


def manual_web_import(*, provider, workspace_id, shot_id, candidate_id, actor,
                      task_id=None, asset_id=None, model=None, settings=None, prompt=None,
                      executed_at=None):
    """Supporting evidence only; unknown values are explicit and never inferred."""
    if not all((provider, workspace_id, shot_id, candidate_id, actor)):
        raise ValueError("manual execution identity required")
    return {"kind": "EXTERNAL_EXECUTION", "execution_surface": "WEB_MANUAL",
            "provider": provider, "workspace_id": workspace_id, "shot_id": shot_id,
            "candidate_id": candidate_id, "actor": actor,
            "provider_task_id": task_id if task_id is not None else UNKNOWN,
            "provider_asset_id": asset_id if asset_id is not None else UNKNOWN,
            "model": model if model is not None else UNKNOWN,
            "settings": settings if settings is not None else UNKNOWN,
            "prompt": prompt if prompt is not None else UNKNOWN,
            "executed_at": executed_at if executed_at is not None else UNKNOWN}


class ExecutionLedger:
    """SQLite supporting record under a project; unique candidate intent across surfaces."""

    def __init__(self, project_dir: Path):
        self.path = Path(project_dir) / "execution-ledger.sqlite3"

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("CREATE TABLE IF NOT EXISTS claims (id INTEGER PRIMARY KEY, project_id TEXT NOT NULL, "
                       "shot_id TEXT NOT NULL, candidate_id TEXT NOT NULL, ticket_id TEXT NOT NULL, "
                       "provider TEXT NOT NULL, workspace_id TEXT NOT NULL, backend TEXT NOT NULL, "
                       "surface TEXT NOT NULL, "
                       "actor TEXT NOT NULL, action TEXT NOT NULL, revision INTEGER NOT NULL, project_hash TEXT NOT NULL, "
                       "claimed_at TEXT NOT NULL, state TEXT NOT NULL, request_fingerprint TEXT, "
                       "local_key TEXT, provider_idempotency_key TEXT, provider_trace_id TEXT, "
                       "provider_task_id TEXT, evidence TEXT)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_candidate_intent ON claims "
                       "(project_id, shot_id, candidate_id) WHERE state != 'NO_SUBMISSION'")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_provider_key ON claims "
                       "(provider, workspace_id, backend, provider_idempotency_key) "
                       "WHERE provider_idempotency_key IS NOT NULL")
            db.execute("CREATE TABLE IF NOT EXISTS receipts (claim_id INTEGER PRIMARY KEY, payload TEXT NOT NULL, "
                       "digest TEXT NOT NULL, FOREIGN KEY(claim_id) REFERENCES claims(id))")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def claims(self):
        with self._connect() as db:
            rows = db.execute("SELECT id, ticket_id, project_id, shot_id, candidate_id, provider, "
                              "workspace_id, surface, actor, revision, project_hash, claimed_at, state, action, backend "
                              "FROM claims ORDER BY id").fetchall()
        return tuple(ExecutionClaim(*row) for row in rows)

    def import_manual_web(self, engine, record: dict):
        """Register observed external work before any later automated attempt."""
        required = ("provider", "workspace_id", "shot_id", "candidate_id", "actor")
        if (record.get("kind") != "EXTERNAL_EXECUTION" or record.get("execution_surface") != "WEB_MANUAL"
                or any(not record.get(key) for key in required)):
            raise ExecutionConflict("invalid manual Web execution record")
        if self.path.parent.resolve() != engine.project_dir.resolve():
            raise ExecutionConflict("execution ledger must belong to the canonical project")
        with engine.lock.acquire("external-execution-import"):
            snapshot = engine.inspect_consistency()
            if record["shot_id"] not in {s.get("id") for s in snapshot.document.get("shots", [])}:
                raise ExecutionConflict("manual execution shot is absent")
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    db.execute("INSERT INTO claims (project_id, shot_id, candidate_id, ticket_id, provider, "
                               "workspace_id, backend, surface, actor, action, revision, project_hash, claimed_at, state, "
                               "provider_task_id, evidence) VALUES (?, ?, ?, ?, ?, ?, 'UNKNOWN', 'WEB_MANUAL', ?, 'EXTERNAL_EXECUTION', ?, ?, ?, ?, ?, ?)",
                               (snapshot.document["project_id"], record["shot_id"], record["candidate_id"],
                                UNKNOWN, record["provider"], record["workspace_id"], record["actor"],
                                snapshot.state_revision, snapshot.project_hash,
                                record["executed_at"] if record.get("executed_at") != UNKNOWN else
                                datetime.now(timezone.utc).isoformat(),
                                "SUBMITTED" if record.get("provider_task_id") not in {None, UNKNOWN} else
                                "UNKNOWN_SUBMISSION", record.get("provider_task_id"),
                                json.dumps(record, sort_keys=True, allow_nan=False)))
                    claim_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                except sqlite3.IntegrityError as exc:
                    raise ExecutionConflict("candidate intent already claimed; reconcile before import") from exc
        return next(item for item in self.claims() if item.id == claim_id)

    def prepare(self, engine, ticket: GenerationTicket, request: ActionRequest, actor: str,
                *, preflight_verifier: PreflightVerifier, approval_verifier: ApprovalVerifier,
                now=None):
        if request.action not in {"PAID_GENERATION", "BATCH_GENERATION"} or not actor or not ticket.verify():
            raise ExecutionConflict("invalid paid execution request")
        if self.path.parent.resolve() != engine.project_dir.resolve():
            raise ExecutionConflict("execution ledger must belong to the canonical project")
        data = ticket.payload()
        expected = (ticket.id, data["shot_id"], data["candidate_id"], data["provider"], data["workspace_id"])
        actual = (request.ticket_id, request.shot_id, request.candidate_id, request.provider, request.workspace_id)
        if actual != expected:
            raise ExecutionConflict("action and ticket differ")
        if data["quote"] is None or request.quoted_cost != data["quote"]:
            raise ExecutionConflict("action cost must match the sealed ticket quote")
        now = now or datetime.now(timezone.utc)
        # Serialize the guard, canonical re-read, and local claim creation with State Engine writes.
        with engine.lock.acquire("execution-claim"):
            if ticket_staleness(ticket, engine):
                raise ExecutionConflict("ticket dependencies are stale")
            decision = guard_action(engine, request, now=now, preflight_verifier=preflight_verifier,
                                    approval_verifier=approval_verifier)
            if decision["decision"] != "ALLOW":
                raise ExecutionConflict("Action Guard denied paid execution")
            with self._connect() as db:
                try:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("INSERT INTO claims (project_id, shot_id, candidate_id, ticket_id, provider, "
                               "workspace_id, backend, surface, actor, action, revision, project_hash, claimed_at, state) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PREPARED')",
                               (data["project_id"], data["shot_id"], data["candidate_id"], ticket.id,
                                data["provider"], data["workspace_id"], data["backend"],
                                data["execution_surface"], actor, request.action,
                                request.expected_state_revision, request.expected_project_hash, now.isoformat()))
                    claim_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                except sqlite3.IntegrityError as exc:
                    raise ExecutionConflict("candidate intent already claimed on an execution surface") from exc
        return next(item for item in self.claims() if item.id == claim_id)

    def transition(self, claim_id: int, state: str, *, request_fingerprint=None, local_key=None,
                   provider_idempotency_key=None, provider_trace_id=None,
                   provider_task_id=None, evidence=None, verifier: ReconciliationVerifier | None = None,
                   engine=None, ticket: GenerationTicket | None = None, request: ActionRequest | None = None,
                   technical: TechnicalCapabilitySnapshot | None = None,
                   entitlement: AccountEntitlementSnapshot | None = None,
                   runtime: ProviderRuntimeSnapshot | None = None,
                   preflight_verifier: PreflightVerifier | None = None,
                   approval_verifier: ApprovalVerifier | None = None, now=None):
        """Caller persists SUBMITTING before any future provider command; ambiguous outcomes stop."""
        if state == "SUBMITTING":
            if provider_idempotency_key == "" or provider_trace_id == "":
                raise ExecutionConflict("provider key and trace ID cannot be empty")
            if None in (engine, ticket, request, technical, entitlement, runtime,
                        preflight_verifier, approval_verifier):
                raise ExecutionConflict("submission needs trusted guard and current runtime evidence")
            now = now or datetime.now(timezone.utc)
            if self.path.parent.resolve() != engine.project_dir.resolve():
                raise ExecutionConflict("execution ledger must belong to the canonical project")
            with engine.lock.acquire("submission-recheck"):
                data = ticket.payload() if ticket.verify() else {}
                claim = next((item for item in self.claims() if item.id == claim_id), None)
                if (ticket_staleness(ticket, engine) or
                        request.action not in {"PAID_GENERATION", "BATCH_GENERATION"} or
                        (request.ticket_id, request.shot_id, request.candidate_id,
                         request.provider, request.workspace_id) !=
                        (ticket.id, data.get("shot_id"), data.get("candidate_id"),
                         data.get("provider"), data.get("workspace_id")) or
                        claim is None or claim.ticket_id != ticket.id or
                        claim.action != request.action or
                        claim.project_id != data.get("project_id") or
                        claim.shot_id != data.get("shot_id") or
                        claim.candidate_id != data.get("candidate_id") or
                        claim.provider != data.get("provider") or
                        claim.backend != data.get("backend") or
                        claim.workspace_id != data.get("workspace_id") or
                        claim.execution_surface != data.get("execution_surface") or
                        claim.state_revision != request.expected_state_revision or
                        claim.project_hash != request.expected_project_hash or
                        request.expected_state_revision != engine.inspect_consistency().state_revision or
                        request.expected_project_hash != engine.inspect_consistency().project_hash or
                        request.quoted_cost != data.get("quote") or
                        runtime.id != data.get("runtime_snapshot_id") or
                        _digest(asdict(runtime)) != data.get("runtime_snapshot_hash") or
                        runtime.provider != data.get("provider") or
                        runtime.backend != technical.backend or
                        runtime.execution_surface != data.get("execution_surface") or
                        runtime.workspace_id != data.get("workspace_id") or
                        technical.id != data.get("technical_snapshot_id") or
                        _digest(asdict(technical)) != data.get("technical_snapshot_hash") or
                        technical.provider != data.get("provider") or
                        data.get("operation") not in technical.operations or not technical.fresh(now) or
                        entitlement.id != data.get("entitlement_snapshot_id") or
                        _digest(asdict(entitlement)) != data.get("entitlement_snapshot_hash") or
                        entitlement.provider != data.get("provider") or
                        entitlement.workspace_id != data.get("workspace_id") or not entitlement.fresh(now)):
                    raise ExecutionConflict("submission evidence or ticket is stale")
                decision = guard_action(engine, request, now=now, preflight_verifier=preflight_verifier,
                                        approval_verifier=approval_verifier)
                if decision["decision"] != "ALLOW":
                    raise ExecutionConflict("Action Guard denied submission")
                operation = data.get("operation")
                if ((technical.supports_idempotency(operation, runtime.backend, now) !=
                     bool(provider_idempotency_key)) or
                        ((operation in technical.trace_operations) != bool(provider_trace_id))):
                    raise ExecutionConflict("provider idempotency/trace evidence is incomplete or unproven")
                return self._transition(claim_id, state, request_fingerprint=request_fingerprint,
                                        local_key=local_key, provider_idempotency_key=provider_idempotency_key,
                                        provider_trace_id=provider_trace_id, provider_task_id=provider_task_id,
                                        evidence=evidence, verifier=verifier)
        return self._transition(claim_id, state, request_fingerprint=request_fingerprint,
                                local_key=local_key, provider_idempotency_key=provider_idempotency_key,
                                provider_trace_id=provider_trace_id, provider_task_id=provider_task_id,
                                evidence=evidence, verifier=verifier)

    def _transition(self, claim_id, state, *, request_fingerprint=None, local_key=None,
                    provider_idempotency_key=None, provider_trace_id=None,
                    provider_task_id=None, evidence=None, verifier=None):
        allowed = {"PREPARED": {"SUBMITTING", "NO_SUBMISSION"},
                   "SUBMITTING": {"UNKNOWN_SUBMISSION", "SUBMITTED", "FAILED"},
                   "UNKNOWN_SUBMISSION": {"NO_SUBMISSION", "SUBMITTED", "FAILED"},
                   "SUBMITTED": {"COMPLETED", "FAILED"}}
        if state != "SUBMITTING" and any((request_fingerprint, local_key, provider_idempotency_key,
                                           provider_trace_id)):
            raise ExecutionConflict("submitted request identity cannot be changed")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state, ticket_id, provider, workspace_id, request_fingerprint, local_key "
                             "FROM claims WHERE id=?", (claim_id,)).fetchone()
            if row is None or state not in allowed.get(row[0], ()):
                raise ExecutionConflict("invalid or duplicate submission transition")
            if state == "SUBMITTING" and (not request_fingerprint or not local_key):
                raise ExecutionConflict("submission fingerprint and local key required")
            if row[0] == "UNKNOWN_SUBMISSION" or state == "NO_SUBMISSION" and row[0] != "PREPARED":
                claim = {"id": claim_id, "state": row[0], "ticket_id": row[1],
                         "provider": row[2], "workspace_id": row[3]}
                details = evidence if isinstance(evidence, dict) else {}
                observed_workspace = details.get("observed_workspace_id")
                evidence_ref = details.get("workspace_evidence_ref")
                if (observed_workspace != row[3] or not isinstance(evidence_ref, str) or
                        not evidence_ref.strip() or verifier is None or
                        verifier(claim, details) != state):
                    raise ExecutionConflict("ambiguous outcome requires trusted reconciliation")
            try:
                db.execute("UPDATE claims SET state=?, request_fingerprint=COALESCE(?, request_fingerprint), "
                           "local_key=COALESCE(?, local_key), "
                           "provider_idempotency_key=COALESCE(?, provider_idempotency_key), "
                           "provider_trace_id=COALESCE(?, provider_trace_id), "
                           "provider_task_id=COALESCE(?, provider_task_id), "
                           "evidence=COALESCE(?, evidence) WHERE id=?",
                           (state, request_fingerprint, local_key, provider_idempotency_key,
                            provider_trace_id, provider_task_id,
                            json.dumps(evidence, sort_keys=True) if evidence is not None else None, claim_id))
            except sqlite3.IntegrityError as exc:
                raise ExecutionConflict("provider idempotency key already binds another claim") from exc
        return state

    def record_receipt(self, receipt: ProviderReceipt, ticket: GenerationTicket,
                       *, workspace_verifier: WorkspaceReceiptVerifier | None = None):
        if not ticket.verify() or receipt.ticket_id != ticket.id:
            raise ExecutionConflict("receipt ticket mismatch")
        intent = ticket.payload()
        if (receipt.observed_workspace_id != intent["workspace_id"] or
                not isinstance(receipt.workspace_evidence_ref, str) or
                not receipt.workspace_evidence_ref.strip() or workspace_verifier is None):
            raise ExecutionConflict("trusted receipt workspace identity is missing")
        try:
            verified = workspace_verifier(receipt, ticket) is True
        except Exception:
            verified = False
        if not verified:
            raise ExecutionConflict("receipt workspace identity is unverified")
        if (receipt.candidate_id != intent["candidate_id"] or receipt.provider != intent["provider"] or
                receipt.workspace_id != intent["workspace_id"] or
                receipt.execution_surface != intent["execution_surface"] or
                receipt.runtime_snapshot_id != intent["runtime_snapshot_id"] or
                receipt.quoted_cost != intent["quote"]):
            raise ExecutionConflict("receipt intent mismatch")
        if intent["prompt"]["transform_policy"] == "EXACT" and receipt.effective_prompt is not None:
            if receipt.effective_prompt != intent["prompt"]["compiled"]:
                raise ExecutionConflict("EXACT prompt changed at execution")
        actual_uploads = {item.asset_id: item for item in receipt.uploaded_inputs}
        if len(actual_uploads) != len(receipt.uploaded_inputs):
            raise ExecutionConflict("duplicate actual upload asset")
        derivatives = {item["source_asset_id"]: item for item in intent["derivative_inputs"]}
        for item in intent["inputs"]:
            upload = actual_uploads.get(item["asset_id"])
            if upload is None or not upload.provider_upload_id or upload.source_sha256 != item["sha256"]:
                raise ExecutionConflict("actual provider upload lineage is missing")
            planned = derivatives.get(item["asset_id"])
            if planned is not None:
                if (upload.derivative_id != planned["derivative_id"] or
                        upload.upload_sha256 != planned["derivative_sha256"]):
                    raise ExecutionConflict("actual provider-ready derivative differs from ticket")
            elif upload.derivative_id is not None or upload.upload_sha256 != item["sha256"]:
                raise ExecutionConflict("unexpected provider input transformation")
        if set(actual_uploads) != {item["asset_id"] for item in intent["inputs"]}:
            raise ExecutionConflict("receipt has extra provider uploads")
        payload = json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT ticket_id, candidate_id, provider, workspace_id, surface, state, "
                             "provider_task_id, project_id, shot_id "
                             "FROM claims WHERE id=?", (receipt.claim_id,)).fetchone()
            if (row is None or row[:6] != (receipt.ticket_id, receipt.candidate_id, receipt.provider,
                                           receipt.workspace_id, receipt.execution_surface,
                                           receipt.submission_state) or
                    (row[6] and row[6] != receipt.provider_task_id) or
                    row[7] != intent["project_id"] or row[8] != intent["shot_id"]):
                raise ExecutionConflict("receipt does not match current claim")
            try:
                db.execute("INSERT INTO receipts (claim_id, payload, digest) VALUES (?, ?, ?)",
                           (receipt.claim_id, payload, digest))
            except sqlite3.IntegrityError as exc:
                raise ExecutionConflict("receipt already exists; corrections require new evidence") from exc
        return digest

    def receipts(self):
        with self._connect() as db:
            rows = db.execute("SELECT payload, digest FROM receipts ORDER BY claim_id").fetchall()
        result = []
        for payload, digest in rows:
            if hashlib.sha256(payload.encode()).hexdigest() != digest:
                raise ExecutionConflict("receipt integrity mismatch")
            value = json.loads(payload)
            if (value.get("observed_workspace_id") != value.get("workspace_id") or
                    not isinstance(value.get("workspace_evidence_ref"), str) or
                    not value["workspace_evidence_ref"].strip()):
                raise ExecutionConflict("stored receipt workspace identity is unverified")
            value["output_ids"] = tuple(value["output_ids"])
            value["uploaded_inputs"] = tuple(ProviderUpload(**item) for item in value["uploaded_inputs"])
            result.append(ProviderReceipt(**value))
        return tuple(result)

    def submission_record(self, claim_id: int):
        """Read the durable identities a future adapter must reuse for reconciliation."""
        with self._connect() as db:
            row = db.execute("SELECT state, request_fingerprint, local_key, provider_idempotency_key, "
                             "provider_trace_id, provider_task_id FROM claims WHERE id=?", (claim_id,)).fetchone()
        if row is None:
            raise ExecutionConflict("claim is absent")
        return dict(zip(("state", "request_fingerprint", "local_key", "provider_idempotency_key",
                         "provider_trace_id", "provider_task_id"), row))


def adopt_generated_output(
    engine,
    ledger: ExecutionLedger,
    ticket: GenerationTicket,
    receipt: ProviderReceipt,
    file_path,
    sha256: str,
    probed_metadata: dict | None = None,
    *,
    actor: str = "operator",
    transaction_id: str | None = None,
    workspace_verifier: WorkspaceReceiptVerifier | None = None,
    ffprobe_path: str = "ffprobe",
    timeout: int = 10,
):
    """Adopt a verified generated media file into the canonical project using State Engine."""
    if ledger.path.parent.resolve() != engine.project_dir.resolve():
        raise ExecutionConflict("execution ledger must belong to the canonical project")

    if not ticket.verify():
        raise ExecutionConflict("invalid ticket integrity")

    if ticket_staleness(ticket, engine):
        raise ExecutionConflict("ticket dependencies are stale")

    intent = ticket.payload()

    if receipt.ticket_id != ticket.id or receipt.candidate_id != intent["candidate_id"]:
        raise ExecutionConflict("receipt ticket or candidate mismatch")

    if (receipt.provider != intent["provider"] or
            receipt.workspace_id != intent["workspace_id"] or
            receipt.execution_surface != intent["execution_surface"] or
            receipt.runtime_snapshot_id != intent["runtime_snapshot_id"]):
        raise ExecutionConflict("receipt environment or runtime mismatch")

    if (receipt.observed_workspace_id != intent["workspace_id"] or
            not isinstance(receipt.workspace_evidence_ref, str) or
            not receipt.workspace_evidence_ref.strip()):
        raise ExecutionConflict("missing trusted receipt workspace identity")

    if receipt.submission_state != "COMPLETED":
        raise ExecutionConflict("generated output requires a completed receipt")

    persisted_receipt = next(
        (item for item in ledger.receipts() if item.claim_id == receipt.claim_id),
        None,
    )
    if persisted_receipt is None or persisted_receipt != receipt:
        raise ExecutionConflict("generated output requires the exact persisted trusted receipt")

    claim = next((c for c in ledger.claims() if c.id == receipt.claim_id), None)
    if (claim is None or claim.submission_state != "COMPLETED" or
            claim.ticket_id != ticket.id or
            claim.project_id != intent["project_id"] or
            claim.shot_id != intent["shot_id"] or
            claim.candidate_id != intent["candidate_id"] or
            claim.provider != intent["provider"] or
            claim.workspace_id != intent["workspace_id"] or
            claim.execution_surface != intent["execution_surface"]):
        raise ExecutionConflict("receipt claim identity mismatch")

    snapshot = engine.inspect_consistency()
    if snapshot.access != "WRITABLE_VERSION":
        raise ExecutionConflict(f"canonical project state is not writable ({snapshot.access})")

    doc = snapshot.document
    if doc.get("project_id") != intent["project_id"]:
        raise ExecutionConflict("ticket project ID does not match current canonical state")

    shots = {s["id"]: s for s in doc.get("shots", []) if isinstance(s, dict) and isinstance(s.get("id"), str)}
    if intent["shot_id"] not in shots:
        raise ExecutionConflict(f"shot {intent['shot_id']} is absent from canonical state")

    path = Path(file_path)
    if not path.is_file():
        raise ExecutionConflict("downloaded local file does not exist")

    try:
        rel_path = path.resolve().relative_to(engine.project_dir.resolve()).as_posix()
    except ValueError:
        try:
            rel_path = path.relative_to(engine.project_dir).as_posix()
        except ValueError:
            raise ExecutionConflict("local media file must be locateable within project directory")

    computed_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if computed_sha256.lower() != sha256.lower():
        raise ExecutionConflict("local file SHA-256 mismatch")

    if probed_metadata is None:
        probed_metadata = probe_media(path, timeout=timeout, ffprobe_path=ffprobe_path)

    if not isinstance(probed_metadata, dict) or not probed_metadata.get("exists") or not probed_metadata.get("readable"):
        raise ExecutionConflict("media file is unreadable or malformed")

    codec = probed_metadata.get("codec")
    resolution = probed_metadata.get("resolution")
    duration = probed_metadata.get("duration")
    if not isinstance(codec, str) or not codec.strip():
        raise ExecutionConflict("media file is missing a video codec")
    if not isinstance(resolution, str) or "x" not in resolution.lower():
        raise ExecutionConflict("media file is missing a valid video resolution")
    try:
        width_text, height_text = resolution.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (TypeError, ValueError):
        raise ExecutionConflict("media file is missing a valid video resolution")
    if width <= 0 or height <= 0:
        raise ExecutionConflict("media file is missing a valid video resolution")
    if (not isinstance(duration, (int, float)) or isinstance(duration, bool) or
            duration <= 0):
        raise ExecutionConflict("media file is missing a positive duration")

    q0_results = check_file_metadata(probed_metadata, origin="GENERATION")
    if q0_results.get("exists") and q0_results["exists"].status == "FAIL":
        raise ExecutionConflict("Q0 media exists check failed")
    if q0_results.get("readable") and q0_results["readable"].status == "FAIL":
        raise ExecutionConflict("Q0 media readability check failed")

    candidate_id = intent["candidate_id"]
    shot_id = intent["shot_id"]
    asset_id = f"asset-{candidate_id}"

    existing_assets = [a for a in doc.get("assets", []) if isinstance(a, dict) and a.get("id") == asset_id]
    if existing_assets:
        existing = existing_assets[0]
        if (existing.get("sha256") == computed_sha256 and
                existing.get("provider_task_id") == (receipt.provider_task_id or UNKNOWN)):
            return snapshot
        raise ExecutionConflict(f"candidate asset {asset_id} already exists with different hash/task")

    new_asset = {
        "id": asset_id,
        "origin": "PROVIDER_OUTPUT",
        "lifecycle": "RECEIVED",
        "criticality": "OPTIONAL",
        "sha256": computed_sha256,
        "provenance": f"Provider {intent['provider']} execution (task {receipt.provider_task_id or UNKNOWN}, ticket {ticket.id}, claim {receipt.claim_id})",
        "locators": [{"type": "LOCAL", "path": rel_path, "availability": "AVAILABLE"}],
        "media_metadata": probed_metadata,
        "provider_task_id": receipt.provider_task_id or UNKNOWN,
        "lineage": {
            "ticket_id": ticket.id,
            "claim_id": receipt.claim_id,
            "candidate_id": candidate_id,
            "shot_id": shot_id,
            "provider": intent["provider"],
            "workspace_id": intent["workspace_id"],
            "execution_surface": intent["execution_surface"],
            "runtime_snapshot_id": intent["runtime_snapshot_id"],
        },
    }

    target_next_action = f"Perform Q1 visual and technical QC on adopted candidate {candidate_id}"

    after_document = deepcopy(doc)
    after_document["state_revision"] = snapshot.state_revision + 1
    after_document["next_action"] = target_next_action
    after_document["assets"].append(new_asset)

    tx_id = transaction_id or f"adopt-{candidate_id}-{snapshot.state_revision + 1}"
    tx_request = TransactionRequest(
        expected_state_revision=snapshot.state_revision,
        expected_project_hash=snapshot.project_hash,
        transaction_id=tx_id,
        actor=actor,
        event_type="GENERATED_OUTPUT_ADOPTION",
    )

    transition_metadata = {
        "adoption_type": "GENERATED_OUTPUT",
        "ticket_id": ticket.id,
        "claim_id": receipt.claim_id,
        "candidate_id": candidate_id,
        "shot_id": shot_id,
        "provider": intent["provider"],
        "workspace_id": intent["workspace_id"],
        "sha256": computed_sha256,
        "local_path": rel_path,
        "q0_summary": {k: v.status for k, v in q0_results.items()},
    }

    return engine.begin_transaction(tx_request, after_document, transition_metadata=transition_metadata)
