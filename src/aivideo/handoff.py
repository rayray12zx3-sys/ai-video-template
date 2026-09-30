"""Git base evidence for explicit single-workstation handoff."""

import subprocess
import hashlib
import json
from pathlib import Path

from .state_engine import RemoteStateConflict, StateEngine


def _git(repo: Path, *args):
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True, timeout=5)
    return result.stdout.strip()


def _git_bytes(repo: Path, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          check=True, timeout=5).stdout


def capture_handoff_base(repo: Path, project_dir: Path):
    """Capture local evidence. Caller must fetch before relying on remote refs."""
    snapshot = StateEngine(project_dir).read()
    return {
        "handoff_version": "1.0",
        # A remote URL may contain credentials; keep only its fingerprint.
        "remote_identity_sha256": hashlib.sha256(_git(repo, "remote", "get-url", "origin").encode("utf-8")).hexdigest(),
        "branch": _git(repo, "branch", "--show-current"),
        "base_commit": _git(repo, "rev-parse", "HEAD"),
        "state_revision": snapshot.state_revision,
        "project_hash": snapshot.project_hash,
    }


def verify_handoff_base(repo: Path, project_dir: Path, base: dict, snapshot=None):
    """Reject a different local HEAD/tracking ref or canonical base.

    This checks fetched refs only; a stale origin/* ref cannot prove remote
    freshness. The handoff operator must fetch before the next workstation
    writes. No remote lock or network request is performed here.
    """
    try:
        repo = Path(repo).resolve()
        project_dir = Path(project_dir).resolve()
        relative = project_dir.relative_to(repo)
        actual = capture_handoff_base(repo, project_dir)
        for field in ("handoff_version", "remote_identity_sha256", "branch",
                      "base_commit", "state_revision", "project_hash"):
            if actual[field] != base[field]:
                raise RemoteStateConflict(f"handoff base differs: {field}")
        if snapshot is not None and (snapshot.state_revision != base["state_revision"] or
                                     snapshot.project_hash != base["project_hash"]):
            raise RemoteStateConflict("canonical state differs from handoff base")
        tracked = _git(repo, "rev-parse", f"refs/remotes/origin/{base['branch']}")
        if tracked != base["base_commit"]:
            raise RemoteStateConflict("fetched origin branch differs from handoff base")
        project_name = (relative / "project.yaml").as_posix()
        events_name = (relative / "events.jsonl").as_posix()
        committed_project = _git_bytes(repo, "cat-file", "--filters",
                                       f"--path={project_name}",
                                       f"{base['base_commit']}:{project_name}")
        committed_events = _git_bytes(repo, "cat-file", "--filters",
                                      f"--path={events_name}",
                                      f"{base['base_commit']}:{events_name}")
        current_events = (project_dir / "events.jsonl").read_bytes()
        committed_hash = hashlib.sha256(committed_project).hexdigest()
        committed_revision = json.loads(committed_project)["state_revision"]
        if (not current_events.startswith(committed_events) or
                (committed_events and not committed_events.endswith(b"\n"))):
            raise RemoteStateConflict("canonical event history differs from committed base")
        extra = current_events[len(committed_events):]
        if extra:
            first = json.loads(extra.splitlines()[0])
            if (first.get("state_revision_before") != committed_revision or
                    first.get("project_hash_before") != committed_hash):
                raise RemoteStateConflict("local history is not anchored to committed base")
        else:
            current_hash = snapshot.project_hash if snapshot is not None else actual["project_hash"]
            current_revision = snapshot.state_revision if snapshot is not None else actual["state_revision"]
            if current_hash != committed_hash or current_revision != committed_revision:
                raise RemoteStateConflict("canonical state differs from committed base")
    except (KeyError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise RemoteStateConflict("cannot verify handoff base and fetched origin ref") from exc
