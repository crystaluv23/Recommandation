"""Read-only native-cache reconstruction and exact preservation check."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

OUT=Path(__file__).resolve().parent
ROOT=OUT/'control-native'


def snapshot():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in ROOT.rglob('*') if p.is_file()}


if __name__=='__main__':
    before=snapshot()
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':'src:scripts:tests:.'}
    start=time.monotonic()
    run=subprocess.run(['/Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',str(ROOT/'driver.py')],
        env=env,capture_output=True,text=True)
    after=snapshot()
    result={'scope':'exact native cache reconstruction only; not OS interruption or whole-loop recovery',
        'returncode':run.returncode,'stdout':run.stdout,'stderr':run.stderr,'elapsed_seconds':time.monotonic()-start,
        'files_before':len(before),'files_after':len(after),'all_unchanged':before==after,
        'changed':[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)],
        'receipts':len(list((ROOT/'exchange/receipts').glob('*.json'))),'bindings':before}
    (OUT/'restore.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='bindings'}))
    if run.returncode or before!=after: raise SystemExit(1)
