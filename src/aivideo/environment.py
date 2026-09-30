"""Local-only machine profile and allowlisted tool-version capture."""

import json
import platform
import subprocess
from pathlib import Path


LOCAL_PROFILE_NAME = "local-profile.json"
ALLOWED_PROFILE_KEYS = {"profile_version", "root_mappings", "capabilities", "constraints"}
TOOLS = {"git": ["git", "--version"], "codex": ["codex", "--version"], "node": ["node", "--version"], "npm": ["npm.cmd", "--version"], "python": ["python", "--version"]}


def load_local_profile(project_dir: Path):
    path = Path(project_dir) / LOCAL_PROFILE_NAME
    if not path.exists():
        return None
    profile = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict) or set(profile) - ALLOWED_PROFILE_KEYS:
        raise ValueError("local profile contains unsupported keys")
    return profile


def capture_environment():
    """Returns an in-memory snapshot; caller controls local persistence."""
    versions = {}
    for name, command in TOOLS.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, check=False)
            versions[name] = result.stdout.strip() or None if result.returncode == 0 else None
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            versions[name] = None
    if versions["npm"] is None:
        try:
            result = subprocess.run(["npm", "--version"], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=5, check=False)
            if result.returncode == 0:
                versions["npm"] = result.stdout.strip() or None
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
    if versions["python"] is None:
        try:
            result = subprocess.run(["py", "-3", "--version"], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=5, check=False)
            if result.returncode == 0:
                versions["python"] = result.stdout.strip() or None
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
    return {"snapshot_version": "1.0", "platform": platform.system(), "tools": versions}
