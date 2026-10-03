"""Offline revision-zero bootstrap and empty-base Git handoff regressions."""

from copy import deepcopy
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

from aivideo.handoff import (capture_bootstrap_base, capture_handoff_base,
                            verify_bootstrap_base)
from aivideo.schema import SchemaError
from aivideo.state_engine import (RecoveryConflict, RemoteStateConflict, StateConflict,
                                  StateEngine, TransactionRequest, WriterLockConflict,
                                  _atomic_replace)


def initial_document():
    # Construct a new project through public APIs; never copy canonical samples.
    return {"schema_version": "2.0", "template_version": "2.0",
            "project_id": "bootstrap-test", "state_revision": 0,
            "mode": "NEW_PRODUCTION", "interaction_mode": "DISCOVERY",
            "next_action": "Review the brief", "assets": [], "shots": [],
            "dependencies": []}


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "new-project"
        self.engine = StateEngine(self.path)
        self.document = initial_document()

    def canonical_bytes(self):
        return tuple(path.read_bytes() if path.exists() else None
                     for path in (self.engine.project_path, self.engine.events_path))

    def test_local_genesis_consistency_recovery_and_first_transaction(self):
        original = deepcopy(self.document)
        snapshot = self.engine.bootstrap(self.document)
        self.assertEqual(snapshot.document, original)
        self.assertEqual(self.document, original)
        self.assertEqual(snapshot.state_revision, 0)
        self.assertEqual(snapshot.access, "WRITABLE_VERSION")
        self.assertEqual(snapshot.project_hash, hashlib.sha256(self.engine.project_path.read_bytes()).hexdigest())
        self.assertEqual(self.engine.events_path.read_bytes(), b"")
        self.assertEqual(self.engine.inspect_consistency(), snapshot)
        self.assertEqual(self.engine.inspect_history(), ())
        self.assertEqual(self.engine.recover_pending(), "NO_PENDING")
        self.assertFalse(self.engine.journal.path.exists())
        after = {**self.document, "state_revision": 1, "next_action": "Review storyboard"}
        result = self.engine.begin_transaction(TransactionRequest(
            0, snapshot.project_hash, "first", "tester", "EDIT"), after)
        event, = self.engine.inspect_history()
        self.assertEqual((event["state_revision_before"], event["state_revision_after"]), (0, 1))
        self.assertEqual(event["project_hash_before"], snapshot.project_hash)
        self.assertEqual(event["project_hash_after"], result.project_hash)
        before = self.canonical_bytes()
        with self.assertRaises(StateConflict):
            self.engine.bootstrap(self.document)
        self.assertEqual(self.canonical_bytes(), before)

    def test_invalid_candidates_create_no_canonical_files(self):
        cases = [None, [], {}, {**self.document, "schema_version": "2.1"},
                 {**self.document, "schema_version": "1.9"}]
        for field, value in (("project_id", ""), ("next_action", ""),
                             ("mode", "INVALID"), ("interaction_mode", "INVALID"),
                             ("assets", {}), ("shots", {}), ("dependencies", {}),
                             ("state_revision", True), ("state_revision", -1)):
            cases.append({**self.document, field: value})
        for field in self.document:
            cases.append({key: value for key, value in self.document.items() if key != field})
        for candidate in cases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(SchemaError):
                    self.engine.bootstrap(candidate)
                self.assertEqual(self.canonical_bytes(), (None, None))

    def test_nonzero_revision_rejected_without_files(self):
        with self.assertRaises(StateConflict):
            self.engine.bootstrap({**self.document, "state_revision": 1})
        self.assertEqual(self.canonical_bytes(), (None, None))

    def test_prepared_empty_history_is_retryable(self):
        self.path.mkdir()
        self.engine.events_path.write_bytes(b"")
        self.assertEqual(self.engine.bootstrap(self.document).state_revision, 0)
        self.assertEqual(self.engine.events_path.read_bytes(), b"")

    def test_nonempty_or_malformed_history_without_project_conflicts(self):
        self.path.mkdir()
        for raw in (b"\n", b" ", b"{}\n", b"{partial"):
            with self.subTest(raw=raw):
                self.engine.events_path.write_bytes(raw)
                with self.assertRaises(StateConflict):
                    self.engine.bootstrap(self.document)
                self.assertEqual(self.canonical_bytes(), (None, raw))

    def test_exact_retry_never_mutates_canonical_files(self):
        first = self.engine.bootstrap(self.document)
        before = self.canonical_bytes()
        stamps = tuple(path.stat().st_mtime_ns for path in
                       (self.engine.project_path, self.engine.events_path))
        with patch("aivideo.state_engine._atomic_replace", side_effect=AssertionError("retry wrote")):
            self.assertEqual(self.engine.bootstrap(dict(reversed(list(self.document.items())))), first)
        self.assertEqual(self.canonical_bytes(), before)
        self.assertEqual(stamps, tuple(path.stat().st_mtime_ns for path in
                                      (self.engine.project_path, self.engine.events_path)))

    def test_existing_different_or_reformatted_project_is_preserved(self):
        snapshot = self.engine.bootstrap(self.document)
        for candidate in ({**self.document, "project_id": "other"},
                          {**self.document, "next_action": "Different action"}):
            before = self.canonical_bytes()
            with self.assertRaises(StateConflict):
                self.engine.bootstrap(candidate)
            self.assertEqual(self.canonical_bytes(), before)
        self.engine.project_path.write_text(json.dumps(snapshot.document, indent=2), encoding="utf-8")
        before = self.canonical_bytes()
        with self.assertRaises(StateConflict):
            self.engine.bootstrap(self.document)
        self.assertEqual(self.canonical_bytes(), before)

    def test_malformed_or_unsupported_existing_project_is_preserved(self):
        self.path.mkdir()
        self.engine.events_path.write_bytes(b"")
        for raw in (b"{bad", b"[]", b"", b'{"schema_version":"9.0"}',
                    b'{"schema_version":"1.9"}'):
            self.engine.project_path.write_bytes(raw)
            before = self.canonical_bytes()
            with self.subTest(raw=raw), self.assertRaises(StateConflict):
                self.engine.bootstrap(self.document)
            self.assertEqual(self.canonical_bytes(), before)

    def test_existing_exact_project_with_missing_or_mismatched_history_conflicts(self):
        self.engine.bootstrap(self.document)
        self.engine.events_path.unlink()
        before = self.canonical_bytes()
        with self.assertRaises(StateConflict):
            self.engine.bootstrap(self.document)
        self.assertEqual(self.canonical_bytes(), before)
        self.engine.events_path.write_bytes(b"{}\n")
        before = self.canonical_bytes()
        with self.assertRaises(StateConflict):
            self.engine.bootstrap(self.document)
        self.assertEqual(self.canonical_bytes(), before)

    def test_pending_journal_is_never_recovered_or_changed_by_bootstrap(self):
        for initialized in (False, True):
            with self.subTest(initialized=initialized):
                if initialized:
                    self.engine.journal.path.unlink()
                    self.engine.bootstrap(self.document)
                else:
                    self.path.mkdir()
                self.engine.journal.path.write_bytes(b"{pending")
                before = self.canonical_bytes()
                with self.assertRaises(RecoveryConflict):
                    self.engine.bootstrap(self.document)
                self.assertEqual(self.canonical_bytes(), before)
                self.assertEqual(self.engine.journal.path.read_bytes(), b"{pending")

    def test_active_lock_blocks_bootstrap(self):
        with self.engine.lock.acquire("other-writer"):
            with self.assertRaises(WriterLockConflict):
                StateEngine(self.path).bootstrap(self.document)
        self.assertEqual(self.canonical_bytes(), (None, None))

    def test_crash_between_history_and_project_is_retryable(self):
        def fail_project(path, raw):
            if path == self.engine.project_path:
                raise OSError("injected process interruption")
            _atomic_replace(path, raw)
        with patch("aivideo.state_engine._atomic_replace", side_effect=fail_project):
            with self.assertRaises(OSError):
                self.engine.bootstrap(self.document)
        self.assertEqual(self.canonical_bytes(), (None, b""))
        self.assertFalse(self.engine.journal.path.exists())
        self.assertEqual(StateEngine(self.path).bootstrap(self.document).state_revision, 0)

    def test_crash_after_project_creation_leaves_consistent_genesis(self):
        with patch.object(self.engine, "inspect_consistency", side_effect=OSError("lost result")):
            with self.assertRaises(OSError):
                self.engine.bootstrap(self.document)
        snapshot = self.engine.inspect_consistency()
        self.assertEqual(snapshot.state_revision, 0)
        with patch("aivideo.state_engine._atomic_replace", side_effect=AssertionError("retry wrote")):
            self.assertEqual(StateEngine(self.path).bootstrap(self.document), snapshot)

    def test_local_bootstrap_rejects_git_evidence(self):
        with self.assertRaises(RemoteStateConflict):
            self.engine.bootstrap(self.document, handoff_base={})
        self.assertEqual(self.canonical_bytes(), (None, None))

    def test_canonical_directories_and_symlinks_conflict(self):
        self.path.mkdir()
        for path in (self.engine.project_path, self.engine.events_path):
            path.mkdir()
            with self.assertRaises(StateConflict):
                self.engine.bootstrap(self.document)
            self.assertTrue(path.is_dir())
            path.rmdir()
            try:
                path.symlink_to(self.path / "absent")
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(StateConflict):
                self.engine.bootstrap(self.document)
            self.assertTrue(path.is_symlink())
            path.unlink()


class GitBootstrapTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.repo = self.path / "repo"
        self.repo.mkdir()
        self.project = self.repo / "project"
        self.engine = StateEngine(self.project, repo=self.repo)
        self.document = initial_document()
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        # Exercise the Windows default while preserving canonical exact bytes.
        # This noncanonical policy is committed before bootstrap, not a state edit.
        self.git("config", "core.autocrlf", "true")
        (self.repo / ".gitattributes").write_bytes(b"project.yaml -text\nevents.jsonl -text\n")
        (self.repo / "marker").write_text("base", encoding="utf-8")
        self.git("add", "marker", ".gitattributes")
        self.git("commit", "-m", "empty canonical base")
        self.remote = self.path / "remote.git"
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-u", "origin", "main")
        self.git("fetch", "origin")
        self.base = capture_bootstrap_base(self.repo, self.project)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    def assert_rejected(self, base=None):
        before = tuple(p.read_bytes() if p.is_file() else None for p in
                       (self.engine.project_path, self.engine.events_path))
        with self.assertRaises(RemoteStateConflict):
            self.engine.bootstrap(self.document, handoff_base=self.base if base is None else base)
        self.assertEqual(before, tuple(p.read_bytes() if p.is_file() else None for p in
                                      (self.engine.project_path, self.engine.events_path)))

    def test_explicit_bootstrap_evidence_and_exact_git_retry(self):
        with self.assertRaises(RemoteStateConflict):
            self.engine.bootstrap(self.document)
        verify_bootstrap_base(self.repo, self.project, self.base)
        self.assertNotIn("remote_url", self.base)
        self.assertEqual(len(self.base["remote_identity_sha256"]), 64)
        self.assertEqual(set(self.base["canonical_attributes"]),
                         {"project/project.yaml", "project/events.jsonl"})
        for attributes in self.base["canonical_attributes"].values():
            self.assertEqual(attributes["text"], "unset")
        result = self.engine.bootstrap(self.document, handoff_base=self.base)
        with patch("aivideo.state_engine._atomic_replace", side_effect=AssertionError("retry wrote")):
            self.assertEqual(self.engine.bootstrap(self.document, handoff_base=self.base), result)
        with self.assertRaises(RemoteStateConflict):
            capture_bootstrap_base(self.repo, self.project)
        with self.assertRaises(RemoteStateConflict):
            self.engine.bootstrap(self.document)
        # Checkpoint genesis before ordinary Git-backed handoff, as for all writes.
        self.git("add", "project/project.yaml", "project/events.jsonl")
        self.git("commit", "-m", "genesis checkpoint")
        self.git("push", "origin", "main")
        self.git("fetch", "origin")
        handoff = capture_handoff_base(self.repo, self.project)
        self.engine.begin_transaction(TransactionRequest(0, result.project_hash,
            "first-git", "tester", "EDIT", handoff), {**self.document, "state_revision": 1})
        event, = self.engine.inspect_history()
        self.assertEqual((event["state_revision_before"], event["state_revision_after"]), (0, 1))
        self.assertEqual(event["project_hash_before"], result.project_hash)

    def assert_attributes_rejected_before_canonical_writes(self):
        with self.assertRaises(RemoteStateConflict):
            capture_bootstrap_base(self.repo, self.project)
        with self.assertRaises(RemoteStateConflict):
            verify_bootstrap_base(self.repo, self.project, self.base)
        with patch("aivideo.state_engine._atomic_replace", side_effect=AssertionError("unsafe bootstrap wrote")):
            self.assert_rejected()
        self.assertFalse(self.engine.project_path.exists())
        self.assertFalse(self.engine.events_path.exists())

    def test_autocrlf_without_nontext_attributes_fails_before_bootstrap(self):
        # An empty working attribute file overrides the previously committed one.
        (self.repo / ".gitattributes").write_bytes(b"")
        self.assertEqual(self.git("config", "core.autocrlf"), "true")
        self.assert_attributes_rejected_before_canonical_writes()

    def test_each_canonical_path_requires_effective_nontext_attribute(self):
        for raw in (b"project.yaml -text\n", b"events.jsonl -text\n",
                    b"project.yaml text\nevents.jsonl -text\n",
                    b"project.yaml -text\nevents.jsonl text=auto\n",
                    b"project.yaml eol=lf\nevents.jsonl -text\n"):
            with self.subTest(attributes=raw):
                (self.repo / ".gitattributes").write_bytes(raw)
                self.assert_attributes_rejected_before_canonical_writes()

    def test_effective_nested_and_info_attributes_override_root_policy(self):
        self.project.mkdir()
        nested = self.project / ".gitattributes"
        nested.write_bytes(b"events.jsonl text=auto\n")
        self.assert_attributes_rejected_before_canonical_writes()
        nested.unlink()
        info = self.repo / ".git" / "info" / "attributes"
        info.write_bytes(b"project/project.yaml text\n")
        self.assert_attributes_rejected_before_canonical_writes()

    def test_nontext_paths_with_other_byte_conversions_are_rejected(self):
        for name in ("project.yaml", "events.jsonl"):
            for attribute in ("filter=bootstrap-test", "ident", "working-tree-encoding=UTF-16"):
                with self.subTest(name=name, attribute=attribute):
                    raw = f"project.yaml -text\nevents.jsonl -text\n{name} {attribute}\n"
                    (self.repo / ".gitattributes").write_bytes(raw.encode("utf-8"))
                    self.assert_attributes_rejected_before_canonical_writes()

    def test_safe_attribute_change_still_invalidates_captured_evidence(self):
        # -filter is also safe, but this is a different effective attribute set.
        (self.repo / ".gitattributes").write_bytes(
            b"project.yaml -text -filter\nevents.jsonl -text\n")
        changed = capture_bootstrap_base(self.repo, self.project)
        self.assertNotEqual(changed["canonical_attributes"], self.base["canonical_attributes"])
        with self.assertRaises(RemoteStateConflict):
            verify_bootstrap_base(self.repo, self.project, self.base)
        with patch("aivideo.state_engine._atomic_replace", side_effect=AssertionError("stale evidence wrote")):
            self.assert_rejected()
        self.assertEqual(self.engine.bootstrap(self.document, handoff_base=changed).state_revision, 0)

    def test_attribute_change_blocks_exact_retry_without_canonical_mutation(self):
        genesis = self.engine.bootstrap(self.document, handoff_base=self.base)
        before = (self.engine.project_path.read_bytes(), self.engine.events_path.read_bytes())
        (self.repo / ".gitattributes").write_bytes(b"* text=auto\n")
        with self.assertRaises(RemoteStateConflict):
            verify_bootstrap_base(self.repo, self.project, self.base, genesis)
        self.assert_rejected()
        self.assertEqual(before, (self.engine.project_path.read_bytes(), self.engine.events_path.read_bytes()))

    def test_old_evidence_without_attribute_binding_fails_closed(self):
        old = {key: value for key, value in self.base.items() if key != "canonical_attributes"}
        with self.assertRaises(RemoteStateConflict):
            verify_bootstrap_base(self.repo, self.project, old)
        self.assert_rejected(old)

    def test_missing_malformed_or_wrong_kind_evidence_conflicts(self):
        for evidence in ({}, None, [], {"handoff_version": "1.0"},
                         {**self.base, "bootstrap_version": "2.0"}):
            with self.subTest(evidence=evidence):
                with self.assertRaises(RemoteStateConflict):
                    verify_bootstrap_base(self.repo, self.project, evidence)
        for field in self.base:
            with self.subTest(field=field):
                self.assert_rejected({**self.base, field: "different"})

    def test_stale_origin_tracking_ref_and_changed_local_head_conflict(self):
        old = self.git("rev-parse", "HEAD")
        self.git("commit", "--allow-empty", "-m", "local advance")
        self.assert_rejected()
        with self.assertRaises(RemoteStateConflict):
            capture_bootstrap_base(self.repo, self.project)
        new = self.git("rev-parse", "HEAD")
        self.git("reset", "--hard", old)
        self.git("update-ref", "refs/remotes/origin/main", new)
        self.assert_rejected()

    def test_remote_identity_branch_detached_and_missing_origin_conflict(self):
        self.git("remote", "set-url", "origin", str(self.path / "different.git"))
        self.assert_rejected()
        self.git("remote", "set-url", "origin", str(self.remote))
        self.git("switch", "-c", "other")
        self.git("update-ref", "refs/remotes/origin/other", self.base["base_commit"])
        self.assert_rejected()
        self.git("checkout", "--detach")
        self.assert_rejected()
        self.git("switch", "main")
        self.git("remote", "remove", "origin")
        self.assert_rejected()

    def test_project_location_is_bound_and_outside_repo_rejected(self):
        with self.assertRaises(RemoteStateConflict):
            StateEngine(self.repo / "other", repo=self.repo).bootstrap(self.document, handoff_base=self.base)
        with self.assertRaises(RemoteStateConflict):
            capture_bootstrap_base(self.repo, self.path / "outside")

    def test_committed_canonical_files_cannot_be_hidden_by_worktree_deletion(self):
        self.project.mkdir()
        for name in ("project.yaml", "events.jsonl"):
            with self.subTest(name=name):
                path = self.project / name
                path.write_bytes(b"")
                self.git("add", f"project/{name}")
                self.git("commit", "-m", "canonical base occupied")
                self.git("push", "origin", "main")
                self.git("fetch", "origin")
                path.unlink()
                self.assert_rejected({**self.base, "base_commit": self.git("rev-parse", "HEAD")})
                with self.assertRaises(RemoteStateConflict):
                    capture_bootstrap_base(self.repo, self.project)
                self.git("reset", "--hard", self.base["base_commit"])
                self.git("update-ref", "refs/remotes/origin/main", self.base["base_commit"])
                subprocess.run(["git", "--git-dir", str(self.remote), "update-ref",
                                "refs/heads/main", self.base["base_commit"]],
                               check=True, capture_output=True)
                self.project.mkdir(exist_ok=True)

    def test_competing_initialization_and_pending_work_fail_closed(self):
        StateEngine(self.project).bootstrap({**self.document, "project_id": "competitor"})
        before = self.engine.project_path.read_bytes()
        with self.assertRaises(StateConflict):
            self.engine.bootstrap(self.document, handoff_base=self.base)
        self.assertEqual(self.engine.project_path.read_bytes(), before)
        with self.assertRaises(RemoteStateConflict):
            verify_bootstrap_base(self.repo, self.project, self.base)
        self.engine.project_path.unlink()
        self.engine.events_path.write_bytes(b"{}\n")
        with self.assertRaises(RemoteStateConflict):
            capture_bootstrap_base(self.repo, self.project)
        self.engine.events_path.write_bytes(b"")
        self.engine.journal.path.write_bytes(b"pending")
        with self.assertRaises(RemoteStateConflict):
            capture_bootstrap_base(self.repo, self.project)

    def test_git_crash_retry_rechecks_remote_even_for_exact_retry(self):
        def fail_project(path, raw):
            if path == self.engine.project_path:
                raise OSError("interrupted")
            _atomic_replace(path, raw)
        with patch("aivideo.state_engine._atomic_replace", side_effect=fail_project):
            with self.assertRaises(OSError):
                self.engine.bootstrap(self.document, handoff_base=self.base)
        self.assertEqual(capture_bootstrap_base(self.repo, self.project), self.base)
        self.engine.bootstrap(self.document, handoff_base=self.base)
        self.git("commit", "--allow-empty", "-m", "remote advanced")
        advanced = self.git("rev-parse", "HEAD")
        self.git("reset", "--hard", self.base["base_commit"])
        self.git("update-ref", "refs/remotes/origin/main", advanced)
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
