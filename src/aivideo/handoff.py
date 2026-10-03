"""Git base evidence for explicit single-workstation handoff."""

import subprocess
import hashlib
import json
from pathlib import Path

from .state_engine import RemoteStateConflict, StateEngine
from .schema import SchemaError


def _git(repo: Path, *args):
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True, timeout=5)
    return result.stdout.strip()


def _git_bytes(repo: Path, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          check=True, timeout=5).stdout


def _bootstrap_attributes(repo: Path, names: list[str]):
    """Prove byte-preserving canonical paths without invoking any Git filters."""
    attributes = ("text", "eol", "crlf", "filter", "ident", "working-tree-encoding")
    raw = _git_bytes(repo, "check-attr", "-z", *attributes, "--", *names)
    parts = raw.decode("utf-8").split("\0")
    if parts.pop() != "" or len(parts) != len(names) * len(attributes) * 3:
        raise RemoteStateConflict("cannot inspect effective canonical Git attributes")
    result = {name: {} for name in names}
    for name, attribute, value in zip(parts[::3], parts[1::3], parts[2::3]):
        if name not in result or attribute not in attributes or attribute in result[name]:
            raise RemoteStateConflict("unexpected canonical Git attribute result")
        result[name][attribute] = value
    for name, values in result.items():
        # Explicit -text disables autocrlf, eol and the legacy crlf attribute.
        # Other conversions operate even on non-text paths and must be disabled.
        if values["text"] != "unset":
            raise RemoteStateConflict(f"bootstrap requires effective -text for {name}")
        for attribute in ("filter", "ident", "working-tree-encoding"):
            if values[attribute] not in ("unset", "unspecified"):
                raise RemoteStateConflict(f"bootstrap forbids Git {attribute} conversion for {name}")
    return result


def _bootstrap_identity(repo: Path, project_dir: Path):
    repo = Path(repo).resolve()
    project_dir = Path(project_dir).resolve()
    relative = project_dir.relative_to(repo)
    if Path(_git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise RemoteStateConflict("bootstrap repository must be the Git worktree root")
    branch = _git(repo, "branch", "--show-current")
    if not branch:
        raise RemoteStateConflict("bootstrap requires an attached branch")
    commit = _git(repo, "rev-parse", "HEAD")
    if _git(repo, "rev-parse", f"refs/remotes/origin/{branch}") != commit:
        raise RemoteStateConflict("fetched origin branch differs from bootstrap HEAD")
    names = [(relative / name).as_posix() for name in ("project.yaml", "events.jsonl")]
    if _git_bytes(repo, "--literal-pathspecs", "ls-tree", "-z", commit, "--", *names):
        raise RemoteStateConflict("bootstrap committed base already contains canonical files")
    # Bind evidence to the project location as well as the repository identity.
    return {
        "bootstrap_version": "1.1",
        "remote_identity_sha256": hashlib.sha256(_git(repo, "remote", "get-url", "origin").encode("utf-8")).hexdigest(),
        "branch": branch, "base_commit": commit,
        "project_path": relative.as_posix(),
        "canonical_attributes": _bootstrap_attributes(repo, names),
    }


def _check_bootstrap_worktree(project_dir: Path, snapshot=None):
    project_dir = Path(project_dir)
    project = project_dir / "project.yaml"
    events = project_dir / "events.jsonl"
    journal = project_dir / ".pending-transaction.json"
    if journal.exists() or journal.is_symlink():
        raise RemoteStateConflict("pending transaction prevents bootstrap handoff")
    if project.is_symlink() or events.is_symlink():
        raise RemoteStateConflict("bootstrap canonical files must not be symlinks")
    if events.exists() and events.read_bytes() != b"":
        raise RemoteStateConflict("bootstrap working history must be empty")
    if snapshot is None:
        if project.exists():
            raise RemoteStateConflict("bootstrap working project already exists")
    else:
        actual = StateEngine(project_dir).inspect_consistency()
        if (actual.access != "WRITABLE_VERSION" or actual.state_revision != 0 or
                actual != snapshot):
            raise RemoteStateConflict("bootstrap retry differs from the genesis snapshot")


def capture_bootstrap_base(repo: Path, project_dir: Path):
    """Capture an uninitialized Git base after the operator fetches origin.

    Performs only local Git reads. Empty prepared history is permitted; an
    existing project is not. Retain this evidence for an exact bootstrap retry.
    Both canonical paths require effective -text and no other byte conversions.
    """
    try:
        base = _bootstrap_identity(repo, project_dir)
        _check_bootstrap_worktree(project_dir)
        return base
    except (ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise RemoteStateConflict("cannot capture bootstrap base and fetched origin ref") from exc


def verify_bootstrap_base(repo: Path, project_dir: Path, base: dict, snapshot=None):
    """Verify fetched refs and absent committed canonical files before bootstrap.

    A snapshot permits only an exact revision-zero retry in the working tree.
    Effective canonical attributes must remain byte-preserving and match capture.
    Like ordinary handoff, this cannot detect a remote advance until fetch and
    does not provide a distributed lock. No network request is performed.
    """
    try:
        actual = _bootstrap_identity(repo, project_dir)
        for field, value in actual.items():
            if value != base[field]:
                raise RemoteStateConflict(f"bootstrap base differs: {field}")
        _check_bootstrap_worktree(project_dir, snapshot)
    except (KeyError, TypeError, ValueError, SchemaError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, OSError) as exc:
        raise RemoteStateConflict("cannot verify bootstrap base and fetched origin ref") from exc


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
