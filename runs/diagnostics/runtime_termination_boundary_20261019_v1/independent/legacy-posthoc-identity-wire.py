import json,sys,socket,tempfile,hashlib,argparse,importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace
sys.path[:0]=['/Users/l/Project/Recommandation/src']
from stock_opportunity_agent.data.resolution import BasicInfoBundle
from stock_opportunity_agent.research.evolution_core import (ResearchState,RuntimeStopReason,RuntimeUsage,BlindPrediction,GroundTruth,PredictionSelfReflection,ExecutionTrajectory,PlanMetrics,default_information_plan,project_basic_info_bundle,_assemble_final_context,_mask_identity_values)
parser=argparse.ArgumentParser(description='Actual production pending-wire probe; synthetic transport prediction/truth, no answers.')
parser.add_argument('--roles-source',type=Path,default=Path(__file__).parents[1]/'critic_wire_original_roles.py.txt')
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--legacy',action='store_true')
parser.add_argument('--alias-probe',action='store_true')
args=parser.parse_args()
loader=SourceFileLoader('role_wire_module_under_audit',str(args.roles_source.resolve()))
spec=importlib.util.spec_from_loader(loader.name,loader);module=importlib.util.module_from_spec(spec);sys.modules[loader.name]=module;loader.exec_module(module)
LLMBlindPredictor,LLMPlanCritic=module.LLMBlindPredictor,module.LLMPlanCritic
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient,ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange,LocalRoleRequestPending
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.llm.agent import AgentUsage
socket.socket=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden'))
repo=Path('/Users/l/Project/Recommandation');src=json.loads((repo/'runs/diagnostics/reviewed_market_snapshot_20261019_v2/basic_info.json').read_text());
if args.alias_probe:
 for source_row in src['bundle']['requests']:
  if source_row['request']['request_id']=='recent_market_backbone':
   source_row['omitted_context_markers'].append('BMBL Bumble Inc. cik_0001830043 synthetic marker identity probe')
model,lineage=project_basic_info_bundle(BasicInfoBundle.from_dict(src['bundle']));state=ResearchState(next_information_needs=('What operating evidence remained undisclosed by prediction time?',));cut=datetime.fromisoformat('2025-09-30T00:00:00+00:00');aliases=('cik_0001830043','BMBL','Bumble Inc.','Bumble');plan=default_information_plan();final=_assemble_final_context(plan=plan,company_id=aliases[0],additional_identity_aliases=aliases,basic_info=model,state=state,rounds=(),prediction_time=cut);masked_model=_mask_identity_values(model,aliases);direct={**final,'basic_info':masked_model};pred=BlindPrediction(False,'insufficient_information',None,'low',('Synthetic transport fixture; no research conclusion.',),('No model answer was generated.',),'synthetic_visibility_transport');truth=GroundTruth(1.0);reflection=PredictionSelfReflection(True,no_findings_reason='Synthetic diagnostic only; no model reflection.');trajectory=ExecutionTrajectory(company_id=aliases[0],prediction_time=cut,basic_info=src['bundle'],initial_state=state,signal_rounds=(),final_state=state,final_context=final,prediction=pred,prediction_ref='synthetic_prediction_ref',ground_truth=truth,self_reflection=reflection,stop_reason=RuntimeStopReason.NO_SIGNAL_MATCH,usage=RuntimeUsage(0,0,AgentUsage()),basic_info_projection=lineage);metrics=PlanMetrics(0,0,0,0,0,0,0,1,0,1)
if args.legacy:
 from dataclasses import replace
 legacy=json.loads((repo/'runs/diagnostics/basic_info_visibility_boundary_20261019_v1/final_context.json').read_text())
 trajectory=replace(trajectory,final_context=legacy)
rows=[]
with tempfile.TemporaryDirectory(prefix='independent-real-role-wire-') as td:
 root=Path(td);contract=SimpleNamespace(contract_hash='f'*64,limits={'max_structured_corrections':1,'max_request_tokens':131072});client=StructuredRoleClient(registration=get_model('independent-subagent'),contract=contract,workspace=root,ledger=ExternalAttemptLedger(root/'attempts.json',max_attempts=1,max_total_cost=1),local_role_exchange=LocalRoleExchange(root/'exchange',max_calls=8),allow_external=False,environ={});predictor=LLMBlindPredictor(client,anonymous_aliases=aliases);critic=LLMPlanCritic(client);critic.set_anonymous_aliases(aliases)
 with client.anonymous_case(aliases=aliases,company_id=aliases[0],ticker='BMBL'):
  for name,action in [('Posthoc_final',lambda:predictor.reflect(final,pred,truth))]:
   try:action();raise AssertionError('role unexpectedly completed without answer')
   except LocalRoleRequestPending as exc:
    p=Path(exc.pending['inbox_path']);inbox=json.loads(p.read_text());wire=json.dumps(inbox['messages']);payload=json.loads(inbox['messages'][-1]['content']);print(name,'payloadkeys',list(payload),flush=True)
    def collect(x):
     found=[]
     if isinstance(x,dict):
      if x.get('request_id')=='recent_market_backbone' and 'effective_context_truncated' in x:found.append(x)
      for v in x.values():found.extend(collect(v))
     elif isinstance(x,list):
      for v in x:found.extend(collect(v))
     return found
    profiles=payload.get('basic_info_visibility_profiles',{})
    packed=payload.get('trajectories',[])
    expanded=[]
    for t in packed:
     expanded.extend([{**profiles[r['profile_ref']],**({'projection_ids':r['projection_ids']} if 'projection_ids' in r else {})} for r in t['basic_info_source_index']])
    expected=[]
    if name=='Critic':
     expected=_mask_identity_values(module._plan_critic_trajectory(trajectory,case_index=1)['basic_info_source_index'],aliases)
     assert expanded==expected,(expanded,expected)
     assert all(set(r)<= {'profile_ref','projection_ids'} for t in packed for r in t['basic_info_source_index'])
    found=collect(expanded if name=='Critic' else payload);rows.append({'role':name,'request_hash':exc.pending['request_hash'],'stage':exc.pending['stage'],'inbox_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'market_visibility_rows':found,'profiles':profiles,'packed_trajectories':packed,'exact_reconstruction':expanded==expected if name=='Critic' else None,'raw_identity_absent':all(x not in wire for x in aliases),'synthetic_prediction_and_outcome_only_for_transport':name!='Predictor'});print(name,'market_visibility_count',len(found),flush=True)
out={'scope':'Actual production roles/client/anonymous pending wire capture; no role answer or research completion. Prediction/truth are explicit synthetic transport fixtures.','rows':rows,'role_answers':0,'network_calls':0,'legacy_fixture':args.legacy,'synthetic_marker_alias_probe':args.alias_probe,'roles_source_sha256':hashlib.sha256(args.roles_source.read_bytes()).hexdigest(),'visibility_helper_sha256':hashlib.sha256((repo/'src/stock_opportunity_agent/research/basic_info_visibility.py').read_bytes()).hexdigest()};args.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
