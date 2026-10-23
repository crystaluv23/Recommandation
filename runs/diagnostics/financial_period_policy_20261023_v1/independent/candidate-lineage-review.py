"""Real next-version validator lineage, legacy runtime replay, and policy dispatch proof."""
import ast,hashlib,json,subprocess,sys,types
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent import signal_library as cur
from stock_opportunity_agent.data.raw_info import RawInfoDocument,RawInfoStore
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3];ORIGINAL=Path('/Users/l/Project/Recommandation')
BINDINGS={'src/stock_opportunity_agent/signal_library.py':'05e79dbfd4e2d2105c34c8ac66ea2821046a79fe8cedc83931917de2eec7639c','src/stock_opportunity_agent/research/signal_evolution.py':'2d79e35a090966c3f5e38384b5332cc40822cce56af6fc8e5d482b78145e8578'}
for path,digest in BINDINGS.items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
ASOF=datetime(2025,5,30,tzinfo=timezone.utc);COMPANY='cik_0000000001'
old_defs=json.loads((OUT/'source-only-oracle.json').read_text())['version_allocation']
registry=cur.SignalRegistry(OUT/'candidate-lineage-registry/signals',candidate_root=OUT/'candidate-lineage-registry/candidates')
provenance=[]
for allocation in old_defs:
 for binding in allocation['inventory']:
  path=Path(binding['path']);data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==binding['sha256'];s=cur.SignalSpec.from_dict(json.loads(data));registry.register_stable(s);provenance.append(binding)
validator=SignalCandidateValidator(registry,llm_runner=None)
windows=[('2025-01-01','2025-03-31',150),('2024-01-01','2024-03-31',100),('2024-10-01','2024-12-31',120),('2023-10-01','2023-12-31',100),('2023-01-01','2023-03-31',80)]
def fact(tag,s,e,v):return dict(tag=tag,start=s,end=e,value=v,unit='USD')
facts=[fact('Revenues',*w) for w in windows]+[fact('GrossProfit','2025-01-01','2025-03-31',30),fact('GrossProfit','2024-01-01','2024-03-31',10),fact('GrossProfit','2024-10-01','2024-12-31',30)]
def document(rows,name='synthetic',filed='2025-05-08'):
 content=json.dumps(dict(schema_version='sec-company-facts-document-v1',cik='0000000001',accession_number=name,filing_date=filed,form='10-Q',facts=rows),sort_keys=True,separators=(',',':'))
 return RawInfoDocument.create(document_id=name,company_id=COMPANY,source_type='sec_company_facts',published_at=datetime.fromisoformat(filed).replace(tzinfo=timezone.utc),available_at=datetime(2025,5,9,tzinfo=timezone.utc),content=content,metadata={'cik':'0000000001'})
doc=document(facts)
fixture=dict(name='actual-next-version-policy',company_id=COMPANY,as_of=ASOF.isoformat(),expected='positive',documents=[doc.to_dict()])
checks=[];new_specs=[]
def compact(validation):return dict(accepted=validation.accepted,reasons=list(validation.reasons),executed_tests=validation.executed_tests)
with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
 for name,policy,alias in [('gross_margin_change','same_window_yoy','financial.gross_margin_change_yoy'),('revenue_acceleration','adjacent_yoy','financial.revenue_acceleration_adjacent')]:
  previous=registry.latest_spec(name)
  new=replace(previous,version=previous.version+1,parameters={**previous.parameters,'period_policy':policy})
  new_specs.append(new)
  good=validator.validate(new,skill=None,tests=[fixture]);assert good.accepted and good.executed_tests==1,good
  bad=validator.validate(replace(new,function=alias),skill=None,tests=[fixture]);assert not bad.accepted and bad.executed_tests==0 and 'deterministic update must preserve the registered function' in bad.reasons
  wrongconcept=validator.validate(replace(new,description='Measure cash reserves.'),skill=None,tests=[fixture]);assert not wrongconcept.accepted and wrongconcept.executed_tests==0 and any('definition-to-implementation mismatch' in s for s in wrongconcept.reasons)
  snapshot=cur.FrozenSignalRegistry(version=1,registry_hash=canonical_json_hash([new.to_dict()]),specs=(new,),skills={})
  ex=cur.SignalExecutor(snapshot,RawInfoStore(documents=[doc]));result=ex.execute_batch([new.ref],company_id=COMPANY,as_of=ASOF).results[0]
  contract=ex.classification_contracts_for((result,))[new.ref];scope=cur.signal_measurement_scope(new,deterministic_functions=ex.deterministic_functions)
  assert scope['execution']['configured_parameters']['period_policy']==policy
  assert contract['execution']['configured_parameters']['period_policy']==policy
  invalid=[]
  for unknown in ('unknown','same_window_yoy' if policy=='adjacent_yoy' else 'adjacent_yoy','',None,0):
   badspec=replace(new,parameters={**new.parameters,'period_policy':unknown})
   basis=ex.deterministic_functions[new.function].__signal_input_facts__(badspec,(doc,),ASOF)
   badresult=ex.deterministic_functions[new.function](badspec,(doc,),ASOF)
   assert basis.unavailable_reason and badresult.value.value=='unavailable' and badresult.measurement is None
   invalid.append(dict(policy=unknown,basis_reason=basis.unavailable_reason,result=badresult.to_dict()))
  checks.append(dict(previous_spec=previous.to_dict(),next_spec=new.to_dict(),good=compact(good),wrong_function=compact(bad),wrong_concept=compact(wrongconcept),scope=scope,classification_contract=contract,unknown_policies=invalid))

