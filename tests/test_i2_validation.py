import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aivideo.gates import evaluate_gates
from aivideo.guards import ActionRequest, guard_action
from aivideo.state_engine import StateConflict, StateEngine, TransactionRequest
from aivideo.validators import fingerprint, validate_project


class I2Tests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "media").mkdir()
        (self.root / "media" / "input.bin").write_bytes(b"known approved media")
        digest = hashlib.sha256(b"known approved media").hexdigest()
        asset = {"id": "input", "lifecycle": "APPROVED", "criticality": "REQUIRED_FOR_STORYBOARD",
                 "origin": "SOURCE", "sha256": digest, "provenance": "operator import",
                 "locators": [{"type": "LOCAL", "path": "media/input.bin", "availability": "AVAILABLE"}],
                 "external_processing": {"policy": "ALLOWED", "allowed_providers": ["example"]}}
        self.doc = {"schema_version": "2.0", "template_version": "2.0", "project_id": "generic-test",
                    "state_revision": 0, "mode": "NEW_PRODUCTION", "interaction_mode": "PRODUCTION",
                    "next_action": "Review next gate", "assets": [asset],
                    "shots": [{"id": "shot-a", "readiness": "REQUIRED", "intent": "A generic scene",
                               "duration_frames": 24, "production_method": "AI_VIDEO",
                               "generation_ready": True, "input_asset_ids": ["input"]}],
                    "dependencies": [], "brief": {"intent": "A short clip"},
                    "storyboard": {"version": "one"}, "animatic": {"version": "one"},
                    "generation_plan": {"budget_remaining": 10, "batch_size": 1},
                    "final_qc": {"technical": "PASS", "creative": "APPROVED"}, "evidence": []}
        for kind, subject in (("BRIEF_LOCK", "project:brief"),
                              ("ASSET_APPROVAL", "asset:input"),
                              ("STORYBOARD_APPROVAL", "project:storyboard"),
                              ("ANIMATIC_APPROVAL", "project:animatic"),
                              ("GENERATION_READINESS", "shot:shot-a"),
                              ("BATCH_APPROVAL", "project:generation_plan"),
                              ("FINAL_QC_APPROVAL", "project:final_qc")):
            self.doc["evidence"].append(self.evidence(kind, subject))
        self.write_initial()

    def evidence(self, kind, subject, **extra):
        area, ident = subject.split(":", 1)
        value = self.doc[ident] if area == "project" else next(
            x for x in self.doc["assets" if area == "asset" else "shots"] if x["id"] == ident)
        bindings = {"STORYBOARD_APPROVAL": ("shot:shot-a",),
                    "ANIMATIC_APPROVAL": ("project:storyboard",),
                    "GENERATION_READINESS": ("asset:input",),
                    "BATCH_APPROVAL": ("shot:shot-a",)}.get(kind, ())
        bound = {}
        for ref in bindings:
            ref_area, ref_id = ref.split(":", 1)
            target = self.doc[ref_id] if ref_area == "project" else next(
                x for x in self.doc["assets" if ref_area == "asset" else "shots"] if x["id"] == ref_id)
            bound[ref] = fingerprint(target)
        return {"id": f"e-{kind}-{len(self.doc['evidence'])}", "kind": kind,
                "subject": subject, "subject_hash": fingerprint(value), "status": "APPROVED",
                "actor_type": "MACHINE" if kind == "GENERATION_READINESS" else "HUMAN",
                "state_revision": self.doc["state_revision"], "dependency_hashes": bound, **extra}

    def write_initial(self):
        (self.root / "project.yaml").write_text(json.dumps(self.doc), encoding="utf-8")
        (self.root / "events.jsonl").write_bytes(b"")
        self.engine = StateEngine(self.root)

    def commit(self, change):
        before = self.engine.read()
        after = copy.deepcopy(before.document)
        change(after)
        after["state_revision"] = before.state_revision + 1
        self.engine.begin_transaction(TransactionRequest(before.state_revision, before.project_hash,
                                                         f"tx-{after['state_revision']}", "tester", "EDIT"), after)
        self.doc = after

    def request(self, action="PAID_GENERATION", **overrides):
        snapshot = self.engine.read()
        values = dict(action=action, action_id="action-a", expected_state_revision=snapshot.state_revision,
                      expected_project_hash=snapshot.project_hash, provider="example", workspace_id="ws-1",
                      ticket_id="ticket-a", candidate_id="candidate-a", shot_id="shot-a",
                      asset_ids=("input",), quoted_cost=2)
        values.update(overrides)
        return ActionRequest(**values)

    @staticmethod
    def trusted_preflight(request, snapshot, now):
        return {"provider": request.provider, "workspace_id": request.workspace_id,
                "state_revision": snapshot.state_revision, "project_hash": snapshot.project_hash,
                "auth_ready": True, "workspace_matches": True, "entitlement_ready": True,
                "slots_ready": True, "candidate_limit_ready": True, "capability_ready": True,
                "workspace_binding_proven": True,
                "workspace_binding_workspace_id": request.workspace_id,
                "workspace_binding_method": "EXPLICIT_REQUEST",
                "workspace_binding_evidence_ref": "mock:request-schema",
                "provider_cost_cap_enforced": True, "provider_cost_cap": request.quoted_cost,
                "provider_cost_cap_source": "PROVIDER_ENFORCED",
                "provider_cost_cap_evidence_ref": "mock:capability",
                "checked_at": now.isoformat(), "submission_state": "CLEAR"}

    def guard(self, request, **kwargs):
        return guard_action(self.engine, request, preflight_verifier=self.trusted_preflight,
                            approval_verifier=lambda *args: True, **kwargs)

    def test_each_gate_passes_with_minimum_evidence(self):
        self.assertTrue(validate_project(self.engine).ok)
        self.assertEqual({gate: report["status"] for gate, report in evaluate_gates(self.engine, approval_verifier=lambda *args: True).items()},
                         {f"G{i}": "PASS" for i in range(7)})

    def test_each_gate_missing_mandatory_prerequisite(self):
        cases = (("G0", "brief", "MISSING_BRIEF"),
                 ("G1", "asset_approval", "MISSING_EVIDENCE"),
                 ("G2", "storyboard", "MISSING_STORYBOARD"),
                 ("G3", "animatic", "MISSING_ANIMATIC"),
                 ("G4", "generation_ready", "SHOT_NOT_GENERATION_READY"),
                 ("G5", "generation_plan", "MISSING_GENERATION_PLAN"),
                 ("G6", "final_qc", "MISSING_FINAL_QC"))
        for gate, field, code in cases:
            with self.subTest(gate=gate):
                doc = copy.deepcopy(self.doc)
                if field == "asset_approval":
                    doc["evidence"] = [e for e in doc["evidence"] if e["kind"] != "ASSET_APPROVAL"]
                elif field == "generation_ready":
                    doc["shots"][0]["generation_ready"] = False
                else:
                    doc.pop(field)
                (self.root / "project.yaml").write_text(json.dumps(doc), encoding="utf-8")
                report = evaluate_gates(self.engine, approval_verifier=lambda *args: True)[gate]
                self.assertNotEqual(report["status"], "PASS")
                self.assertIn(code, [f["code"] for f in report["blocking_findings"]])
                self.write_initial()

    def test_paid_generation_requires_exact_human_spend_approval(self):
        self.assertEqual(self.guard(self.request())["decision"], "DENY")
        self.commit(lambda doc: doc["evidence"].append({**self.evidence("SPEND_APPROVAL", "project:generation_plan",
                            action_id="action-a", provider="example", ticket_id="ticket-a",
                            candidate_id="candidate-a", shot_id="shot-a", workspace_id="ws-1", max_cost=2),
                            "state_revision": 1}))
        self.assertEqual(guard_action(self.engine, self.request())["decision"], "DENY")
        self.assertEqual(self.guard(self.request())["decision"], "ALLOW")
        for change in ({"ticket_id": "other"}, {"candidate_id": "other"}, {"workspace_id": "other"},
                       {"quoted_cost": 3}, {"expected_project_hash": "0" * 64}):
            with self.subTest(change=change):
                self.assertEqual(self.guard(self.request(**change))["decision"], "DENY")
        self.assertEqual(guard_action(self.engine, self.request(),
            preflight_verifier=lambda *args: {"auth_ready": True},
            approval_verifier=lambda *args: True)["decision"], "DENY")

    def test_paid_preflight_requires_provable_workspace_and_provider_cost_cap(self):
        self.commit(lambda doc: doc["evidence"].append({**self.evidence(
            "SPEND_APPROVAL", "project:generation_plan", action_id="action-a",
            provider="example", ticket_id="ticket-a", candidate_id="candidate-a",
            shot_id="shot-a", workspace_id="ws-1", max_cost=2),
            "state_revision": 1}))

        def inspect(**changes):
            def preflight(request, snapshot, now):
                return {**self.trusted_preflight(request, snapshot, now), **changes}
            return guard_action(self.engine, self.request(), preflight_verifier=preflight,
                                approval_verifier=lambda *args: True)

        for changes, code in (
            ({"workspace_binding_proven": False}, "WORKSPACE_BINDING"),
            ({"workspace_binding_workspace_id": "ws-other"}, "WORKSPACE_BINDING"),
            ({"workspace_binding_method": "ACTIVE_WORKSPACE_READ"}, "WORKSPACE_BINDING"),
            ({"workspace_binding_evidence_ref": None}, "WORKSPACE_BINDING"),
            ({"provider_cost_cap_enforced": False}, "COST_CAP"),
            ({"provider_cost_cap_source": "WEB_UI"}, "COST_CAP"),
            ({"provider_cost_cap_evidence_ref": None}, "COST_CAP"),
            ({"provider_cost_cap": None}, "COST_CAP"),
            ({"provider_cost_cap": 3}, "COST_CAP"),
        ):
            with self.subTest(changes=changes):
                result = inspect(**changes)
                self.assertEqual(result["decision"], "DENY")
                self.assertIn(code, {item["code"] for item in result["blocking_findings"]})

        def missing_claims(request, snapshot, now):
            result = self.trusted_preflight(request, snapshot, now)
            for key in ("workspace_binding_proven", "workspace_binding_workspace_id",
                        "workspace_binding_method", "workspace_binding_evidence_ref",
                        "provider_cost_cap_enforced", "provider_cost_cap",
                        "provider_cost_cap_source", "provider_cost_cap_evidence_ref"):
                result.pop(key)
            return result
        result = guard_action(self.engine, self.request(), preflight_verifier=missing_claims,
                              approval_verifier=lambda *args: True)
        self.assertEqual(result["decision"], "DENY")
        self.assertTrue({"WORKSPACE_BINDING", "COST_CAP"}.issubset(
            {item["code"] for item in result["blocking_findings"]}))

    def test_expired_or_machine_spend_approval_and_unknown_submission_deny(self):
        def add(doc):
            doc["evidence"].append({**self.evidence("SPEND_APPROVAL", "project:generation_plan",
                action_id="action-a", provider="example", ticket_id="ticket-a",
                candidate_id="candidate-a", shot_id="shot-a", workspace_id="ws-1", max_cost=2,
                expires_at="2000-01-01T00:00:00Z"), "state_revision": 1})
        self.commit(add)
        self.assertEqual(self.guard(self.request())["decision"], "DENY")
        self.commit(lambda doc: doc["evidence"].append({**self.evidence("SPEND_APPROVAL", "project:generation_plan",
            action_id="action-a", provider="example", ticket_id="ticket-a", candidate_id="candidate-a",
            shot_id="shot-a", workspace_id="ws-1", max_cost=2), "state_revision": 2,
            "actor_type": "MACHINE", "id": "machine-spend"}))
        self.assertEqual(self.guard(self.request())["decision"], "DENY")
        self.commit(lambda doc: doc["evidence"].append({**self.evidence("SPEND_APPROVAL", "project:generation_plan",
            action_id="action-a", provider="example", ticket_id="ticket-a", candidate_id="candidate-a",
            shot_id="shot-a", workspace_id="ws-1", max_cost=2), "state_revision": 3,
            "id": "human-spend"}))
        self.assertEqual(self.guard(self.request())["decision"], "ALLOW")
        def unknown(request, snapshot, now):
            return {**self.trusted_preflight(request, snapshot, now), "submission_state": "UNKNOWN_SUBMISSION"}
        self.assertEqual(guard_action(self.engine, self.request(), preflight_verifier=unknown,
                                      approval_verifier=lambda *args: True)["decision"], "DENY")

    def test_batch_and_replacement_need_separate_authorization(self):
        self.assertEqual(self.guard(self.request("BATCH_GENERATION"))["decision"], "DENY")
        self.assertEqual(self.guard(self.request("REPLACE_ASSET"))["decision"], "DENY")
        self.assertEqual(self.guard(self.request("DESTRUCTIVE_OPERATION"))["decision"], "DENY")
        self.commit(lambda doc: doc["evidence"].extend((
            {**self.evidence("REPLACEMENT_APPROVAL", "asset:input", action_id="action-a"),
             "state_revision": 1},
            {**self.evidence("DESTRUCTIVE_APPROVAL", "asset:input", action_id="action-a"),
             "state_revision": 1, "id": "destructive-approval"})))
        self.assertEqual(self.guard(self.request("REPLACE_ASSET"))["decision"], "ALLOW")
        self.assertEqual(self.guard(self.request("DESTRUCTIVE_OPERATION"))["decision"], "ALLOW")

    def test_selected_asset_replacement_needs_human_approval(self):
        asset = self.doc["assets"][0]
        asset["lifecycle"] = "REVIEWED"
        asset["criticality"] = "OPTIONAL"
        self.doc["selections"] = {"primary": "input"}
        self.doc["evidence"] = [item for item in self.doc["evidence"]
                                if item["kind"] not in {"ASSET_APPROVAL", "GENERATION_READINESS"}]
        self.write_initial()
        self.assertEqual(self.guard(self.request("REPLACE_ASSET"))["decision"], "DENY")
        self.doc["evidence"].append(self.evidence("REPLACEMENT_APPROVAL", "asset:input",
                                                  action_id="action-a"))
        self.write_initial()
        self.assertEqual(self.guard(self.request("REPLACE_ASSET"))["decision"], "ALLOW")

    def test_malformed_or_dangling_selection_fails_closed(self):
        self.doc["assets"][0]["lifecycle"] = "REVIEWED"
        self.doc["assets"][0]["criticality"] = "OPTIONAL"
        self.doc["evidence"] = [item for item in self.doc["evidence"]
                                if item["kind"] not in {"ASSET_APPROVAL", "GENERATION_READINESS"}]
        self.doc["selections"] = {"primary": {"asset_id": "input"}}
        self.write_initial()
        malformed = ActionRequest("REPLACE_ASSET", "replace", 0, "0" * 64, asset_ids=("input",))
        self.assertEqual(guard_action(self.engine, malformed)["decision"], "DENY")
        self.doc["selections"] = {"primary": "missing-asset"}
        self.write_initial()
        self.assertIn("SELECTION_TARGET", [f["code"] for f in validate_project(self.engine).findings])
        self.assertEqual(self.guard(self.request("REPLACE_ASSET"))["decision"], "DENY")
        self.doc["selections"] = {}
        self.doc["assets"][0]["selected"] = "true"
        self.write_initial()
        self.assertIn("ASSET_SELECTION", [f["code"] for f in validate_project(self.engine).findings])
        self.assertEqual(self.guard(self.request("REPLACE_ASSET"))["decision"], "DENY")

    def test_dependency_change_is_typed_and_reports_missing_propagation(self):
        self.commit(lambda doc: (doc["assets"].append({"id": "derived", "lifecycle": "REVIEWED",
            "criticality": "OPTIONAL"}), doc["dependencies"].append({"source": "asset:input",
            "target": "asset:derived", "impact": "APPEARANCE"})))
        before = self.engine.read()
        after = copy.deepcopy(before.document)
        after["state_revision"] += 1
        after["next_action"] = "Check timing impact"
        self.engine.begin_transaction(TransactionRequest(before.state_revision, before.project_hash,
            "typed-timing", "tester", "EDIT"), after,
            transition_metadata={"change": {"target": "asset:input", "dimensions": ["TIMING"]}})
        self.assertNotIn("MISSING_STALE_PROPAGATION", [f["code"] for f in validate_project(self.engine).findings])
        before = self.engine.read()
        after = copy.deepcopy(before.document)
        after["state_revision"] += 1
        after["next_action"] = "Check appearance impact"
        self.engine.begin_transaction(TransactionRequest(before.state_revision, before.project_hash,
            "typed-appearance", "tester", "EDIT"), after,
            transition_metadata={"change": {"target": "asset:input", "dimensions": ["APPEARANCE"]}})
        self.assertIn("MISSING_STALE_PROPAGATION", [f["code"] for f in validate_project(self.engine).findings])

    def test_state_engine_requires_change_declaration_and_stale_target(self):
        self.commit(lambda doc: (doc["assets"].append({"id": "derived", "lifecycle": "REVIEWED",
            "criticality": "OPTIONAL"}), doc["dependencies"].append({"source": "asset:input",
            "target": "asset:derived", "impact": "APPEARANCE"})))
        before = self.engine.read()
        after = copy.deepcopy(before.document)
        after["state_revision"] += 1
        after["assets"][0]["description"] = "new appearance"
        request = TransactionRequest(before.state_revision, before.project_hash, "upstream-edit", "tester", "EDIT")
        with self.assertRaises(StateConflict):
            self.engine.begin_transaction(request, after)
        declaration = {"change": {"target": "asset:input", "dimensions": ["APPEARANCE"]}}
        with self.assertRaises(StateConflict):
            self.engine.begin_transaction(request, after, transition_metadata=declaration)
        after["assets"][1]["lifecycle"] = "STALE"
        self.engine.begin_transaction(request, after, transition_metadata=declaration)
        self.assertNotIn("MISSING_STALE_PROPAGATION", [f["code"] for f in validate_project(self.engine).findings])
        before = self.engine.read()
        restored = copy.deepcopy(before.document)
        restored["state_revision"] += 1
        restored["assets"][1]["lifecycle"] = "REVIEWED"
        restored["assets"][1]["remediated_after_revision"] = 999
        with self.assertRaises(StateConflict):
            self.engine.begin_transaction(TransactionRequest(before.state_revision, before.project_hash,
                "fake-remediation", "tester", "EDIT"), restored)

    def test_malformed_change_metadata_and_optional_shot_are_safe(self):
        self.commit(lambda doc: (doc["assets"].append({"id": "optional-input", "lifecycle": "EXPECTED",
            "criticality": "OPTIONAL"}), doc["shots"].append({"id": "optional-shot", "readiness": "OPTIONAL",
            "input_asset_ids": ["optional-input"]})))
        self.assertEqual(evaluate_gates(self.engine, approval_verifier=lambda *args: True)["G4"]["status"], "PASS")
        before = self.engine.read()
        after = copy.deepcopy(before.document)
        after["state_revision"] += 1
        self.engine.begin_transaction(TransactionRequest(before.state_revision, before.project_hash,
            "malformed-metadata", "tester", "EDIT"), after, transition_metadata={"change": None})
        self.assertIn("CHANGE_METADATA", [f["code"] for f in validate_project(self.engine).findings])
        self.assertEqual(guard_action(self.engine, self.request())["decision"], "DENY")

    def test_edge_only_change_invalidates_existing_target(self):
        before = self.engine.read()
        after = copy.deepcopy(before.document)
        after["state_revision"] += 1
        edge = {"source": "asset:input", "target": "shot:shot-a", "impact": "APPEARANCE"}
        after["dependencies"].append(edge)
        request = TransactionRequest(before.state_revision, before.project_hash, "edge-add", "tester", "EDIT")
        with self.assertRaises(StateConflict):
            self.engine.begin_transaction(request, after)
        audit = {"dependency_changes": [{**edge, "operation": "ADDED"}]}
        with self.assertRaises(StateConflict):
            self.engine.begin_transaction(request, after, transition_metadata=audit)
        after["shots"][0]["status"] = "STALE"
        self.engine.begin_transaction(request, after, transition_metadata=audit)
        self.assertNotEqual(evaluate_gates(self.engine, approval_verifier=lambda *args: True)["G2"]["status"], "PASS")

    def test_editorial_shot_does_not_require_generation_gates(self):
        self.doc["shots"][0]["production_method"] = "NO_NEW_MEDIA"
        self.doc["shots"][0]["generation_ready"] = False
        self.doc["shots"][0]["input_asset_ids"] = []
        self.doc["evidence"] = [item for item in self.doc["evidence"]
                                if item["kind"] != "GENERATION_READINESS"]
        storyboard = next(item for item in self.doc["evidence"]
                          if item["kind"] == "STORYBOARD_APPROVAL")
        storyboard["dependency_hashes"]["shot:shot-a"] = fingerprint(self.doc["shots"][0])
        batch = next(item for item in self.doc["evidence"]
                     if item["kind"] == "BATCH_APPROVAL")
        batch["dependency_hashes"]["shot:shot-a"] = fingerprint(self.doc["shots"][0])
        self.write_initial()
        report = evaluate_gates(self.engine, approval_verifier=lambda *args: True)
        self.assertEqual(report["G4"]["status"], "NOT_APPLICABLE")
        self.assertEqual(report["G5"]["status"], "NOT_APPLICABLE")
        self.assertEqual(report["G6"]["status"], "PASS")
        self.assertEqual(self.guard(self.request())["decision"], "DENY")

    def test_paid_guard_denies_editorial_and_optional_shots_in_mixed_project(self):
        editorial = {"id": "edit-shot", "readiness": "REQUIRED", "intent": "Editorial cut",
                     "duration_frames": 24, "production_method": "NO_NEW_MEDIA", "input_asset_ids": []}
        optional = {"id": "optional-shot", "readiness": "OPTIONAL", "intent": "Optional idea",
                    "duration_frames": 24, "production_method": "AI_VIDEO", "input_asset_ids": []}
        self.doc["shots"].extend((editorial, optional))
        for kind in ("STORYBOARD_APPROVAL", "BATCH_APPROVAL"):
            record = next(item for item in self.doc["evidence"] if item["kind"] == kind)
            record["dependency_hashes"]["shot:edit-shot"] = fingerprint(editorial)
        for shot, action, ticket in ((editorial, "edit-action", "edit-ticket"),
                                     (optional, "optional-action", "optional-ticket")):
            self.doc["evidence"].append(self.evidence("SPEND_APPROVAL", "project:generation_plan",
                action_id=action, provider="example", ticket_id=ticket, candidate_id="candidate-a",
                shot_id=shot["id"], workspace_id="ws-1", max_cost=2))
        self.write_initial()
        self.assertEqual(evaluate_gates(self.engine, approval_verifier=lambda *args: True)["G4"]["status"], "PASS")
        for shot, action, ticket in ((editorial, "edit-action", "edit-ticket"),
                                     (optional, "optional-action", "optional-ticket")):
            with self.subTest(shot=shot["id"]):
                result = self.guard(self.request(action_id=action, ticket_id=ticket,
                                                shot_id=shot["id"], asset_ids=()))
                self.assertEqual(result["decision"], "DENY")
                self.assertIn("SHOT_NOT_GENERATIVE", [f["code"] for f in result["blocking_findings"]])

    def test_pending_journal_blocks_read_only_evaluation(self):
        (self.root / ".pending-transaction.json").write_text("{}", encoding="utf-8")
        self.assertFalse(validate_project(self.engine).ok)
        self.assertEqual(evaluate_gates(self.engine, approval_verifier=lambda *args: True)["G0"]["status"], "BLOCKED")
        self.assertEqual(guard_action(self.engine, self.request())["decision"], "DENY")
        self.assertTrue((self.root / ".pending-transaction.json").exists())

    def test_upload_policy_allowed_review_required_forbidden(self):
        self.assertEqual(self.guard(self.request("EXTERNAL_UPLOAD"))["decision"], "ALLOW")
        self.commit(lambda doc: doc["assets"][0]["external_processing"].update(policy="REVIEW_REQUIRED"))
        self.assertEqual(self.guard(self.request("EXTERNAL_UPLOAD"))["decision"], "DENY")
        self.commit(lambda doc: doc["evidence"].append({**self.evidence("EXTERNAL_PROCESSING_APPROVAL", "asset:input",
                                    action_id="action-a", provider="example", workspace_id="ws-1"), "state_revision": 2}))
        self.assertEqual(self.guard(self.request("EXTERNAL_UPLOAD"))["decision"], "DENY")
        # A changed approved asset needs renewed asset approval; no silent reapproval.
        self.commit(lambda doc: doc["evidence"].extend((
            {**self.evidence("ASSET_APPROVAL", "asset:input"), "state_revision": 3},
            {**self.evidence("GENERATION_READINESS", "shot:shot-a"), "state_revision": 3,
             "id": "e-GENERATION_READINESS-renewed"})))
        self.assertEqual(self.guard(self.request("EXTERNAL_UPLOAD"))["decision"], "ALLOW")
        self.commit(lambda doc: doc["assets"][0]["external_processing"].update(policy="FORBIDDEN"))
        self.assertEqual(self.guard(self.request("EXTERNAL_UPLOAD"))["decision"], "DENY")

    def test_stale_evidence_hash_and_derived_report_are_non_authoritative(self):
        before = self.engine.read()
        gates = evaluate_gates(self.engine, approval_verifier=lambda *args: True)
        (self.root / "STATUS.md").write_text("All gates passed", encoding="utf-8")
        (self.root / "STATUS.md").write_text("All gates failed", encoding="utf-8")
        self.assertEqual(self.engine.read().project_hash, before.project_hash)
        self.assertEqual(evaluate_gates(self.engine, approval_verifier=lambda *args: True), gates)
        self.commit(lambda doc: doc["brief"].update(intent="Changed intent"))
        self.assertFalse(validate_project(self.engine).ok)
        self.assertNotEqual(evaluate_gates(self.engine, approval_verifier=lambda *args: True)["G0"]["status"], "PASS")

    def test_materialization_hash_and_read_only_evaluators(self):
        before = self.engine.project_path.read_bytes()
        events = self.engine.events_path.read_bytes()
        validate_project(self.engine)
        evaluate_gates(self.engine, approval_verifier=lambda *args: True)
        guard_action(self.engine, self.request())
        self.assertEqual(self.engine.project_path.read_bytes(), before)
        self.assertEqual(self.engine.events_path.read_bytes(), events)
        (self.root / "media" / "input.bin").write_bytes(b"tampered")
        self.assertIn("ASSET_HASH_MISMATCH", [f["code"] for f in validate_project(self.engine).findings])


if __name__ == "__main__":
    unittest.main()
