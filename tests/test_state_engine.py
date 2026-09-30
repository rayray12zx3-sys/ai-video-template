import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aivideo.handoff import capture_handoff_base, verify_handoff_base
from aivideo.migration import MigrationStep, preview_migration
from aivideo.schema import MigrationRequired, SchemaError, UnsupportedNewerSchema
from aivideo.state_engine import (DuplicateTransaction, RecoveryConflict, RemoteStateConflict,
                                  StateConflict, StateEngine, TransactionRequest, WriterLockConflict,
                                  _atomic_replace, _json_bytes)

SAMPLE = ROOT / "examples" / "minimal-project"


class EngineTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        (self.path / "project.yaml").write_bytes((SAMPLE / "project.yaml").read_bytes())
        (self.path / "events.jsonl").write_bytes(b"")
        self.engine = StateEngine(self.path)

    def transition(self, txid="tx-1", next_action="Review shot intent"):
        before = self.engine.read()
        after = {**before.document, "state_revision": before.state_revision + 1,
                 "next_action": next_action}
        request = TransactionRequest(before.state_revision, before.project_hash, txid, "tester", "EDIT")
        return request, after

    def events(self):
        return [json.loads(line) for line in self.engine.events_path.read_text(encoding="utf-8").splitlines()]

    def prepared(self):
        request, after = self.transition()
        before = self.engine.read()
        after_hash = hashlib.sha256(_json_bytes(after)).hexdigest()
        event = {"event_schema_version": "1.0", "transaction_id": request.transaction_id,
                 "state_revision_before": 0, "state_revision_after": 1,
                 "project_hash_before": before.project_hash, "project_hash_after": after_hash,
                 "timestamp": "2026-09-23T00:00:00Z", "actor": "tester", "event_type": "EDIT"}
        self.engine.journal.prepare(request, before, after, event)
        return request, after, event

    def test_success_hash_revision_event_and_next_action(self):
        request, after = self.transition()
        snapshot = self.engine.begin_transaction(request, after)
        self.assertEqual(snapshot.state_revision, 1)
        self.assertEqual(snapshot.next_action, "Review shot intent")
        self.assertEqual(snapshot.project_hash, hashlib.sha256(self.engine.project_path.read_bytes()).hexdigest())
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.events()[0]["transaction_id"], request.transaction_id)
        self.assertEqual(self.events()[0]["project_hash_after"], snapshot.project_hash)
        self.assertFalse(self.engine.journal.path.exists())

    def test_cas_revision_hash_and_duplicate(self):
        request, after = self.transition()
        with self.assertRaises(StateConflict):
            self.engine.begin_transaction(TransactionRequest(7, request.expected_project_hash, "stale", "x", "EDIT"), after)
        with self.assertRaises(StateConflict):
            self.engine.begin_transaction(TransactionRequest(0, "0" * 64, "hash", "x", "EDIT"), after)
        self.engine.begin_transaction(request, after)
        with self.assertRaises(DuplicateTransaction):
            self.engine.begin_transaction(request, after)
        self.assertEqual(len(self.events()), 1)

    def test_no_pending_and_prepared_abort_and_duplicate_recovery(self):
        self.assertEqual(self.engine.recover_pending(), "NO_PENDING")
        self.prepared()
        self.assertEqual(self.engine.recover_pending(), "ABORTED_PREPARED")
        self.assertEqual(self.engine.recover_pending(), "NO_PENDING")
        self.assertEqual(self.engine.read().state_revision, 0)
        self.assertEqual(self.events(), [])

    def test_state_applied_event_missing(self):
        _, after, event = self.prepared()
        _atomic_replace(self.engine.project_path, _json_bytes(after))
        self.assertEqual(self.engine.recover_pending(), "EVENT_REPLAYED")
        self.assertEqual(self.engine.recover_pending(), "NO_PENDING")
        self.assertEqual(self.events(), [event])

    def test_event_applied_state_old(self):
        _, after, event = self.prepared()
        self.engine._append_event(event)
        self.assertEqual(self.engine.recover_pending(), "STATE_REPLAYED")
        self.assertEqual(self.engine.read().document, after)
        self.assertEqual(self.events(), [event])

    def test_committed_with_stale_journal(self):
        _, after, event = self.prepared()
        _atomic_replace(self.engine.project_path, _json_bytes(after))
        self.engine._append_event(event)
        self.assertEqual(self.engine.recover_pending(), "ALREADY_COMMITTED")
        self.assertEqual(len(self.events()), 1)

    def test_crashes_during_commit_are_recoverable(self):
        request, after = self.transition()
        with patch.object(self.engine, "_append_event", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                self.engine.begin_transaction(request, after)
        self.assertTrue(self.engine.journal.path.exists())
        self.assertEqual(self.engine.recover_pending(), "EVENT_REPLAYED")
        self.assertEqual(len(self.events()), 1)

    def test_partial_pending_event_tail_recovers(self):
        _, after, event = self.prepared()
        _atomic_replace(self.engine.project_path, _json_bytes(after))
        with open(self.engine.events_path, "ab") as stream:
            stream.write(_json_bytes(event)[:32])
        self.assertEqual(self.engine.recover_pending(), "EVENT_REPLAYED")
        self.assertEqual(self.events(), [event])

    def test_partial_tail_conflict_preserves_event_bytes(self):
        self.prepared()
        self.engine.events_path.write_bytes(b"{")
        with self.assertRaises(RecoveryConflict):
            self.engine.recover_pending()
        self.assertEqual(self.engine.events_path.read_bytes(), b"{")
        self.assertTrue(self.engine.journal.path.exists())

    def test_external_state_or_history_change_conflicts(self):
        self.prepared()
        self.engine.project_path.write_text('{"schema_version":"2.0","state_revision":88}', encoding="utf-8")
        with self.assertRaises((RecoveryConflict, SchemaError)):
            self.engine.recover_pending()
        self.assertTrue(self.engine.journal.path.exists())

    def test_malformed_journal_conflicts(self):
        self.engine.journal.path.write_text("{bad", encoding="utf-8")
        with self.assertRaises(RecoveryConflict):
            self.engine.recover_pending()

    def test_duplicate_event_and_broken_history_conflict(self):
        request, after = self.transition()
        self.engine.begin_transaction(request, after)
        with open(self.engine.events_path, "ab") as stream:
            stream.write(_json_bytes(self.events()[0]))
        with self.assertRaises(RecoveryConflict):
            self.engine.recover_pending()

    def test_event_revision_jump_conflicts(self):
        request, after = self.transition()
        self.engine.begin_transaction(request, after)
        event = self.events()[0]
        event["state_revision_before"] = 99
        self.engine.events_path.write_bytes(_json_bytes(event))
        with self.assertRaises(RecoveryConflict):
            self.engine.recover_pending()

    def test_active_and_stale_lock(self):
        with self.engine.lock.acquire("first"):
            with self.assertRaises(WriterLockConflict):
                with self.engine.lock.acquire("second"):
                    pass
        self.engine.lock.path.write_bytes(b'L{"pid":999999,"status":"ACTIVE"}\n')
        self.assertEqual(self.engine.recover_pending(), "NO_PENDING")
        self.assertEqual(self.engine.lock.previous_owner["status"], "ACTIVE")

    def test_writer_lock_across_processes(self):
        code = ("import sys; from pathlib import Path; "
                f"sys.path.insert(0, {str(ROOT / 'src')!r}); "
                "from aivideo.state_engine import LocalWriterLock; "
                f"lock=LocalWriterLock(Path({str(self.path)!r})); "
                "ctx=lock.acquire('child'); ctx.__enter__(); "
                "print('READY', flush=True); sys.stdin.readline(); ctx.__exit__(None,None,None)")
        child = subprocess.Popen([sys.executable, "-B", "-c", code], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "READY")
            with self.assertRaises(WriterLockConflict):
                with self.engine.lock.acquire("parent"):
                    pass
        finally:
            child.stdin.write("\n")
            child.stdin.flush()
            child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0)

    def test_schema_migration_boundary_and_audited_commit(self):
        before = self.engine.read()
        newer = {**before.document, "schema_version": "2.1"}
        _atomic_replace(self.engine.project_path, _json_bytes(newer))
        current = self.engine.read()
        with self.assertRaises(UnsupportedNewerSchema):
            self.engine.begin_transaction(TransactionRequest(0, current.project_hash, "newer", "x", "EDIT"), current.document)
        older = {**before.document, "schema_version": "1.9"}
        _atomic_replace(self.engine.project_path, _json_bytes(older))
        current = self.engine.read()
        with self.assertRaises(MigrationRequired):
            self.engine.begin_transaction(TransactionRequest(0, current.project_hash, "older", "x", "EDIT"), current.document)
        with self.assertRaises(MigrationRequired):
            preview_migration(current.document, ())
        def validate_old(doc):
            if doc.get("schema_version") != "1.9" or doc.get("state_revision") != 0:
                raise SchemaError("invalid source")
        step = MigrationStep("1.9", "2.0", validate_old,
                             lambda doc: {**doc, "schema_version": "2.0"})
        destructive = MigrationStep("1.9", "2.0", validate_old,
                                    lambda doc: {**doc, "schema_version": "2.0", "shots": []})
        declared_destructive = MigrationStep("1.9", "2.0", validate_old,
                                             lambda doc: {**doc, "schema_version": "2.0", "shots": []},
                                             ("schema_version", "shots"))
        populated = {**current.document, "shots": [{"shot_id": "s1"}]}
        with self.assertRaises(SchemaError):
            preview_migration(populated, (destructive,))
        with self.assertRaises(SchemaError):
            preview_migration(populated, (declared_destructive,))
        output, report = preview_migration(current.document, (step,))
        self.assertEqual(output["state_revision"], 1)
        self.assertEqual(current.state_revision, 0)
        self.assertEqual(report["source_version"], "1.9")
        request = TransactionRequest(0, current.project_hash, "migration-1", "tester", "MIGRATION")
        result = self.engine.migrate(request, (step,))
        self.assertEqual(result.document["schema_version"], "2.0")
        audit = self.events()[0]["transition_metadata"]
        self.assertEqual(audit["source_version"], report["source_version"])
        self.assertEqual(audit["backup_sha256"], current.project_hash)
        self.assertTrue((self.path / audit["backup_path"]).exists())

    def test_handoff_base_conflicts(self):
        repo = self.path / "repo"
        repo.mkdir()
        project = repo / "project"
        project.mkdir()
        (project / "project.yaml").write_bytes((SAMPLE / "project.yaml").read_bytes())
        (project / "events.jsonl").write_bytes(b"")
        git = lambda *args: subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        git("init", "-b", "main")
        git("config", "user.email", "test@example.invalid")
        git("config", "user.name", "Test")
        (repo / "marker").write_text("one", encoding="utf-8")
        git("add", "marker", "project/project.yaml", "project/events.jsonl")
        git("commit", "-m", "base")
        bare = self.path / "remote.git"
        subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
        git("remote", "add", "origin", str(bare))
        git("push", "-u", "origin", "main")
        engine = StateEngine(project, repo=repo)
        before = engine.read()
        after = {**before.document, "state_revision": 1}
        base = capture_handoff_base(repo, project)
        verify_handoff_base(repo, project, base)
        verify_handoff_base(repo, project, base, snapshot=before)
        outside = StateEngine(self.path, repo=repo)
        with self.assertRaises(RemoteStateConflict):
            outside.begin_transaction(TransactionRequest(0, outside.read().project_hash,
                                    "outside", "x", "EDIT", base), after)
        untracked_dir = repo / "untracked"
        untracked_dir.mkdir()
        (untracked_dir / "project.yaml").write_bytes((SAMPLE / "project.yaml").read_bytes())
        (untracked_dir / "events.jsonl").write_bytes(b"")
        untracked = StateEngine(untracked_dir, repo=repo)
        untracked_base = capture_handoff_base(repo, untracked_dir)
        with self.assertRaises(RemoteStateConflict):
            untracked.begin_transaction(TransactionRequest(0, untracked.read().project_hash,
                                        "untracked", "x", "EDIT", untracked_base), after)
        original = engine.project_path.read_bytes()
        engine.project_path.write_bytes(_json_bytes({**before.document, "next_action": "local change"}))
        changed = engine.read()
        changed_base = capture_handoff_base(repo, project)
        with self.assertRaises(RemoteStateConflict):
            engine.begin_transaction(TransactionRequest(0, changed.project_hash,
                                     "uncommitted", "x", "EDIT", changed_base),
                                     {**changed.document, "state_revision": 1})
        with self.assertRaises(RemoteStateConflict):
            verify_handoff_base(repo, project, base)
        with self.assertRaises(RemoteStateConflict):
            verify_handoff_base(repo, project, base, snapshot=changed)
        engine.project_path.write_bytes(original)
        with self.assertRaises(RemoteStateConflict):
            engine.begin_transaction(TransactionRequest(0, before.project_hash, "no-base", "x", "EDIT"), after)
        bad = {**base, "base_commit": "0" * 40}
        with self.assertRaises(RemoteStateConflict):
            engine.begin_transaction(TransactionRequest(0, before.project_hash, "bad-base", "x", "EDIT", bad), after)
        engine.begin_transaction(TransactionRequest(0, before.project_hash, "with-base", "x", "EDIT", base), after)
        self.assertEqual(engine.read().state_revision, 1)
        second = engine.read()
        second_base = capture_handoff_base(repo, project)
        verify_handoff_base(repo, project, second_base)
        verify_handoff_base(repo, project, second_base, snapshot=second)
        engine.begin_transaction(TransactionRequest(1, second.project_hash, "second", "x", "EDIT", second_base),
                                 {**second.document, "state_revision": 2})
        self.assertEqual(engine.read().state_revision, 2)


if __name__ == "__main__":
    unittest.main()