# Compare legacy bodies to base after removing only the added dispatch and revised public docs/decorators.
base_source=subprocess.check_output(['git','show','ba309796:src/stock_opportunity_agent/signal_library.py'],cwd=ROOT,text=True)
base_tree=ast.parse(base_source);current_tree=ast.parse((ROOT/'src/stock_opportunity_agent/signal_library.py').read_text())
old_nodes={n.name:n for n in base_tree.body if isinstance(n,ast.FunctionDef)};new_nodes={n.name:n for n in current_tree.body if isinstance(n,ast.FunctionDef)}
names=['_revenue_acceleration_signal','_gross_margin_change_signal','_revenue_acceleration_input_facts','_gross_margin_input_facts']
body_checks=[]
for name in names:
 old=list(old_nodes[name].body);new=list(new_nodes[name].body)
 if old and isinstance(old[0],ast.Expr) and isinstance(old[0].value,ast.Constant) and isinstance(old[0].value.value,str):old=old[1:]
 if new and isinstance(new[0],ast.Expr) and isinstance(new[0].value,ast.Constant) and isinstance(new[0].value.value,str):new=new[1:]
 assert isinstance(new[0],ast.If) and 'period_policy' in ast.unparse(new[0]);new=new[1:]
 assert [ast.dump(n,include_attributes=False) for n in old]==[ast.dump(n,include_attributes=False) for n in new],name
 body_checks.append(name)
assert ast.dump(old_nodes['_numeric_result'],include_attributes=False)==ast.dump(new_nodes['_numeric_result'],include_attributes=False)
# Execute the exact base source under a separate module namespace: no subprocess/filesystem write or real source apply.
oldmod=types.ModuleType('financial_period_policy_baseline_ba309796');oldmod.__file__='git:ba309796:signal_library.py';sys.modules[oldmod.__name__]=oldmod
exec(compile(base_source,oldmod.__file__,'exec'),oldmod.__dict__)
legacy=[]
variants={'full':facts,'no_current_profit':[f for f in facts if not(f['tag']=='GrossProfit' and f['end']=='2025-03-31')],'no_current_yoy':[f for f in facts if not(f['tag']=='Revenues' and f['start']=='2024-01-01')],'no_quarter4':[f for f in facts if f['start']!='2024-10-01'],'zero_prior':[dict(f,value=0) if f['tag']=='Revenues' and f['start']=='2024-01-01' else f for f in facts],'currency':[dict(f,unit='EUR') if f['start']=='2024-01-01' else f for f in facts],'empty':[]}
with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
 for new in new_specs:
  current_spec=registry.latest_spec(new.signal_id);baseline_spec=oldmod.SignalSpec.from_dict(current_spec.to_dict())
  new_fn=cur.default_deterministic_signal_functions()[current_spec.function];old_fn=oldmod.default_deterministic_signal_functions()[baseline_spec.function]
  for key,sourcefacts in variants.items():
   docs=(document(sourcefacts),);a=new_fn(current_spec,docs,ASOF);b=old_fn(baseline_spec,docs,ASOF);assert a.to_dict()==b.to_dict(),(new.signal_id,key)
   aa=cur._input_basis_identity(new_fn.__signal_input_facts__(current_spec,docs,ASOF));bb=oldmod._input_basis_identity(old_fn.__signal_input_facts__(baseline_spec,docs,ASOF));assert aa==bb,(new.signal_id,key,'basis')
   legacy.append(dict(ref=current_spec.ref,variant=key,result=a.to_dict(),basis_equal=True,output_equal=True))
report=dict(status='passed',code_bindings=BINDINGS,actual_prior_spec_provenance=provenance,next_version_checks=checks,old_algorithm_bodies_equal_after_explicit_dispatch=body_checks,old_numeric_result_whole_AST_equal=True,legacy_replays=legacy,legacy_replay_count=len(legacy),baseline_module_source_sha256=hashlib.sha256(base_source.encode()).hexdigest(),real_source_Signal_execution=0,network_calls=0,models=0,labels=0)
(OUT/'candidate-lineage-review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(status='passed',actual_next_versions=[s.ref for s in new_specs],validator_good=2,wrong_ID_rejected=2,wrong_concept_rejected=2,unknown_policies_unavailable=10,legacy_outputs_and_bases_equal=len(legacy))))
