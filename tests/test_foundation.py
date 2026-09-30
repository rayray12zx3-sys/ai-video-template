import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aivideo.environment import capture_environment, load_local_profile
from aivideo.handoff import capture_handoff_base
from aivideo.schema import MigrationRequired, SchemaError, UnsupportedNewerSchema, validate
from aivideo.state_engine import PhaseI1Required, StateEngine, TransactionRequest


SAMPLE = ROOT / "examples" / "minimal-project"


class FoundationTests(unittest.TestCase):
    def test_sample_loads_and_has_no_initial_events(self):
        snapshot = StateEngine(SAMPLE).read()
        self.assertEqual(snapshot.state_revision, 0)
        self.assertEqual(snapshot.access, "WRITABLE_VERSION")
        self.assertEqual(len(snapshot.project_hash), 64)
        self.assertTrue(snapshot.next_action)
        self.assertEqual((SAMPLE / "events.jsonl").read_text(encoding="utf-8"), "")

    def test_invalid_and_newer_project_schema(self):
        document = json.loads((SAMPLE / "project.yaml").read_text(encoding="utf-8"))
        validate(document, "project")
        invalid = {**document, "state_revision": -1}
        with self.assertRaises(SchemaError):
            validate(invalid, "project")
        with self.assertRaises(SchemaError):
            validate({**document, "project_id": ""}, "project")
        with self.assertRaises(UnsupportedNewerSchema):
            validate({**document, "schema_version": "2.1"}, "project")
        with self.assertRaises(MigrationRequired):
            validate({**document, "schema_version": "1.9"}, "project")

    def test_newer_project_is_inspectable_but_not_writable(self):
        document = json.loads((SAMPLE / "project.yaml").read_text(encoding="utf-8"))
        document["schema_version"] = "2.1"
        engine = StateEngine(SAMPLE)
        original_read = Path.read_bytes
        def project_override(path):
            return json.dumps(document).encode("utf-8") if path == engine.project_path else original_read(path)
        with patch.object(Path, "read_bytes", project_override):
            self.assertEqual(engine.read().access, "UNSUPPORTED_NEWER_SCHEMA")
            with self.assertRaises(UnsupportedNewerSchema):
                engine.begin_transaction(TransactionRequest(0, "abc", "tx", "test", "TEST"))

        future = {"schema_version": "3.0", "new_revision_model": {"sequence": 10}}
        with patch.object(Path, "read_bytes", return_value=json.dumps(future).encode("utf-8")):
            snapshot = engine.read()
            self.assertEqual(snapshot.access, "UNSUPPORTED_NEWER_SCHEMA")
            self.assertIsNone(snapshot.state_revision)
            self.assertIsNone(snapshot.next_action)

    def test_event_schema(self):
        event = {"event_schema_version": "1.0", "transaction_id": "tx-1", "state_revision_before": 0,
                 "state_revision_after": 1, "project_hash_before": "0" * 64,
                 "project_hash_after": "1" * 64, "timestamp": "2026-09-23T00:00:00Z",
                 "actor": "test", "event_type": "TEST"}
        validate(event, "event")
        with self.assertRaises(SchemaError):
            validate({**event, "transaction_id": ""}, "event")

    def test_local_profile_stays_out_of_canonical_project(self):
        engine = StateEngine(SAMPLE)
        before = engine.read().project_hash
        with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value='{"profile_version":"1.0","root_mappings":{"media":"C:/local"}}'):
            self.assertEqual(load_local_profile(SAMPLE)["root_mappings"]["media"], "C:/local")
        self.assertEqual(engine.read().project_hash, before)
        self.assertNotIn("C:/local", json.dumps(engine.read().document))

    def test_local_profile_rejection(self):
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value='{"profile_version":"1.0","unsupported_key":true}'):
                with self.assertRaises(ValueError):
                    load_local_profile(SAMPLE)
            with patch.object(Path, "read_text", return_value='["unsupported", "array"]'):
                with self.assertRaises(ValueError):
                    load_local_profile(SAMPLE)

    def test_secret_and_local_files_are_ignored(self):
        paths = [".env", "secrets/key.json", "credentials/auth.json", "config.local.json",
                 "examples/minimal-project/local-profile.json", "examples/minimal-project/.pending-transaction.json",
                 "examples/minimal-project/.state-engine.lock", "environment-snapshot.local.json", "runtime-media/private.mov"]
        for path in paths:
            with self.subTest(path=path):
                result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
                self.assertEqual(result.returncode, 0)

    def test_environment_and_handoff_are_read_only(self):
        environment = capture_environment()
        self.assertIn("python", environment["tools"])
        handoff = capture_handoff_base(ROOT, SAMPLE)
        self.assertEqual(handoff["project_hash"], StateEngine(SAMPLE).read().project_hash)
        self.assertEqual(len(handoff["remote_identity_sha256"]), 64)
        self.assertNotIn("remote_url", handoff)

    def test_environment_python_launcher_fallback(self):
        real_run = subprocess.run

        def fake_run(command, **kwargs):
            if command[0] == "python":
                raise FileNotFoundError
            if command[0] == "py":
                return subprocess.CompletedProcess(command, 0, stdout="Python 3.13.14\n", stderr="")
            return real_run(command, **kwargs)

        with patch("aivideo.environment.subprocess.run", side_effect=fake_run):
            self.assertEqual(capture_environment()["tools"]["python"], "Python 3.13.14")

    def test_environment_npm_cmd_succeeds_no_fallback(self):
        real_run = subprocess.run
        executed_commands = []

        def fake_run(command, **kwargs):
            executed_commands.append(command[0])
            if command[0] == "npm.cmd":
                return subprocess.CompletedProcess(command, 0, stdout="10.8.0\n", stderr="")
            return real_run(command, **kwargs)

        with patch("aivideo.environment.subprocess.run", side_effect=fake_run):
            env = capture_environment()
            self.assertEqual(env["tools"]["npm"], "10.8.0")
            self.assertIn("npm.cmd", executed_commands)
            self.assertNotIn("npm", executed_commands)

    def test_environment_npm_cmd_fails_fallback_npm_succeeds(self):
        real_run = subprocess.run

        def fake_run(command, **kwargs):
            if command[0] == "npm.cmd":
                raise FileNotFoundError
            if command[0] == "npm":
                return subprocess.CompletedProcess(command, 0, stdout="10.9.0\n", stderr="")
            return real_run(command, **kwargs)

        with patch("aivideo.environment.subprocess.run", side_effect=fake_run):
            env = capture_environment()
            self.assertEqual(env["tools"]["npm"], "10.9.0")

    def test_environment_npm_both_fail_returns_none(self):
        real_run = subprocess.run

        def fake_run(command, **kwargs):
            if command[0] in ("npm.cmd", "npm"):
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="error")
            return real_run(command, **kwargs)

        with patch("aivideo.environment.subprocess.run", side_effect=fake_run):
            env = capture_environment()
            self.assertIsNone(env["tools"]["npm"])

    def test_environment_empty_stdout_returns_none(self):
        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, stdout=" \n", stderr="")

        with patch("aivideo.environment.subprocess.run", side_effect=fake_run):
            env = capture_environment()
            for tool in env["tools"]:
                self.assertIsNone(env["tools"][tool])

    def test_environment_npm_cmd_whitespace_fallback_npm_succeeds(self):
        real_run = subprocess.run

        def fake_run(command, **kwargs):
            if command[0] == "npm.cmd":
                return subprocess.CompletedProcess(command, 0, stdout=" \n", stderr="")
            if command[0] == "npm":
                return subprocess.CompletedProcess(command, 0, stdout="10.9.0\n", stderr="")
            return real_run(command, **kwargs)

        with patch("aivideo.environment.subprocess.run", side_effect=fake_run):
            env = capture_environment()
            self.assertEqual(env["tools"]["npm"], "10.9.0")

    def test_environment_python_whitespace_fallback_succeeds(self):
        real_run = subprocess.run

        def fake_run(command, **kwargs):
            if command[0] == "python":
                return subprocess.CompletedProcess(command, 0, stdout=" \n", stderr="")
            if command[0] == "py":
                return subprocess.CompletedProcess(command, 0, stdout="Python 3.13.14\n", stderr="")
            return real_run(command, **kwargs)

        with patch("aivideo.environment.subprocess.run", side_effect=fake_run):
            env = capture_environment()
            self.assertEqual(env["tools"]["python"], "Python 3.13.14")

    def test_i0_reader_remains_available_after_i1(self):
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            project = Path(folder)
            (project / "project.yaml").write_bytes((SAMPLE / "project.yaml").read_bytes())
            (project / "events.jsonl").write_bytes(b"")
            engine = StateEngine(project)
            self.assertEqual(engine.recover_pending(), "NO_PENDING")
            before = engine.read()
            with self.assertRaises(PhaseI1Required):
                engine.begin_transaction(TransactionRequest(0, before.project_hash, "tx", "test", "TEST"))


if __name__ == "__main__":
    unittest.main()
