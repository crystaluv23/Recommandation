"""Independent synthetic native-parser/controller controls; no Store/network/model."""
from pathlib import Path
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from copy import deepcopy
from unittest.mock import patch
import hashlib,json,sys,types
from stock_opportunity_agent.models import StructuredValidationError
from stock_opportunity_agent.research.evolution_core import ResearchState,ResearchEvidenceRef,default_information_plan
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.repair import is_mechanical_issue
from stock_opportunity_agent.research import evolution_research_validation as v
from stock_opportunity_agent.signal_library import SignalBatchResult,SignalResult,SignalValue,SignalCoverage,SignalEvidence,NumericMeasurement
from tests.evolution_runtime_test_support import ScriptedRoleCaller
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/unavailable_topic_grounding_20261021_v1';NOW=datetime(2025,9,30,tzinfo=timezone.utc);CONTEXT={'prediction_time':NOW.isoformat()}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
bind=lambda p:{'path':str(Path(p).resolve()),'sha256':sha(p)}
expected={'src/stock_opportunity_agent/research/evolution_research_validation.py':'8192e404cc8aab8deb20f52ccc9bf950e131e808e339e9f4259e92267fff9ad6','spec/src/stock_opportunity_agent/research/evolution_research_validation.md':'5abfb94b31814c200e05e1f6aa850630097b160577cb28e14f067c4bd1aa5007','tests/test_unavailable_topic_grounding.py':'ceaefcb5c6efc21ac4e98ca80024cb45e70cd4ab52a8ff2364d3a4b0f5d96000'}
for name,h in expected.items():assert sha(R/name)==h,name
oldpath=D/'driver/original-evolution_research_validation.py';old=types.ModuleType('_independent_original_unavailable_validator');sys.modules[old.__name__]=old;exec(compile(oldpath.read_text(),str(oldpath),'exec'),old.__dict__)
P=ResearchState(hypotheses=('A new product may change expectations.',),current_beliefs=('The issuer disclosed domestic expansion.',),supporting_evidence=(ResearchEvidenceRef(kind='basic_info',projection_id='prior-expansion',exact_text='The issuer disclosed domestic expansion.',claim='The issuer disclosed domestic expansion.'),),next_information_needs=('What next product milestone was disclosed by prediction time?',))
U=SignalResult(signal_id='customer_concentration',version=1,value=SignalValue.UNAVAILABLE,confidence=0,interpretation='Coverage unavailable.',coverage=SignalCoverage.UNAVAILABLE)
F=SignalResult(signal_id='financing_disclosure',version=1,value=SignalValue.NEUTRAL,confidence=.5,interpretation='Historical financing context.')
B=SignalBatchResult((U,F),signal_calls=2)
CLAIM='Customer concentration was weak during the reported period.'
def state(text,refs=(),prior=P,field='current_beliefs'):
 return replace(prior,**{field:getattr(prior,field)+(text,)},supporting_evidence=prior.supporting_evidence+tuple(refs))
def source(raw=CLAIM,claim=CLAIM,timestamp=NOW-timedelta(days=1),numeric=False):
 result=SignalResult(signal_id='customer_concentration',version=2,value=SignalValue.NEUTRAL,confidence=.5,interpretation=claim,supporting_evidence=(SignalEvidence('synthetic-independent-source',raw,timestamp),),measurement=NumericMeasurement(.25,'ratio','part / total','2025-06-30') if numeric else None)
 return ResearchEvidenceRef(kind='signal',signal_ref=result.ref,evidence_group='supporting',evidence_index=0,claim=claim),SignalBatchResult(B.results+(result,),signal_calls=3)
def outcome(s,b=B,prior=P,module=v):
 try:
  result=module._validate_research_state_refs(s,phase='reflect',previous_state=prior,batch=b,need_dispositions=[],evaluation_context=CONTEXT)
  return {'accepted':True,'state':result.to_dict()}
 except StructuredValidationError as error:
  return {'accepted':False,'issue_codes':[i.code for i in error.issues],'unavailable_obligations':[{'paths':list(i.paths),'allowed_repairs':list(i.allowed_repairs),'mechanical':is_mechanical_issue(i)} for i in error.issues if i.code=='unavailable_signal_treated_as_finding']}
