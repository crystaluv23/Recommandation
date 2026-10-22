"""Independent synthetic source-backed wiring checks; no labels, models, network, or product edits."""
from __future__ import annotations
import copy, hashlib, json, socket, traceback
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from stock_opportunity_agent.data.raw_info import RawInfoStore, RawInfoDocument
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (SignalSpec, SignalExecutionType, FrozenSignalRegistry, SignalExecutor, SignalResult, SignalValue, SignalBatchResult, signal_result_model_view, signal_classification_contract, saved_signal_classification_contracts, default_deterministic_signal_functions, signal_parameter_names)
from stock_opportunity_agent.research.evolution_core import (ResearchState, ResearchDecision, SignalSelectionDecision, SignalRound, _assemble_final_context, default_information_plan)
from stock_opportunity_agent.research.evolution_plan_roles import _plan_critic_trajectory
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context, _require_context_signal_pit
from stock_opportunity_agent.research.evolution_research_validation import _signal_batch_model_view
socket.socket = lambda *a, **k: (_ for _ in ()).throw(AssertionError('Network forbidden'))
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[3]
FILES=['src/stock_opportunity_agent/signal_library.py','src/stock_opportunity_agent/research/evolution_core.py','src/stock_opportunity_agent/research/evolution_plan_roles.py','src/stock_opportunity_agent/research/evolution_research_validation.py','src/stock_opportunity_agent/research/evolution_output_validation.py','src/stock_opportunity_agent/research/signal_evolution.py','spec/src/stock_opportunity_agent/signal_library.md','spec/src/stock_opportunity_agent/research/evolution_core.md','spec/src/stock_opportunity_agent/research/evolution_plan_roles.md','tests/test_signal_classification_contract.py']
def hashes(): return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
BEFORE=hashes()
ASOF=datetime(2025,1,31,tzinfo=timezone.utc)
NEEDS=('What funding obligations remain unknown?',)
STATE=ResearchState(next_information_needs=NEEDS,decision=ResearchDecision.FINALIZE)
CHECKS=[]
def check(name,fn):
    try:
        detail=fn(); CHECKS.append({'name':name,'pass':True,'detail':detail})
    except Exception as e:
        CHECKS.append({'name':name,'pass':False,'error_type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc()})
def expect_reject(fn):
    try: fn()
    except ValidationError as e: return str(e)
    raise AssertionError('Expected ValidationError')
def fixture(pos=6,neg=12,ocf=-60,cash=100):
    spec=SignalSpec('runway_scope',1,'financial','Independent synthetic runway control',SignalExecutionType.DETERMINISTIC,('financials',),function='financial.liquidity_runway_months',parameters={'positive_runway_max_months':pos,'negative_runway_min_months':neg})
    content=json.dumps({'schema_version':'sec-company-facts-document-v1','filing_date':'2025-01-20','form':'10-K','cik':'0000000001','facts':[{'taxonomy':'us-gaap','tag':'CashAndCashEquivalentsAtCarryingValue','start':None,'end':'2024-12-31','unit':'USD','value':cash},{'taxonomy':'us-gaap','tag':'NetCashProvidedByUsedInOperatingActivities','start':'2024-10-01','end':'2024-12-31','unit':'USD','value':ocf}]},sort_keys=True,separators=(',',':'))
    t=datetime(2025,1,20,tzinfo=timezone.utc)
    doc=RawInfoDocument.create(document_id='independent-source',company_id='cik_0000000001',source_type='financials',published_at=t,available_at=t,content=content,metadata={'cik':'0000000001'})
    registry=FrozenSignalRegistry(1,'f'*64,(spec,),{})
    store=RawInfoStore(documents=(doc,))
    return spec,registry,store

def execute(**kwargs):
    spec,registry,store=fixture(**kwargs)
    ex=SignalExecutor(registry,store)
    batch=ex.execute_batch((spec.ref,),company_id='cik_0000000001',as_of=ASOF)
    result=batch.results[0]
    return spec,ex,batch,result,ex.classification_contracts_for((result,))

def metadata(card): return card['interpretation'].get('measurement_context',{})
def intent(ref): return SignalSelectionDecision(ref,reason_code='combine_evidence',selection_reason='Historical context.',applicability_hypothesis='No question answered.',expected_role='coverage',context_tags=('capital_intensive',))
def context(results,contracts):
    rounds=tuple(SignalRound(NEEDS,(intent(r.ref),),SignalBatchResult((r,),1)) for r in results)
    c=_assemble_final_context(plan=default_information_plan(),company_id='cik_0000000001',additional_identity_aliases=(),basic_info={'requests':[]},state=STATE,rounds=rounds,prediction_time=ASOF,signal_classification_contracts=contracts)
    return rounds,c

def critic(rounds,c):
    # No labels or truth objects are provided or read in this synthetic trajectory.
    data={'final_context':c,'signal_rounds':[r.to_dict() for r in rounds]}
    item=SimpleNamespace(signal_rounds=rounds,prediction_time=ASOF,state_deltas=(),to_dict=lambda:copy.deepcopy(data))
    return _plan_critic_trajectory(item,case_index=1)

def scalar_states():
    rows=[]
    for pos,neg,expected in ((6,12,'positive'),(4,12,'neutral'),(3,4,'negative'),(5,5,'positive')):
        s,ex,b,r,cs=execute(pos=pos,neg=neg)
        original=r.to_dict(); m=metadata(signal_result_model_view(r,classification_contract=cs[s.ref]))
        assert m['numeric_measurement']['value']==5.0
        assert m['numeric_measurement']['numeric_sign']=='positive'
        assert m['numeric_measurement']['categorical_state']==expected
        assert cs[s.ref]['execution']['configured_parameters']==dict(s.parameters)
        assert 'positive branch is checked first' in cs[s.ref]['execution']['contract']
        assert original==r.to_dict() and 'classification_contract' not in original['interpretation']
        rows.append({'parameters':[pos,neg],'value':5.0,'numeric_sign':'positive','state':expected})
    return rows
check('same_positive_scalar_different_states_and_equal_boundary',scalar_states)

s,ex,b,live,decl=execute()
clone=SignalResult.from_dict(live.to_dict())
check('exact_object_sidecar_and_thaw_copy',lambda:(
    (lambda:None)() if ex.classification_contracts_for((clone,))=={} else (_ for _ in ()).throw(AssertionError('clone inherited contract'))))
def thaw():
    a=ex.classification_contracts_for((live,));a[s.ref]['execution']['configured_parameters']['positive_runway_max_months']=999
    assert ex.classification_contracts_for((live,))[s.ref]['execution']['configured_parameters']['positive_runway_max_months']==6
    return 'Returned metadata mutation does not mutate sidecar'
check('sidecar_copies_are_isolated',thaw)

def rounds_case(results,contracts,expected):
    rounds,c=context(results,contracts)
    c=json.loads(json.dumps(c))
    assert c['final_research_state']['next_information_needs']==list(NEEDS)
    _require_context_signal_pit(c)
    actual=[bool(saved_signal_classification_contracts(c,round_index=i)) for i in range(len(results))]
    assert actual==expected,(actual,expected)
    cr=critic(rounds,c)
    got=['classification_contract' in metadata(row['signal_results'][0]) for row in cr['signal_rounds']]
    assert got==expected,(got,expected)
    compact=_compact_posthoc_context(c)
    got_post=['classification_contract' in metadata(card) for card in compact['signal_results']]
    assert got_post==expected,(got_post,expected)
    return {'expected':expected,'final':actual,'critic':got,'posthoc':got_post}
check('legacy_then_live_same_ref_no_backfill',lambda:rounds_case((clone,live),({},decl),[False,True]))
check('live_then_clone_same_ref_no_forward_fill',lambda:rounds_case((live,clone),(decl,{}),[True,False]))
s2,ex2,b2,live2,decl2=execute(cash=180)
check('two_live_same_ref_distinct_result_hash_per_round',lambda:rounds_case((live,live2),(decl,decl2),[True,True]))
check('same_ref_wrong_result_binding_reject',lambda:expect_reject(lambda:signal_result_model_view(live2,classification_contract=decl[s.ref])))
check('misaligned_per_round_contract_reject',lambda:expect_reject(lambda:context((live,live2),(decl2,decl))))
check('wrong_round_coordinate_count_reject',lambda:expect_reject(lambda:context((live,live2),(decl,))))

def override():
    sp,reg,store=fixture()
    default=default_deterministic_signal_functions()[sp.function]
    def later(*args):
        """Later mapping must not supply the earlier invoked declaration."""
        raise AssertionError('not invoked')
    @signal_parameter_names('positive_runway_max_months','negative_runway_min_months')
    def fn(*args):
        """Actual custom callable controls its own declared states."""
        executor.deterministic_functions[sp.function]=later
        return default(*args)
    executor=SignalExecutor(reg,store,deterministic_functions={sp.function:fn})
    batch=executor.execute_batch((sp.ref,),company_id='cik_0000000001',as_of=ASOF)
    contract=executor.classification_contracts_for(batch.results)[sp.ref]
    assert contract['execution']['contract']==fn.__doc__
    skipped=executor.execute_batch((sp.ref,),company_id='cik_0000000001',as_of=ASOF,prior_fingerprints=batch.document_fingerprints)
    assert not skipped.results and executor.classification_contracts_for(batch.results)=={}
    return 'Actual callable captured before invocation map mutation; skipped batch clears old sidecar'
check('same_name_override_precall_and_skip',override)

def unknown_llm():
    unknown=signal_classification_contract(s)
    assert not unknown['declaration_available']
    llm=replace(s,execution_type=SignalExecutionType.LLM,function=None,skill_file='skill.md',parameters={'materiality':7})
    text='Complete frozen skill: interpret only declared branches. '*500
    d=signal_classification_contract(llm,skill=text)
    assert d['execution']['contract']==text and d['execution']['configured_parameters']=={'materiality':7}
    assert d['declaration_available']
    return {'unknown_default_absent':True,'full_skill_chars':len(text),'retained_chars':len(d['execution']['contract'])}
check('unknown_no_default_and_full_skill_not_truncated',unknown_llm)

def unbounded_missing():
    sp,e,ba,r,ds=execute(ocf=0)
    m=metadata(signal_result_model_view(r,classification_contract=ds[sp.ref]))
    assert r.value is SignalValue.NEGATIVE and 'numeric_measurement' not in m and 'classification_contract' in m
    missing_ex=SignalExecutor(fixture()[1],RawInfoStore())
    missing=missing_ex.execute_batch((s.ref,),company_id='cik_0000000001',as_of=ASOF).results[0]
    assert missing_ex.classification_contracts_for((missing,))=={}
    assert 'measurement_context' not in signal_result_model_view(missing,classification_contract=decl[s.ref])['interpretation']
    return 'Available nonnumeric negative keeps declaration; unavailable stays status-only'
check('unbounded_and_unavailable_are_distinct',unbounded_missing)

def bad_bindings():
    reasons=[]
    for patch in ({'signal_ref':'runway_scope:v2'},{'definition':'tampered'},{'result_hash':'0'*64},{'spec_hash':'0'*64}):
        reasons.append(expect_reject(lambda p=patch:signal_result_model_view(live,classification_contract={**decl[s.ref],**p})))
    forged=live.to_dict();forged['interpretation']['measurement_context']={'classification_contract':decl[s.ref]}
    assert 'classification_contract' not in metadata(signal_result_model_view(forged))
    return reasons
check('identity_hash_tamper_and_model_injected_projection',bad_bindings)

def reflect_projection():
    with_decl=_signal_batch_model_view(b,classification_contracts=decl)
    without_decl=_signal_batch_model_view(SignalBatchResult((clone,),1),classification_contracts={})
    assert with_decl[0]['measurement_context']['classification_contract']==decl[s.ref]
    assert 'classification_contract' not in without_decl[0]['measurement_context']
    return 'Current empty batch map stays empty; complete saved declaration unchanged'
check('reflect_projection_current_batch_only',reflect_projection)
AFTER=hashes()
report={'schema':'independent-classification-counterexamples-v1','scope':'Synthetic deterministic source facts and no-label trajectory; offline wiring only; no model/production calls.','checks':CHECKS,'passed':sum(c['pass'] for c in CHECKS),'total':len(CHECKS),'source_hashes_before':BEFORE,'source_hashes_after':AFTER,'source_drift':BEFORE!=AFTER,'network_calls':0,'new_model_calls':0,'product_edits':0,'canonical_result_changed':live.to_dict()!=clone.to_dict()}
(BASE/'counterexample-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'total':report['total'],'source_drift':report['source_drift'],'failed':[{'name':c['name'],'error':c.get('error')} for c in CHECKS if not c['pass']]},indent=2))
