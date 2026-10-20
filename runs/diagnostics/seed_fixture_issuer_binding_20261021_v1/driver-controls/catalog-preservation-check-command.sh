python3 - <<'PY'
import hashlib,json,subprocess
from pathlib import Path
p=Path('configs/signals_v1.json');new=p.read_bytes();old=subprocess.check_output(['git','show','HEAD:configs/signals_v1.json'])
stripped=new.replace(b'"metadata": {"cik": "0000000001"}, ',b'').replace(b'\\"cik\\":\\"0000000001\\",',b'')
assert stripped==old,'catalog changed beyond six explicit identity bindings'
paths=['configs/signals_v1.json','spec/src/stock_opportunity_agent/signal_library.md','spec/src/stock_opportunity_agent/data/sec_company_facts.md','tests/test_seed_fixture_issuer_binding.py']
print(json.dumps({'catalog_original_bytes_sha256':hashlib.sha256(old).hexdigest(),'catalog_identity_only_change':stripped==old,'code_changes':False,'bindings':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in paths}},indent=2))
PY
git diff --stat -- configs/signals_v1.json spec/src/stock_opportunity_agent/signal_library.md spec/src/stock_opportunity_agent/data/sec_company_facts.md
git status --short --untracked-files=no
