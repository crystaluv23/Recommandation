"""Independent synthetic counterexamples; no model, API or business labels."""
import json, hashlib, traceback
from pathlib import Path
from copy import deepcopy
from dataclasses import replace, asdict
from tests.test_mining_controller import _fixture_store, _controller
from stock_opportunity_agent.research.mining_controller import InvalidMiningAction
from stock_opportunity_agent.research.stage_contracts import json_bytes
BASE=Path(__file__).parent
FILES=['spec/src/stock_opportunity_agent/research/signal_mining_agent.md','src/stock_opportunity_agent/research/mining_controller.py','src/stock_opportunity_agent/research/mining_role_model.py']
ROOT=Path('/Users/l/Project/Recommandation')
hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
rows=[]
def fresh():
 cases,store=_fixture_store()
 c=_controller(store,cases,object(),seed='discovery',heavy_action_limit=100)
 c._execute_fetch({'action':'fetch_evidence','rationale':['Synthetic source fixture.'],'case_refs':['case-001','case-002'],'source_families':['company_facts'],'max_documents':1})
 return c
def compare(c,concepts):
 c._execute_compare({'action':'compare_groups','rationale':['Synthetic comparison fixture.'],'concepts':concepts})
def read(c,ref):
 c._read_fact_span({'action':'read_span','rationale':['Synthetic source read.'],'fact_ref':ref})
def test(name,fn):
 try:
  detail=fn()
  rows.append({'name':name,'passed':True,'detail':detail})
 except Exception as e: rows.append({'name':name,'passed':False,'error':repr(e),'traceback':traceback.format_exc()})
def loc(c,concept):
 return next(x for x in c._model_view()['comparison_progress']['items'] if x['concept']==concept)
def view_only(reverse=False):
 c=fresh()
 # Concept selection is from current public manifest, never private fact graph.
 concept=c._model_view()['measurable_evidence_manifest']['structured_financial_concepts'][0]['concept']
 compare(c,[concept])
 selected=[]
 for which in (('comparable_prior','latest') if reverse else ('latest','comparable_prior')):
  v=c._model_view()
  unit=next(x for x in v['comparison_progress']['items'] if x['concept']==concept)
  group=next(g for g in unit['groups'].values() if g[which])
  ref=next(iter(group[which].values()))['fact_ref']
  assert ref in v['known_fact_refs']
  selected.append(ref); read(c,ref)
 end=c._model_view()
 assert len(end['structured_read_progress']['items'])==2
 assert len(set(selected))==2
 assert end['comparison_progress']['snapshot_status']=='current'
 return {'selected_from_current_progress':selected,'read_receipts':2}
test('T01_view_only_current_then_prior',lambda:view_only(False))
test('T02_view_only_prior_then_current',lambda:view_only(True))
def complete():
 c=fresh(); concept=c._model_view()['measurable_evidence_manifest']['structured_financial_concepts'][0]['concept']
 compare(c,[concept,'Absent',concept]); p=c._model_view()['comparison_progress']
 assert [r['concept'] for r in p['items']]==sorted({concept,'Absent'})
 for unit in p['items']:
  assert set(unit['groups'])=={'positive','control'}
  for row in unit['groups'].values():
   assert set(row)=={'case_count','available_cases','latest','comparable_prior','unresolved_basis_cases'}
 assert loc(c,'Absent')['groups']['control']['available_cases']==[]
 compare(c,['Absent']); assert c._model_view()['comparison_progress']['items'][0]['concept']=='Absent'
 return {'duplicates':1,'whole_branches_preserved':True}
test('T03_complete_units_sorted_ties_recent_dedup',complete)
def invalidations():
 results=[]
 for field in ('value','taxonomy','period','exact_span','document_ref','content_hash','available_at','unit','source_display_name','case_ref','record_selection','label_map','research_axis'):
  c=fresh(); concept=next(iter(c._facts.values())).concept; compare(c,[concept])
  original=c._model_view()
  if field=='label_map': c._label_map['case-001']='positive'
  elif field=='research_axis': c.research_axis={'axis':'other'}
  else:
   key=next(iter(c._facts));fact=c._facts[key]; old=getattr(fact,field)
   new={'end':'1900-01-01'} if field=='period' else str(old)+'-changed'
   c._facts[key]=replace(fact,**{field:new})
  v=c._model_view(); assert v['comparison_progress']['snapshot_status']=='invalidated'
  assert v['comparison_progress']['items']==[]
  assert v['last_action_result']=={'action':'compare_groups','snapshot_status':'invalidated'}
  assert original['last_action_result'].get('groups')
  compare(c,['Absent'])
  assert [r['concept'] for r in c._model_view()['comparison_progress']['items']]==['Absent']
  results.append(field)
 return results
