"""Independent sealed-source audit and numeric self-cost counterexample; no execution."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json
R=Path(__file__).resolve().parents[4]
O=Path(__file__).resolve().parent
S=R/'runs/diagnostics/mining_locator_generalization_20261023_v1/stage'
def size(messages):return len(json.dumps(messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
rows=[]
for sample in ('a','b'):
 root=S/sample
 req={p.stem:json.loads(p.read_text())['request'] for p in (root/'requests').glob('*.json')}
 consumed={p.stem for p in (root/'exchange/receipts').glob('*.json')}
 answered=[];pending=[]
 for key,q in req.items():
  payload=json.loads(next(m['content'] for m in q['messages'] if m['role']=='user'))
  row={'request_hash':key,'reservation':size(q['messages'])+q['max_output_tokens'],'request_budget_visible':'request_budget' in payload}
  (answered if key in consumed else pending).append(row)
 views=[json.loads(p.read_text()) for p in sorted(root.glob('view-*.json'))]
 rows.append({'sample':sample,'answered':answered,'pending_prepared':pending,'answered_total':sum(x['reservation'] for x in answered),'views':len(views),'all_views_lack_request_budget':all('request_budget' not in v for v in views),'failure':json.loads((root/'failure.json').read_text())['error']})
# Fully explicit finite two-cycle for x = fixed_cost + decimal_len(x) + decimal_len(cap-x).
# JSON numbers are unpadded; constant includes every other byte. At x=99/100 digit width cancels here;
# choose cap=1099 so cap-x crosses 1000 at x=99/100, constructing a declining reservation step.
cycles=[]
for cap in range(1000,1200):
 for base in range(80,110):
  def f(x):return base+len(str(x))+len(str(cap-x))
  for x in range(90,115):
   y=f(x)
   if x!=y and f(y)==x:
    cycles.append({'cap':cap,'fixed_cost':base,'x':x,'f_x':y,'f_f_x':f(y)});break
  if cycles:break
 if cycles:break
assert cycles
old=json.loads((O/'frozen-controls-v1.json').read_text())
preserved=[str(p) for item in old['source_bindings'] if '/stage/' in item['path'] and (p:=Path(item['path'])).is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']]
result={'at':datetime.now(timezone.utc).isoformat(),'evidence':'read-only sealed audit and explicit numeric algebra, no model execution','original_samples':rows,'numeric_fixed_point_counterexample':cycles[0],'plain_numeric_fixed_point_not_guaranteed':True,'fixed_width_risk':'Any fixed width must fit all accepted limits and computed reservation; otherwise width itself changes. A bound or dynamically proven width is necessary.','sealed_bound_files_unchanged':len(preserved),'external_API':0,'fresh_authors':0}
(O/'baseline-results-v1.json').open('x').write(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps(result,sort_keys=True))
