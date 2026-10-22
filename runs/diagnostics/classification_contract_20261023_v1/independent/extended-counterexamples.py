"""Further independent boundary checks using only synthetic facts and no model/labels."""
import copy, json, runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
p=Path(__file__).resolve().parent
h=runpy.run_path(str(p/'counterexamples.py'))
checks=[]
def check(name,fn):
    try: checks.append({'name':name,'pass':True,'detail':fn()})
    except Exception as e: checks.append({'name':name,'pass':False,'error_type':type(e).__name__,'error':str(e)})
def require(x):
    if not x: raise AssertionError('Expected true')
from stock_opportunity_agent.signal_library import SignalExecutionStatus, signal_execution_failure_result
from stock_opportunity_agent.research.evolution_core import _merge_runtime_signal_batches, _mask_identity_values, _assert_identity_values_masked, ResearchEvidenceRef
from stock_opportunity_agent.research.evolution_research_validation import _validate_research_state_refs
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor, LLMResearchController
from stock_opportunity_agent.llm.agent import AgentUsage

def default_values():
    got=[]
    for months,expected in ((5,'positive'),(6,'positive'),(9,'neutral'),(12,'negative'),(13,'negative')):
        s,e,b,r,d=h['execute'](cash=months*20)
        require(r.value.value==expected and r.measurement.value==months)
        got.append([months,expected])
    for months,expected in ((5,'neutral'),(9,'negative')):
        s,e,b,r,d=h['execute'](pos=3,neg=8,cash=months*20)
        require(r.value.value==expected)
        got.append([months,expected,{'positive_max':3,'negative_min':8}])
    return got
check('exact_default_boundaries_and_nondefault_3_8',default_values)

def default_and_partial():
    s,reg,store=h['fixture']();f=h['default_deterministic_signal_functions']()[s.function]
    omitted=replace(s,parameters={})
    d=h['signal_classification_contract'](omitted,deterministic_functions={s.function:f})
    require(d['execution']['configured_parameters']=={} and 'default 6' in d['execution']['contract'])
    def undocumented(*a): return f(*a)
    undocumented.__signal_parameter_names__=('duplicate','duplicate')
    d=h['signal_classification_contract'](s,deterministic_functions={s.function:undocumented})
    require(not d['declaration_available'] and d['execution']['parameter_names'] is None and d['execution']['configured_parameters'] is None)
    def only_text(*a):
        """A partial description without inferred names or default branches."""
        return f(*a)
    d=h['signal_classification_contract'](s,deterministic_functions={s.function:only_text})
    require(d['declaration_available'] and d['execution']['parameter_names'] is None)
    return 'Exact explicit defaults copied as text; no synthesized config; malformed consumed-name metadata remains unknown'
check('omitted_defaults_and_partial_or_invalid_declaration',default_and_partial)

def failures_status_only():
    s,e,b,r,d=h['execute']()
    rows=[]
    for status in SignalExecutionStatus:
        if status in (SignalExecutionStatus.SUCCESS,SignalExecutionStatus.DOMAIN_UNAVAILABLE): continue
        fail=signal_execution_failure_result(s,status=status,error_code='independent_control',error_message='Synthetic failure')
        v=h['signal_result_model_view'](fail,classification_contract=d[s.ref])
        require('measurement_context' not in v['interpretation'])
        rows.append(status.value)
    return rows
check('all_five_technical_statuses_keep_status_only',failures_status_only)