def controller(s,b=B,prior=P):
 output=s.to_dict();output['need_dispositions']=[];original=deepcopy(output);caller=ScriptedRoleCaller([output]);c=LLMResearchController(caller);c.set_evaluation_context(NOW);step=c.reflect(default_information_plan(),prior,b)
 assert output==original and len(caller.calls)==1
 return step.value.to_dict()
rows=[]
# Old full parser accepted qualitative unsupported topic; candidate rejects then
# existing atomic fallback removes exactly that newly authored member in one call.
weak=state('Customer concentration is weak.');before=outcome(weak,module=old);after=outcome(weak);assert before['accepted'] and not after['accepted'];assert controller(weak)==P.to_dict()
rows.append({'control':'original_weak_full_parser','old':before,'current':after,'native_single_call_exact_prior':True})
# Independent literal was falsely attributed by old validator despite exact source.
ref,b=source(claim='Customer concentration was not strong during the reported period.',raw='Customer concentration was not strong during the reported period.');s=state(ref.claim,(ref,));before=outcome(s,b,module=old);after=outcome(s,b);assert not before['accepted'] and after['accepted'];assert controller(s,b)==s.to_dict()
rows.append({'control':'original_independent_exact_literal','old':before,'current':after,'native_single_call_preserved':True})
for text in ('Customer concentration is strong.','Customer concentration is zero.','Customer concentration is unknown, not evidence of economic absence. Customer concentration is weak.','Customer concentration is weak. Operating cash flow is unknown, not absent.','Historical financing remains context; customer concentration is weak despite no economic absence conclusion.'):
 s=state(text);out=outcome(s);assert not out['accepted'] and 'unavailable_signal_treated_as_finding' in out['issue_codes'];assert controller(s)==P.to_dict();rows.append({'control':'unsupported_atomic_member','text':text,'result':out,'native_single_call_exact_prior':True})
# Numeric quantity gate remains; no claim that the old full parser accepted0%.
out=outcome(state('Customer concentration is 0%.'));assert not out['accepted'] and 'assertion_without_support' in out['issue_codes'];rows.append({'control':'zero_percent_complete_quantity_gate','result':out})
# Topic-matched resolution is equally unsupported; correct placement survives.
s=state('Customer concentration remains unknown.',field='resolved_questions');out=outcome(s);assert not out['accepted'];assert controller(s)==P.to_dict();rows.append({'control':'unknown_is_not_resolution','result':out})
s=replace(P,open_questions=('Why is customer concentration still unknown?',),next_information_needs=P.next_information_needs+('What customer concentration was disclosed by prediction time?',));assert outcome(s)['accepted'];assert controller(s)==s.to_dict();rows.append({'control':'correct_question_and_need_placement','accepted':True})
# Cross-topic negation cannot exempt either actual topic.
extra=replace(U,signal_id='operating_cash_flow');b=SignalBatchResult(B.results+(extra,),signal_calls=3);s=state('Customer concentration is weak. Operating cash flow is unknown, not absent.');errors=v._unavailable_signal_state_errors(P,s,b,evaluation_context=CONTEXT);assert {e['signal_ref'] for e in errors}=={'customer_concentration:v1','operating_cash_flow:v1'};rows.append({'control':'cross_topic_no_global_disclaimer_exemption','errors':errors})
# Prior exact provenance is trusted only as an exact key+claim pair.
for prior_ref in (ResearchEvidenceRef(kind='basic_info',projection_id='old-concentration',exact_text=CLAIM,claim=CLAIM),ResearchEvidenceRef(kind='signal',signal_ref='old_report:v4',evidence_group='counter',evidence_index=0,claim=CLAIM)):
 prior=replace(P,supporting_evidence=P.supporting_evidence+(prior_ref,));s=state(CLAIM,prior=prior);assert outcome(s,prior=prior)['accepted'];assert controller(s,prior=prior)==s.to_dict();rows.append({'control':'prior_exact_'+prior_ref.kind,'accepted':True})
 altered=replace(prior_ref,claim='Customer concentration was strong during the reported period.');s=replace(state(altered.claim,prior=prior),supporting_evidence=P.supporting_evidence+(altered,));out=outcome(s,prior=prior);assert not out['accepted'] and 'unavailable_signal_treated_as_finding' in out['issue_codes'];rows.append({'control':'prior_changed_claim_'+prior_ref.kind,'result':out})
