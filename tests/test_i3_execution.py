"""Offline I3 contract tests. All verifier callbacks in this file are test-only."""

import copy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import test_i2_validation as i2_fixture
from aivideo.execution import (ExecutionConflict, ExecutionLedger, ProviderReceipt, ProviderUpload,
                               manual_web_import)
from aivideo.guards import guard_action
from aivideo.router import plan_shots, route_shot
from aivideo.tickets import (AccountEntitlementSnapshot, CanvasLiveState,
                             OperationCapability, ProviderRuntimeSnapshot,
                             TechnicalCapabilitySnapshot, compile_ticket, ticket_staleness)


class I3Tests(unittest.TestCase):
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

    @staticmethod
    def _mock_preflight(request, snapshot, now):
        return i2_fixture.I2Tests.trusted_preflight(request, snapshot, now)

    @staticmethod
    def _mock_approval(*args):
        return True

    def approve_spend(self, ticket, candidate_id="candidate-a"):
        next_revision = self.engine.read().state_revision + 1
        self.fixture.commit(lambda doc: doc["evidence"].append({**self.fixture.evidence(
            "SPEND_APPROVAL", "project:generation_plan", action_id="action-a", provider="example",
            ticket_id=ticket.id, candidate_id=candidate_id, shot_id="shot-a",
            workspace_id="ws-1", max_cost=2), "state_revision": next_revision}))

    def submit(self, claim, ticket, request, **overrides):
        values = dict(engine=self.engine, ticket=ticket, request=request,
                      technical=self.technical, entitlement=self.entitlement, runtime=self.runtime,
                      preflight_verifier=self._mock_preflight, approval_verifier=self._mock_approval)
        values.update(overrides)
        return self.ledger.transition(claim.id, "SUBMITTING", request_fingerprint="request-hash",
            local_key="local-key", **values)

    def test_router_determinism_explanation_and_generic_rules(self):
        shot = {"id": "arbitrary-123", "input_asset_ids": [], "production_method": "AUTO",
                "motion_required": True, "requirements": {"camera": {"complex_geometry": True}}}
        first = route_shot(shot, capabilities=(self.technical,))
        self.assertEqual(first, route_shot(copy.deepcopy(shot), capabilities=(self.technical,)))
        self.assertEqual(first.method, "AUTO")  # No TEXT_TO_VIDEO proof.
        self.assertIn("CAPABILITY_UNPROVEN", first.reasons)
        self.assertEqual(first.previs, "STATIC_3D")
        shot["input_asset_ids"] = ["source"]
        asset = {"id": "source", "origin": "REAL_UI", "media_type": "VIDEO", "lifecycle": "APPROVED"}
        self.assertEqual(route_shot(shot, (asset,)).method, "SOURCE_VIDEO")
        shot["error_owner"] = "REFERENCE"
        self.assertEqual(route_shot(shot, (asset,)).owner, "REFERENCE")
        self.assertEqual(route_shot(shot, (asset,)).method, "AUTO")
        identity = {"id": "generic-identity", "production_method": "AI_VIDEO", "input_asset_ids": [],
                    "requirements": {"identity_sensitivity": "HIGH"}}
        self.assertIn("IDENTITY_REFERENCE_REQUIRED", route_shot(identity, capabilities=(self.technical,)).reasons)
        identity["input_asset_ids"] = ["audio"]
        audio_asset = {"id": "audio", "media_type": "AUDIO", "lifecycle": "APPROVED"}
        self.assertIn("IDENTITY_REFERENCE_REQUIRED", route_shot(identity, (audio_asset,),
                                                                 (self.technical,)).reasons)
        identity["requirements"]["required_features"] = "motion-control"
        with self.assertRaises(ValueError):
            route_shot(identity, (audio_asset,), (self.technical,))
        self.assertEqual(plan_shots((shot,), (asset,))[0].shot_id, "arbitrary-123")

    def test_ticket_hash_scope_prompt_and_source_lineage(self):
        source_hash = self.fixture.doc["assets"][0]["sha256"]
        derivative = {"source_asset_id": "input", "source_sha256": source_hash,
                      "derivative_id": "ready-1", "derivative_sha256": hashlib.sha256(b"ready").hexdigest(),
                      "transform_fingerprint": hashlib.sha256(b"resize:v1").hexdigest()}
        ticket = self.ticket(derivative_inputs=(derivative,))
        self.assertEqual(ticket.id, self.ticket(derivative_inputs=(derivative,)).id)
        self.assertTrue(ticket.verify())
        self.assertEqual(ticket_staleness(ticket, self.engine), ())
        payload = ticket.payload()
        self.assertEqual(payload["prompt"]["source"], "Source")
        self.assertEqual(payload["prompt"]["compiled"], "Source")
        self.assertEqual(payload["derivative_inputs"][0]["source_sha256"], source_hash)
        payload["prompt"]["source"] = "tampered copy"
        self.assertEqual(ticket.payload()["prompt"]["source"], "Source")
        with self.assertRaises(ValueError):
            self.ticket(compiled_prompt="Optimized")
        optimized = self.ticket(compiled_prompt="Optimized", transform_policy="ALLOW_OPTIMIZATION")
        self.assertEqual(optimized.payload()["prompt"]["source"], "Source")
        self.assertEqual(optimized.payload()["prompt"]["compiled"], "Optimized")
        with self.assertRaises(ValueError):
            self.ticket(derivative_inputs=({**derivative, "source_sha256": "0" * 64},))
        with self.assertRaises(ValueError):
            self.ticket(derivative_inputs=(derivative, derivative))

    def test_ticket_dependency_staleness_is_scoped(self):
        ticket = self.ticket()
        self.fixture.commit(lambda doc: doc.update(next_action="Unrelated editorial note"))
        self.assertEqual(ticket_staleness(ticket, self.engine), ())
        self.fixture.commit(lambda doc: doc["shots"][0].update(intent="Changed intent"))
        self.assertIn("shot:shot-a", ticket_staleness(ticket, self.engine))

    def test_capability_entitlement_canvas_and_surface_validation(self):
        self.assertEqual(self.ticket().payload()["entitlement_snapshot_id"], "ent-1")
        with self.assertRaises(ValueError):
            self.ticket(surface="CLI")
        with self.assertRaises(ValueError):
            self.ticket(entitlement=None)
        with self.assertRaises(ValueError):
            self.ticket(parameters={"duration_seconds": 9})
        with self.assertRaises(ValueError):
            self.ticket(surface="CANVAS_WEB")
        canvas = CanvasLiveState("canvas-1", "2", "7", "6", datetime.now(timezone.utc).isoformat())
        self.assertEqual(canvas.base_edit_version, "6")
        self.assertFalse(self.technical.supports_idempotency("IMAGE_TO_VIDEO", "mock-backend"))
        declared = TechnicalCapabilitySnapshot("tech-2", "example", "mock-backend",
            self.technical.captured_at, self.technical.expires_at, ("IMAGE_TO_VIDEO",),
            idempotent_operations=("IMAGE_TO_VIDEO",), native_evidence_ref="evidence/mock-help.txt")
        self.assertTrue(declared.supports_idempotency("IMAGE_TO_VIDEO", "mock-backend"))
        self.assertFalse(declared.supports_idempotency("IMAGE_TO_VIDEO", "other-backend"))

    def test_claim_conflict_unknown_and_reconciled_no_submission(self):
        ticket = self.ticket()
        self.approve_spend(ticket)
        request = self.fixture.request(ticket_id=ticket.id)
        self.assertEqual(guard_action(self.engine, request)["decision"], "DENY")
        with self.assertRaises(ExecutionConflict):
            self.ledger.prepare(self.engine, ticket, self.fixture.request(ticket_id=ticket.id, quoted_cost=0),
                                "tester", preflight_verifier=self._mock_preflight,
                                approval_verifier=self._mock_approval)
        claim = self.ledger.prepare(self.engine, ticket, request, "tester",
                                    preflight_verifier=self._mock_preflight,
                                    approval_verifier=self._mock_approval)
        self.assertEqual(claim.submission_state, "PREPARED")
        with self.assertRaises(ExecutionConflict):
            self.ledger.transition(claim.id, "SUBMITTING", request_fingerprint="request-hash",
                                   local_key="local-key")
        with self.assertRaises(ExecutionConflict):
            self.submit(claim, ticket, self.fixture.request(action="EXTERNAL_UPLOAD", ticket_id=ticket.id))
        with self.assertRaises(ExecutionConflict):
            self.submit(claim, ticket, self.fixture.request(ticket_id=ticket.id, candidate_id="other"))
        self.submit(claim, ticket, request)
        self.assertEqual(self.ledger.submission_record(claim.id)["local_key"], "local-key")
        self.ledger.transition(claim.id, "UNKNOWN_SUBMISSION")
        web_runtime = ProviderRuntimeSnapshot("run-web", "example", "mock-backend", "WEB_MANUAL",
                                               "ws-1", self.runtime.captured_at, "tech-1", "ent-1")
        web_ticket = self.ticket(surface="WEB_MANUAL", runtime=web_runtime)
        self.approve_spend(web_ticket)
        web_request = self.fixture.request(ticket_id=web_ticket.id)
        with self.assertRaises(ExecutionConflict):
            self.ledger.prepare(self.engine, web_ticket, web_request, "second surface",
                                preflight_verifier=self._mock_preflight,
                                approval_verifier=self._mock_approval)
        with self.assertRaises(ExecutionConflict):
            self.ledger.transition(claim.id, "SUBMITTING", request_fingerprint="new-hash", local_key="new-key")
        with self.assertRaises(ExecutionConflict):
            self.ledger.transition(claim.id, "NO_SUBMISSION", evidence={"review": "manual"})
        self.ledger.transition(claim.id, "NO_SUBMISSION", evidence={
            "proof": "no task", "observed_workspace_id": "ws-1",
            "workspace_evidence_ref": "mock:account-history"},
                               verifier=lambda claim, evidence: "NO_SUBMISSION")  # test-only
        second = self.ledger.prepare(self.engine, web_ticket, web_request, "tester",
                                     preflight_verifier=self._mock_preflight,
                                     approval_verifier=self._mock_approval)
        self.assertNotEqual(second.id, claim.id)

    def test_unknown_submission_never_retries_and_reconciliation_needs_workspace_evidence(self):
        ticket = self.ticket()
        self.approve_spend(ticket)
        request = self.fixture.request(ticket_id=ticket.id)
        claim = self.ledger.prepare(self.engine, ticket, request, "tester",
                                    preflight_verifier=self._mock_preflight,
                                    approval_verifier=self._mock_approval)
        self.submit(claim, ticket, request)
        self.ledger.transition(claim.id, "UNKNOWN_SUBMISSION")
        with self.assertRaises(ExecutionConflict):
            self.submit(claim, ticket, request)
        with self.assertRaises(ExecutionConflict):
            self.ledger.prepare(self.engine, ticket, request, "tester",
                                preflight_verifier=self._mock_preflight,
                                approval_verifier=self._mock_approval)
        for evidence in ({"provider_task_id": "task-1"},
                         {"observed_workspace_id": "ws-other", "workspace_evidence_ref": "mock:status"}):
            with self.subTest(evidence=evidence), self.assertRaises(ExecutionConflict):
                self.ledger.transition(claim.id, "SUBMITTED", provider_task_id="task-1",
                                       evidence=evidence,
                                       verifier=lambda claim, evidence: "SUBMITTED")  # test-only
        self.assertEqual(self.ledger.submission_record(claim.id)["state"], "UNKNOWN_SUBMISSION")

    def test_receipt_requires_verified_observed_workspace(self):
        ticket = self.ticket()
        self.approve_spend(ticket)
        request = self.fixture.request(ticket_id=ticket.id)
        claim = self.ledger.prepare(self.engine, ticket, request, "tester",
                                    preflight_verifier=self._mock_preflight,
                                    approval_verifier=self._mock_approval)
        self.submit(claim, ticket, request)
        self.ledger.transition(claim.id, "SUBMITTED", provider_task_id="task-1")
        asset_hash = self.fixture.doc["assets"][0]["sha256"]
        upload = (ProviderUpload("input", asset_hash, asset_hash, "upload-1"),)
        base = (ticket.id, "candidate-a", claim.id, "example", "ws-1", "RAW_CLI",
                "SUBMITTED", "run-1", "task-1", 2, None, (),
                datetime.now(timezone.utc).isoformat(), None, "provider callback")
        missing = ProviderReceipt(*base, effective_prompt="Source", uploaded_inputs=upload)
        with self.assertRaises(ExecutionConflict):
            self.ledger.record_receipt(missing, ticket, workspace_verifier=lambda *args: True)
        mismatched = ProviderReceipt(*base, effective_prompt="Source", uploaded_inputs=upload,
                                     observed_workspace_id="ws-other", workspace_evidence_ref="mock:status")
        with self.assertRaises(ExecutionConflict):
            self.ledger.record_receipt(mismatched, ticket, workspace_verifier=lambda *args: True)
        observed = ProviderReceipt(*base, effective_prompt="Source", uploaded_inputs=upload,
                                   observed_workspace_id="ws-1", workspace_evidence_ref="mock:status")
        with self.assertRaises(ExecutionConflict):
            self.ledger.record_receipt(observed, ticket)
        with self.assertRaises(ExecutionConflict):
            self.ledger.record_receipt(observed, ticket, workspace_verifier=lambda *args: False)
        self.ledger.record_receipt(observed, ticket,
                                   workspace_verifier=lambda receipt, ticket: True)  # test-only
        self.assertEqual(self.ledger.receipts(), (observed,))
        legacy = asdict(observed)
        legacy.pop("observed_workspace_id")
        legacy.pop("workspace_evidence_ref")
        payload = json.dumps(legacy, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self.ledger._connect() as db:
            db.execute("UPDATE receipts SET payload=?, digest=? WHERE claim_id=?",
                       (payload, hashlib.sha256(payload.encode()).hexdigest(), claim.id))
        with self.assertRaises(ExecutionConflict):
            self.ledger.receipts()

    def test_receipt_does_not_change_canonical_or_approve_output(self):
        ticket = self.ticket()
        self.approve_spend(ticket)
        request = self.fixture.request(ticket_id=ticket.id)
        claim = self.ledger.prepare(self.engine, ticket, request, "tester",
                                    preflight_verifier=self._mock_preflight,
                                    approval_verifier=self._mock_approval)
        before_project = self.engine.project_path.read_bytes()
        before_events = self.engine.events_path.read_bytes()
        self.submit(claim, ticket, request)
        self.ledger.transition(claim.id, "SUBMITTED", provider_task_id="task-1")
        asset_hash = self.fixture.doc["assets"][0]["sha256"]
        upload = (ProviderUpload("input", asset_hash, asset_hash, "upload-1"),)
        wrong_task = ProviderReceipt(ticket.id, "candidate-a", claim.id, "example", "ws-1", "RAW_CLI",
                                     "SUBMITTED", "run-1", "task-2", 2, None, (),
                                     datetime.now(timezone.utc).isoformat(), None, "provider callback",
                                     effective_prompt="Source", uploaded_inputs=upload,
                                     observed_workspace_id="ws-1", workspace_evidence_ref="mock:status")
        with self.assertRaises(ExecutionConflict):
            self.ledger.record_receipt(wrong_task, ticket, workspace_verifier=lambda *args: True)
        receipt = ProviderReceipt(ticket.id, "candidate-a", claim.id, "example", "ws-1", "RAW_CLI",
                                  "SUBMITTED", "run-1", "task-1", 2, None, (),
                                  datetime.now(timezone.utc).isoformat(), None, "provider callback",
                                  effective_prompt="Source", uploaded_inputs=upload,
                                  observed_workspace_id="ws-1", workspace_evidence_ref="mock:status")
        self.ledger.record_receipt(receipt, ticket, workspace_verifier=lambda *args: True)
        self.assertEqual(self.ledger.receipts(), (receipt,))
        with self.assertRaises(ExecutionConflict):
            self.ledger.record_receipt(receipt, ticket, workspace_verifier=lambda *args: True)
        self.assertEqual(self.engine.project_path.read_bytes(), before_project)
        self.assertEqual(self.engine.events_path.read_bytes(), before_events)
        self.assertEqual(len(self.engine.read().document["assets"]), 1)

    def test_manual_web_import_preserves_unknown(self):
        record = manual_web_import(provider="example", workspace_id="ws-1", shot_id="s",
                                   candidate_id="c", actor="operator")
        self.assertEqual(record["kind"], "EXTERNAL_EXECUTION")
        self.assertEqual(record["execution_surface"], "WEB_MANUAL")
        self.assertEqual(record["provider_task_id"], "UNKNOWN")
        self.assertEqual(record["settings"], "UNKNOWN")

    def test_imported_web_work_blocks_same_candidate_automation(self):
        ticket = self.ticket()
        self.approve_spend(ticket)
        record = manual_web_import(provider="example", workspace_id="ws-1", shot_id="shot-a",
                                   candidate_id="candidate-a", actor="operator")
        claim = self.ledger.import_manual_web(self.engine, record)
        self.assertEqual(claim.submission_state, "UNKNOWN_SUBMISSION")
        with self.assertRaises(ExecutionConflict):
            self.ledger.prepare(self.engine, ticket, self.fixture.request(ticket_id=ticket.id), "tester",
                                preflight_verifier=self._mock_preflight,
                                approval_verifier=self._mock_approval)

    def test_ledger_cannot_be_redirected_to_evade_claim(self):
        ticket = self.ticket()
        self.approve_spend(ticket)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as other:
            foreign = ExecutionLedger(Path(other))
            with self.assertRaises(ExecutionConflict):
                foreign.prepare(self.engine, ticket, self.fixture.request(ticket_id=ticket.id), "tester",
                                preflight_verifier=self._mock_preflight,
                                approval_verifier=self._mock_approval)

    def test_submission_rechecks_action_and_capability_freshness(self):
        ticket = self.ticket()
        self.approve_spend(ticket)
        batch = self.fixture.request(action="BATCH_GENERATION", ticket_id=ticket.id)
        claim = self.ledger.prepare(self.engine, ticket, batch, "tester",
                                    preflight_verifier=self._mock_preflight,
                                    approval_verifier=self._mock_approval)
        with self.assertRaises(ExecutionConflict):
            self.submit(claim, ticket, self.fixture.request(ticket_id=ticket.id))
        now = datetime.now(timezone.utc)
        expired = TechnicalCapabilitySnapshot("tech-1", "example", "mock-backend",
            (now - timedelta(hours=2)).isoformat(), (now - timedelta(hours=1)).isoformat(),
            ("IMAGE_TO_VIDEO",))
        with self.assertRaises(ExecutionConflict):
            self.submit(claim, ticket, batch, technical=expired)
        self.submit(claim, ticket, batch)

    def test_provider_idempotency_and_trace_must_be_proven_and_durable(self):
        technical = TechnicalCapabilitySnapshot("tech-verified", "example", "mock-backend",
            self.technical.captured_at, self.technical.expires_at, ("IMAGE_TO_VIDEO",),
            idempotent_operations=("IMAGE_TO_VIDEO",), trace_operations=("IMAGE_TO_VIDEO",),
            native_evidence_ref="evidence/mock-help.txt",
            operation_profiles=self.technical.operation_profiles)
        runtime = ProviderRuntimeSnapshot("run-verified", "example", "mock-backend", "RAW_CLI",
            "ws-1", self.runtime.captured_at, "tech-verified", "ent-1")
        ticket = self.ticket(technical=technical, runtime=runtime)
        self.approve_spend(ticket)
        request = self.fixture.request(ticket_id=ticket.id)
        claim = self.ledger.prepare(self.engine, ticket, request, "tester",
                                    preflight_verifier=self._mock_preflight,
                                    approval_verifier=self._mock_approval)
        with self.assertRaises(ExecutionConflict):
            self.submit(claim, ticket, request, technical=technical, runtime=runtime)
        with self.assertRaises(ExecutionConflict):
            self.submit(claim, ticket, request, technical=technical, runtime=runtime,
                        provider_idempotency_key="", provider_trace_id="trace-1")
        self.ledger.transition(claim.id, "SUBMITTING", request_fingerprint="request-hash",
            local_key="local-key", provider_idempotency_key="provider-key-1", provider_trace_id="trace-1",
            engine=self.engine, ticket=ticket, request=request, technical=technical,
            entitlement=self.entitlement, runtime=runtime,
            preflight_verifier=self._mock_preflight, approval_verifier=self._mock_approval)
        record = ExecutionLedger(self.fixture.root).submission_record(claim.id)
        self.assertEqual((record["provider_idempotency_key"], record["provider_trace_id"]),
                         ("provider-key-1", "trace-1"))
        with self.assertRaises(ExecutionConflict):
            self.ledger.transition(claim.id, "UNKNOWN_SUBMISSION", provider_idempotency_key="new-key")

    def test_receipt_binds_actual_derivative_upload(self):
        source_hash = self.fixture.doc["assets"][0]["sha256"]
        derivative_hash = hashlib.sha256(b"ready").hexdigest()
        derivative = {"source_asset_id": "input", "source_sha256": source_hash,
                      "derivative_id": "ready-1", "derivative_sha256": derivative_hash,
                      "transform_fingerprint": hashlib.sha256(b"resize:v1").hexdigest()}
        ticket = self.ticket(derivative_inputs=(derivative,))
        self.approve_spend(ticket)
        request = self.fixture.request(ticket_id=ticket.id)
        claim = self.ledger.prepare(self.engine, ticket, request, "tester",
                                    preflight_verifier=self._mock_preflight,
                                    approval_verifier=self._mock_approval)
        self.submit(claim, ticket, request)
        self.ledger.transition(claim.id, "SUBMITTED", provider_task_id="task-1")
        def receipt(upload):
            return ProviderReceipt(ticket.id, "candidate-a", claim.id, "example", "ws-1", "RAW_CLI",
                "SUBMITTED", "run-1", "task-1", 2, None, (),
                datetime.now(timezone.utc).isoformat(), None, "provider callback",
                effective_prompt="Source", uploaded_inputs=(upload,),
                observed_workspace_id="ws-1", workspace_evidence_ref="mock:status")
        with self.assertRaises(ExecutionConflict):
            self.ledger.record_receipt(receipt(ProviderUpload("input", source_hash, source_hash,
                                                               "upload-1", "ready-1")), ticket,
                                       workspace_verifier=lambda *args: True)
        good = receipt(ProviderUpload("input", source_hash, derivative_hash, "upload-1", "ready-1"))
        self.ledger.record_receipt(good, ticket, workspace_verifier=lambda *args: True)
        self.assertEqual(self.ledger.receipts(), (good,))

    def test_provider_key_is_unique_across_candidates(self):
        technical = TechnicalCapabilitySnapshot("tech-verified", "example", "mock-backend",
            self.technical.captured_at, self.technical.expires_at, ("IMAGE_TO_VIDEO",),
            idempotent_operations=("IMAGE_TO_VIDEO",), native_evidence_ref="evidence/mock-help.txt",
            operation_profiles=self.technical.operation_profiles)
        runtime = ProviderRuntimeSnapshot("run-verified", "example", "mock-backend", "RAW_CLI",
            "ws-1", self.runtime.captured_at, "tech-verified", "ent-1")
        first = self.ticket(technical=technical, runtime=runtime)
        self.approve_spend(first)
        first_request = self.fixture.request(ticket_id=first.id)
        first_claim = self.ledger.prepare(self.engine, first, first_request, "tester",
            preflight_verifier=self._mock_preflight, approval_verifier=self._mock_approval)
        self.submit(first_claim, first, first_request, technical=technical, runtime=runtime,
                    provider_idempotency_key="provider-key-1")
        second = self.ticket(candidate_id="candidate-b", technical=technical, runtime=runtime)
        self.approve_spend(second, candidate_id="candidate-b")
        second_request = self.fixture.request(ticket_id=second.id, candidate_id="candidate-b")
        second_claim = self.ledger.prepare(self.engine, second, second_request, "tester",
            preflight_verifier=self._mock_preflight, approval_verifier=self._mock_approval)
        with self.assertRaises(ExecutionConflict):
            self.submit(second_claim, second, second_request, technical=technical, runtime=runtime,
                        provider_idempotency_key="provider-key-1")
        self.assertEqual(self.ledger.submission_record(second_claim.id)["state"], "PREPARED")
        self.submit(second_claim, second, second_request, technical=technical, runtime=runtime,
                    provider_idempotency_key="provider-key-2")

    def test_snapshot_content_hash_blocks_same_id_changed_capability(self):
        ticket = self.ticket()
        self.approve_spend(ticket)
        request = self.fixture.request(ticket_id=ticket.id)
        claim = self.ledger.prepare(self.engine, ticket, request, "tester",
            preflight_verifier=self._mock_preflight, approval_verifier=self._mock_approval)
        altered = TechnicalCapabilitySnapshot("tech-1", "example", "mock-backend",
            self.technical.captured_at, self.technical.expires_at, ("IMAGE_TO_VIDEO",),
            features=("changed",), operation_profiles=self.technical.operation_profiles)
        with self.assertRaises(ExecutionConflict):
            self.submit(claim, ticket, request, technical=altered)


if __name__ == "__main__":
    unittest.main()
