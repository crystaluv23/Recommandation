"""Independent whole fact-receipt progress checks. No model, network, or business labels."""
from __future__ import annotations
import copy,hashlib,json,socket,traceback
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from stock_opportunity_agent.data.raw_info import RawInfoDocument,RawInfoStore
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.mining_agent_tools import EvidenceFact
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController,InvalidMiningAction
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
from stock_opportunity_agent.research.stage_contracts import json_bytes
socket.socket=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden'))
ROOT=Path('/Users/l/Project/Recommandation');BASE=Path(__file__).resolve().parent
FILES=['spec/src/stock_opportunity_agent/research/signal_mining_agent.md','spec/scripts/run_mining_taxonomy_consumer_stage.md','src/stock_opportunity_agent/research/mining_controller.py','src/stock_opportunity_agent/research/mining_role_model.py','tests/test_mining_fact_read_progress.py']
def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
BEFORE=hashes();CHECKS=[]
def check(name,fn):
 try:CHECKS.append({'name':name,'pass':True,'detail':fn()})
 except Exception as e:CHECKS.append({'name':name,'pass':False,'error_type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc()})
def require(x,msg='Expected true'):
 if not x:raise AssertionError(msg)
original=json.loads((ROOT/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/0671.json').read_text())
doc=RawInfoDocument.create(**{k:(datetime.fromisoformat(original[k]) if k in ('published_at','available_at') else original[k]) for k in ('document_id','company_id','source_type','published_at','available_at','content','metadata')})
# Opaque group copied solely from frozen source-reference; no business truth source.
label=json.loads((ROOT/'runs/diagnostics/mining_taxonomy_consumer_20261023_v1/reference/source-reference.json').read_text())['opaque_existing_metadata']['label_map']['case-008']
def controller(*,source=True,aliases=(),limit=50):
 case=SimpleNamespace(case_id='cik_0000800457:20250731',company_id=doc.company_id,prediction_time=datetime(2025,7,31,tzinfo=timezone.utc),ground_truth=SimpleNamespace(is_surge=label=='positive'))
 c=LabelAwareMiningController(store=RawInfoStore(documents=(doc,) if source else ()),model=object(),case_pairs=(('case-008',case),),measurable_evidence_manifest={},signal_catalog=(),seed='discovery',heavy_action_limit=limit,label_map={'case-008':label},identity_aliases=aliases,research_axis={'axis_id':'source-consumption-control'})
 if source:c._execute_fetch({'action':'fetch_evidence','rationale':['Controlled historical source fetch.'],'case_refs':['case-008'],'source_families':['sec_company_facts'],'max_documents':1})
 if not source:c._state='evidence_ready'  # Explicit synthetic already-fetched boundary fixture.
 return c
def read(c,ref):
 action={'action':'read_span','rationale':['Read original provenance.'],'fact_ref':ref}
 c._validate_action_shape(action);c._execute('read_span',action)
 return copy.deepcopy(c._last_action_result)
def ocf(c):
 return sorted((f for f in c._facts.values() if f.concept=='NetCashProvidedByUsedInOperatingActivities'),key=lambda f:f.period['end'])
def syn(c,n,context='{}'):
 ref=f'synthetic-fact-{n:03d}'
 c._facts[ref]=EvidenceFact(ref,'case-008','SyntheticMetric','USD',{'end':'2024-06-30'},str(n),'latest','synthetic-document',context,'f'*64,'2024-08-02T00:00:00+00:00',taxonomy='synthetic')
 return ref

def actual_two():
 c=controller();fs=ocf(c);require(len(fs)==2)
 require('structured_read_progress' not in c._model_view())
 receipts=[read(c,f.fact_ref) for f in fs]
 action={'action':'compare_groups','rationale':['Compare the selected historical concept.'],'concepts':[fs[0].concept]}
 c._validate_action_shape(action);c._execute('compare_groups',action)
 view=c._model_view();page=view['structured_read_progress']
 expected=[{**{k:v for k,v in r.items() if k!='action'},'read_count':1} for r in reversed(receipts)]
 require(page['items']==expected)
 require(view['last_action_result']['action']=='compare_groups')
 require(all(row['fact']['taxonomy']=='us-gaap' for row in page['items']))
 require([row['fact']['value'] for row in page['items']]==['9506313','4342261'])
 require(c.ledger.entries[1].output_hash==canonical_json_hash({k:v for k,v in receipts[0].items() if k!='action'}))
 captured={}
 def complete(**kwargs):captured.update(copy.deepcopy(kwargs));return {'action':'record_deferred','rationale':['Controlled module boundary.']},AgentUsage()
 MiningAgentRoleModel(SimpleNamespace(complete_json=complete)).next_action(view)
 require(captured['payload']['structured_read_progress']==page)
 require('structured_read_progress' in captured['system_prompt'])
 return {'fact_refs':[f.fact_ref for f in fs],'values':['4342261','9506313'],'whole_receipt_bytes':json_bytes(page['items']),'actual_adapter_payload_bytes':json_bytes(captured['payload']),'source_rows_visible_after_compare':True,'native_transport_budget_not_recomputed':True}
check('actual_source_two_receipts_and_role_adapter_after_compare',actual_two)

def dedup_mutation():
 c=controller();fs=ocf(c)
 for ref in (fs[0].fact_ref,fs[1].fact_ref,fs[0].fact_ref):read(c,ref)
 view=c._model_view();page=view['structured_read_progress'];before=copy.deepcopy(c._fact_read_progress)
 require([r['fact_ref'] for r in page['items']]==[fs[0].fact_ref,fs[1].fact_ref])
 require([r['read_count'] for r in page['items']]==[2,1])
 page['items'][0]['fact']['period']['start']='9999-01-01';page['items'][0]['case_refs'].append('forged');page['items'][0]['masked']='forged'
 require(c._fact_read_progress==before)
 require(c._heavy_used==4 and sum(e.action=='read_span' for e in c.ledger.entries)==3)
 return 'Recent-first dedup, read_count, deep-copy isolation and ordinary heavy/ledger counts agree'
check('dedup_recency_nested_mutation_and_cost',dedup_mutation)

def atomic_changed():
 rows=[]
 for field,new in [('taxonomy','different'),('value','-999'),('period',{'end':'2024-01-01'}),('content_hash','e'*64),('document_ref','another-document'),('available_at','2024-09-01T00:00:00+00:00'),('case_ref','another-case'),('exact_span','changed context')]:
  c=controller();f=ocf(c)[0];read(c,f.fact_ref)
  before=(copy.deepcopy(c._fact_read_progress),copy.deepcopy(c._last_action_result),c.ledger.to_dict(),c._heavy_used)
  c._facts[f.fact_ref]=replace(f,**{field:new})
  try:read(c,f.fact_ref)
  except InvalidMiningAction as e:require('same fact_ref' in str(e))
  else:raise AssertionError('Changed receipt accepted: '+field)
  after=(copy.deepcopy(c._fact_read_progress),copy.deepcopy(c._last_action_result),c.ledger.to_dict(),c._heavy_used)
  require(before==after,'Nonatomic changed receipt: '+field)
  rows.append(field)
 return {'changed_bindings_rejected_atomically':rows}
check('changed_same_ref_all_source_bindings_atomic',atomic_changed)

def paging():
 c=controller(source=False)
 refs=[syn(c,n) for n in range(15)]
 for ref in refs:read(c,ref)
 page=c._model_view()['structured_read_progress']
 require(len(page['items'])==12 and [r['fact_ref'] for r in page['items']]==list(reversed(refs))[:12])
 require(page['counts']['available']==15 and not page['selection_is_exhaustive'])
 require(json_bytes(page['items'])<=8000)
 omitted=refs[0];read(c,omitted);page2=c._model_view()['structured_read_progress']
 require(page2['items'][0]['fact_ref']==omitted and page2['items'][0]['read_count']==2)
 require(c._heavy_used==16)
 return {'counts':page['counts'],'reread_first':page2['items'][0]['fact_ref'],'max_units':len(page['items']),'unit_bytes':json_bytes(page['items'])}
check('fifteen_units_cap_and_omitted_ref_reread',paging)

def unicode_oversize():
 c=controller(source=False);a=syn(c,1);b=syn(c,2,'长'*3000);read(c,a);read(c,b)
 page=c._model_view()['structured_read_progress'];require([r['fact_ref'] for r in page['items']]==[a])
 require(page['counts']['oversized']==1 and page['oversized_entries'][0]['fact_ref']==b)
 require(page['oversized_entries'][0]['required_bytes']>8000 and not page['selection_is_exhaustive'])
 require(c._last_action_result['masked']=='长'*3000)
 require(json_bytes(page['items'])<=8000)
 return {'counts':page['counts'],'oversized_entries':page['oversized_entries'],'last_action_full_chars':len(c._last_action_result['masked'])}
check('unicode_whole_oversize_and_smaller_complete_unit',unicode_oversize)

def near_byte_boundary():
 outcomes=[]
 for length in (7400,7600,7800,8000):
  c=controller(source=False);ref=syn(c,1,'a'*length);read(c,ref);page=c._model_view()['structured_read_progress']
  items=page['items'];require(json_bytes(items)<=8000)
  require(not items or items[0]['masked']=='a'*length)
  require(bool(items)!=(page['counts']['oversized']>0))
  outcomes.append({'raw_context_chars':length,'returned':bool(items),'selected_unit_bytes':json_bytes(items),'oversized':page['counts']['oversized']})
 return outcomes
check('serializer_boundaries_no_partial_unit',near_byte_boundary)

def aliases_and_otheractions():
 c=controller(source=False,aliases=('Private Issuer',))
 a=syn(c,1,'Private Issuer evidence.');b=syn(c,2,'Other complete evidence.')
 read(c,a);read(c,b);snapshot=copy.deepcopy(c._fact_read_progress)
 for action in ({'action':'compare_groups','rationale':['Inspect defined basis.'],'concepts':['SyntheticMetric']},{'action':'compute_statistic','rationale':['Explicit arithmetic only.'],'rule':'latest_over_latest','fact_refs':[a,b]}):
  c._validate_action_shape(action);c._execute(action['action'],action)
  require(c._fact_read_progress==snapshot)
 page=c._model_view()['structured_read_progress'];require('Private Issuer' not in json.dumps(page))
 require(all(r['masked'] for r in page['items']))
 return {'read_units_preserved_across_compare_compute':True,'alias_not_in_page':True,'explicit_arithmetic_not_disabled':True}
check('intervening_actions_mask_and_generic_arithmetic',aliases_and_otheractions)

def replay():
 def reconstruct():
  c=controller();fs=ocf(c)
  for f in (fs[1],fs[0],fs[1]):read(c,f.fact_ref)
  c._execute_compare({'action':'compare_groups','rationale':['Compare.'],'concepts':[fs[0].concept]})
  return c
 c,d=reconstruct(),reconstruct();require(c._model_view()==d._model_view() and c.ledger.to_dict()==d.ledger.to_dict())
 return 'Fresh deterministic action reconstruction identical; no claim of pending LocalRoleExchange or OS-kill recovery'
check('deterministic_action_reconstruction_complete_view_ledger',replay)
AFTER=hashes()
report={'schema':'independent-mining-read-progress-counterexamples-v1','scope':'Actual saved source for meaningful two-operand test; synthetic field/boundary variants only. No fresh model, external API, business label/check/LockedTest, source edits or canonical changes.','passed':sum(r['pass'] for r in CHECKS),'total':len(CHECKS),'checks':CHECKS,'source_hashes_before':BEFORE,'source_hashes_after':AFTER,'source_drift':BEFORE!=AFTER}
(BASE/'progress-counterexample-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'total':report['total'],'source_drift':report['source_drift'],'failures':[r for r in CHECKS if not r['pass']]},ensure_ascii=False,indent=2))