# Raw literal and complete normalized HTML literal are independent valid sources.
for raw,claim in ((CLAIM,CLAIM),('Customer <b>concentration</b> was weak during the reported period.',CLAIM)):
 ref,b=source(raw,claim);s=state(claim,(ref,));assert outcome(s,b)['accepted'];assert controller(s,b)==s.to_dict();rows.append({'control':'exact_current_raw_or_complete_readable','raw':raw,'accepted':True})
ref,b=source();variants=[('ref_membership_only',replace(ref,signal_ref='not_present:v9'),b),('wrong_group',replace(ref,evidence_group='counter'),b),('wrong_index',replace(ref,evidence_index=10),b),('substring',replace(ref,claim=CLAIM[:-1]),b),('paraphrase',replace(ref,claim='Customer concentration appears weak during this period.'),b)]
future_ref,future_batch=source(timestamp=NOW+timedelta(microseconds=1));variants.append(('future_source',future_ref,future_batch))
for name,ref,b in variants:
 out=outcome(state(ref.claim,(ref,)),b);assert not out['accepted'] and 'unavailable_signal_treated_as_finding' in out['issue_codes'];rows.append({'control':name,'result':out})
# A complete source is allowed, but a truncated display prefix/omission marker
# is not a new whole-source literal, even when topic words remain in the prefix.
ref,b=source(raw=CLAIM+' Additional independent source narrative.'*100)
for limit in (30,1000):
 with patch.object(v,'MAX_REFLECT_SIGNAL_BATCH_EVIDENCE_CHARS',limit):
  compact=v._signal_batch_model_view(b)[-1]['evidence']['supporting'][0]['model_evidence_text'];assert compact!=b.results[-1].supporting_evidence[0].exact_span
  out=outcome(state(compact,(replace(ref,claim=compact),)),b);assert not out['accepted'] and 'unavailable_signal_treated_as_finding' in out['issue_codes'];rows.append({'control':'bounded_prefix_or_omission_is_not_exact','limit':limit,'visible':compact,'result':out})
# Existing canonical numeric adoption string remains available, not free prose.
claim='customer_concentration=0.25';ref,b=source(raw='{"part":25,"total":100}',claim=claim,numeric=True);assert outcome(state(claim,(ref,)),b)['accepted'];rows.append({'control':'canonical_numeric_exact_adoption','accepted':True})
wrong=replace(ref,claim='Customer concentration is 0.25 and weak.');out=outcome(state(wrong.claim,(wrong,)),b);assert not out['accepted'] and 'unavailable_signal_treated_as_finding' in out['issue_codes'];rows.append({'control':'canonical_numeric_free_paraphrase_rejected','result':out})
# Literal whole-word contract: no stemming or substring widening.
text='Customer concentrationary evidence is unavailable.';assert not v._unavailable_signal_state_errors(P,state(text),B,evaluation_context=CONTEXT);rows.append({'control':'whole_word_no_substring_topic','accepted_by_topic_guard':True})
report={'verdict':'PASS_bounded_guard_family','controls':len(rows),'rows':rows,'source_before':{name:bind(R/name) for name in expected},'old_source':bind(oldpath),'probe':bind(__file__),'limits':['All fixtures synthetic; no fresh model behavior or actual stage/source admission tested.','Atomic indexed member remains repair unit: mixed invalid text may be wholly removed under existing authority.','Previous p01 clause-preservation defect claim is withdrawn: existing coverage placement and mechanical authorization explain deletion; true fixed bugs are weak false acceptance and exact-source false attribution.','Whole-word Signal-ID token matching is literal, without synonym/stemming completeness or general semantic proof.','No whole F7/MVP or independent benefit closure; original stage evidence remains untouched.']}
for name,h in expected.items():assert sha(R/name)==h
path=D/'independent-review.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('PASS',len(rows),'controls; review',sha(path))