test('T04_T05_all_source_fields_group_axis_stale_copies',invalidations)
def idempotence():
 c=fresh();concept=next(iter(c._facts.values())).concept;compare(c,[concept])
 expected=deepcopy(c._model_view()['comparison_progress']);before=c._heavy_used
 c._facts=dict(reversed(list(c._facts.items())))
 c._group_summary=lambda *_: (_ for _ in ()).throw(AssertionError('view recomputed summary'))
 assert c._model_view()['comparison_progress']==expected
 c._execute_fetch({'action':'fetch_evidence','rationale':['Idempotent source fixture.'],'case_refs':['case-001','case-002'],'source_families':['company_facts'],'max_documents':1})
 assert c._model_view()['comparison_progress']==expected
 read(c,next(iter(c._facts)))
 assert c._model_view()['comparison_progress']==expected
 assert c._heavy_used==before+2
 return {'view_recomputation':False,'fetch_graph_preserved':True}
test('T06_idempotent_fetch_reorder_read_no_view_compute',idempotence)
def atomic():
 c=fresh(); concept=next(iter(c._facts.values())).concept; compare(c,[concept])
 before=deepcopy((c._last_action_result,c._comparison_progress,c._comparison_snapshot,c.ledger.entries,c._heavy_used))
 original=c._group_summary
 def mutate(wanted):
  summary=original(wanted);key=next(iter(c._facts));c._facts[key]=replace(c._facts[key],taxonomy='changed');return summary
 c._group_summary=mutate
 try: compare(c,['Absent'])
 except InvalidMiningAction as e: assert 'inputs changed' in str(e)
 else: raise AssertionError('accepted graph mutation during comparison')
 after=(c._last_action_result,c._comparison_progress,c._comparison_snapshot,c.ledger.entries,c._heavy_used)
 assert before==after
 # Returned nested copies cannot mutate saved summary or last result.
 c._group_summary=original;compare(c,[concept])
 v=c._model_view();v['comparison_progress']['items'][0]['groups']['control']['case_count']=999
 v['last_action_result']['groups']['control']['case_count']=999
 assert c._model_view()['last_action_result']['groups']['control']['case_count']!=999
 assert loc(c,concept)['groups']['control']['case_count']!=999
 return {'context_mutation_rejected_before_acceptance':True,'view_mutation_isolated':True}
test('T07_atomic_acceptance_and_deepcopy',atomic)
def pages():
 c=fresh();compare(c,[f'Empty{i:02}' for i in range(14)])
 p=c._model_view()['comparison_progress'];assert len(p['items'])==12
 assert p['counts']['omitted_after']==2 and not p['selection_is_exhaustive']
 assert json_bytes(p['items'])<=8000
 huge='长'*3000;compare(c,[huge,'Small'])
 p=c._model_view()['comparison_progress'];assert huge not in [r['concept'] for r in p['items']]
 assert p['oversized_entries'][0]['concept']==huge
 assert p['oversized_entries'][0]['required_bytes']>8000
 assert any(r['concept']=='Small' for r in p['items'])
 return {'items_bytes':json_bytes(p['items']),'oversized_units':p['counts']['oversized'],'omissions_explicit':True}
test('T08_whole_units_Unicode_oversized_omissions',pages)
def reconstruct():
 def replay():
  c=fresh();concept=c._model_view()['measurable_evidence_manifest']['structured_financial_concepts'][0]['concept']
  compare(c,[concept])
  for key in ('latest','comparable_prior'):
   unit=c._model_view()['comparison_progress']['items'][0]
   ref=next(iter(next(row[key] for row in unit['groups'].values() if row[key]).values()))['fact_ref']
   read(c,ref)
  return c
 a,b=replay(),replay();assert a._model_view()==b._model_view();assert a.ledger.to_dict()==b.ledger.to_dict()
 return {'deterministic_controller_reconstruction':True,'native_cache_not_yet_tested':True}
test('T10_deterministic_action_reconstruction',reconstruct)
after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
report={'scope':'Synthetic controller-only independent controls, no model/API/inbox or business labels. Native budget/cache/source1780 checks are not established by this script.','source_hashes':hashes,'source_hashes_after':after,'drift':hashes!=after,'checks':rows,'all_pass':all(r['passed'] for r in rows)}
with (BASE/'comparison-counterexamples-v1.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'all_pass':report['all_pass'],'drift':report['drift'],'checks':[{'name':r['name'],'passed':r['passed'],'error':r.get('error')} for r in rows]},indent=2))
