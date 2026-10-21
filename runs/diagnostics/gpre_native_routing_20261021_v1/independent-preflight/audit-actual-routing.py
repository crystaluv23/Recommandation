"""Read actual routing artifacts and original contracts only; no native execution."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/gpre_native_routing_20261021_v1';S=D/'stage';O=D/'independent-preflight';P=R/'runs/diagnostics/gpre_native_initial_20261021_v1/stage'
def read(p):return json.loads(p.read_text())
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return {'path':str(p),'sha256':h(p),'bytes':p.stat().st_size}
def hv(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
manifest=read(S/'manifest.json')
assert manifest['manifest_hash']=='5fa5965db3a256df1fc267c1eee79de52178e2136dc5d7015b7f2cd55e6aadbf'
assert hv({k:v for k,v in manifest.items() if k!='manifest_hash'})==manifest['manifest_hash']
for row in manifest['source_files']+manifest['code_files']+[manifest['expectations']]:assert h(Path(row['path']))==row['sha256'],row['path']
assert h(O/'pre-answer-routing-oracle.json')=='9ba88dc139e18e0e50142ea68f17cfd73e76de56ae19dcf1f6d4c51facd930df'
assert h(O/'pre-answer-budget-amendment.json')=='f34cc8b2da4a3f8cecb6ed3851b75312b3004573b25097c5329b8d5c41e0f086'
assert h(O/'pre-answer-native-review.json')=='9115654a1ef1b0bd238d4d1c95dc03962445a8c36dac06a0c183cad02231004d'
preserve=read(D/'root/before-preservation.json');assert len(preserve['files'])==32
for row in preserve['files']:assert h(R/row['path'])==row['sha256']
r0='6dd836684a001330e31e78797bfbb439f2d751fc1aa79a6364224836029aabf8';r1='3b4e9ca097b8a894319b9d665263d15d20ece751898522559b91e78c34e801be'
rawp=S/'exchange/outbox'/f'{r0}.txt';raw=read(rawp);rh=read(D/'root/raw-handoff-01.json');neutral=Path(rh['neutral_outbox'])
assert rawp.read_bytes()==neutral.read_bytes() and h(rawp)==rh['raw_sha256']=='a388947bb9fbcabee75ee4445497a15545bf44649fc8fa4ce26e7554c794be91'
assert rawp.stat().st_size==2291
receiptpath=S/'exchange/receipts'/f'{r0}.json';receipt=read(receiptpath);cachepath=S/'cache/responses'/f'{r0}.json';cache=read(cachepath)
assert receipt['agent_id']==rh['agent_id']==cache['usage']['agent_id']=='/root/exact_routing_88'
assert receipt['raw_output_sha256']==h(rawp)==cache['usage']['raw_output_sha256'] and cache['json_output']==raw and cache['raw_output']==rawp.read_text()
assert receipt['inbox_sha256']==h(S/'exchange/inbox'/f'{r0}.json')=='7404e51bc9b498d408b5fb90b6085ee7acb7d5bb068d981652a7628751656ff9'
assert len(list((S/'exchange/receipts').glob('*.json')))==len(list((S/'exchange/inbox').glob('*.json')))==len(list((S/'exchange/outbox').glob('*.txt')))==1
assert len(list((S/'requests').glob('*.json')))==2
q0=read(S/'requests'/f'{r0}.json');q1=read(S/'requests'/f'{r1}.json')
for q in (q0,q1):assert hv(q['request'])==q['request_hash']
u0=json.loads(q0['request']['messages'][1]['content']);u1=json.loads(q1['request']['messages'][1]['content']);feedback=u1['validation_feedback']
assert q1['request']['stage']=='signal_retrieval_cards_correction'
assert feedback['invalid_output']==raw and feedback['obligation_count']==1
ob=feedback['obligations'][0];assert ob['issue_code']=='routing_answer_ownership_invalid' and ob['item_id']=='order_confirmation_disclosed:v3'
assert ob['remove_terms_from_selection_reason']==['ultra','high','protein']
assert "shared phrase 'ultra high protein'" in ob['instruction']
assert not (S/'exchange/inbox'/f'{r1}.json').exists() and not (S/'exchange/receipts'/f'{r1}.json').exists() and not (S/'cache/responses'/f'{r1}.json').exists()
reservations=[]
for q in (q0,q1):
 req=q['request'];reservations.append(len(json.dumps(req['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+req['max_output_tokens'])
assert reservations==[49144,54598]
ctx=read(S/'native-select-context.json');assert ctx['native_request_token_budget']==68139 and ctx['native_predictor_reservation']==61973
assert 68139-49144==18995<54598
accepted=read(S/'accepted-selection.json');completion=read(S/'completion.json');boundary=read(S/'routing-boundary.json');rr=read(S/'request-reservations.json')
assert h(S/'accepted-selection.json')=='6dc28a13a4811968dbfcf05954abd8c574a773a331586a865322e9c126ef9ab3'
assert accepted['new_selection_usage']=={'cost':0.0,'llm_calls':1,'tokens':49144}
assert accepted['native_combined_case_usage']=={'cost':0.0,'llm_calls':2,'tokens':111032}
assert rr['combined_case_reservation']==completion['combined_case_reservation']==61888+49144+54598==165630
assert accepted['request_hashes']==[r0,r1]
rows=raw['selections'];out=accepted['selections'];assert len(rows)==len(out)==3
assert rows[0]==out[0]
assert {k:v for k,v in rows[2].items() if v is not None}==out[2]
assert out[1]['signal_ref']==rows[1]['signal_ref']=='order_confirmation_disclosed:v3' and out[1]['target_need_indices']==rows[1]['target_need_indices']==[1]
assert out[1]['reason_code']=='assess_applicability' and out[1]['expected_role']=='coverage' and out[1].get('answer_scope') is None and out[1].get('residual_need') is None
assert out[1]['context_tags']==rows[1]['context_tags']
assert out[0]['signal_ref']=='financing_listing_action:v5' and out[0]['target_need_indices']==[3] and out[0]['answer_scope']=='partial'
assert out[2]['signal_ref']=='liquidity_runway_months:v3' and out[2]['reason_code']=='combine_evidence' and out[2]['target_need_indices']==[3]
assert [r['signal_ref'] for r in out]==[r['signal_ref'] for r in rows]
parent=read(P/'samples/h01/initial_state.json');assert accepted['original_needs_retained']==ctx['information_needs']==parent['state']['next_information_needs'] and accepted['original_need_count']==5
assert read(S/'inputs.json')['accepted_initial_step']==parent
assert boundary['actual_first_batch_refs']==['financing_listing_action:v5'] and boundary['actual_first_batch_intents']==[out[0]]
assert boundary['executor_entry_attempts']==1 and boundary['prepare_inputs']==boundary['Signal_calculations']==0
assert boundary['company_id']=='cik_0001309402' and boundary['as_of']=='2025-05-30T00:00:00+00:00' and boundary['prior_fingerprints']=={}
assert accepted['post_select_core_caps']=={'max_signals_per_round':4,'max_llm_signals_per_round':2,'remaining_signal_calls':1}
assert completion['accepted_selection']['sha256']==h(S/'accepted-selection.json') and completion['boundary']['sha256']==h(S/'routing-boundary.json')
assert completion['status']=='accepted_routing_intents_require_independent_review' and all(completion[k]==0 for k in ('Signal_execution','Reflect','Predictor','labels','source_queries','model_API'))
assert not (S/'failure.json').exists()
changes=[{'field':k,'raw':rows[1].get(k),'accepted':out[1].get(k)} for k in sorted(set(rows[1])|set(out[1])) if rows[1].get(k)!=out[1].get(k)]
reason=rows[1]['selection_reason'];residual=rows[1]['residual_need'];need=ctx['information_needs'][1]
assert 'Ultra-High Protein' in reason and 'Ultra-High Protein' in residual and 'Ultra-High Protein' in need
card=next(c for c in u0['available_signal_cards'] if c['signal_ref']=='order_confirmation_disclosed:v3')
assert '$1M' in card['description'] and '1000' in card['description']
semantic={
 'raw_financing_partial_need3':{'verdict':'SUPPORTED_INTENDED_PARTIAL','reason':'Card directly covers debt/financing/listingactions affecting runway/dilution; target need3 contains exact debt maturities phrase. Reason only takes maturity/issuanceterms/dilution/fundingfacet. Residual retains cash/burn/capex/covenant/remainingmilestonefunding. It explicitly requires actualexecutionevidence, not a claim terms exist or are adequate.'},
 'raw_order_partial_need1':{'verdict':'SUPPORTED_INTENDED_PARTIAL_FALSELY_REJECTED','reason':'Card directly covers qualifying binding customerorder/offtake in180daywindow; raw reason names object Ultra-High Protein then relevant counterparty/program/delivery/materiality. Residual retains sameobject salesvolume/premium/cost/qualification/milestones and still-effective commitments outside180daywindow. Shared objectname does not claim these facets answered. This matches the preansweroracle potentialpartial and the actualprompt exception shared research topic may appear.'},
 'raw_liquidity_context_need3':{'verdict':'SUPPORTED_CONTEXT_ONLY','reason':'Latestduration cashburn/runway measurement can supplement fundingassessment, but explicitly not unrestrictedfunding or futureaffordability. combine_evidence has nullanswer_scope/residual and cannot answer/deleteneed.'},
 'validator_obligation':{'verdict':'FALSE_POSITIVE_SHARED_OBJECT_NOT_RESIDUAL_ONLY_FACET','exact_flagged_phrase':'ultra high protein','remove_terms':ob['remove_terms_from_selection_reason'],'reason':'The obligation flags only the shared productnoun. The firsttargetclause contains product+salesvolume, but product identity qualifies laterparallel facets andofftake, not an exclusiveunanswered measurement. No error points to selectionreason claiming volumes/premiums/cost/qualification or prewindow commitmentcoverage. Native conservative stringcheck failed its own allowed-shared-topic contract on this actualrow.'},
 'fallback':{'verdict':'NATIVE_CONSERVATIVE_SALVAGE_WITH_PORTFOLIO_OWNERSHIP_LOSS','reason':'Existing authorized fallback downgrades row1 from answer_need/partial to context, preservingSignalref/target/tags and the originalneed in suppliedstate. The mechanism is authorized but here triggered by falseownershipdiagnosis; it loses a semanticallysupported partialselection, so not faithfulrawportfolio success.'},
 'core_actual_first_batch':{'verdict':'SUPPORTED_FIRST_FINANCING_INTENT_ONLY','reason':'Core appliescaps/eligibility/dedup and remainingcall1, retaining firstfinance ref+exactacceptedintent. It is a legitimate intendedpartial need3 measurement. This is Executorentryonly;0prepare/calculation/results/Reflect means no issuerfact answered or needresolved.'}}
report={'status':'FAIL_NATIVE_STRICT_FIRST_PORTFOLIO_FIDELITY_WITH_VALID_SALVAGED_CORE_FIRST_ENTRY','audited_at_utc':datetime.now(timezone.utc).isoformat(),
 'fixed_denominators':{'routing_first_answer_portfolios':1,'native_first_answer_without_repair_pass':0,'independent_guard_falsepositive_found':1,'semantically_supported_core_first_entry':1,'core_first_entry_cases':1},
 'preanswer_oracle':bind(O/'pre-answer-routing-oracle.json'),'preanswer_budget_amendment':bind(O/'pre-answer-budget-amendment.json'),'preanswer_native_review':bind(O/'pre-answer-native-review.json'),
 'raw':bind(rawp),'neutral_raw':bind(neutral),'receipt':bind(receiptpath),'cache':bind(cachepath),'accepted_selection':bind(S/'accepted-selection.json'),'native_boundary':bind(S/'routing-boundary.json'),'completion':bind(S/'completion.json'),
 'initial_request':bind(S/'requests'/f'{r0}.json'),'blocked_correction_request':bind(S/'requests'/f'{r1}.json'),'feedback_obligation':ob,
 'raw_to_accepted_changes':{'row0_financing':'exact','row1_order':changes,'row2_liquidity':'Exact substantivefields; nativeSignalSelectionDecision.to_dict omits explicitnullanswer_scope/residual keys, no semanticchange.'},
 'semantic_reviews':semantic,
 'budget_accounting':{'prior_H_init_calls':1,'prior_H_init_logical':61888,'new_actor_calls':1,'new_actor_logical':49144,'actual_native_combined_calls':2,'actual_native_combined_logical':111032,
  'journals_prepared':2,'second_prepared_correction_reservation':54598,'native_correction_remaining':18995,'second_request_blocked_before_exchange_receive':True,'correction_inboxes':0,'correction_answers':0,
  'completion_observer_prepared_total':165630,'prepared_total_is_not_consumed_usage':True,'case_cap':256000,'native_finalization_reserve':64000,'native_Predictor_estimate_reserve':61973,
  'host_cost_and_tokens':'unknown; externalAPI0 accounting is not measuredhostcost'},
 'need_state_preservation':{'all5_original_needstrings_order_occurrences_exact':True,'no_actualneedresolution_orstateupdate':True,'orderownership_lost_but_need_notdeleted':True},
 'frozen_current_equal':{'source':1844,'code':105,'original_preservation_files':32},
 'effects':{'executor_entry_attempt':1,'prepare_inputs':0,'Signal_calculation':0,'Reflect':0,'Predictor_model':0,'GET':0,'LabelStore':0,'reviewer_native':0,'reviewer_Store':0},
 'stage_files_current':[bind(p) for p in sorted(S.rglob('*')) if p.is_file()],
 'scope_limits':['Native acceptedcompletion is salvage, not strictfirstanswerpass or fullportfoliofidelity.','No independentclaim that any financingfact exists, selectedSignalmeasurement works, chosenneed isanswered or downstreamReflectowns successfulresults.','Only first finance row reached realcoreentry; order/liquidity are not executed or adoptedfirstbatch even though retained inacceptedportfolio.','No actualrestore/resume/reopennative constructor byreviewer; only JSON reread. Original9financialdenominator andunknowns unchanged.','Source/rootfiles preserved; no productcode/oldstage/oracle changes. Proposed guardrepair must be separatefrozenrevision; no hotfix or rerunthisterminalstage.']}
p=O/'actual-routing-review.json';assert not p.exists();p.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n');print(json.dumps({'status':report['status'],'review':bind(p),'native_strictfirstpass':0,'actors':1,'correction_answers':0,'core_first_financing_intent':1,'source_and_code':1949,'preservation':32},indent=2))
