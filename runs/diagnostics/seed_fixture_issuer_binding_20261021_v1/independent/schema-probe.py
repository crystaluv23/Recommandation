"""Both supported synthetic fixture schemas retain strict native issuer checks."""
from pathlib import Path
from copy import deepcopy
from contextlib import ExitStack
from unittest.mock import patch
import json,hashlib
from stock_opportunity_agent.signal_library import SignalSpec,_audit_deterministic_fixture
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
R=Path('/Users/l/Project/Recommandation');O=R/'runs/diagnostics/seed_fixture_issuer_binding_20261021_v1/independent'
catalog=json.loads((R/'configs/signals_v1.json').read_text());item=next(x for x in catalog['signals'] if x['spec']['signal_id']=='cash_reserves');spec=SignalSpec.from_dict(item['spec']);base=item['tests'][0];rows=[];forbidden=[]
def block(*a,**k):forbidden.append(True);raise AssertionError('No network/model/labels')
with ExitStack() as guards:
 guards.enter_context(patch('socket.socket',block))
 guards.enter_context(patch.object(LabelStore,'load',block))
 for name in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores'):guards.enter_context(patch.object(StructuredRoleClient,name,block))
 for schema in ('typed','nested'):
  positive=deepcopy(base)
  if schema=='nested':
   payload=json.loads(positive['documents'][0]['content']);concepts={}
   for fact in payload['facts']:
    row={k:fact[k] for k in ('start','end')};row.update(val=fact['value'],filed=payload['filing_date'],form=payload['form'])
    concepts.setdefault(fact['tag'],{'units':{}})['units'].setdefault(fact['unit'],[]).append(row)
   positive['documents'][0]['content']=json.dumps({'cik':'0000000001','facts':{'us-gaap':concepts}},sort_keys=True,separators=(',',':'))
  for variation in ('positive','missing_body','missing_metadata','mismatch'):
   fixture=deepcopy(positive);raw=fixture['documents'][0];body=json.loads(raw['content'])
   if variation=='missing_body':body.pop('cik')
   if variation=='missing_metadata':raw.pop('metadata')
   if variation=='mismatch':raw['metadata']['cik']='0000000002'
   raw['content']=json.dumps(body,sort_keys=True,separators=(',',':'))
   try:_audit_deterministic_fixture(spec,fixture,index=0);accepted=True;error=None
   except Exception as exc:accepted=False;error={'type':type(exc).__name__,'message':str(exc)}
   assert accepted==(variation=='positive'),(schema,variation,error)
   rows.append({'schema':schema,'variant':variation,'native_capability_fixture_accepted':accepted,'error':error})
assert not forbidden
out={'verdict':'PASS_both_synthetic_schemas_strict_without_gate_changes','controls':rows,'forbidden_calls':forbidden,'limits':'Only synthetic fixtures and native in-memory capability auditor. No real company/source, production Registry or model behavior established.'}
(O/'schema-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
