"""Print a non-secret local tool snapshot; no provider or network calls."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aivideo.environment import capture_environment


if __name__ == "__main__":
    print(json.dumps(capture_environment(), indent=2, sort_keys=True))
