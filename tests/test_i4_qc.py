"""Offline I4 QC contract tests; no provider or media probe is invoked."""

from dataclasses import asdict
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import test_i2_validation as i2_fixture
import test_i3_execution as i3_fixture
from aivideo.gates import evaluate_gates
from aivideo.qc import (QCBinding, DimensionResult, HumanReview, applicable_dimensions, binding_from_ticket,
                        check_delivery_assets, check_exact_text, check_file_metadata, check_handle, check_interactions,
                        check_locked_properties, evaluate_qc, evaluate_stop_loss, failure,
                        record_human_override)
from aivideo.tickets import GenerationTicket
from aivideo.validators import fingerprint
import hashlib


class QCTests(unittest.TestCase):
    def setUp(self):
        self.shot = {"id": "generic-shot", "constraints": {}}
        self.binding = QCBinding("generic-project", 2, "a" * 64, "generic-shot", "candidate-1",
                                 shot_hash=fingerprint(self.shot), strategy_id="strategy-a")

    def report(self, layer="Q1", profile="REAL_UI", results=None, **kwargs):
        shot = kwargs.pop("shot", self.shot if layer == "Q1" else None)
        binding = replace(self.binding, shot_hash=fingerprint(shot)) if layer == "Q1" else self.binding
        if layer == "Q2" or kwargs.get("conditional_justification"):
            reviewed = tuple(name for name, result in (results or {}).items()
                             if result.authority == "HUMAN" and result.status in {"PASS", "FAIL"})
            if reviewed:
                kwargs.setdefault("human_review", HumanReview("reviewer", "review-note:1",
                                  "2026-09-24T10:00:00+08:00", reviewed))
                kwargs.setdefault("human_verifier", lambda review, subject: True)  # test-only verifier
        return evaluate_qc(binding, layer, profile, results or {}, shot=shot, **kwargs)

    def pass_results(self, layer, profile, *, authority="HUMAN"):
        return {name: DimensionResult("PASS", authority, "reviewed")
                for name in applicable_dimensions(layer, profile)}

    def test_q0_metadata_and_dimension_statuses(self):
        metadata = {"exists": True, "readable": True, "codec": "h264", "fps": 24,
                    "frame_count": 120, "duration": 5, "resolution": "1920x1080",
                    "audio_presence": False, "container": "mp4", "color_metadata": "bt709"}
        results = check_file_metadata(metadata, {"codec": "prores", "fps": 24,
                                               "resolution": "1920x1080"}, origin="SOURCE")
        self.assertEqual(results["codec"].status, "FAIL")
        self.assertEqual(results["codec"].owner, "SOURCE")
        self.assertEqual(results["fps"].status, "PASS")
        self.assertEqual(results["duration"].status, "NOT_APPLICABLE")
        self.assertEqual(self.report("Q0", "REAL_UI", results).overall, "FAIL")
        missing = check_file_metadata({"exists": False, "readable": False}, origin="SOURCE")
        self.assertEqual(missing["exists"].severity, "CRITICAL")
        self.assertEqual(missing["codec"].status, "NOT_APPLICABLE")
        self.assertEqual(check_file_metadata({"codec": "bad"}, {"codec": "good"},
                                             origin="GENERATION")["codec"].owner, "GENERATION")
        self.assertEqual(check_file_metadata({"codec": "bad"}, {"codec": "good"},
                                             origin="POST")["codec"].owner, "POST")

    def test_profile_applicability_and_canonical_constraints(self):
        self.assertIn("identity", applicable_dimensions("Q1", "CHARACTER_LOCKED_LOW_MOTION"))
        self.assertNotIn("identity", applicable_dimensions("Q1", "REAL_UI"))
        shot = {"id": "generic-shot", "constraints": {"must_preserve": ["wardrobe"], "exact_text": "A",
                                "interaction": [{"subject": "hand", "action": "CONTACT", "object": "sample_object"}]}}
        names = applicable_dimensions("Q1", "REAL_UI", shot)
        self.assertTrue({"locked_properties", "exact_text", "interaction"}.issubset(names))
        report = self.report(shot=shot)
        self.assertEqual(dict(report.dimensions)["locked_properties"].status, "NOT_REVIEWED")
        self.assertEqual(dict(report.dimensions)["identity"].status, "NOT_APPLICABLE")
        self.assertEqual(report.overall, "NOT_REVIEWED")
        self.assertEqual(self.report("Q3", "REAL_UI").overall, "NOT_APPLICABLE")
        with self.assertRaises(ValueError):
            self.report(shot=shot, results={"locked_properties": DimensionResult("NOT_APPLICABLE")})
        with self.assertRaises(ValueError):
            evaluate_qc(self.binding, "Q1", "REAL_UI", {})  # cannot omit canonical shot

    def test_q1_exact_text_interaction_locked_properties_and_handles(self):
        self.assertEqual(check_exact_text("ABC", "ABＣ", origin="GENERATION").status, "FAIL")
        self.assertEqual(check_exact_text("ABC", "ABC", origin="GENERATION").status, "PASS")
        self.assertEqual(check_exact_text("ABC", "bad", origin="POST", role="OVERLAY").owner, "POST")
        relation = [{"subject": "hand", "action": "CONTACT", "object": "sample_object"}]
        self.assertEqual(check_interactions(relation, []).status, "FAIL")
        self.assertEqual(check_interactions(relation, relation).status, "PASS")
        self.assertEqual(check_locked_properties(["wardrobe"], {"wardrobe": "blue"},
                                                 {"wardrobe": "red"}, origin="GENERATION").severity, "CRITICAL")
        self.assertEqual(check_locked_properties(["wardrobe"], {"wardrobe": "blue"},
                                                 {}, origin="GENERATION").status, "NOT_REVIEWED")
        self.assertEqual(check_locked_properties(["wardrobe"], {"wardrobe": "blue"},
                                                 {"wardrobe": "red"}, origin="POST").owner, "POST")
        self.assertEqual(check_handle(False, position="start").owner, "GENERATION")
        self.assertEqual(check_handle(False, position="end", post_fixable=True).owner, "POST")
        self.assertEqual(check_handle(True, position="end").status, "PASS")

    def test_failure_ownership_and_action_are_structured(self):
        cases = {
            "REFERENCE_IDENTITY_MISMATCH": "REFERENCE", "SOURCE_BAD_CONTENT": "SOURCE",
            "PREVIS_CAMERA_GEOMETRY": "PREVIS", "GENERATION_TEMPORAL_ARTIFACT": "GENERATION",
            "POST_FIXABLE": "POST", "STORY_SPEC_CONFLICT": "STORY",
        }
        for code, owner in cases.items():
            with self.subTest(code=code):
                item = failure(authority="HUMAN", observation="observed", interpretation="failed",
                               reason_code=code, severity="CRITICAL")
                self.assertEqual(item.owner, owner)
                self.assertTrue(item.recommended_action)
                self.assertEqual(item.reason_codes, (code,))
        with self.assertRaises(ValueError):
            DimensionResult("FAIL", "HUMAN", "observed", "failed", ("SOURCE_BAD_CONTENT",),
                            "CRITICAL", (), "GENERATION", "REVIEW_GENERATION_STRATEGY")

    def test_q2_requires_human_and_q3_delivery_is_not_approval(self):
        q2 = self.pass_results("Q2", "REAL_UI")
        self.assertEqual(self.report("Q2", "REAL_UI", q2).overall, "PASS")
        q2["composition"] = DimensionResult("PASS", "AI_ASSISTED", "looks good")
        with self.assertRaises(ValueError):
            self.report("Q2", "REAL_UI", q2)
        q2["composition"] = DimensionResult("PASS", "HUMAN", "claimed human review")
        with self.assertRaises(ValueError):
            evaluate_qc(self.binding, "Q2", "REAL_UI", q2)  # no trusted verifier
        q3 = self.pass_results("Q3", "DELIVERY_MASTER", authority="MACHINE")
        report = self.report("Q3", "DELIVERY_MASTER", q3)
        self.assertEqual(report.overall, "PASS")
        self.assertFalse(hasattr(report, "approved"))

    def test_q3_final_assets_need_durable_materialization(self):
        asset = {"lifecycle": "FINAL", "sha256": "b" * 64, "provenance": "export",
                 "locators": [{"type": "LOCAL", "path": "media/final.mp4", "availability": "AVAILABLE"}]}
        asset["id"] = "master"
        canonical = {"project_id": self.binding.project_id,
                     "assets": [{**asset, "criticality": "REQUIRED_FOR_DELIVERY"}]}
        snapshot = SimpleNamespace(document=canonical, state_revision=self.binding.state_revision,
                                   project_hash=self.binding.project_hash, access="WRITABLE_VERSION")
        engine = SimpleNamespace(inspect_consistency=lambda: snapshot)
        self.assertEqual(check_delivery_assets(engine, self.binding, [canonical["assets"][0]]).status, "PASS")
        self.assertEqual(check_delivery_assets(engine, self.binding, []).reason_codes,
                         ("POST_MISSING_DELIVERABLE",))
        canonical["assets"].append({**asset, "id": "clean", "criticality": "REQUIRED_FOR_DELIVERY"})
        self.assertEqual(check_delivery_assets(engine, self.binding, [canonical["assets"][0]]).status, "FAIL")
        canonical["assets"].pop()
        canonical["assets"][0]["locators"] = []
        self.assertEqual(check_delivery_assets(engine, self.binding, [canonical["assets"][0]]).reason_codes,
                         ("POST_MATERIALIZATION",))
        canonical["assets"][0]["locators"] = None
        self.assertEqual(check_delivery_assets(engine, self.binding, [canonical["assets"][0]]).status, "FAIL")
        with self.assertRaises(ValueError):
            check_delivery_assets(engine, replace(self.binding, state_revision=3), [canonical["assets"][0]])
        with self.assertRaises(ValueError):
            check_delivery_assets(engine, self.binding, [canonical["assets"][0], {"foo": "bar"}])

    def test_not_applicable_not_reviewed_and_conditional_pass(self):
        results = self.pass_results("Q2", "REAL_UI")
        results["pacing"] = DimensionResult("NOT_APPLICABLE")
        self.assertEqual(self.report("Q2", "REAL_UI", results).overall, "PASS")
        del results["composition"]
        self.assertEqual(self.report("Q2", "REAL_UI", results).overall, "NOT_REVIEWED")
        results["composition"] = failure(authority="HUMAN", observation="slightly slow",
                                          interpretation="minor pacing issue", reason_code="POST_FIXABLE",
                                          severity="MINOR")
        report = self.report("Q2", "REAL_UI", results,
                             conditional_justification="Reviewer accepts for this use")
        self.assertEqual(report.overall, "CONDITIONAL_PASS")
        results["composition"] = failure(authority="HUMAN", observation="missing story beat",
                                          interpretation="critical intent missing",
                                          reason_code="STORY_SPEC_CONFLICT", severity="CRITICAL")
        with self.assertRaises(ValueError):
            self.report("Q2", "REAL_UI", results, conditional_justification="accept")
        self.assertEqual(self.report("Q2", "REAL_UI", results).overall, "FAIL")
        mixed = self.pass_results("Q1", "REAL_UI", authority="MACHINE")
        mixed["artifacts"] = failure(authority="MACHINE", observation="minor artifact",
                                      interpretation="local repair needed", reason_code="POST_FIXABLE",
                                      severity="MINOR")
        mixed["camera"] = DimensionResult("PASS", "HUMAN", "camera approved")
        review = HumanReview("reviewer", "review-note:1", "2026-09-24T10:00:00+08:00",
                             ("camera",))
        with self.assertRaises(ValueError):
            evaluate_qc(self.binding, "Q1", "REAL_UI", mixed, shot=self.shot,
                        conditional_justification="accept", human_review=review,
                        human_verifier=lambda record, subject: True)

    def test_stop_loss_uses_strategy_reason_dimension_and_distinct_candidates(self):
        def candidate(name, code="GENERATION_TEMPORAL_ARTIFACT", dimension="artifacts"):
            binding = replace(self.binding, candidate_id=name)
            result = failure(authority="HUMAN", observation="temporal defect",
                             interpretation="invalid candidate", reason_code=code)
            return evaluate_qc(binding, "Q1", "REAL_UI", {dimension: result}, shot=self.shot)
        first, second, third = (candidate(f"candidate-{number}") for number in (1, 2, 3))
        trusted = lambda binding: binding.strategy_id == "strategy-a"  # test-only verifier
        decision = evaluate_stop_loss(third, (first, second), strategy_verifier=trusted)
        self.assertEqual(decision.status, "REPLAN_REQUIRED")
        self.assertEqual(decision.matching_candidate_ids, ("candidate-1", "candidate-2", "candidate-3"))
        unrelated = candidate("candidate-4", "PREVIS_CAMERA_GEOMETRY", "camera")
        self.assertEqual(evaluate_stop_loss(third, (first, unrelated), strategy_verifier=trusted).status,
                         "BELOW_THRESHOLD")
        other_strategy = (replace(first, binding=replace(first.binding, strategy_id="strategy-b")),
                          replace(second, binding=replace(second.binding, strategy_id="strategy-b")))
        self.assertEqual(evaluate_stop_loss(third, other_strategy, strategy_verifier=trusted).status,
                         "BELOW_THRESHOLD")
        self.assertEqual(evaluate_stop_loss(third, (first, first), strategy_verifier=trusted).status,
                         "BELOW_THRESHOLD")
        with self.assertRaises(ValueError):
            evaluate_stop_loss(third, (first,), strategy_verifier=None)

    def test_ticket_and_receipt_are_provenance_only(self):
        data = {"project_id": "generic-project", "state_revision": 2,
                "project_hash": "a" * 64, "shot_id": "generic-shot", "candidate_id": "candidate-1",
                "provider": "mock", "workspace_id": "workspace", "execution_surface": "RAW_CLI",
                "runtime_snapshot_id": "runtime", "strategy_id": "strategy-a"}
        raw = json.dumps(data).encode()
        ticket = GenerationTicket(raw, hashlib.sha256(raw).hexdigest())
        receipt = SimpleNamespace(ticket_id=ticket.id, candidate_id="candidate-1", provider="mock",
                                  workspace_id="workspace", execution_surface="RAW_CLI",
                                  runtime_snapshot_id="runtime", claim_id=7, submission_state="COMPLETED")
        binding = binding_from_ticket(ticket, receipt)
        self.assertEqual(binding.receipt_claim_id, 7)
        self.assertEqual(binding.strategy_id, "strategy-a")
        self.assertEqual(evaluate_qc(binding, "Q2", "REAL_UI", {}).overall, "NOT_REVIEWED")
        with self.assertRaises(ValueError):
            binding_from_ticket(ticket, SimpleNamespace(**{**vars(receipt), "workspace_id": "wrong"}))

    def test_ticket_strategy_stays_stable_across_attempt_seeds(self):
        fixture = i3_fixture.I3Tests("test_ticket_hash_scope_prompt_and_source_lineage")
        fixture.setUp()
        self.addCleanup(fixture.fixture.tmp.cleanup)
        first = fixture.ticket(strategy_id="strategy-a", candidate_id="candidate-1",
                               parameters={"duration_seconds": 5, "resolution": "720p", "seed": 1})
        second = fixture.ticket(strategy_id="strategy-a", candidate_id="candidate-2",
                                parameters={"duration_seconds": 5, "resolution": "720p", "seed": 2})
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(binding_from_ticket(first).strategy_id,
                         binding_from_ticket(second).strategy_id)

    def test_override_requires_audit_binding_and_has_no_hidden_mutation(self):
        report = self.report("Q2", "REAL_UI")
        override = record_human_override(report, actor="reviewer", decision="REVIEW_REQUIRED",
                                         reason="Need source frames", timestamp="2026-09-24T10:00:00+08:00",
                                         dimension="composition")
        self.assertEqual(override.report_id, report.id)
        self.assertEqual(override.binding, self.binding)
        self.assertEqual(report.overall, "NOT_REVIEWED")
        for kwargs in ({"actor": ""}, {"reason": ""}, {"timestamp": "2026-09-24T10:00:00"},
                       {"dimension": "unknown"}):
            args = dict(actor="reviewer", decision="ACCEPT", reason="reviewed",
                        timestamp="2026-09-24T10:00:00+08:00", dimension="composition")
            args.update(kwargs)
            with self.assertRaises(ValueError):
                record_human_override(report, **args)

    def test_report_file_does_not_mutate_canonical_or_bypass_g6(self):
        fixture = i2_fixture.I2Tests("test_each_gate_passes_with_minimum_evidence")
        fixture.setUp()
        self.addCleanup(fixture.tmp.cleanup)
        def remove_final_approval(doc):
            doc["evidence"] = [item for item in doc["evidence"]
                               if item["kind"] != "FINAL_QC_APPROVAL"]
        fixture.commit(remove_final_approval)
        before = fixture.engine.read()
        self.assertNotEqual(evaluate_gates(fixture.engine)["G6"]["status"], "PASS")
        report = self.report("Q3", "DELIVERY_MASTER",
                             self.pass_results("Q3", "DELIVERY_MASTER"))
        with tempfile.TemporaryDirectory(dir=fixture.root) as location:
            Path(location, "qc-report.json").write_text(json.dumps(asdict(report)), encoding="utf-8")
            self.assertNotEqual(evaluate_gates(fixture.engine)["G6"]["status"], "PASS")
        after = fixture.engine.read()
        self.assertEqual((before.state_revision, before.project_hash),
                         (after.state_revision, after.project_hash))


if __name__ == "__main__":
    unittest.main()
