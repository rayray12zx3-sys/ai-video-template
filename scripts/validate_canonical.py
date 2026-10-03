"""Private-safe local canonical validation; prints only counts and finding codes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from aivideo.state_engine import StateEngine
from aivideo.validators import validate_project
from aivideo.gates import evaluate_gates

parser = argparse.ArgumentParser()
parser.add_argument('project', type=Path)
args = parser.parse_args()
engine = StateEngine(args.project)
try:
    result = validate_project(engine)
    gates = {k: v['status'] for k, v in evaluate_gates(engine).items()}
except Exception:
    # Private path/contents must never enter a traceback in shared validation logs.
    print(json.dumps({'validation': 'FAIL', 'findings': ['CANONICAL_VALIDATION_ERROR']}))
    sys.exit(1)
doc = result.snapshot.document if result.snapshot else {}
print(json.dumps({'validation': 'PASS' if result.ok else 'FAIL',
                  'state_revision': doc.get('state_revision'),
                  'assets': len(doc.get('assets', [])), 'shots': len(doc.get('shots', [])),
                  'dependencies': len(doc.get('dependencies', [])),
                  'findings': sorted({f['code'] for f in result.findings}),
                  'gates_without_trusted_operator': gates}))
sys.exit(0 if result.ok else 1)
