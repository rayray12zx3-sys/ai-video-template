"""Offline I8 output closure contracts and adapter tests."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
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

import test_i2_validation as i2_fixture
import test_i3_execution as i3_fixture
from aivideo.execution import (ExecutionConflict, ExecutionLedger, ProviderReceipt, ProviderUpload,
                               adopt_generated_output)
from aivideo.gates import evaluate_gates
from aivideo.qc import check_file_metadata, probe_media, probe_q0
from aivideo.state_engine import StateEngine, TransactionRequest, _atomic_replace, _hash, _json_bytes
from aivideo.tickets import (AccountEntitlementSnapshot, OperationCapability, ProviderRuntimeSnapshot,
                             TechnicalCapabilitySnapshot, compile_ticket)


class OutputClosureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = i2_fixture.I2Tests("test_each_gate_passes_with_minimum_evidence")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tmp.cleanup)
        self.engine = self.fixture.engine
        self.ledger = ExecutionLedger(self.fixture.root)
        now = datetime.now(timezone.utc)
        start = (now - timedelta(minutes=1)).isoformat()
        end = (now + timedelta(minutes=30)).isoformat()
        self.technical = TechnicalCapabilitySnapshot(
            "tech-1", "example", "mock-backend", start, end, ("IMAGE_TO_VIDEO",),
            operation_profiles=(OperationCapability("IMAGE_TO_VIDEO", "model-1", (5,),
                                                   ("720p",), ("9:16",), 1, False),))
        self.entitlement = AccountEntitlementSnapshot("ent-1", "example", "ws-1", start, end,
                                                       True, True, 20, 1)
        self.runtime = ProviderRuntimeSnapshot("run-1", "example", "mock-backend", "RAW_CLI",
                                                "ws-1", start, "tech-1", "ent-1")

    def ticket(self, **overrides):
        values = dict(shot_id="shot-a", candidate_id="candidate-a", provider="example",
                      surface="RAW_CLI", workspace_id="ws-1", operation="IMAGE_TO_VIDEO",
                      mode="I2V", source_prompt="Source", compiled_prompt="Source",
                      transform_policy="EXACT", technical=self.technical, runtime=self.runtime,
                      entitlement=self.entitlement, model="model-1",
                      parameters={"duration_seconds": 5, "resolution": "720p"}, quote=2,
                      external_processing_decision="ALLOWED")
        values.update(overrides)
        return compile_ticket(self.engine, **values)

    def approve_spend(self, ticket, candidate_id="candidate-a"):
        next_revision = self.engine.read().state_revision + 1
        self.fixture.commit(lambda doc: doc["evidence"].append({**self.fixture.evidence(
            "SPEND_APPROVAL", "project:generation_plan", action_id="action-a", provider="example",
            ticket_id=ticket.id, candidate_id=candidate_id, shot_id="shot-a",
            workspace_id="ws-1", max_cost=2), "state_revision": next_revision}))

    def prepare_submission_and_receipt(self, ticket=None, task_id="task-100", *,
                                       completed=True, persist_receipt=True):
        ticket = ticket or self.ticket()
        self.approve_spend(ticket)
        request = self.fixture.request(ticket_id=ticket.id)
        claim = self.ledger.prepare(
            self.engine, ticket, request, "tester",
            preflight_verifier=i3_fixture.I3Tests._mock_preflight,
            approval_verifier=i3_fixture.I3Tests._mock_approval,
        )
        self.ledger.transition(
            claim.id, "SUBMITTING", request_fingerprint="request-hash", local_key="local-key",
            engine=self.engine, ticket=ticket, request=request, technical=self.technical,
            entitlement=self.entitlement, runtime=self.runtime,
            preflight_verifier=i3_fixture.I3Tests._mock_preflight,
            approval_verifier=i3_fixture.I3Tests._mock_approval,
        )
        self.ledger.transition(claim.id, "SUBMITTED", provider_task_id=task_id)
        if completed:
            self.ledger.transition(claim.id, "COMPLETED")
        asset_hash = self.fixture.doc["assets"][0]["sha256"]
        upload = (ProviderUpload("input", asset_hash, asset_hash, "upload-1"),)
        now = datetime.now(timezone.utc).isoformat()
        receipt = ProviderReceipt(
            ticket.id, ticket.payload()["candidate_id"], claim.id, "example", "ws-1", "RAW_CLI",
            "COMPLETED" if completed else "SUBMITTED", "run-1", task_id, 2,
            2 if completed else None, ("output-1",) if completed else (),
            now, now if completed else None, "provider callback",
            effective_prompt="Source", uploaded_inputs=upload,
            observed_workspace_id="ws-1", workspace_evidence_ref="mock:status",
        )
        if persist_receipt:
            self.ledger.record_receipt(
                receipt, ticket, workspace_verifier=lambda r, t: True
            )
        return ticket, receipt, claim

    def create_mock_media(self, filename="candidate-a.mp4", content=b"mock mp4 media bytes"):
        media_dir = self.fixture.root / "media"
        media_dir.mkdir(exist_ok=True)
        file_path = media_dir / filename
        file_path.write_bytes(content)
        sha256 = hashlib.sha256(content).hexdigest()
        return file_path, sha256

    def valid_probed_metadata(self):
        return {
            "exists": True, "readable": True, "container": "mov,mp4,m4a,3gp,3g2,mj2",
            "codec": "h264", "resolution": "1280x720", "fps": 24, "frame_count": 120,
            "duration": 5.0, "audio_presence": False, "color_metadata": "bt709",
        }

    # --- Scope A: ffprobe bridge tests ---

    def test_ffprobe_valid_video(self):
        file_path, _ = self.create_mock_media()
        sample_ffprobe_out = {
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "5.000000"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1280,
                    "height": 720,
                    "r_frame_rate": "24/1",
                    "nb_frames": "120",
                    "color_space": "bt709",
                }
            ],
        }
        mock_res = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout=json.dumps(sample_ffprobe_out), stderr=""
        )
        with patch("subprocess.run", return_value=mock_res):
            meta = probe_media(file_path)
            self.assertTrue(meta["exists"])
            self.assertTrue(meta["readable"])
            self.assertEqual(meta["container"], "mov")
            self.assertEqual(meta["codec"], "h264")
            self.assertEqual(meta["resolution"], "1280x720")
            self.assertEqual(meta["fps"], 24)
            self.assertEqual(meta["duration"], 5.0)
            self.assertFalse(meta["audio_presence"])
            self.assertEqual(meta["color_metadata"], "bt709")

            metadata, q0_check = probe_q0(file_path, expected={"codec": "h264", "resolution": "1280x720"})
            self.assertEqual(q0_check["codec"].status, "PASS")
            self.assertEqual(q0_check["resolution"].status, "PASS")

    def test_ffprobe_unreadable_or_missing_file(self):
        missing = self.fixture.root / "media" / "nonexistent.mp4"
        meta = probe_media(missing)
        self.assertFalse(meta["exists"])
        self.assertFalse(meta["readable"])

    def test_ffprobe_malformed_json(self):
        file_path, _ = self.create_mock_media()
        mock_res = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="not valid json {{{", stderr=""
        )
        with patch("subprocess.run", return_value=mock_res):
            meta = probe_media(file_path)
            self.assertTrue(meta["exists"])
            self.assertFalse(meta["readable"])

    def test_ffprobe_no_video_stream(self):
        file_path, _ = self.create_mock_media()
        sample_ffprobe_out = {
            "format": {"format_name": "mp3", "duration": "10.0"},
            "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
        }
        mock_res = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout=json.dumps(sample_ffprobe_out), stderr=""
        )
        with patch("subprocess.run", return_value=mock_res):
            meta = probe_media(file_path)
            self.assertTrue(meta["exists"])
            self.assertTrue(meta["readable"])
            self.assertIsNone(meta["codec"])
            self.assertIsNone(meta["resolution"])
            self.assertTrue(meta["audio_presence"])

    # --- Scope B & C: Adoption tests ---

    def test_valid_video_adoption(self):
        ticket, receipt, claim = self.prepare_submission_and_receipt()
        file_path, sha256 = self.create_mock_media()
        probed = self.valid_probed_metadata()

        revision_before = self.engine.read().state_revision
        snapshot = adopt_generated_output(
            self.engine, self.ledger, ticket, receipt, file_path, sha256, probed,
            actor="qc_operator",
        )
        self.assertEqual(snapshot.state_revision, revision_before + 1)
        doc = snapshot.document
        asset_id = "asset-candidate-a"
        asset = next((a for a in doc["assets"] if a["id"] == asset_id), None)
        self.assertIsNotNone(asset)
        self.assertEqual(asset["origin"], "PROVIDER_OUTPUT")
        self.assertEqual(asset["lifecycle"], "RECEIVED")
        self.assertEqual(asset["sha256"], sha256)
        self.assertEqual(asset["media_metadata"]["codec"], "h264")
        self.assertEqual(asset["provider_task_id"], "task-100")
        self.assertEqual(asset["lineage"]["ticket_id"], ticket.id)
        self.assertEqual(asset["lineage"]["claim_id"], claim.id)
        self.assertIn("Perform Q1 visual and technical QC", doc["next_action"])

    def test_unreadable_file_adoption_fails_closed(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        missing_file = self.fixture.root / "media" / "missing.mp4"
        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, receipt, missing_file, "0" * 64,
            )

        file_path, sha256 = self.create_mock_media()
        unreadable_meta = {"exists": True, "readable": False, "container": None, "codec": None,
                           "resolution": None, "fps": None, "frame_count": None, "duration": None,
                           "audio_presence": False, "color_metadata": None}
        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, receipt, file_path, sha256, unreadable_meta,
            )

    def test_no_video_stream_adoption_fails_closed(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        file_path, sha256 = self.create_mock_media()
        audio_only = {
            "exists": True, "readable": True, "container": "mp3", "codec": None,
            "resolution": None, "fps": None, "frame_count": None, "duration": 10.0,
            "audio_presence": True, "color_metadata": None,
        }
        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, receipt, file_path, sha256, audio_only,
            )

    def test_wrong_sha256_adoption_fails_closed(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        file_path, _ = self.create_mock_media()
        wrong_sha256 = "f" * 64
        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, receipt, file_path, wrong_sha256, self.valid_probed_metadata(),
            )

    def test_stale_state_revision_or_hash_fails_closed(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        file_path, sha256 = self.create_mock_media()

        # Update bound shot to cause ticket staleness
        self.fixture.commit(lambda doc: doc["shots"][0].update(intent="Changed shot intent"))

        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, receipt, file_path, sha256, self.valid_probed_metadata(),
            )

    def test_wrong_ticket_candidate_shot_binding_fails_closed(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        file_path, sha256 = self.create_mock_media()

        wrong_receipt = replace(receipt, candidate_id="wrong-candidate")
        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, wrong_receipt, file_path, sha256, self.valid_probed_metadata(),
            )

    def test_provider_workspace_mismatch_fails_closed(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        file_path, sha256 = self.create_mock_media()

        wrong_receipt = replace(receipt, workspace_id="ws-other", observed_workspace_id="ws-other")
        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, wrong_receipt, file_path, sha256, self.valid_probed_metadata(),
            )

    def test_missing_trusted_receipt_identity_fails_closed(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        file_path, sha256 = self.create_mock_media()

        unverified_receipt = replace(receipt, observed_workspace_id=None)
        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, unverified_receipt, file_path, sha256, self.valid_probed_metadata(),
            )

    def test_submitted_receipt_or_claim_cannot_be_adopted(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt(completed=False)
        file_path, sha256 = self.create_mock_media()
        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, receipt, file_path, sha256,
                self.valid_probed_metadata(),
            )

    def test_matching_unpersisted_receipt_is_rejected(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt(persist_receipt=False)
        file_path, sha256 = self.create_mock_media()
        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, receipt, file_path, sha256,
                self.valid_probed_metadata(),
            )

    def test_adoption_next_action_is_deterministic_qc_only(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        file_path, sha256 = self.create_mock_media()
        snapshot = adopt_generated_output(
            self.engine, self.ledger, ticket, receipt, file_path, sha256,
            self.valid_probed_metadata(),
        )
        self.assertIn("Q1", snapshot.document["next_action"])
        self.assertNotIn("delivery", snapshot.document["next_action"].lower())
        self.assertNotIn("final", snapshot.document["next_action"].lower())
        with self.assertRaises(TypeError):
            adopt_generated_output(
                self.engine, self.ledger, ticket, receipt, file_path, sha256,
                self.valid_probed_metadata(), next_action="FINAL DELIVERY",
            )

    def test_incomplete_video_metadata_fails_closed(self):
        for field, value in (
            ("codec", None),
            ("resolution", None),
            ("resolution", "0x720"),
            ("resolution", "1280x0"),
            ("duration", None),
            ("duration", 0),
        ):
            with self.subTest(field=field, value=value):
                fixture = i2_fixture.I2Tests("test_each_gate_passes_with_minimum_evidence")
                fixture.setUp()
                self.addCleanup(fixture.tmp.cleanup)
                engine = fixture.engine
                ledger = ExecutionLedger(fixture.root)

                original_engine, original_ledger, original_fixture = self.engine, self.ledger, self.fixture
                self.engine, self.ledger, self.fixture = engine, ledger, fixture
                try:
                    ticket, receipt, _ = self.prepare_submission_and_receipt()
                    file_path, sha256 = self.create_mock_media()
                    metadata = self.valid_probed_metadata()
                    metadata[field] = value
                    with self.assertRaises(ExecutionConflict):
                        adopt_generated_output(
                            self.engine, self.ledger, ticket, receipt, file_path, sha256, metadata,
                        )
                finally:
                    self.engine, self.ledger, self.fixture = original_engine, original_ledger, original_fixture

    def test_duplicate_adoption_idempotent_safe(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        file_path, sha256 = self.create_mock_media()
        probed = self.valid_probed_metadata()

        first_snapshot = adopt_generated_output(
            self.engine, self.ledger, ticket, receipt, file_path, sha256, probed,
        )
        second_snapshot = adopt_generated_output(
            self.engine, self.ledger, ticket, receipt, file_path, sha256, probed,
        )
        self.assertEqual(first_snapshot.state_revision, second_snapshot.state_revision)
        self.assertEqual(first_snapshot.project_hash, second_snapshot.project_hash)

        # Adoption with same candidate_id but different SHA-256 fails closed
        other_path, other_sha256 = self.create_mock_media("candidate-a2.mp4", b"different bytes")
        with self.assertRaises(ExecutionConflict):
            adopt_generated_output(
                self.engine, self.ledger, ticket, receipt, other_path, other_sha256, probed,
            )

    def test_q0_failure_remains_non_final(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        file_path, sha256 = self.create_mock_media()
        snapshot = adopt_generated_output(
            self.engine, self.ledger, ticket, receipt, file_path, sha256, self.valid_probed_metadata(),
        )
        asset = next(a for a in snapshot.document["assets"] if a["id"] == "asset-candidate-a")
        self.assertNotEqual(asset["lifecycle"], "APPROVED")
        self.assertNotEqual(asset["lifecycle"], "FINAL")
        self.assertEqual(asset["lifecycle"], "RECEIVED")
        # Remove final QC approval to confirm adoption alone does not authorize G6
        self.fixture.commit(lambda doc: doc.update(
            evidence=[e for e in doc["evidence"] if e["kind"] != "FINAL_QC_APPROVAL"]
        ))
        self.assertNotEqual(evaluate_gates(self.engine)["G6"]["status"], "PASS")

    def test_state_engine_transaction_recovery_behavior(self):
        ticket, receipt, _ = self.prepare_submission_and_receipt()
        file_path, sha256 = self.create_mock_media()

        # Simulate an interrupted adoption (journal prepared, project.yaml replaced, event not appended)
        before = self.engine.inspect_consistency()
        doc = before.document
        asset_id = "asset-candidate-a"
        new_asset = {
            "id": asset_id, "origin": "PROVIDER_OUTPUT", "lifecycle": "RECEIVED",
            "criticality": "OPTIONAL", "sha256": sha256, "provenance": "interrupted adoption",
            "locators": [{"type": "LOCAL", "path": "media/candidate-a.mp4", "availability": "AVAILABLE"}],
            "media_metadata": self.valid_probed_metadata(), "provider_task_id": "task-100",
            "lineage": {"ticket_id": ticket.id, "claim_id": receipt.claim_id, "candidate_id": "candidate-a",
                        "shot_id": "shot-a", "provider": "example", "workspace_id": "ws-1",
                        "execution_surface": "RAW_CLI", "runtime_snapshot_id": "run-1"},
        }
        after = {**doc, "state_revision": before.state_revision + 1, "assets": [*doc["assets"], new_asset]}
        after_hash = _hash(_json_bytes(after))
        event = {
            "event_schema_version": "1.0", "transaction_id": "tx-adopt-pending",
            "state_revision_before": before.state_revision,
            "state_revision_after": before.state_revision + 1,
            "project_hash_before": before.project_hash,
            "project_hash_after": after_hash,
            "timestamp": "2026-09-25T00:00:00Z", "actor": "tester",
            "event_type": "GENERATED_OUTPUT_ADOPTION",
        }
        req = TransactionRequest(before.state_revision, before.project_hash, "tx-adopt-pending", "tester", "GENERATED_OUTPUT_ADOPTION")
        self.engine.journal.prepare(req, before, after, event)
        _atomic_replace(self.engine.project_path, _json_bytes(after))

        # Recover pending transaction
        result = self.engine.recover_pending()
        self.assertEqual(result, "EVENT_REPLAYED")
        snapshot = self.engine.inspect_consistency()
        self.assertEqual(snapshot.state_revision, before.state_revision + 1)
        self.assertTrue(any(a["id"] == asset_id for a in snapshot.document["assets"]))


if __name__ == "__main__":
    unittest.main()
