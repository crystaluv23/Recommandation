PYTHONPATH=.:src:scripts /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 - <<'PY'
import json
from pathlib import Path
import run_reviewed_owned_partial_stage as s
p=Path('runs/diagnostics/owned_partial_three_controls_20261021_v1/expectations.json');expected=s.read(p)
print('oracle keys',list(expected));print('binding keys',list(expected['bindings']))
for sample in s.CONTROL_NEEDS:
 value=s._control_set(expected,s.CONTROL_STAGE_ROOT/sample,sample,s.CAPTURE_SOURCE_PROFILE,s.CAPTURE_SOURCE_COMMIT)
print('three pure oracle-control checks passed; no prepare/dispatch/source loader')
PY
git diff --check
python3 - <<'PY'
import hashlib,json
from pathlib import Path
print(json.dumps({p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['scripts/run_reviewed_owned_partial_stage.py','spec/scripts/run_reviewed_owned_partial_stage.md','tests/test_reviewed_owned_partial_stage.py']},indent=2))
PY
