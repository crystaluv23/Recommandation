"""Three named synthetic producer metadata additions, exact original byte comparison."""
from pathlib import Path
from datetime import datetime
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch
import ast,json,hashlib,tempfile
from tests import test_information_plan_engine as runtime
from tests.scheme_evolution_test_support import candidate_growth_fixture,NOW
from stock_opportunity_agent.data.raw_info import RawInfoDocument,RawInfoStore
from stock_opportunity_agent.signal_library import SignalExecutor,SignalRegistry,SignalSpec,SignalExecutionType,SignalModality
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator,signal_candidate_execution_contract
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
import run_minimal_rounds
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/seed_fixture_issuer_binding_20261021_v1';O=D/'independent'
def b(p):return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
runtime_path=R/'tests/test_information_plan_engine.py';support_path=R/'tests/scheme_evolution_test_support.py';oldruntime=D/'consumer-runtime-controls/original-test-source.py';oldsupport=D/'candidate-controls/original-support-source.py'
assert b(runtime_path)['sha256']=='4723ab4c41e4671434921f5c626739ce4a9186e81192d4f7e4b7bc50a0a9490f'
assert b(support_path)['sha256']=='9caf193e3098ce159b914ac1df598e3cd3aa6e13485315965bbc9510dca6cef9'
newcode=runtime_path.read_text();oldcode=oldruntime.read_text();support=support_path.read_text();old_support=oldsupport.read_text()
assert sum(line.strip()=='metadata={"cik": "0000000001"},' for line in newcode.splitlines())==2
assert ''.join(line for line in newcode.splitlines(keepends=True) if line.strip()!='metadata={"cik": "0000000001"},')==oldcode
assert ''.join(line for line in support.splitlines(keepends=True) if line.strip()!='"metadata": {"cik": "0000000001"},')==old_support
assertions=lambda text:[ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Assert) or isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr.startswith('assert')]
assert assertions(newcode)==assertions(oldcode) and assertions(support)==assertions(old_support)
def method(text,name):return next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.FunctionDef) and n.name==name)
def compile_function(node,namespace):
 scope=dict(namespace);exec(compile(ast.Module(body=[node],type_ignores=[]),'<isolated original fixture producer>','exec'),scope);return scope[node.name]
oldhelper=compile_function(method(oldcode,'_registry_and_store'),runtime.__dict__)
def shared_document(text):
 node=method(text,'test_repeated_issuer_cases_keep_distinct_truths_and_prediction_files')
 call=next(n for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='create' and isinstance(n.func.value,ast.Name) and n.func.value.id=='RawInfoDocument' and any(k.arg=='document_id' and isinstance(k.value,ast.Constant) and k.value.value=='shared_financials' for k in n.keywords))
 return eval(compile(ast.Expression(call),'<isolated exact shared document constructor>','eval'),runtime.__dict__)
forbidden=[]
def deny(*args,**kwargs):forbidden.append(True);raise AssertionError('fixture-only boundary')
rows=[];bindings=[b(p) for p in (runtime_path,support_path,R/'src/stock_opportunity_agent/signal_library.py',R/'src/stock_opportunity_agent/data/sec_company_facts.py',R/'src/stock_opportunity_agent/research/signal_evolution.py')]
with ExitStack() as guards,tempfile.TemporaryDirectory(prefix='independent-named-fixture-') as tmp:
 for target,name in ((LabelStore,'load'),(LabelStore,'record'),(run_minimal_rounds,'prepare')):guards.enter_context(patch.object(target,name,deny))
 for name in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores'):guards.enter_context(patch.object(StructuredRoleClient,name,deny))
 guards.enter_context(patch('socket.socket',deny));guards.enter_context(patch('socket.create_connection',deny))
 tmp=Path(tmp)
 oldregistry,oldstore=oldhelper(runtime.InformationPlanRuntimeTests(),str(tmp/'old'))
 newregistry,newstore=runtime.InformationPlanRuntimeTests()._registry_and_store(str(tmp/'new'))
 for name,prior,current,snapshot,expected in (
  ('registry_and_store',oldstore.documents[0],newstore.documents[0],newregistry.freeze(),0.3),
  ('exact_shared_constructor',shared_document(oldcode),shared_document(newcode),newregistry.freeze(),0.25)):
  before=prior.to_dict();after=current.to_dict();assert json.loads(before['content'])['cik']==1
  assert before['metadata']=={} and after['metadata']=={'cik':'0000000001'}
  after['metadata']={};assert digest(before)==digest(after)
  outputs=[]
  for phase,doc in [('original',prior),('fixed',current)]:
   result=SignalExecutor(snapshot,RawInfoStore(documents=(doc,))).execute_batch(('revenue_growth_yoy:v1',),company_id=doc.company_id,as_of=NOW).results[0]
   if phase=='original':assert result.execution_status.value=='validation_failed' and result.value.value=='unavailable' and 'opaque company has no explicit issuer binding' in result.execution_error_message
   else:assert result.execution_status.value=='success' and abs(result.measurement.value-expected)<1e-12
   outputs.append({'phase':phase,'result':result.to_dict()})
  rows.append({'producer':name,'body_and_all_except_metadata_exact':True,'outputs':outputs})
 # Actual candidate authoring fixture before/after; no high-level evolution loop.
 original_fixture=json.loads((D/'candidate-controls/original-fixture.json').read_text());fixed=candidate_growth_fixture();stripped=deepcopy(fixed)
 stripped['documents'][0].pop('metadata');assert digest(stripped)==digest(original_fixture)
 spec=SignalSpec(signal_id='independent_named_candidate',version=1,category='financial',description='Measure year-over-year revenue growth.',execution_type=SignalExecutionType.DETERMINISTIC,modality=SignalModality.STRUCTURED,function='financial.revenue_growth_yoy',source_types=('financials',))
 registry=SignalRegistry(tmp/'candidate/signals');candidate=[]
 for phase,fixture in [('original',original_fixture),('fixed',fixed)]:
  result=SignalCandidateValidator(registry,llm_runner=None).validate(spec,skill=None,tests=(fixture,))
  assert result.accepted==(phase=='fixed') and result.executed_tests==(1 if phase=='fixed' else 0)
  candidate.append({'phase':phase,'accepted':result.accepted,'executed_tests':result.executed_tests,'reasons':list(result.reasons)})
assert not forbidden and bindings==[b(Path(x['path'])) for x in bindings]
contract=signal_candidate_execution_contract();assert 'cik' not in json.dumps(contract).casefold()
out={'verdict':'PASS_three_named_positive_producers_only','bindings':bindings,'original_bindings':[b(oldruntime),b(oldsupport)],'exact_bytes_restored_by_removing_only_three_metadata_lines':True,'assertion_AST_sequences_identical':True,'runtime_native_controls':rows,'candidate_native_controls':candidate,'candidate_all_but_metadata_exact':True,'forbidden_calls':forbidden,'remaining_authoring_gap':'Shared signal_candidate_execution_contract does not explicitly disclose CIK binding obligations; no prompt repair or fresh S5 obedience is demonstrated here.','limits':['Only synthetic named positive fixtures were changed; no general helper, real source, issuer gate, existing published Registry, production code, assertions or clocks were changed.','This is isolated native fixture/runtime-input behavior and candidate validation, not fresh F7/S5 or Mining/Slow/research gain. No high-level evolution module/suite or real stage was executed.']}
(O/'producer-addendum-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('runtime_native_controls',)},ensure_ascii=False,indent=2))
