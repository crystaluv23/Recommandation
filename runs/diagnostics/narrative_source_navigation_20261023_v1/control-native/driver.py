"""Frozen actual-source capability control, exact native roles and no network."""
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

from diagnose_executed_answer_scope import StageContract
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending, _immutable
from stock_opportunity_agent.research.signal_source_reading import SignalSourceSession
from stock_opportunity_agent.signal_library import FrozenSignalRegistry, SignalSpec, SignalExecutor, SignalRetrievalPolicy, SignalExecutionType, LLMSignalBatchInput

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
DEFINITION=ROOT.parent/'control-definition.json'
ORACLE=ROOT.parent/'control-oracle/oracle.json'
CLARIFICATION=ROOT.parent/'control-oracle/evidence-matching-clarification.json'


def read(path):
    """Read one local frozen JSON object."""
    return json.loads(Path(path).read_bytes())


def bindings():
    """Bind production code and the private source-only definition/reference."""
    files=[*sorted((REPO/'src').rglob('*.py')),Path(__file__),DEFINITION,ORACLE,CLARIFICATION]
    return {str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def registry(inputs):
    """Construct only the isolated test registry; do not publish a Signal."""
    spec=SignalSpec.from_dict(inputs['spec'])
    return FrozenSignalRegistry(version=1,registry_hash=canonical_json_hash(inputs['spec']),
        specs=(spec,),skills={spec.ref:inputs['skill']})


def prepare():
    """Freeze qualified actual sources without supplying private coordinates."""
    definition=read(DEFINITION)
    oracle=read(ORACLE)
    # The source reference is mandatory, frozen and outside all role requests.
    if oracle.get('status')!='supported_unique_state':
        raise ValidationError('control source-only answerability precondition missing')
    plan=read(REPO/'runs/diagnostics/measurement_input_selection_20261021_v1/plan.json')
    sample=read(REPO/'runs/diagnostics/gpre_native_initial_20261021_v1/stage/inputs.json')['sample']
    cutoff=datetime.fromisoformat(sample['prediction_time'])
    source_view=open_raw_info_store(plan['reviewed_source_snapshot']['root'],reviewed_snapshot=plan['reviewed_source_snapshot'])
    spec=SignalSpec(signal_id=definition['signal_id'],version=definition['version'],category='catalysts',
        description=definition['definition'],execution_type=SignalExecutionType.LLM,
        source_types=tuple(definition['retrieval']['source_types']),skill_file='control.md',
        parameters={'window_calendar_days':definition['window_calendar_days']},
        retrieval_policy=SignalRetrievalPolicy(lookback_days=definition['retrieval']['lookback_days'],
            query_terms=tuple(definition['retrieval']['query_terms'])))
    skill=definition['definition']+' States: '+json.dumps(definition['states'])+' Obligations: '+' '.join(definition['evidence_obligations'])
    inputs={'as_of':cutoff.isoformat(),'spec':spec.to_dict(),'skill':skill,'sample':sample,
        'scope':definition['scope']}
    ex=SignalExecutor(registry(inputs),source_view)
    resolution=ex.prepare_inputs((spec.ref,),company_id=sample['company_id'],identity=sample['identity'],as_of=cutoff)[0]
    docs=ex.resolver.eligible_documents(resolution.request,company_id=sample['company_id'],identity=sample['identity'],as_of=cutoff)
    inputs['documents']=[d.to_dict() for d in docs]
    selected=ex.resolver.load_documents(resolution,as_of=cutoff)
    session=SignalSourceSession(LLMSignalBatchInput(SignalSpec.from_dict(inputs['spec']),selected,skill,docs),cutoff)
    catalog=session.catalog()
    _immutable(ROOT/'inputs.json',inputs)
    _immutable(ROOT/'preflight.json',{'source_view':len(source_view.documents),'eligible':len(docs),
        'catalog':catalog,'body_read_documents':len(session.documents),'code':bindings(),
        'scope':'input-only, no private oracle coordinates used in navigation'})
    _immutable(ROOT/'contract.json',{'schema_version':'actual-source-maturity-control-v1',
        'scope':definition['scope'],'code':bindings(),'input_hash':canonical_json_hash(inputs),
        'source_snapshot':plan['reviewed_source_snapshot'],'external_llm_api_calls':0,
        'limits':{'max_structured_corrections':1,'max_request_tokens':65536,'max_case_tokens':131072,'max_local_role_calls':4}})


def resume():
    """Reconstruct unchanged executor state until pending or completed."""
    contract=read(ROOT/'contract.json'); inputs=read(ROOT/'inputs.json')
    if contract['code']!=bindings() or contract['input_hash']!=canonical_json_hash(inputs):
        raise ValidationError('frozen actual-source control code/input drift')
    exchange=LocalRoleExchange(ROOT/'exchange',max_calls=4)
    caller=StructuredRoleClient(registration=get_model('independent-subagent'),contract=StageContract(contract),
        workspace=ROOT,ledger=ExternalAttemptLedger(ROOT/'unused_external.json',max_attempts=1,max_total_cost=.01),
        allow_external=False,local_role_exchange=exchange,environ={})
    runner=StructuredLLMSignalRunner(caller)
    runner.set_request_token_budget(contract['limits']['max_case_tokens'])
    sample=inputs['sample']
    runner.set_identity_cases((SimpleNamespace(case_id='r01',company_id=sample['company_id'],basic_info=sample['identity']),))
    ex=SignalExecutor(registry(inputs),RawInfoStore(documents=tuple(RawInfoDocument.from_dict(d) for d in inputs['documents'])),llm_runner=runner)
    try:
        batch=ex.execute_batch((inputs['spec']['signal_id']+':v1',),company_id=sample['company_id'],
            identity=sample['identity'],as_of=datetime.fromisoformat(inputs['as_of']))
    except LocalRoleRequestPending as pending:
        return {'state':'pending',**pending.pending}
    record={'results':[r.to_dict() for r in batch.results],'resolutions':[r.to_dict() for r in batch.resolutions],
        'usage':asdict(batch.usage),'document_fingerprints':{k:list(v) for k,v in batch.document_fingerprints.items()},
        'request_hashes':caller.request_hash_trace}
    _immutable(ROOT/'result.json',record)
    _immutable(ROOT/'completion.json',{'state':'completed','production_receipts':len(list((ROOT/'exchange/receipts').glob('*.json'))),
        'execution_status':batch.results[0].execution_status.value,'scope':contract['scope'],
        'semantic_acceptance':'pending independent source comparison; mechanical result is not semantic acceptance',
        'external_llm_api_calls':0})
    return {'state':'completed','result_path':str(ROOT/'result.json')}


if __name__=='__main__':
    def forbidden(*args,**kwargs): raise AssertionError('network forbidden in actual-source native control')
    socket.create_connection=forbidden
    socket.socket.connect=forbidden
    socket.socket.connect_ex=forbidden
    if sys.argv[1:]==['prepare']:
        prepare(); print(json.dumps({'state':'prepared'}))
    else:
        print(json.dumps(resume()))
