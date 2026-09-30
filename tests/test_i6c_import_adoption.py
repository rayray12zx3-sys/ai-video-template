"""I6c external-import adoption and recovery contract."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aivideo.schema import MigrationRequired, UnsupportedNewerSchema
from aivideo.state_engine import (DuplicateImport, DuplicateTransaction, RecoveryConflict,
                                  StateConflict, StateEngine, TransactionRequest, _json_bytes)
from aivideo.legacy_import import import_legacy_project


class ImportAdoptionTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        sample = ROOT / "examples" / "minimal-project" / "project.yaml"
        (self.path / "project.yaml").write_bytes(sample.read_bytes())
        (self.path / "events.jsonl").write_bytes(b"")
        self.engine = StateEngine(self.path)
        self.fixture = {
            "format": "legacy-project-sanitized-v1",
            "project": {"legacy_project_id": "sample-minimal", "state_revision": 7,
                        "next_action": "Review imported material"},
        }
        self.candidate, self.report = import_legacy_project(self.fixture)
        self.before = self.engine.read()
        self.request = self.make_request("import-1")

    def make_request(self, txid, revision=None, project_hash=None):
        return TransactionRequest(
            self.before.state_revision if revision is None else revision,
            self.before.project_hash if project_hash is None else project_hash,
            txid, "reviewer", "IMPORT_ADOPTION")

    def events(self):
        return [json.loads(line) for line in self.engine.events_path.read_bytes().splitlines()]

    def test_preview_is_deterministic_and_read_only(self):
        original = (self.engine.project_path.read_bytes(), self.engine.events_path.read_bytes())
        plan = self.engine.preview_import_adoption(self.request, self.fixture, self.candidate, self.report)
        self.assertEqual(plan, self.engine.preview_import_adoption(
            self.request, self.fixture, self.candidate, self.report))
        self.assertEqual(plan.document["state_revision"], 1)
        self.assertEqual(self.candidate["state_revision"], 7)
        self.assertEqual(original, (self.engine.project_path.read_bytes(), self.engine.events_path.read_bytes()))
        self.assertFalse(self.engine.journal.path.exists())
        self.assertFalse((self.path / ".import-backups").exists())
        self.assertFalse((self.path / ".import-evidence").exists())

    def test_commit_binds_checkpoint_report_and_provenance(self):
        before_bytes = self.engine.project_path.read_bytes()
        plan = self.engine.preview_import_adoption(self.request, self.fixture, self.candidate, self.report)
        result = self.engine.commit_import_adoption(self.request, self.fixture, self.candidate, self.report)
        self.assertEqual(result.document, plan.document)
        self.assertEqual(result.state_revision, 1)
        self.assertEqual(len(self.events()), 1)
        event = self.events()[0]
        self.assertEqual(event["event_type"], "IMPORT_ADOPTION")
        metadata = event["transition_metadata"]
        self.assertEqual(metadata, plan.transition_metadata)
        self.assertEqual((self.path / metadata["checkpoint_path"]).read_bytes(), before_bytes)
        self.assertEqual((self.path / metadata["report_evidence_path"]).read_bytes(), _json_bytes(self.report))
        self.assertEqual(metadata["checkpoint_sha256"], hashlib.sha256(before_bytes).hexdigest())
        self.assertEqual(metadata["report_sha256"], hashlib.sha256(_json_bytes(self.report)).hexdigest())
        self.assertEqual(metadata["candidate_sha256"], hashlib.sha256(_json_bytes(self.candidate)).hexdigest())
        self.assertEqual(metadata["source_fingerprint"], self.report["source_fingerprint"])
        self.assertEqual(metadata["candidate_source_revision"], 7)
        self.assertFalse(self.engine.journal.path.exists())

    def test_stale_identity_and_blocking_report_reject_before_artifacts(self):
        for request in (self.make_request("stale-revision", revision=9),
                        self.make_request("stale-hash", project_hash="0" * 64)):
            with self.assertRaises(StateConflict):
                self.engine.commit_import_adoption(request, self.fixture, self.candidate, self.report)
        changed = {**self.candidate, "project_id": "other"}
        with self.assertRaises(StateConflict):
            self.engine.commit_import_adoption(self.request, self.fixture, changed, self.report)
        blocked = deepcopy(self.report)
        blocked["unresolved_items"].append({"code": "NEEDS_REVIEW", "blocking": True})
        with self.assertRaises(StateConflict):
            self.engine.commit_import_adoption(self.request, self.fixture, self.candidate, blocked)
        for key, value in (("source_format", "wrong"), ("target_schema_version", "9.0"),
                           ("source_fingerprint", "bad")):
            bad = {**self.report, key: value}
            with self.assertRaises(StateConflict):
                self.engine.commit_import_adoption(self.request, self.fixture, self.candidate, bad)
        self.assertEqual(self.engine.read(), self.before)
        self.assertEqual(self.events(), [])
        self.assertFalse((self.path / ".import-backups").exists())

    def test_duplicate_transaction_and_import_identity(self):
        self.engine.commit_import_adoption(self.request, self.fixture, self.candidate, self.report)
        with self.assertRaises(DuplicateTransaction):
            self.engine.commit_import_adoption(self.request, self.fixture, self.candidate, self.report)
        with self.assertRaises(DuplicateImport):
            self.engine.commit_import_adoption(self.make_request("import-2"), self.fixture,
                                                self.candidate, self.report)
        self.assertEqual(len(self.events()), 1)

    def test_candidate_report_must_reproduce_from_source_fixture(self):
        changed = deepcopy(self.candidate)
        changed["next_action"] = "Unreviewed edit"
        with self.assertRaises(StateConflict):
            self.engine.commit_import_adoption(self.request, self.fixture, changed, self.report)
        changed_fixture = deepcopy(self.fixture)
        changed_fixture["project"]["next_action"] = "Different fixture"
        with self.assertRaises(StateConflict):
            self.engine.preview_import_adoption(self.request, changed_fixture,
                                                self.candidate, self.report)
        typed_fixture = deepcopy(self.fixture)
        typed_fixture["assets"] = [{"id": "asset-1", "media_type": "VIDEO",
                                    "origin": "REAL_UI", "content_role": "UI",
                                    "lifecycle": "RECEIVED", "selected": True}]
        typed_candidate, typed_report = import_legacy_project(typed_fixture)
        typed_candidate["assets"][0]["selected"] = 1
        with self.assertRaises(StateConflict):
            self.engine.commit_import_adoption(self.request, typed_fixture,
                                               typed_candidate, typed_report)
        self.assertEqual(self.engine.read(), self.before)
        self.assertEqual(self.events(), [])

    def test_artifact_collision_fails_closed(self):
        plan = self.engine.preview_import_adoption(self.request, self.fixture, self.candidate, self.report)
        artifact = self.path / plan.transition_metadata["checkpoint_path"]
        artifact.parent.mkdir()
        artifact.write_bytes(b"unrelated")
        with self.assertRaises(RecoveryConflict):
            self.engine.commit_import_adoption(self.request, self.fixture, self.candidate, self.report)
        self.assertEqual(self.engine.read(), self.before)
        self.assertEqual(self.events(), [])
        artifact.unlink()
        evidence = self.path / plan.transition_metadata["report_evidence_path"]
        evidence.parent.mkdir()
        evidence.write_bytes(b"unrelated")
        with self.assertRaises(RecoveryConflict):
            self.engine.commit_import_adoption(self.request, self.fixture, self.candidate, self.report)
        self.assertEqual(self.engine.read(), self.before)
        self.assertEqual(self.events(), [])

    def test_artifact_directory_link_outside_project_fails_closed(self):
        outside = self.path.parent / (self.path.name + "-outside")
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        linked = self.path / ".import-backups"
        try:
            linked.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlink creation is unavailable")
        with self.assertRaises(RecoveryConflict):
            self.engine.commit_import_adoption(self.request, self.fixture,
                                               self.candidate, self.report)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.engine.read(), self.before)

    def test_failed_prepare_leaves_canonical_unchanged_and_retry_reuses_artifacts(self):
        with patch.object(self.engine.journal, "prepare", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                self.engine.commit_import_adoption(self.request, self.fixture, self.candidate, self.report)
        self.assertEqual(self.engine.read(), self.before)
        self.assertEqual(self.events(), [])
        self.assertFalse(self.engine.journal.path.exists())
        self.assertEqual(self.engine.commit_import_adoption(
            self.request, self.fixture, self.candidate, self.report).state_revision, 1)

    def test_interrupted_after_project_replace_recovers_with_evidence(self):
        with patch.object(self.engine, "_append_event", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                self.engine.commit_import_adoption(self.request, self.fixture, self.candidate, self.report)
        self.assertTrue(self.engine.journal.path.exists())
        self.assertEqual(self.engine.recover_pending(), "EVENT_REPLAYED")
        self.assertEqual(self.engine.read().state_revision, 1)
        self.assertEqual(len(self.events()), 1)
        metadata = self.events()[0]["transition_metadata"]
        self.assertTrue((self.path / metadata["checkpoint_path"]).exists())
        self.assertTrue((self.path / metadata["report_evidence_path"]).exists())

    def test_recovery_refuses_missing_import_evidence(self):
        with patch.object(self.engine, "_append_event", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                self.engine.commit_import_adoption(self.request, self.fixture, self.candidate, self.report)
        record = self.engine.journal.load()
        evidence = self.path / record["event"]["transition_metadata"]["report_evidence_path"]
        evidence.unlink()
        with self.assertRaises(RecoveryConflict):
            self.engine.recover_pending()
        self.assertTrue(self.engine.journal.path.exists())
        self.assertEqual(self.events(), [])

    def test_external_adoption_uses_whole_import_dependency_semantics(self):
        fixture = {
            "format": "legacy-project-sanitized-v1",
            "project": {"legacy_project_id": "sample-minimal", "state_revision": 0},
            "assets": [{"id": "source", "media_type": "VIDEO", "origin": "REAL_UI",
                        "content_role": "UI", "lifecycle": "RECEIVED"}],
            "shots": [{"id": "dependent", "duration_frames": 60, "intent": "UI view",
                       "input_asset_ids": ["source"], "production_method": "SOURCE_VIDEO",
                       "readiness": "REQUIRED", "new_media_required": False,
                       "editorial_only": True}],
            "dependencies": [{"source": "asset:source", "target": "shot:dependent",
                              "impact": "SEMANTIC_CONTENT"}],
        }
        seeded, report = import_legacy_project(fixture)
        initial = {**seeded, "state_revision": 1}
        self.engine.begin_transaction(TransactionRequest(
            0, self.before.project_hash, "seed", "reviewer", "EDIT"), initial)
        snapshot = self.engine.read()
        fixture["assets"][0]["lifecycle"] = "SELECTED"
        candidate, report = import_legacy_project(fixture)
        ordinary = {**candidate, "state_revision": 2}
        with self.assertRaises(StateConflict):
            self.engine.begin_transaction(TransactionRequest(
                1, snapshot.project_hash, "ordinary", "reviewer", "EDIT"), ordinary)
        request = TransactionRequest(1, snapshot.project_hash, "adopt", "reviewer", "IMPORT_ADOPTION")
        self.assertEqual(self.engine.commit_import_adoption(
            request, fixture, candidate, report).state_revision, 2)
        self.assertEqual(self.events()[-1]["event_type"], "IMPORT_ADOPTION")

    def test_schema_and_ordinary_transaction_boundaries(self):
        with self.assertRaises(ValueError):
            self.engine.begin_transaction(self.request, self.candidate)
        with self.assertRaises(ValueError):
            self.engine.commit_import_adoption(TransactionRequest(
                0, self.before.project_hash, "wrong-type", "reviewer", "MIGRATION"),
                self.fixture, self.candidate, self.report)
        self.engine.project_path.write_bytes(_json_bytes({**self.before.document,
                                                           "schema_version": "2.1"}))
        with self.assertRaises(UnsupportedNewerSchema):
            self.engine.preview_import_adoption(self.request, self.fixture, self.candidate, self.report)
        self.engine.project_path.write_bytes(_json_bytes({**self.before.document,
                                                           "schema_version": "1.9"}))
        with self.assertRaises(MigrationRequired):
            self.engine.preview_import_adoption(self.request, self.fixture, self.candidate, self.report)


if __name__ == "__main__":
    unittest.main()
