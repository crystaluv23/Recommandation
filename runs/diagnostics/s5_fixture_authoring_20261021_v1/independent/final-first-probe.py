"""Independent S5 authoring producer/validator checks; synthetic temp artifacts only."""
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch
import hashlib,json,socket,sys,types
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.signal_library import SignalRegistry,SignalSpec,SignalResult,SignalValue,SignalEvidence
from stock_opportunity_agent.research.evolution_core import AgentUsage
from stock_opportunity_agent.research import signal_evolution as s
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/s5_fixture_authoring_20261021_v1/independent';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();bind=lambda p:{'path':str(Path(p).resolve()),'sha256':sha(p)}
expected={'src/stock_opportunity_agent/research/signal_evolution.py':'3f3723a2008d8e2aa1e2f30d5fff03d76e10e55595833f909a46aafe0bdd99ca','spec/src/stock_opportunity_agent/research/signal_evolution.md':'e8eb9604cf3819b9c0d8f64adb1d09a5b87790ef26ea5406e3aeb4eaff5ca459','tests/test_candidate_fixture_authoring_contract.py':'a57fb998ef54c7d7d9725cd08f4aa81323b84cb963ff78810f7c6a6516346eed'}
for p,h in expected.items():assert sha(R/p)==h
oldpath=D/'original-af3c-signal_evolution.py.txt';assert sha(oldpath)=='af3c4bf5f5624087ac900b2218161466cffdb8ab817b9829f19172c9f4059a8d'
old=types.ModuleType('_independent_original_s5_af3c');sys.modules[old.__name__]=old;exec(compile(oldpath.read_text(),str(oldpath),'exec'),old.__dict__)
base=json.loads((D/'content-shape-probe.json').read_text())['fixture'];nested=json.loads(base['documents'][0]['content']);facts=nested['facts']['us-gaap']['Revenues']['units']['USD'];typed={'schema_version':'sec-company-facts-document-v1','cik':nested['cik'],'filing_date':'2025-02-03','form':'10-K','facts':[{'tag':'Revenues','unit':'USD','value':x['val'],'start':x['start'],'end':x['end']} for x in facts]}
second=deepcopy(base);second['name']='independent typed synthetic growth';second['documents'][0]['document_id']='synthetic-typed-source';second['documents'][0]['content']=json.dumps(typed,sort_keys=True,separators=(',',':'));fixtures=[base,second]
entry=next(x for x in json.loads((R/'configs/signals_v1.json').read_text())['signals'] if x['spec']['signal_id']=='revenue_growth_yoy');spec=SignalSpec.from_dict(entry['spec']);rows=[];tripwires=[]
def tree(p):return {str(x.relative_to(p)):sha(x) for x in p.rglob('*') if x.is_file()}
class Author:
 def __init__(self,values):self.values=deepcopy(values);self.calls=[]
 def complete_json(self,**request):self.calls.append(deepcopy(request));return {'tests':deepcopy(self.values)},AgentUsage(llm_calls=1)
