"""Independent offline native controls; no stage actor or network execution."""
from copy import deepcopy
from dataclasses import replace,asdict
from datetime import datetime
import hashlib,json,pathlib,socket,sys,traceback,types
from unittest.mock import patch
from stock_opportunity_agent.data.raw_info import RawInfoDocument,RawInfoStore
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController,InvalidMiningAction
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel,MiningRequestBudgetExhausted
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient,ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange,LocalRoleRequestPending
from stock_opportunity_agent.research.stage_contracts import json_bytes
from stock_opportunity_agent.llm import get_model
from tests.test_mining_catalog_working_context import MiningCatalogWorkingContextTests
from tests.test_mining_narrative_citation_readiness import fixture,event,candidate,execute
from tests.test_mining_narrative_read_evidence import Contract
R=pathlib.Path('/Users/l/Project/Recommandation');O=pathlib.Path(__file__).resolve().parent/sys.argv[1];O.mkdir(exist_ok=False)
H=MiningCatalogWorkingContextTests();RESULTS=[]
CODE=['src/stock_opportunity_agent/research/'+n+'.py' for n in ['mining_controller','mining_role_model','mining_agent_tools','stage_contracts','evolution_transport','local_role_exchange','evolution_reflection_memory']]+['spec/src/stock_opportunity_agent/research/signal_mining_agent.md','tests/test_mining_catalog_working_context.py','tests/test_mining_narrative_citation_readiness.py','tests/test_mining_narrative_read_evidence.py']
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def bindings():return {p:sha(R/p) for p in CODE}
def dump(n,x):(O/(n+'.json')).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n')
def record(n,fn):
 try:RESULTS.append({'id':n,'passed':True,'detail':fn()})
 except BaseException as e:RESULTS.append({'id':n,'passed':False,'type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc()})
def act(c,a,**kw):
 raw={'action':a,'rationale':['Independent offline native control.'],**kw};c._validate_action_shape(raw);return c._execute(a,raw)
def catalog(c,s='evidence',**kw):act(c,'inspect_catalog',scope=s,**kw);return deepcopy(c._last_action_result['result'])
def page(c):
 p=c._model_view()['catalog_observations'];assert len(p['items'])<=8 and json_bytes(p['items'])<=32000;return p
def state(c):return deepcopy((c.ledger.to_dict(),c._remaining_budget(),c.materialization_evidence()))
def actual():
 b=json.loads((R/'runs/diagnostics/mining_narrative_read_evidence_20261023_v1/independent/source-bindings-frozen.json').read_text());docs=[];pairs=[]
 for row in b['actual_sources']:
  assert sha(row['path'])==row['sha256'];d=RawInfoDocument.from_dict(json.loads(pathlib.Path(row['path']).read_text()));docs.append(d)
  pairs.append((row['case_ref'],types.SimpleNamespace(company_id=d.company_id,case_id='offline-'+row['case_ref'],prediction_time=datetime.fromisoformat(row['cutoff']),ground_truth=types.SimpleNamespace(is_surge=False))))
 mod=types.ModuleType('independent_catalog_baseline');sys.modules[mod.__name__]=mod
 path=R/'runs/diagnostics/mining_narrative_read_evidence_20261023_v1/catalog-family-review/frozen-baseline/src/stock_opportunity_agent/research/mining_controller.py';exec(compile(path.read_text(),str(path),'exec'),mod.__dict__)
 result=[]
 for cls in [mod.LabelAwareMiningController,LabelAwareMiningController]:
  c=cls(store=RawInfoStore(documents=docs),model=None,case_pairs=pairs,signal_catalog=[],measurable_evidence_manifest={},seed='discovery')
  act(c,'fetch_evidence',case_refs=[x[0] for x in pairs],source_families=['filing'],max_documents=24,query='internal control over financial reporting material weakness remediation disclosure controls')
  original=catalog(c);before=deepcopy(original)
  actual_page=json.loads((R/'runs/diagnostics/mining_narrative_read_evidence_20261023_v1/catalog-family-review/evidence.json').read_text())['evidence_directory']['first_page_items']
  for card in original['items']:
   fixed=next(x for x in actual_page if card['document_ref'].split(':')[-1] in x['document_ref'])
   for key in ['sections','section_count','raw_chars','readable_start','case_bindings','available_at']:assert card[key]==fixed[key],key
  for docid,offset in [('000149315225011966',1148801),('000149315225011966',1152908),('000114036125018373',3969625)]:
   d=next(d for d in docs if d.document_id.endswith(docid));e=next(e for e in c._events.values() if e.document_ref=='document-'+d.document_id)
   act(c,'read_span',event_ref=e.event_ref,offset=offset,length=4000)
  result.append(c)
 old,new=result;assert state(old)==state(new);assert 'catalog_observations' not in old._model_view()
 row=page(new)['items'][0];assert row['result']==before and row['source_snapshot_matches'];assert len(new._model_view()['narrative_read_evidence']['items'])==3
 assert all(not x.get('read_windows') for x in before['items']);assert all(x.get('read_windows') for x in new._evidence_catalog_view()['items'])
 snapshot=state(new);page(new);assert state(new)==snapshot
 dump('actual-two-source-projection',{'old_view_has_catalog':False,'new_observation':row,'body_units':new._model_view()['narrative_read_evidence'],'source_bindings':b['actual_sources']})
 return {'two_real_sources_three_windows':True,'old_new_ledger_budgets_s5_equal':True,'scope':'offline projection, not full14doc actual replay'}
def cursor():
 c,docs=H.controller(body_count=19);initial=catalog(c);cursor=initial['next_cursor'];assert cursor
 for d in docs[:2]:H.read(c,d)
 refs=list(c._facts)[:2];act(c,'compute_statistic',rule='latest_minus_comparable_prior',fact_refs=refs)
 assert page(c)['items'][0]['source_snapshot_matches'];nextpage=catalog(c,cursor=cursor);assert {r['document_ref'] for r in nextpage['items']}-{r['document_ref'] for r in initial['items']}
 # Native payload ordering variation: same document set/hash, reversed result order.
 for key,result in list(c._documents.items()):c._documents[key]=replace(result,documents=tuple(reversed(result.documents)))
 current=c._evidence_catalog_view();assert current['items']!=initial['items'];assert not page(c)['items'][0]['source_snapshot_matches']
 assert page(c)['items'][1]['result']==initial
 return {'saved_cursor_after_read_compute':cursor,'changed_order_invalidates_same_set':True}
def scope_gate():
 c=fixture(shared=True);first,second=event(c,'case-001'),event(c,'case-002');catalog(c)
 execute(c,'read_span',event_ref=first.event_ref,offset=0,length=4000)
 before=state(c)
 try:execute(c,'propose_candidate',candidate=candidate(second.event_ref))
 except InvalidMiningAction as e:assert 'executed readable window' in str(e)
 else:raise AssertionError('shared unread event got citation permission')
 assert second.event_ref not in c.materialization_evidence();assert state(c)==before
 h=fixture(hidden=True);catalog(h);item=event(h,'case-002');execute(h,'read_span',event_ref=item.event_ref,offset=0,length=28)
 try:execute(h,'propose_candidate',candidate=candidate(item.event_ref,'filing'))
 except InvalidMiningAction:pass
 else:raise AssertionError('hidden-only got citation permission')
 return {'catalog_does_not_authorize_other_case_or_hidden_window':True}
def needs():
 c,docs=H.controller(needs=60);catalog(c,'backlog',item_refs=['n037','n038']);H.read(c,docs[0]);v=c._model_view()['need_disposition_contract'];assert {'n037','n038'}<=set(v['allowed_need_refs']) and 'n039' not in v['allowed_need_refs']
 row=lambda ref:{'need_refs':[ref],'disposition':'deferred_measurement','signal_refs':[],'rationale':['Keep exact current scoped need.']}
 c._record_need_dispositions({'base_hash':v['base_hash'],'need_dispositions':[row('n037')]})
 for ref,base in [('n037',c._need_state_hash()),('n038',v['base_hash'])]:
  try:c._record_need_dispositions({'base_hash':base,'need_dispositions':[row(ref)]})
  except InvalidMiningAction:pass
  else:raise AssertionError('staged or stale base authorized')
 assert 'n038' in c._disclosed_need_refs();c._backlog_by_ref['n038']['sources'][0]['detail']='Different original';assert 'n038' not in c._disclosed_need_refs()
 # Whole actual original legal at16KB, but repeated provenance wrapper makes cache oversize possible only at larger response grouping.
 for i in range(9):catalog(c,'signals',cursor=0 if i==0 else 0) if False else catalog(c,'backlog',item_refs=[f'n{i+40:03d}'])
 H.read(c,docs[0]);assert 'n038' not in c._disclosed_need_refs();assert page(c)['omitted_entries']
 before=deepcopy(c._catalog_observations)
 try:catalog(c,'backlog',item_refs=['missing-need'])
 except InvalidMiningAction:pass
 else:raise AssertionError('unknown need accepted')
 assert c._catalog_observations==before
 return {'current_visible_pending_legal':True,'staged_stale_changed_omitted_unknown_rejected':True}
def signal_capacity():
 c,docs=H.controller(signals=24);card=catalog(c,'signals',cursor=14);whole=catalog(c,'signals',item_refs=['measure_19:v1']);H.read(c,docs[0]);text=json.dumps(page(c),ensure_ascii=False)
 assert 'exact original 19' in text and 'exact original 18' not in text and 'Hidden Holder Inc.' not in text
 before=deepcopy(c._catalog_observations);c._signal_originals['measure_19:v1']['skill']='DRIFT'
 try:catalog(c,'signals',item_refs=['measure_19:v1'])
 except InvalidMiningAction:pass
 else:raise AssertionError('changed original accepted')
 assert c._catalog_observations==before and not all(r['source_snapshot_matches'] for r in page(c)['items'])
 u,_=H.controller(memory={'items':[{'item_ref':f'm{i}','original':'𠀀'*2800,'brief':f'b{i}'} for i in range(5)]})
 for i in range(5):catalog(u,'memory',item_refs=[f'm{i}'])
 p=page(u);assert p['omitted_entries'] and all(r['result']['items'][0]['original']=='𠀀'*2800 for r in p['items'])
 return {'signal_unread_skill_absent_changed_hash_refused':True,'unicode_whole_omission':p['counts']}
def memory():
 index=ReflectionMemoryIndex.from_case_rows([{'source_identity':'case:large','candidate_judgment_feedback':{'note':'原'*11600}},{'source_identity':'case:unread','candidate_judgment_feedback':{'note':'UNREAD_MEMORY_ORIGINAL'}}],owner_ref='offline-plan')
 c,docs=H.controller();c.memory_index=index;catalog(c,'memory',cursor=0)
 ref=next(x['source_ref'] for x in index.source_catalog() if x['case_refs']==['case:large'])
 response=catalog(c,'memory',item_refs=[ref]);H.read(c,docs[0]);v=c._model_view();assert '原'*11600 in json.dumps(v['meta_memory_disclosures'],ensure_ascii=False);assert 'UNREAD_MEMORY_ORIGINAL' not in json.dumps(v['catalog_observations'],ensure_ascii=False)
 p=page(c);assert p['oversized_entries'] and p['oversized_entries'][0]['required_bytes']>32000;assert 'result' not in p['oversized_entries'][0]
 before=state(c);disclosed=deepcopy(c.meta_memory_disclosures)
 try:catalog(c,'memory',item_refs=['reflection_source:missing'])
 except InvalidMiningAction:pass
 else:raise AssertionError('unknown memory accepted')
 assert c.meta_memory_disclosures==disclosed and state(c)==before
 return {'actual_packet_bytes':json_bytes(response),'unclipped_in_existing_disclosure':True,'oversize_locator':p['oversized_entries'][0]}
def computed():
 c,docs=H.controller();refs=list(c._facts)[:2];rule='latest_minus_comparable_prior'
 act(c,'compute_statistic',rule=rule,fact_refs=refs);ref=c._last_action_result['relation_ref'];relation=c._relations[ref]
 catalog(c);H.read(c,docs[0]);view=c._model_view()['computed_statistics'];row=next(r for r in view['items'] if r['relation_ref']==ref)
 assert row['relation']['fact_refs']==tuple(refs) or row['relation']['fact_refs']==refs
 assert row['snapshot_status']=='current_since_last_fetch';assert row['relation']['value']==relation.value
 assert all(r['relation_ref'] in {e.evidence_refs[0] for e in c.ledger.entries if e.action=='compute_statistic'} for r in view['items'])
 act(c,'fetch_evidence',case_refs=['case-001'],source_families=['company_facts'],max_documents=40)
 # Adversarial input state: existing same fact_ref now carries changed value/taxonomy after a real fetch.
 prior=c._facts[refs[0]];c._facts[refs[0]]=replace(prior,value=str(int(prior.value)+123),taxonomy='different-taxonomy')
 row=next(r for r in c._model_view()['computed_statistics']['items'] if r['relation_ref']==ref)
 assert row['snapshot_status']=='invalidated' and 'operands' not in row;assert row['relation']==asdict(relation)
 proposal={'measurement':{'observable':'synthetic_local_number','value_kind':'numeric','normalization':'local arithmetic fixture'},'falsifiers':[{'condition':'missing input','expected_observation':'unavailable'}],'evidence_refs':[ref]}
 try:act(c,'propose_candidate',candidate=proposal)
 except InvalidMiningAction as e:assert 'comput' in str(e).lower() or 'operand' in str(e).lower()
 else:raise AssertionError('invalid old computed relation admitted')
 assert c._relations[ref]==relation
 act(c,'compute_statistic',rule=rule,fact_refs=refs);newref=c._last_action_result['relation_ref']
 current=next(r for r in c._model_view()['computed_statistics']['items'] if r['relation_ref']==newref);assert current['snapshot_status']=='current_since_last_fetch'
 assert current['operands'][0]['value']==str(int(prior.value)+123) and current['operands'][0]['taxonomy']=='different-taxonomy'
 assert json_bytes(c._model_view()['computed_statistics']['items'])<=8000
 act(c,'propose_candidate',candidate={**proposal,'evidence_refs':[newref]})
 return {'ordinary_read_catalog_preserves_result':True,'post_fetch_same_ref_value_taxonomy_old_relation_rejected':True,'recompute_restores_citation':True,'semantic_comparability_not_claimed':True}
def wire():
 c,docs=H.controller(signals=3);catalog(c,'signals',item_refs=['measure_2:v1']);
 extra=RawInfoDocument.create(document_id='HiddenHolder-transport',company_id=docs[0].company_id,source_type='filing',published_at=docs[0].published_at,available_at=docs[0].available_at,content='Transport-only exact source.')
 c.store.append(extra);act(c,'fetch_evidence',case_refs=['case-001'],source_families=['filing'],max_documents=40);catalog(c);H.read(c,docs[0]);before=state(c);root=O/'synthetic-native';root.mkdir()
 exchange=LocalRoleExchange(root/'exchange',max_calls=1)
 client=StructuredRoleClient(registration=get_model('independent-subagent'),contract=Contract(),workspace=root,ledger=ExternalAttemptLedger(root/'unused.json',max_attempts=1,max_total_cost=.01),local_role_exchange=exchange,allow_external=False,environ={})
 model=MiningAgentRoleModel(client,identity_aliases=('Hidden Holder Inc.','HiddenHolder'),max_request_tokens=262144,max_total_tokens=1048576,max_calls=10)
 try:model.next_action(c._model_view())
 except LocalRoleRequestPending as e:pending=e.pending
 else:raise AssertionError('expected synthetic pending')
 wire=json.loads(pathlib.Path(pending['inbox_path']).read_text());payload=json.loads(wire['messages'][1]['content']);cost=json_bytes(wire['messages'])+wire['max_output_tokens'];assert int(payload['request_budget']['this_request'])==cost
 assert 'exact original 2' in json.dumps(wire) and 'exact original 1' not in json.dumps(wire);assert 'Hidden Holder Inc.' not in json.dumps(wire) and 'HIDDEN_' not in json.dumps(wire)
 # Actual native receive/parse path, explicitly synthetic answer only in this NEW directory.
 masked_ref=next(row['document_ref'] for observation in payload['catalog_observations']['items'] if observation['scope']=='evidence' for row in observation['result']['items'] if 'transport' in row['document_ref']);assert '[ANON_ID_' in masked_ref
 pathlib.Path(pending['outbox_path']).write_text(json.dumps({'action':'read_span','document_ref':masked_ref,'offset':0,'length':40,'rationale':['Synthetic transport response only.']}))
 exchange.submit(pending['request_hash'],agent_id='independent-synthetic-control-author')
 answer=model.next_action(c._model_view());assert answer['document_ref']=='document-'+extra.document_id
 limited=MiningAgentRoleModel(client,max_request_tokens=cost-1000)
 with patch.object(LocalRoleExchange,'receive',side_effect=AssertionError('must reject before receive')):
  try:limited.next_action(c._model_view())
  except MiningRequestBudgetExhausted:pass
  else:raise AssertionError('request cap ignored')
 assert state(c)==before
 dump('native-wire-cost',{'complete_messages_bytes_plus_output':cost,'request_hash':pending['request_hash'],'synthetic_only':True})
 return {'native_complete_wire_cost':cost,'one_synthetic_response_no_actor':True,'gate_before_receive':True}
start=bindings();dump('source-bindings-start',start)
with patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
 for n,f in [('actual-two-source-old-new',actual),('cursor-read-compute-order',cursor),('scope-readiness-rejections',scope_gate),('need-authority-rejections',needs),('signal-unread-hash-unicode',signal_capacity),('indexed-memory-real-oversize',memory),('native-wire-budget',wire),('computed-source-invalid-recompute',computed)]:
  if len(sys.argv)<3 or n in sys.argv[2:]:record(n,f)
end=bindings();dump('source-bindings-end',end);dump('results',{'preliminary':True,'source_stable_during_run':start==end,'controls':RESULTS});print(json.dumps({'stable':start==end,'passed':sum(r['passed'] for r in RESULTS),'count':len(RESULTS),'failed':[r['id'] for r in RESULTS if not r['passed']]}))