def mixed_batch():
    s,reg,store=h['fixture'](); live=h['execute']()[3]
    llm=replace(s,signal_id='llm_scope',execution_type=h['SignalExecutionType'].LLM,function=None,skill_file='skill.md',parameters={'nested':{'branch':['a','b']}})
    skill='完整技能 Independent Issuer Inc. END_BRANCH\n'*1200
    frozen=h['FrozenSignalRegistry'](1,'f'*64,(s,llm),{llm.ref:skill})
    result=replace(live,signal_id=llm.signal_id,measurement=None,interpretation='Synthetic source evidence remains historical.')
    runner=SimpleNamespace(execute=lambda *args:(result,AgentUsage()))
    ex=h['SignalExecutor'](frozen,store,llm_runner=runner)
    a=ex.execute_batch((s.ref,),company_id='cik_0000000001',as_of=h['ASOF'])
    b=ex.execute_batch((llm.ref,),company_id='cik_0000000001',as_of=h['ASOF'])
    merged=_merge_runtime_signal_batches((llm.ref,s.ref),(a,b))
    require(merged.results[0] is b.results[0] and merged.results[1] is a.results[0])
    cs=ex.classification_contracts_for(merged.results)
    require(set(cs)=={s.ref,llm.ref})
    require(cs[llm.ref]['execution']['contract']==skill)
    projection=h['_signal_batch_model_view'](merged,classification_contracts=cs)
    require(projection[0]['interpretation']['measurement_context']['classification_contract']['execution']['contract']==skill)
    rounds,c=h['context']((merged.results[0],),( {llm.ref:cs[llm.ref]},))
    compact=h['_compact_posthoc_context'](c)
    require(h['metadata'](compact['signal_results'][0])['classification_contract']==cs[llm.ref])
    masked=_mask_identity_values(c,('Independent Issuer Inc.',),expand_aliases=False)
    _assert_identity_values_masked(masked,('Independent Issuer Inc.',),expand_aliases=False)
    require('END_BRANCH' in json.dumps(masked,ensure_ascii=False))
    return {'skill_chars':len(skill),'reflect_retained_chars':len(projection[0]['interpretation']['measurement_context']['classification_contract']['execution']['contract']),'merge_preserves_objects':True,'nonnumeric_posthoc_preserves_skill':True,'alias_masked_at_egress':True}
check('mixed_subgroups_full_llm_skill_nonnumeric_and_masking',mixed_batch)

def predictor_preflight():
    s,e,b,r,d=h['execute']()
    rounds,c=h['context']((r,),(d,))
    c['runtime_termination']={'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':None}
    got={}
    def estimate(**kwargs): got['estimate']=kwargs;return len(json.dumps(kwargs,ensure_ascii=False,sort_keys=True))
    predictor=LLMBlindPredictor(SimpleNamespace(estimate_json_request_tokens=estimate),anonymous_aliases=('Private Identity',))
    required=predictor.estimate_prediction_tokens(c)
    require(required>0 and got['estimate']['payload']['final_context']==c)
    import stock_opportunity_agent.research.evolution_plan_roles as mod
    class Stop(Exception): pass
    def intercept(*args,**kwargs): got['dispatch']=kwargs;raise Stop()
    try:
        with patch.object(mod,'_complete_parsed_role',side_effect=intercept): predictor.predict(c)
    except Stop: pass
    require(got['estimate']['payload']==got['dispatch']['payload'])
    require(got['estimate']['max_output_tokens']==got['dispatch']['max_output_tokens'])
    require(got['estimate']['anonymous_aliases']==got['dispatch']['anonymous_aliases'])
    controller=LLMResearchController(SimpleNamespace())
    controller.set_signal_classification_contracts(d);controller.set_signal_classification_contracts({})
    require(controller.signal_classification_contracts=={})
    return {'full_context_equal_at_estimate_dispatch_boundary':True,'configured_output_reserve_equal':True,'anonymity_args_equal':True,'empty_current_setter_clears':True,'wire_billing_not_independently_recomputed':True}
check('predictor_estimate_and_dispatch_full_context_and_empty_setter',predictor_preflight)

def permission():
    s,e,b,r,d=h['execute']()
    claim='The issuer has a positive_runway_max_months threshold of 6.'
    bad=replace(h['STATE'],supporting_evidence=(ResearchEvidenceRef('signal',claim,signal_ref=s.ref,evidence_group='supporting',evidence_index=0),))
    try:
        _validate_research_state_refs(bad,phase='reflect',previous_state=h['STATE'],batch=b,selections=(h['intent'](s.ref),),need_dispositions=[],must_finalize=True,evaluation_context={'prediction_time':h['ASOF'].isoformat()})
    except Exception as exc:
        require(type(exc).__name__ in ('StructuredValidationError','ValidationError'))
        return {'rejected_type':type(exc).__name__,'reason':str(exc)}
    raise AssertionError('Definition threshold became issuer claim')
check('definition_threshold_not_issuer_evidence',permission)
report={'scope':'Additional synthetic offline boundaries; no labels/models/network, no new research/forecast expectation.','checks':checks,'passed':sum(c['pass'] for c in checks),'total':len(checks)}
(p/'extended-counterexample-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
