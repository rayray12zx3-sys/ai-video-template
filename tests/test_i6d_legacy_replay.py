"""Tests for I6d replay of sanitized legacy project cases and reconstructed v2 state comparison."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aivideo import import_legacy_project
from aivideo.qc import check_exact_text, check_interactions, check_locked_properties
from aivideo.router import route_shot
from aivideo.schema import validate
from aivideo.state_engine import StateEngine, TransactionRequest, _json_bytes


FIXTURES_DIR = ROOT / "tests" / "fixtures" / "legacy_project"


class LegacyReplayTests(unittest.TestCase):

    def setUp(self):
        self.fixture_files = {
            "text-interaction": FIXTURES_DIR / "exact_text_interaction.json",
            "scale-motion": FIXTURES_DIR / "scale_camera_motion.json",
            "revision-recovery": FIXTURES_DIR / "revision_reference_recovery.json",
            "source-video": FIXTURES_DIR / "source_video_route.json",
            "editorial-cut": FIXTURES_DIR / "editorial_match_cut.json",
        }
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)

    def load_fixture(self, case_key: str) -> dict:
        filepath = self.fixture_files[case_key]
        self.assertTrue(filepath.exists(), f"Fixture file missing for {case_key}: {filepath}")
        return json.loads(filepath.read_text(encoding="utf-8"))

    def test_all_five_fixtures_exist_and_import_deterministically(self):
        self.assertEqual(len(self.fixture_files), 5)
        for case_key, filepath in self.fixture_files.items():
            with self.subTest(case=case_key):
                fixture = self.load_fixture(case_key)
                self.assertEqual(fixture["format"], "legacy-project-sanitized-v1")

                candidate1, report1 = import_legacy_project(fixture)
                candidate2, report2 = import_legacy_project(fixture)

                self.assertEqual(candidate1, candidate2)
                self.assertEqual(report1, report2)

                # Validate canonical candidate against schema
                validated = validate(candidate1, "project")
                self.assertEqual(validated, candidate1)

    def test_no_private_or_machine_paths_in_fixtures_or_candidates(self):
        for case_key in self.fixture_files:
            with self.subTest(case=case_key):
                fixture = self.load_fixture(case_key)
                candidate, report = import_legacy_project(fixture)

                serialized = json.dumps({"fixture": fixture, "candidate": candidate, "report": report}).lower()

                # json.dumps escapes Windows separators; scan common real user-path signatures.
                for signature in ("c:\\\\users\\\\", "/home/", "/users/"):
                    self.assertNotIn(signature, serialized)

                # Keep generic sentinels as additional regression coverage.
                self.assertNotIn("c:\\\\testdata\\\\", serialized)
                self.assertNotIn("/var/tmp/", serialized)
                self.assertNotIn("password", serialized.lower())
                self.assertNotIn("secret", serialized.lower())

                # Check redactions list in report
                self.assertEqual(len(report["redactions"]), 0)

    def test_adoption_into_state_engine(self):
        for case_key in self.fixture_files:
            with self.subTest(case=case_key):
                fixture = self.load_fixture(case_key)
                candidate, report = import_legacy_project(fixture)

                proj_dir = self.tmp_path / f"project_{case_key.lower()}"
                proj_dir.mkdir()
                sample = ROOT / "examples" / "minimal-project" / "project.yaml"
                sample_doc = json.loads(sample.read_bytes())
                sample_doc["project_id"] = candidate["project_id"]
                (proj_dir / "project.yaml").write_bytes(_json_bytes(sample_doc))
                (proj_dir / "events.jsonl").write_bytes(b"")

                engine = StateEngine(proj_dir)
                initial_state = engine.read()

                req = TransactionRequest(
                    initial_state.state_revision,
                    initial_state.project_hash,
                    f"tx-adopt-{case_key.lower()}",
                    "replay-test",
                    "IMPORT_ADOPTION",
                )

                result = engine.commit_import_adoption(req, fixture, candidate, report)
                self.assertEqual(result.state_revision, 1)
                self.assertEqual(result.document["project_id"], candidate["project_id"])

                # Prove imported dependency impacts are compatible with ordinary
                # State Engine dependency validation, not only IMPORT_ADOPTION.
                ordinary = deepcopy(result.document)
                ordinary["state_revision"] = 2
                ordinary_result = engine.begin_transaction(
                    TransactionRequest(
                        1,
                        result.project_hash,
                        f"tx-ordinary-{case_key.lower()}",
                        "replay-test",
                        "EDIT",
                    ),
                    ordinary,
                )
                self.assertEqual(ordinary_result.state_revision, 2)

    def test_exact_text_interaction_and_interaction_replay(self):
        fixture = self.load_fixture("text-interaction")
        candidate, report = import_legacy_project(fixture)

        shot = candidate["shots"][0]
        self.assertEqual(shot["id"], "shot-text-interaction")
        self.assertEqual(shot["constraints"]["exact_text"], "SAMPLE")
        self.assertEqual(shot["requirements"]["motion_complexity"], "LOW")
        self.assertTrue(shot["constraints"]["text_readable"])
        self.assertIn("contact_unmarked_panel", shot["constraints"]["must_not"])
        self.assertEqual(
            shot["constraints"]["interaction"][0],
            {"subject": "hand", "action": "CONTACT", "object": "MARKED_PANEL"},
        )

        # Route shot evaluation
        route = route_shot(shot, candidate["assets"])
        self.assertEqual(route.method, "COMPOSITE")
        self.assertIn("EXACT_CONTENT_OR_COMPOSITING", route.reasons)

        # QC exact text verification
        pass_text = check_exact_text("SAMPLE", "SAMPLE", origin="GENERATION")
        self.assertEqual(pass_text.status, "PASS")

        fail_text = check_exact_text("SAMPLE", "WrongText", origin="GENERATION")
        self.assertEqual(fail_text.status, "FAIL")
        self.assertEqual(fail_text.owner, "GENERATION")

        # QC interaction verification
        required_int = shot["constraints"]["interaction"]
        pass_int = check_interactions(required_int, required_int)
        self.assertEqual(pass_int.status, "PASS")

        fail_int = check_interactions(
            required_int,
            [{"subject": "different hand", "action": "CONTACT", "object": "MARKED_PANEL"}],
        )
        self.assertEqual(fail_int.status, "FAIL")

    def test_scale_camera_motion_replay(self):
        fixture = self.load_fixture("scale-motion")
        candidate, report = import_legacy_project(fixture)

        shot = candidate["shots"][0]
        self.assertEqual(shot["id"], "shot-scale-motion")
        self.assertEqual(shot["requirements"]["motion_complexity"], "HIGH")
        self.assertEqual(shot["requirements"]["structure_sensitivity"], "HIGH")
        camera = shot["requirements"]["camera"]
        self.assertTrue(camera["complex_geometry"])
        self.assertTrue(camera["lens_sensitive"])
        self.assertEqual(camera["sensitivity"], "HIGH")
        self.assertEqual(camera["lens_mm"], 24)
        self.assertEqual(camera["angle"], "LOW")
        self.assertEqual(camera["fisheye"], "SLIGHT")
        self.assertEqual(
            shot["constraints"]["key_states"],
            ["low_structure", "rapid_growth_and_lift", "elevated_end_state"],
        )
        self.assertIn("distort_subject", shot["constraints"]["must_not"])
        self.assertEqual(candidate["dependencies"][0]["impact"], "STRUCTURE")

        # Router recommends MOTION_3D previs due to complex camera + complex motion
        route = route_shot(shot, candidate["assets"])
        self.assertEqual(route.previs, "MOTION_3D")
        self.assertIn("PREVIS_RECOMMENDED", route.reasons)

    def test_revision_reference_recovery_replay(self):
        fixture = self.load_fixture("revision-recovery")
        candidate, report = import_legacy_project(fixture)

        self.assertEqual(candidate["mode"], "REVISION")
        shot = candidate["shots"][0]
        self.assertEqual(shot["id"], "shot-revision-recovery")
        self.assertEqual(shot["error_owner"], "GENERATION")
        self.assertEqual(shot["constraints"]["allowed_motion"], ["one_natural_blink"])
        self.assertEqual(
            set(shot["constraints"]["forbidden"]),
            {"smile", "body_sway", "head_sway"},
        )

        # Locked properties verification
        must_preserve = shot["constraints"]["must_preserve"]
        self.assertIn("framing", must_preserve)
        baseline_props = {
            "subject_identity": "sample_identity",
            "framing": "centered",
            "environment": "plain_environment",
            "camera": "eye_level",
        }

        # Matching revision passes
        pass_qc = check_locked_properties(
            must_preserve, baseline_props, deepcopy(baseline_props), origin="GENERATION"
        )
        self.assertEqual(pass_qc.status, "PASS")

        # Drift in environment triggers failure owned by GENERATION
        drifted_props = deepcopy(baseline_props)
        drifted_props["environment"] = "drifted_environment"
        fail_qc = check_locked_properties(
            must_preserve, baseline_props, drifted_props, origin="GENERATION"
        )
        self.assertEqual(fail_qc.status, "FAIL")
        self.assertEqual(fail_qc.owner, "GENERATION")

    def test_source_video_route_replay(self):
        fixture = self.load_fixture("source-video")
        candidate, report = import_legacy_project(fixture)

        asset = candidate["assets"][0]
        self.assertEqual(asset["origin"], "REAL_UI")
        self.assertEqual(asset["content_role"], "UI")

        shot = candidate["shots"][0]
        self.assertEqual(shot["production_method"], "SOURCE_VIDEO")
        self.assertFalse(shot["new_media_required"])
        self.assertTrue(shot["editorial_only"])

        route = route_shot(shot, candidate["assets"])
        self.assertEqual(route.method, "SOURCE_VIDEO")
        # Ensure source-video does not acquire AI-generation requirements
        self.assertEqual(route.eligible_operations, ())

    def test_editorial_match_cut_replay(self):
        fixture = self.load_fixture("editorial-cut")
        candidate, report = import_legacy_project(fixture)

        self.assertEqual(len(candidate["assets"]), 2)
        shot = candidate["shots"][0]
        self.assertEqual(shot["production_method"], "PREMIERE")
        self.assertFalse(shot["new_media_required"])
        self.assertTrue(shot["editorial_only"])
        self.assertIn("match cut", shot["intent"].lower())
        self.assertTrue(all(dep["impact"] == "TIMING" for dep in candidate["dependencies"]))

        route = route_shot(shot, candidate["assets"])
        self.assertEqual(route.method, "PREMIERE")
        # Ensure editorial match cut does not acquire AI-generation requirements
        self.assertEqual(route.eligible_operations, ())

    def test_legacy_unresolved_information_reporting(self):
        for case_key in self.fixture_files:
            with self.subTest(case=case_key):
                fixture = self.load_fixture(case_key)
                candidate, report = import_legacy_project(fixture)

                # Verify unresolved items contains the unknown legacy notes field
                unresolved_keys = [u["source_key"] for u in report["unresolved_items"]]
                self.assertIn("unknown_fields.legacy_notes", unresolved_keys)

                # Verify evidence_only items includes legacy_records and approvals
                evidence_keys = [e["source_key"] for e in report["evidence_only_items"]]
                self.assertIn("legacy_records[0]", evidence_keys)
                self.assertIn("approvals[0]", evidence_keys)

                # Verify source accounting assigns explicit disposition to every fact
                accounting = {item["source_key"]: item["disposition"] for item in report["source_accounting"]}
                self.assertEqual(accounting["unknown_fields.legacy_notes[0]"], "UNRESOLVED")
                self.assertEqual(accounting["legacy_records[0].note"], "EVIDENCE_ONLY")

    def test_no_shot_id_specific_runtime_logic_in_aivideo_src(self):
        src_dir = ROOT / "src" / "aivideo"
        py_files = list(src_dir.glob("*.py"))
        self.assertTrue(len(py_files) > 0)

        forbidden_shot_ids = [
            shot["id"]
            for fixture_path in self.fixture_files.values()
            for shot in json.loads(fixture_path.read_text(encoding="utf-8"))["shots"]
        ]

        for py_file in py_files:
            source = py_file.read_text(encoding="utf-8").lower()
            for fixture_shot_id in forbidden_shot_ids:
                self.assertNotIn(
                    fixture_shot_id.lower(),
                    source,
                    f"Fixture-specific shot ID {fixture_shot_id!r} found in {py_file.name}",
                )


if __name__ == "__main__":
    unittest.main()