"""Tests for the I6b deterministic legacy-project importer and dry-run report."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aivideo import import_legacy_project
from aivideo.schema import validate


class LegacyImportTests(unittest.TestCase):

    def setUp(self):
        self.valid_fixture = {
            "format": "legacy-project-sanitized-v1",
            "fixture_id": "legacy-project-representative",
            "project": {
                "legacy_project_id": "legacy-project",
                "mode_hint": "NEW_PRODUCTION",
                "workflow_status_hint": "COMPLETE",
                "template_version": "2.0",
                "state_revision": 0,
                "next_action": "Verify imported replay status",
            },
            "assets": [
                {
                    "id": "asset-ui-01",
                    "media_type": "VIDEO",
                    "origin": "REAL_UI",
                    "content_role": "UI",
                    "lifecycle": "RECEIVED",
                    "selected": True,
                    "locators": [
                        {
                            "type": "LOCAL",
                            "path": "media/source_ui.mp4",
                            "availability": "AVAILABLE",
                        }
                    ],
                }
            ],
            "shots": [
                {
                    "id": "shot-01",
                    "duration_frames": 120,
                    "intent": "UI interaction recording",
                    "input_asset_ids": ["asset-ui-01"],
                    "production_method": "SOURCE_VIDEO",
                    "readiness": "REQUIRED",
                    "new_media_required": False,
                    "editorial_only": True,
                }
            ],
            "dependencies": [
                {
                    "source": "asset:asset-ui-01",
                    "target": "shot:shot-01",
                    "impact": "SEMANTIC_CONTENT",
                }
            ],
            "selections": {
                "ui_main": "asset-ui-01",
            },
            "approvals": [
                {
                    "id": "app-01",
                    "status": "APPROVED",
                    "actor_type": "HUMAN",
                    "subject": "shot:shot-01",
                }
            ],
            "legacy_records": [
                {
                    "type": "WORKLOG",
                    "note": "Replaced legacy composite with source video",
                }
            ],
            "unknown_fields": {
                "legacy_flags": ["NO_PROVIDER_EXECUTION_NEEDED"],
            },
        }

    def test_representative_valid_sanitized_fixture(self):
        candidate, report = import_legacy_project(self.valid_fixture)

        self.assertEqual(candidate["schema_version"], "2.0")
        self.assertEqual(candidate["project_id"], "legacy-project")
        self.assertEqual(candidate["mode"], "NEW_PRODUCTION")
        self.assertEqual(candidate["workflow_status"], "COMPLETE")
        self.assertEqual(len(candidate["assets"]), 1)
        self.assertEqual(len(candidate["shots"]), 1)
        self.assertEqual(len(candidate["dependencies"]), 1)

        self.assertEqual(report["source_format"], "legacy-project-sanitized-v1")
        self.assertTrue(isinstance(report["source_fingerprint"], str))
        self.assertEqual(len(report["source_fingerprint"]), 64)
        self.assertTrue(any(item["code"] == "PROJECT_METADATA_MAPPED" for item in report["mapped_items"]))
        self.assertTrue(any(item["code"] == "ASSET_MAPPED" for item in report["mapped_items"]))
        self.assertTrue(any(item["code"] == "SHOT_MAPPED" for item in report["mapped_items"]))
        self.assertTrue(any(item["code"] == "EXPLICIT_UNKNOWN_FIELD" for item in report["unresolved_items"]))
        self.assertTrue(any(item["code"] == "LEGACY_RECORD_RETAINED" for item in report["evidence_only_items"]))
        self.assertEqual(
            next(item["value"] for item in report["evidence_only_items"]
                 if item["code"] == "FIXTURE_ID_RETAINED"),
            "legacy-project-representative",
        )

    def test_malformed_input_rejection(self):
        with self.assertRaises(ValueError):
            import_legacy_project("not a dict")

        with self.assertRaises(ValueError):
            import_legacy_project({})

        with self.assertRaises(ValueError):
            import_legacy_project({"format": "wrong-format"})

        bad_assets = deepcopy(self.valid_fixture)
        bad_assets["assets"] = "not a list"
        with self.assertRaises(ValueError):
            import_legacy_project(bad_assets)

        bad_shots = deepcopy(self.valid_fixture)
        bad_shots["shots"] = "not a list"
        with self.assertRaises(ValueError):
            import_legacy_project(bad_shots)

    def test_unknown_and_unmapped_field_reporting(self):
        fixture = deepcopy(self.valid_fixture)
        fixture["custom_top_level_flag"] = "mystery_value"
        fixture["project"]["custom_project_setting"] = 123
        fixture["assets"][0]["custom_asset_property"] = "extra"
        fixture["shots"][0]["custom_shot_setting"] = True

        candidate, report = import_legacy_project(fixture)

        validate(candidate, "project")

        unresolved_codes = [u["code"] for u in report["unresolved_items"]]
        self.assertIn("UNRECOGNIZED_TOP_LEVEL_KEY", unresolved_codes)
        self.assertIn("UNRESOLVED_PROJECT_FIELD", unresolved_codes)
        self.assertIn("UNRESOLVED_ASSET_FIELD", unresolved_codes)
        self.assertIn("UNRESOLVED_SHOT_FIELD", unresolved_codes)

        top_unresolved = [u for u in report["unresolved_items"] if u["code"] == "UNRECOGNIZED_TOP_LEVEL_KEY"]
        self.assertEqual(top_unresolved[0]["source_key"], "custom_top_level_flag")
        self.assertEqual(top_unresolved[0]["value"], "mystery_value")
        for location, value in (
            ("project.custom_project_setting", 123),
            ("assets[0].custom_asset_property", "extra"),
            ("shots[0].custom_shot_setting", True),
        ):
            self.assertEqual(
                next(item["value"] for item in report["unresolved_items"]
                     if item["source_key"] == location), value)

    def test_incomplete_and_malformed_records_retain_safe_source_values(self):
        fixture = deepcopy(self.valid_fixture)
        fixture["evidence"] = [{"id": "incomplete", "note": {"status": "historical"}}]
        fixture["assets"].extend(["malformed asset", {"origin": "REAL_UI"}])
        fixture["shots"].extend(["malformed shot", {"intent": "unidentified"}])
        fixture["dependencies"].append("malformed dependency")
        fixture["dependencies"].append({"source": ["bad"], "target": "shot:shot-01"})
        _, report = import_legacy_project(fixture)
        expected = {
            "evidence[0]": ("value", fixture["evidence"][0]),
            "assets[1]": ("value", "malformed asset"),
            "assets[2]": ("value", {"origin": "REAL_UI"}),
            "shots[1]": ("value", "malformed shot"),
            "shots[2]": ("value", {"intent": "unidentified"}),
            "dependencies[1]": ("value", "malformed dependency"),
            "dependencies[2]": ("value", fixture["dependencies"][2]),
        }
        items = report["evidence_only_items"] + report["unresolved_items"]
        for location, (field, value) in expected.items():
            with self.subTest(location=location):
                self.assertEqual(next(item[field] for item in items
                                      if item["source_key"] == location), value)

    def test_recognized_fallbacks_and_extra_dependency_fields_accounted_for(self):
        fixture = deepcopy(self.valid_fixture)
        fixture["project"].update({"project_id": "current", "mode": "REVISION",
                                   "workflow_status": "ACTIVE", "brief": "not-an-object"})
        fixture["dependencies"][0]["legacy_note"] = {"safe": "retained"}
        candidate, report = import_legacy_project(fixture)
        self.assertEqual(candidate["project_id"], "current")
        self.assertEqual(candidate["mode"], "REVISION")
        self.assertEqual(candidate["workflow_status"], "ACTIVE")
        accounting = {item["source_key"]: item for item in report["source_accounting"]}
        self.assertEqual(accounting["project.legacy_project_id"]["disposition"], "EVIDENCE_ONLY")
        self.assertEqual(accounting["project.mode_hint"]["disposition"], "EVIDENCE_ONLY")
        self.assertEqual(accounting["project.workflow_status_hint"]["disposition"], "EVIDENCE_ONLY")
        self.assertEqual(accounting["project.brief"]["disposition"], "UNRESOLVED")
        self.assertEqual(accounting["dependencies[0].legacy_note.safe"]["disposition"], "UNRESOLVED")
        self.assertEqual(accounting["dependencies[0].legacy_note.safe"]["value"], "retained")

    def test_deterministic_output(self):
        candidate1, report1 = import_legacy_project(self.valid_fixture)
        candidate2, report2 = import_legacy_project(self.valid_fixture)

        self.assertEqual(candidate1, candidate2)
        self.assertEqual(report1, report2)
        reordered = {key: self.valid_fixture[key] for key in reversed(self.valid_fixture)}
        self.assertEqual((candidate1, report1), import_legacy_project(reordered))

    def test_no_input_mutation(self):
        original = deepcopy(self.valid_fixture)
        import_legacy_project(self.valid_fixture)
        self.assertEqual(self.valid_fixture, original)

    def test_current_schema_validation(self):
        candidate, _ = import_legacy_project(self.valid_fixture)
        validated = validate(candidate, "project")
        self.assertEqual(validated, candidate)

    def test_private_and_machine_path_leakage(self):
        fixture = deepcopy(self.valid_fixture)
        # Synthetic absolute paths exercise redaction without naming a user or machine.
        fixture["assets"][0]["locators"] = [
            {
                "type": "LOCAL",
                "path": "C:\\TestData\\sample\\fixture_data\\video.mp4",
                "availability": "AVAILABLE",
            },
            {
                "type": "LOCAL",
                "path": "/var/tmp/sample/video.mp4",
                "availability": "AVAILABLE",
            },
            {
                "type": "LOCAL",
                "path": "safe/relative/path.mp4",
                "availability": "AVAILABLE",
            },
        ]

        candidate, report = import_legacy_project(fixture)

        locs = candidate["assets"][0]["locators"]
        self.assertEqual(locs[0]["path"], "REDACTED")
        self.assertEqual(locs[0]["availability"], "UNAVAILABLE")
        self.assertEqual(locs[1]["path"], "REDACTED")
        self.assertEqual(locs[1]["availability"], "UNAVAILABLE")
        self.assertEqual(locs[2]["path"], "safe/relative/path.mp4")

        redaction_codes = [r["code"] for r in report["redactions"]]
        self.assertEqual(redaction_codes, ["ABSOLUTE_PATH_REDACTED", "ABSOLUTE_PATH_REDACTED"])

        serialized = json.dumps({"candidate": candidate, "report": report}, sort_keys=True)
        self.assertNotIn("C:\\TestData\\sample", serialized)
        self.assertNotIn("/var/tmp/sample", serialized)
        self.assertIn("safe/relative/path.mp4", serialized)
        self.assertEqual(
            next(item["disposition"] for item in report["source_accounting"]
                 if item["source_key"] == "assets[0].locators[0].path"), "REDACTED")

        validate(candidate, "project")

    def test_private_paths_are_redacted_in_other_report_values(self):
        fixture = deepcopy(self.valid_fixture)
        fixture["extra"] = {"machine_path": "/var/var/tmp/sample/video.mp4"}
        fixture["evidence"] = [{"note": "C:\\TestData\\sample\\fixture_data\\note.txt"}]
        fixture["legacy_records"].append({"note": "Archived at /var/tmp/sample/video.mp4"})
        candidate, report = import_legacy_project(fixture)
        serialized = json.dumps({"candidate": candidate, "report": report}, sort_keys=True)
        self.assertNotIn("/var/var/tmp/sample", serialized)
        self.assertNotIn("C:\\TestData\\sample", serialized)
        self.assertNotIn("/var/tmp/sample", serialized)
        self.assertEqual(len(report["redactions"]), 3)
