"""Capture the unmodified two-fact consumer boundary before its repair."""
from datetime import datetime
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import ExitStack
import hashlib,json,socket
from diagnose_executed_answer_scope import StageContract,binding,read_json
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_core import EvolutionControlFlow
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient,ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange,_immutable
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
REPO=Path.cwd();BASE=REPO/'runs/diagnostics/mining_taxonomy_consumer_20261023_v1';ROOT=BASE/'baseline'
if ROOT.exists():raise AssertionError('single entry only')
ROOT.mkdir()
class Captured(EvolutionControlFlow):pass
def forbidden(*a,**kw):raise AssertionError('network forbidden')
def save(name,v):_immutable(ROOT/(name+'.json'),v)
forbidden_reads=[]
with ExitStack() as guards:
 for owner,name in ((socket,'create_connection'),(socket.socket,'connect'),(socket.socket,'connect_ex'),(ExternalAttemptLedger,'reserve')):
  guards.enter_context(patch.object(owner,name,forbidden))
 inventory=read_json(REPO/'runs/diagnostics/mining_positive_frontier_20261021_v1/oracle/static-inventory.json')
 src=inventory['sources']['first_native_manifest_wire'];binding(Path(src['path']),src['sha256'])
 inbox=read_json(Path(src['path']));payload=json.loads(next(m['content'] for m in inbox['messages'] if m['role']=='user'))
 metadata=next(r for r in inventory['dev8'] if r['case_ref']=='case-008')
 ref=metadata['case_ref'];label=payload['label_map'][ref]
 assert payload['case_prediction_times'][ref]==metadata['cutoff']
 case=SimpleNamespace(case_id=metadata['case_id'],company_id=metadata['case_id'].split(':')[0],prediction_time=datetime.fromisoformat(metadata['cutoff']),ground_truth=SimpleNamespace(is_surge=label=='positive'))
 snapshot=inventory['sources']['reviewed_snapshot'];binding(Path(snapshot['path']),snapshot['sha256'])
 store=open_raw_info_store(Path(snapshot['path']).parent,reviewed_snapshot={'root':str(Path(snapshot['path']).parent),'store_type':'reviewed','manifest_sha256':snapshot['sha256']})
 def observe(event):
  if event.get('event_type')=='request_ready':save('request-ready',event);raise Captured()
 contract={'limits':{'max_request_tokens':65536,'max_structured_corrections':1,'max_case_tokens':98304,'max_local_role_calls':1,'structured_reasoning_token_reserve':0}}
 caller=StructuredRoleClient(registration=get_model('independent-subagent'),contract=StageContract(contract),workspace=ROOT,ledger=ExternalAttemptLedger(ROOT/'unused_external.json',max_attempts=1,max_total_cost=.01),local_role_exchange=LocalRoleExchange(ROOT/'exchange',max_calls=1),allow_external=False,environ={},on_progress=observe)
 controller=LabelAwareMiningController(store=store,model=MiningAgentRoleModel(caller),case_pairs=[(ref,case)],measurable_evidence_manifest={},signal_catalog=[],seed='discovery',label_map={ref:label},heavy_action_limit=6,identity_aliases=(case.case_id,case.company_id))
 def execute(raw):controller._validate_action_shape(raw);controller._execute(raw['action'],raw)
 execute({'action':'fetch_evidence','rationale':['Controlled source preparation.'],'case_refs':[ref],'source_families':['sec_company_facts'],'max_documents':1})
 tag='NetCashProvidedByUsedInOperatingActivities'
 facts=sorted((f for f in controller._facts.values() if f.concept==tag),key=lambda f:f.period['end'])
 assert len(facts)==2 and {f.taxonomy for f in facts}=={'us-gaap'}
 reads=[]
 for f in facts:
  execute({'action':'read_span','rationale':['Controlled operand visibility probe.'],'fact_ref':f.fact_ref});reads.append(controller._last_action_result)
 execute({'action':'compare_groups','rationale':['Controlled comparison visibility probe.'],'concepts':[tag]})
 save('read-receipts',{'reads':reads,'facts':[asdict(f) for f in facts],'ledger':controller.ledger.to_dict()})
 stopped=False
 try:controller.model.next_action(controller._model_view())
 except Captured:stopped=True
 assert stopped and not list(ROOT.rglob('inbox/*.json'))
 save('result',{'state':'captured_missing_two_operand_read_context','read_count':2,'final_view_has_fact_history':'structured_read_progress' in controller._model_view(),'final_last_action':controller._model_view()['last_action_result']['action'],'source_file':binding(REPO/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/0671.json'),'controller_code':binding(REPO/'src/stock_opportunity_agent/research/mining_controller.py'),'script':binding(Path(__file__)),'production_answers':0,'inboxes':0,'external_API':0,'new_business_labels':0,'label_scope':'Only prior native opaque dev8 label_map[case-008] imported; no labelstore/check/LockedTest.'})
print('baseline native request-ready capture: two fact reads lost; no model receive/inbox')
