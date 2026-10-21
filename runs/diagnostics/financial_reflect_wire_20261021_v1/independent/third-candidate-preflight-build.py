"""Readonly sealing of candidate3 and independently rerun synthetic controls."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
R=Path('/Users/l/Project/Recommandation');B=R/'runs/diagnostics/financial_reflect_wire_20261021_v1';I=B/'independent';D=B/'driver'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
expected={D/'capture-native-config.py':'48b107515437e877fcb837ac4890e5b94720de707e87c99fb933b39ba9382093',D/'contract-v3.json':'450f3e947181ffb186a6b99b365e17a82d3b47ca9690f90d747c5bddabc4a3ba',I/'pre-capture-expectations.json':'d23d09d8036575534d6d71dacfade8d4fe4be6c0726b816bb12d415531568754'}
assert all(sha(p)==h for p,h in expected.items())
c=json.loads((D/'contract-v3.json').read_text());assert c['selected_indices']==[0,1,2,4,5,6] and c['source_denominator']==9
assert c['limits']['max_structured_corrections']==1 and c['limits']['max_request_tokens']==131072
assert c['overall_capture_ceiling']=={'all_attempts_combined_request_journals':1,'model_calls':0,'role_dispatches':0}
assert not (D/'execution-v3').exists()
assert all(sha(Path(b['path']))==b['sha256'] for b in c['source_bindings']+c['code_bindings'])
controls=json.loads((I/'synthetic-observer-independent-results.json').read_text());assert controls['tests_run']==5 and controls['errors']==controls['failures']==0 and not controls['forbidden_calls'] and not controls['actual_source_access_attempts']
failures=[]
for name in ('execution','execution-v2'):
 p=D/name;f=json.loads((p/'failure.json').read_text());assert f['counts']=={'pre_egress_calls':0,'request_ready':0} and f['forbidden_calls']==[]
 assert not list((p/'requests').glob('*.json'))
 failures.append({'root':str(p),'error':f['message'],'counts':f['counts'],'files':[{'path':str(x),'sha256':sha(x)} for x in sorted(p.rglob('*')) if x.is_file()]})
rows=json.loads((I/'pre-capture-expectations.json').read_text())['expected_rows'];assert len(rows)==6 and sum(len(r['source_observations']) for r in rows)==11
files=[I/'run-synthetic-observer-review.py',I/'synthetic-observer-independent.log',I/'synthetic-observer-independent-results.json',D/'synthetic-observer-controls.py',D/'synthetic-observer-controls-result.json',D/'synthetic-observer-controls.log',D/'failure-binding-review.json',D/'failure-v2-binding-review.json',I/'explicit-carrier-amendment.json',Path(__file__)]
r={'status':'PASS_CANDIDATE3_FOR_ONE_SOURCE_WIRE_CAPTURE_NOT_RESEARCH_STAGE','reviewed_at':datetime.now(timezone.utc).isoformat(),'candidate_bindings':[{'path':str(p),'sha256':h} for p,h in expected.items()],'frozen_source_code_bindings_verified':len(c['source_bindings']+c['code_bindings']),'first_two_failures':failures,'first_two_combined_actual_source_journals':0,'third_output_existed_at_review':False,
 'independent_synthetic_tests':{'passed':5,'errors':0,'forbidden_calls':0,'actual_source_access_attempts':0,'same_candidate_observer':True,'native_Controller_client_journal':True,'critical_boundary_mocks':'Only cache.load/exchange.receive/external reserve/network/labels/Signal/fullprepare/Store construction forbidden tripwires. Controller.reflect, parsing configuration, complete_json forwarding, anonymous serialization, request journal and actual candidate request_ready_observer are not mocked.'},
 'candidate_delta':['Keep explicit legal FINALIZE/0needs empty carrier and defaultPlan. Correction CONFIG becomes1 to satisfy native _complete_parsed_role_impl; no actual author correction can execute because capture stops before cache/receive.','Actual observer independently checks canonical native messages JSON UTF8 bytes plus max_output_tokens reservation <=131072. Cap1 synthetic proves its rejection, not only a setter argument.','Distinct execution-v3/contract-v3/script preserves both failed outputs; no retry/resume of old failure root. Old zero journals plus new at-most-one retains the original total ceiling.'],
 'gold_unchanged':'d23d six expected values/states/period/unit/canonical claims, eleven operands, evidence/PIT/fingerprint/privacy and excluded3 scope remain unchanged; expectations only sha-checked, never parsed into payload.',
 'limitations':['Synthetic positives cover numeric and narrative request construction with different synthetic documents, not source measurement correctness or model behavior.','Pre-egress kwargs are deliberately unmasked audit material; only actual native outgoing request is expected anonymous.','Old invalid ResearchState and invalid correction configuration were harness preconditions, not actual6 projection failures; neither is reclassified success.','FINALIZE carrier is not normal production continuation, accepted GPRE prior/H_init/ownership or fresh F7. No source admission or old F6 rerun allowed.','At review no actual candidate3 capture has run. Final actual request equality and all counts must be audited against original d23d afterward.'],
 'evidence_bindings':[{'path':str(p),'sha256':sha(p)} for p in files]}
p=I/'third-candidate-preflight-review.json';p.write_text(json.dumps(r,indent=2)+'\n');print(sha(p))