with ExitStack() as guards,TemporaryDirectory(prefix='independent-S5-final-') as t:
 for target,name in [(socket,'socket'),(socket,'create_connection'),(LabelStore,'load'),(LabelStore,'record')]:
  p=guards.enter_context(patch.object(target,name,side_effect=AssertionError('forbidden real external/label access')));tripwires.append(p)
 root=Path(t);registry=SignalRegistry(root/'signals');v=s.SignalCandidateValidator(registry,llm_runner=None);ov=old.SignalCandidateValidator(registry,llm_runner=None)
 for fixture in fixtures:
  schema=json.loads(fixture['documents'][0]['content']).get('schema_version','nested');out=v.validate(spec,skill=None,tests=[fixture]);assert out.accepted and out.executed_tests==1,out.reasons;rows.append({'control':'independent_'+schema+'_positive','accepted':True,'executed_tests':1})
  for kind in ['object','null','list','bool']:
   x=deepcopy(fixture);x['expected']='unavailable';x['documents'][0]['content']={'object':json.loads(fixture['documents'][0]['content']),'null':None,'list':[],'bool':False}[kind];before=deepcopy(x)
   oldr=ov.validate(spec,skill=None,tests=[x]);newr=v.validate(spec,skill=None,tests=[x]);assert oldr.accepted and oldr.executed_tests==1;assert not newr.accepted and newr.executed_tests==0 and 'content must be a string' in newr.reasons[0];assert x==before
   rows.append({'control':schema+'_nonstring_'+kind,'old_accepted':oldr.accepted,'new_accepted':newr.accepted,'new_reasons':newr.reasons})
  for kind in ['missing_metadata','missing_body','mismatch']:
   x=deepcopy(fixture);x['expected']='unavailable';raw=x['documents'][0];body=json.loads(raw['content'])
   if kind=='missing_metadata':raw.pop('metadata')
   elif kind=='missing_body':body.pop('cik')
   else:raw['metadata']['cik']='0000000002'
   raw['content']=json.dumps(body,sort_keys=True,separators=(',',':'));checked=v.validate(spec,skill=None,tests=[x]);assert not checked.accepted and checked.executed_tests==0 and 'technical execution failure' in checked.reasons[0];rows.append({'control':schema+'_'+kind,'reasons':checked.reasons})
  x=deepcopy(fixture);x['company_id']='cik_0987654321';x['documents'][0].pop('metadata');checked=v.validate(spec,skill=None,tests=[x]);assert checked.accepted;rows.append({'control':schema+'_canonical_explicit_body_without_redundant_metadata','accepted':True})
 # Actual producer method, generic offline caller, genuine temp native staging.
 engine=object.__new__(s.SignalEvolutionEngine);engine.registry=registry;engine.validator=v;engine.slow_role_identity_guards=();accepted={'spec':spec.to_dict(),'skill':None};author=Author(fixtures)
 result,issues=engine._materialize_tests_module({'measurement':{'observable':'independent_revenue_growth'}},caller=author,evidence={},last_issues=[],seed='synthetic-independent',accepted=accepted)
 assert result and not issues and len(author.calls)==1
 req=author.calls[0];payload=req['payload'];assert req['stage']=='mining_candidate_materialize_tests' and req['max_output_tokens']==4000
 assert payload['execution_semantics']==s.signal_candidate_execution_contract();assert payload['tests_schema']==engine._candidate_arguments_schema(clone=False)['properties']['tests']
 meaning=payload['execution_semantics']['retrieval']['fixtures'];assert all(term in meaning for term in ['metadata.cik','body cik','synthetic','sort_keys','separators'])
 assert list(registry.load_candidate_tests(result[0]))==fixtures
 rows.append({'control':'actual_tests_author_payload_native_staging_reread','request':req,'candidate_ref':result[0],'fixtures_exact':True})
 before=tree(root);bad=deepcopy(fixtures);bad[0]['documents'][0]['content']=json.loads(bad[0]['documents'][0]['content']);bad[0]['expected']='unavailable';invalid=Author(bad)
 rejected,issues=engine._materialize_tests_module({'measurement':{'observable':'independent_revenue_growth'}},caller=invalid,evidence={},last_issues=[],seed='synthetic-independent',accepted={'spec':spec.to_dict(),'skill':None});assert rejected is None and 'content must be a string' in issues[0] and tree(root)==before and len(invalid.calls)==1;rows.append({'control':'actual_author_nonstring_does_not_stage_or_fill','issues':issues,'temp_registry_unchanged':True})
 # No source-family-wide metadata requirement is introduced.
 def custom(spec,documents,as_of):
  d=documents[0];return SignalResult(signal_id=spec.signal_id,version=spec.version,value=SignalValue.NEUTRAL,confidence=1,interpretation='Source is present.',supporting_evidence=(SignalEvidence(d.document_id,d.content,as_of),))
 customspec=spec.to_dict();customspec['signal_id']='independent_nonfinancial_source';customspec['execution']={'type':'deterministic','function':'independent.source_present'};customspec['raw_retrieval']={'source_types':['news']};news={'name':'synthetic news','as_of':base['as_of'],'expected':'neutral','documents':[{'document_id':'synthetic-news','source_type':'news','available_at':'2025-02-04T00:00:00+00:00','content':'A company announcement.'}]};nv=s.SignalCandidateValidator(registry,llm_runner=None,deterministic_functions={'independent.source_present':custom});out=nv.validate(SignalSpec.from_dict(customspec),skill=None,tests=[news]);assert out.accepted;rows.append({'control':'nonfinancial_optional_metadata','accepted':True})
 # Existing Update cannot silently migrate old invalid financial fixtures.
 oldfixture=deepcopy(base);oldfixture['documents'][0].pop('metadata');registry.register_stable(spec,tests=(oldfixture,));published=tree(root);nextspec=spec.to_dict();nextspec['version']=2;nextspec['parameters']['positive_min']=float(nextspec['parameters'].get('positive_min',0))+.01;candidate={'signal_ref':spec.ref,'spec':nextspec,'skill':None,'tests':[deepcopy(oldfixture)]}
 try:engine._validate_update_candidate_for_role(spec.ref,candidate,('spec.parameters.positive_min',))
 except ValidationError as error:assert 'opaque company has no explicit issuer binding' in str(error);reason=str(error)
 else:raise AssertionError('Old invalid fixture was silently migrated')
 assert tree(root)==published and list(registry.load_tests(spec.ref))==[oldfixture]
 changed=deepcopy(candidate);changed['tests'][0]['documents'][0]['metadata']={'cik':'0987654321'}
 try:engine._validate_update_candidate_for_role(spec.ref,changed,('spec.parameters.positive_min',))
 except ValidationError as error:assert 'preserve stable executable fixtures' in str(error)
 else:raise AssertionError('Update gained fixture-edit authority')
 assert tree(root)==published;rows.append({'control':'Update_old_fixture_remains_invalid_and_immutable','reason':reason,'published_temp_tree_unchanged':True,'fixture_edit_rejected':True})
 assert all(x.call_count==0 for x in tripwires)
for p,h in expected.items():assert sha(R/p)==h
report={'verdict':'PASS_bounded_S5_producer_contract_and_content_shape_gate','controls':len(rows),'rows':rows,'sources':{p:bind(R/p) for p in expected},'old_content_shape_source':bind(oldpath),'probe':bind(__file__),'tripwires_calls':0,'limits':['Synthetic offline authors are scripted, not fresh model behavior.','Native temp Registry candidate staging is not stable publication, effectiveness admission, mining gain or overall S5/MVP closure.','No published fixtures, real case labels, source records or completed stages were read or rewritten.','Whole spec file includes pre-existing Experience text outside this task; audit does not authorize staging that unrelated hunk.']}
p=D/'final-review.json';p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('PASS',len(rows),'controls;',sha(p))
