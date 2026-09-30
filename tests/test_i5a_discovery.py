"""Provider discovery remains offline and cannot authorize a paid request."""

import hashlib
import json
import unittest
from unittest.mock import patch

from aivideo.provider_discovery import (SurfaceEvidence, i3_snapshots,
                                        preferred_surface, snapshot_candidate)
from aivideo.tickets import UNKNOWN


NOW = "2026-09-24T00:00:00+00:00"


def ready(surface):
    return SurfaceEvidence(surface, "YES", "YES", "YES", "YES", "YES", "YES")


class DiscoveryTests(unittest.TestCase):
    def test_surface_priority_and_fallback(self):
        self.assertEqual(preferred_surface((ready("RAW_CLI"), ready("CODEX_PLUGIN"))),
                         "CODEX_PLUGIN")
        self.assertEqual(preferred_surface((SurfaceEvidence("CODEX_PLUGIN", installed="NO"),
                                            ready("RAW_CLI"))), "RAW_CLI")
        self.assertEqual(preferred_surface((SurfaceEvidence("CODEX_PLUGIN", executable="NO"),
                                            SurfaceEvidence("RAW_CLI", installed="NO"))), "WEB_MANUAL")

    def test_auth_and_workspace_fail_closed(self):
        unauth = SurfaceEvidence("CODEX_PLUGIN", "YES", "YES", "NO")
        self.assertEqual(unauth.status, "AUTH_REQUIRED")
        self.assertEqual(SurfaceEvidence("RAW_CLI", installed="NO",
                                         authenticated="NO").status, "UNAVAILABLE")
        self.assertFalse(unauth.execution_ready)
        self.assertEqual(preferred_surface((unauth,)), "WEB_MANUAL")
        self.assertFalse(SurfaceEvidence("RAW_CLI", "YES", "YES", "YES", "YES", "YES").execution_ready)

    def test_unknowns_remain_separate_and_unusable(self):
        candidate = snapshot_candidate(probes=(SurfaceEvidence("CODEX_PLUGIN", "YES", "YES"),),
                                       captured_at=NOW, evidence_source="PVX_SETUP_STATUS",
                                       plugin_version="1.3.1")
        self.assertEqual(candidate["technical"]["operations"], UNKNOWN)
        self.assertEqual(candidate["technical"]["idempotent_operations"], UNKNOWN)
        self.assertEqual(candidate["entitlement"]["credits_available"], UNKNOWN)
        self.assertEqual(candidate["runtime"]["workspace_id"], UNKNOWN)
        self.assertEqual(candidate["installed_plugin_version"], "1.3.1")
        self.assertEqual(candidate["runtime"]["plugin_version"], UNKNOWN)
        self.assertFalse(candidate["trusted_preflight"])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            i3_snapshots(candidate, native_evidence_ref="fixture")

    def test_i3_conversion_requires_proven_local_route_and_workspace(self):
        candidate = snapshot_candidate(
            probes=(ready("CODEX_PLUGIN"),), captured_at=NOW,
            evidence_source="CAPTURED_FIXTURE", evidence_surface="CODEX_PLUGIN",
            workspace_id="ws-123",
            operations=("IMAGE_TO_VIDEO",), authenticated=True,
            subscription_active=True, slots_available=2,
            idempotent_operations=(), trace_operations=())
        cap, account, runtime = i3_snapshots(candidate, native_evidence_ref="fixture:capability")
        self.assertEqual(cap.operations, ("IMAGE_TO_VIDEO",))
        self.assertEqual(cap.idempotent_operations, ())
        self.assertEqual(account.workspace_id, runtime.workspace_id)
        self.assertEqual(runtime.technical_snapshot_id, cap.id)
        self.assertFalse(candidate["trusted_preflight"])
        candidate["technical"]["backend"] = "RAW_CLI"
        content = {key: value for key, value in candidate.items() if key != "id"}
        candidate["id"] = hashlib.sha256(json.dumps(content, sort_keys=True,
                                                     ensure_ascii=False).encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            i3_snapshots(candidate, native_evidence_ref="fixture:capability")
        candidate["technical"]["backend"] = "PLUGIN_WRAPPER"
        content = {key: value for key, value in candidate.items() if key != "id"}
        candidate["id"] = hashlib.sha256(json.dumps(content, sort_keys=True,
                                                     ensure_ascii=False).encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "bind selected"):
            snapshot_candidate(probes=(ready("CODEX_PLUGIN"),), captured_at=NOW,
                               evidence_source="CAPTURED_FIXTURE", evidence_surface="RAW_CLI",
                               workspace_id="ws-123", operations=("IMAGE_TO_VIDEO",))
        with self.assertRaisesRegex(ValueError, "secret-shaped"):
            snapshot_candidate(probes=(ready("CODEX_PLUGIN"),), captured_at=NOW,
                               evidence_source="CAPTURED_FIXTURE", evidence_surface="CODEX_PLUGIN",
                               workspace_id=" ", operations=("IMAGE_TO_VIDEO",))
        candidate["runtime"]["workspace_id"] = UNKNOWN
        with self.assertRaisesRegex(ValueError, "altered"):
            i3_snapshots(candidate, native_evidence_ref="fixture:capability")

    def test_secret_shaped_raw_fields_are_rejected_not_serialized(self):
        with self.assertRaises(ValueError):
            SurfaceEvidence("CODEX_PLUGIN", evidence=("Bearer abc",))
        with self.assertRaises(ValueError):
            snapshot_candidate(probes=(), captured_at=NOW,
                               evidence_source="FIXTURE", canvas={"access_token": "secret"})
        with self.assertRaises(ValueError):
            snapshot_candidate(probes=(), captured_at=NOW,
                               evidence_source="Bearer secret")
        with self.assertRaises(ValueError):
            snapshot_candidate(probes=(), captured_at=NOW,
                               evidence_source="FIXTURE", plugin_version="sk-123456")
        candidate = snapshot_candidate(probes=(), captured_at=NOW,
                                       evidence_source="FIXTURE")
        self.assertNotIn("access_token", json.dumps(candidate))

    def test_discovery_has_no_provider_or_submission_calls(self):
        with patch("subprocess.run", side_effect=AssertionError("provider invocation")), \
             patch("aivideo.guards.guard_action", side_effect=AssertionError("guard invoked")):
            candidate = snapshot_candidate(probes=(SurfaceEvidence("RAW_CLI", installed="NO"),),
                                           captured_at=NOW, evidence_source="FIXTURE")
            self.assertEqual(candidate["preferred_surface"], "WEB_MANUAL")


if __name__ == "__main__":
    unittest.main()
