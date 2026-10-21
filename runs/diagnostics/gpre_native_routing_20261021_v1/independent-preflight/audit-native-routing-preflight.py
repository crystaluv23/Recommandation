"""Read final native pending artifacts only; no product/native helper imports."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/gpre_native_routing_20261021_v1';O=D/'independent-preflight';T=D/'driver/temp-native-preflight-v3';S=T/'stage';P=R/'runs/diagnostics/gpre_native_initial_20261021_v1/stage'
def read(p):return json.loads(p.read_text())
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def b(p):return {'path':str(p),'sha256':h(p),'bytes':p.stat().st_size}
def c(v):return json.dumps(v,sort_keys=True,separators=(',',':'))
def hashv(v):return hashlib.sha256(c(v).encode()).hexdigest()
def save(n,v):
 p=O/n;assert not p.exists();p.write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n');return b(p)
oraclepath=O/'pre-answer-routing-oracle.json';assert h(oraclepath)=='9ba88dc139e18e0e50142ea68f17cfd73e76de56ae19dcf1f6d4c51facd930df'
capath=O/'exact-version-capability-basis.json';assert h(capath)=='bc2e923420af3c9c50821a95c1ea73ee5bc02d8d365418c43b82b4e69ba085e5'
oracle=read(oraclepath);basis=read(capath);pre=read(T/'result.json');man=read(S/'manifest.json');inputs=read(S/'inputs.json');contract=read(S/'contract.json');ctx=read(S/'native-select-context.json');pred=read(S/'native-predictor-reservation.json')
assert h(R/'scripts/run_gpre_native_routing_stage.py')=='6a5866d010949cd135c0ba6ab4f702ac9d578fd2c00bb15d8d1e6c1952237bef'
assert h(R/'spec/scripts/run_gpre_native_routing_stage.md')=='c8c8c8557eb504ee8ff8faf0bf5c65a29f1559e0f17c17b9b5cf8948c01e5c4d'
assert pre['status']=='native_routing_pending_connection_passed' and not (D/'stage').exists()
assert len(man['source_files'])==1844 and len(man['code_files'])==105
for row in man['source_files']+man['code_files']+[man['expectations']]:assert h(Path(row['path']))==row['sha256'],row['path']
assert hashv({k:v for k,v in man.items() if k!='manifest_hash'})==man['manifest_hash']
assert hashv(inputs)==man['inputs_hash'] and hashv(contract)==man['contract_hash']
assert not any(x['path']==str(P/'exchange/.dispatch.lock') for x in man['source_files'])
for row in basis['source_definition_bindings']:assert h(Path(row['path']))==row['sha256']
parent_files=[p for p in P.rglob('*') if p.is_file()]
sourcepaths={x['path']:x for x in man['source_files']}
for p in parent_files:
 if p==P/'exchange/.dispatch.lock':continue
 assert str(p) in sourcepaths and h(p)==sourcepaths[str(p)]['sha256'],str(p)
assert (S/'recomputed-bootstrap.json').read_bytes()==(P/'samples/h01/bootstrap.json').read_bytes()
accepted=read(P/'samples/h01/initial_state.json');assert inputs['accepted_initial_step']==accepted
assert ctx['research_state']==accepted['state'] and ctx['information_needs']==accepted['state']['next_information_needs']
assert [r['need'] for r in oracle['need_matching_boundaries']]==ctx['information_needs']
assert ctx['prior_fingerprints']==ctx['prior_results']=={} and ctx['prior_context_tags']==[]
assert ctx['eligible_signal_refs']==basis['group']['refs']
assert ctx['native_request_token_budget']==68139
assert ctx['native_predictor_reservation']==61973
assert pred['estimated_logical_units']==61973
assert contract['runtime_limits']['max_llm_calls']==5 and contract['runtime_limits']['finalization_token_reserve']==64000
assert contract['prior_case_usage']==accepted['native_budget_usage']=={'cost':0.0,'llm_calls':1,'tokens':61888}
assert 256000-61888-64000-61973==68139
qpaths=list((S/'requests').glob('*.json'));ips=list((S/'exchange/inbox').glob('*.json'));assert len(qpaths)==len(ips)==1
q=read(qpaths[0]);request=q['request'];ib=read(ips[0]);assert hashv(request)==q['request_hash']==ib['request_hash']
assert request['stage']=='signal_retrieval_cards' and request['max_output_tokens']==2000
assert request['messages']==ib['messages']
user=json.loads(request['messages'][1]['content']);assert set(user)=={'available_signal_cards','evaluation_context','information_needs','learned_profile_default','performance_interpretation','previous_context_tags','previous_signal_results','research_context','selection_caps','validation_feedback'}
assert user['information_needs']==ctx['information_needs'] and user['evaluation_context']==ctx['evaluation_context']
assert user['previous_context_tags']==[] and user['previous_signal_results']=={} and user['validation_feedback'] is None
assert user['selection_caps']=={'signals':4,'llm_signals':2}
st=accepted['state'];expected_context={k:st[k] for k in ('hypotheses','current_beliefs','contradictions','resolved_questions','open_questions')};expected_context['evidence_claims']=list(dict.fromkeys(r['claim'] for r in st['supporting_evidence']))
assert user['research_context']==expected_context
cards=user['available_signal_cards'];byref={x['signal_ref']:x for x in basis['cards']}
assert len(cards)==17 and [x['signal_ref'] for x in cards]==[ref for ref in basis['group']['refs'] if ref!='order_quality:v2']
cardchecks=[]
for card in cards:
 source=byref[card['signal_ref']];spec=read(Path(source['spec']['path']));scope=card['measurement_scope'];wanted=source['scope']
 assert card['description']==wanted['version_owned_description'] and card['execution_type']==wanted['execution_type']
 assert scope['signal_ref']==card['signal_ref'] and scope['source_types']==wanted['source_types']
 expected_raw={k:v for k,v in wanted['raw_retrieval'].items() if k!='source_types'}
 assert scope['raw_retrieval']==expected_raw,(card['signal_ref'],scope['raw_retrieval'],expected_raw)
 if card['execution_type']=='deterministic':
  e=scope['execution'];assert e['callable_status']=='registered' and e['function']==wanted['callable_name']
  assert ' '.join(e['contract'].split())==' '.join(wanted['callable_contract_read_from_AST'].split())
  assert e['configured_parameters']==wanted['configured_callable_parameters']
 else:assert scope['execution']=={'type':'llm'}
 for name in ('routing_need_phrases','routing_answer_need_phrases','routing_required_research_phrases','routing_excluded_context_tags'):
  if spec['parameters'].get(name):assert card[name]==spec['parameters'][name]
 assert 'learned_profile' not in card and 'research_status' not in card
 assert card['performance']['independent_cases']==card['performance']['evaluated_cases']==0
 cardchecks.append({'signal_ref':card['signal_ref'],'measurement_scope_exact':True,'callable_status':scope['execution'].get('callable_status')})
def norm(text):return ' '+re.sub(r'[^a-z0-9]+',' ',text.casefold()).strip()+' '
research=[norm(x) for x in ctx['information_needs']]+[norm(x) for values in expected_context.values() for x in values]
for row in basis['cards']:
 spec=read(Path(row['spec']['path']));phrases=spec['parameters'].get('routing_required_research_phrases',[])
 visible=not phrases or any(norm(phrase) in text for phrase in phrases for text in research)
 assert visible==(row['signal_ref'] in {c['signal_ref'] for c in cards}),row['signal_ref']
text=json.dumps(request['messages'],ensure_ascii=False)
for marker in ('GPRE','GREEN PLAINS','1309402','0001309402-25-000089','000130940225000089','gpre-20250331','sec.gov/Archives/edgar/data/1309402','gpreinc','pre-answer-routing-oracle','need_matching_boundaries','9ba88dc139e18e0e50142ea68f17cfd73e76de56ae19dcf1f6d4c51facd930df','capability_basis'):
 assert marker.casefold() not in text.casefold(),marker
assert not re.findall(r'\[ANON_ID_\d+\]',text)
reservation=len(json.dumps(request['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+request['max_output_tokens'];assert reservation==49144<=68139<131072
res=read(S/'request-reservations.json');assert res['prior_case_usage']==61888 and res['combined_case_reservation']==111032
assert len(res['requests'])==1 and res['requests'][0]=={'request_hash':q['request_hash'],'reservation':49144}
assert not list((S/'exchange/receipts').glob('*.json')) and not list((S/'exchange/outbox').glob('*'))
assert not (S/'completion.json').exists() and not (S/'failure.json').exists() and not (S/'accepted-selection.json').exists()
amend={'schema':'gpre-routing-pre-answer-budget-and-boundary-amendment-v1','frozen_at_utc':datetime.now(timezone.utc).isoformat(),'source_oracle_unchanged':b(oraclepath),
 'timing':'After only actualnativepending, before any routinganswer. No need/capabilitygold or modelvisiblepayload content changed.',
 'corrected_budget':{'prior_usage':61888,'case_cap':256000,'case_remaining':194112,'native_finalization_reserve':64000,'native_Predictor_estimator_reserve':61973,'native_selection_chain_budget':68139,'actual_first_request':49144,'combined_case_reserved':111032,'remaining_native_correction_chain_budget':18995,'new_author_max':2,'native_corrections_max':1,'correction_not_guaranteed_to_fit':True},
 'previous_130112_error':'Originaloracle/commonacceptance130112 omitted actualnativePredictor localestimator by usingSimpleNamespace lacking estimator. It remains originalbytes as a wrongfullnativebudget premise, not final authority. Native LLMBlindPredictor delegateestimate adds61973; no Predictor model request occurs.',
 'native_estimator_evidence':b(S/'native-predictor-reservation.json'),'native_context':b(S/'native-select-context.json'),
 'boundary_scope_addendum':'Nonempty native selectorstep now returns unchanged tocore for real consume/eligible/duplicate/caps/remaining_call1 truncation. Executor.execute_batch subclass records realadoptedfirstrefs atentry then raises before super/prepare/calculation. Emptyselection stops atselectorboundary beforefinalization. Currentzeroanswerpreflight does not exercise either acceptedbranch.',
 'private_skill_visibility_clarification':'exact-version capabilitybasis storesLLMskills for reviewer background. Actualrouting LLMscope only type, source/query anddescription: do not fail actor for hidden skill-onlydetails absent actualcard. Actualhardroutinggates and displayedcapability govern choice.',
 'operational_lock_correction':'Exactparentexchange/.dispatch.lock is not researchauthority; finalsourcebindings exclude onlythat absolute path. No deletion/change of parentlock or otherartifacts.'}
ab=save('pre-answer-budget-amendment.json',amend)
review={'status':'PASS_FORMAL_PREPARE_READY_NO_ROUTING_ANSWER','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'source_oracle':b(oraclepath),'capability_basis':b(capath),'preanswer_budget_and_scope_amendment':ab,
 'final_script':b(R/'scripts/run_gpre_native_routing_stage.py'),'final_spec':b(R/'spec/scripts/run_gpre_native_routing_stage.md'),
 'native_preflight':b(T/'result.json'),'manifest':b(S/'manifest.json'),'inputs':b(S/'inputs.json'),'contract':b(S/'contract.json'),'native_select_context':b(S/'native-select-context.json'),'native_Predictor_reservation':b(S/'native-predictor-reservation.json'),'bootstrap':b(S/'recomputed-bootstrap.json'),'journal':b(qpaths[0]),'native_inbox':b(ips[0]),
 'frozen_current_equal':{'source':1844,'code':105},'parent_artifacts_bound_except_one_exact_operationallock':len(parent_files)-1,
 'actual_old_H_init_state_usage_metadata_plan_bootstrap_exact':True,'native_eligible_refs':18,'actual_visible_cards':cardchecks,
 'omitted_card':{'signal_ref':'order_quality:v2','reason':'None of its exactrequiredresearchphrases occurs in originalneeds/context. Hardapplicabilityfilter, not missing issuerdata or unsupported source.'},
 'visibility_limits':['Routingsees label-freeacceptedcontext claims, not BasicInfo17rawprojections or sourcecatalogbody; no six financialresults injected.','All12 deterministicfunctions are registered withexactcallablecontract/configuredparameters. FiveLLMcards visible; LLMonlyscope.type, not actualskillbody.','Previousresult/fingerprint/contexttags empty, no fabricatedprior or outcomeprofile.'],
 'budget':{'prior':61888,'Predictor_reserve':61973,'finalization_reserve':64000,'native_chain_available':68139,'new_actual_request':49144,'combined_case_reservation':111032,'remaining_native_chain':18995},
 'anonymous_actualwire':'No issuername/ticker/padded-unpaddedCIK/accession/URL/website/privateoracle. Userneeds/context andcards equal canonical directly, noopaqueidentitytoken onthis input; no exercised inverse-remapbranch claimed.',
 'scope_and_not_yet_proven':['Noactualroutinganswer, acceptedselection, nativeadoptedbatch or semanticneedcoverage yet.','Nonemptycoreadoption/entryboundary only code-reviewed, not exercised inthiszeroanswerpreflight; lateractual must distinguishacceptedintents andactualfirstbatch.','Rootmustneutralbytecopy actualinbox/raw, dispatchfreshforknone onlynativeinbox; formalroot notyetexists.','Neither sourcepresence nor routingcapability provesexecutedfacts, evidencefullness, requestedperiodpolicy, F5reading or F7consumption. Original9verdict/unknowns remain unchanged.'],
 'counts':{'newauthoredanswers':0,'routingjournals':1,'native_pending_receive_attempt':1,'H_init_model':0,'Predictor_model':0,'executorentry':0,'Signalcalculation':0,'reviewer_native':0,'reviewer_Store':0,'GET':0,'LabelStore':0},
 'earlier_diagnostics_retained':['v1 originalsource-lockmisbinding and missingPredictorestimator; v2 lockfix but stillno realestimator. Neither isfreshsemantic evidence; no reentry ofthose roots.']}
rb=save('pre-answer-native-review.json',review)
print(json.dumps({'status':'PASS','review':rb,'budget_amendment':ab,'boundfiles':1949,'nativecards':17,'request_reservation':49144,'native_budget':68139,'possible_correction_remaining':18995},indent=2))
