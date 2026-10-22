"""Read-only independent final audit of the two sealed fresh consumer samples."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path('/Users/l/Project/Recommandation');BASE=ROOT/'runs/diagnostics/mining_taxonomy_consumer_20261023_v1';STAGE=BASE/'stage'
OUT=BASE/'independent/fresh-consumer-final-review.json';assert not OUT.exists()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def file_sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
manifest=read(STAGE/'manifest.json');mh=manifest.pop('manifest_hash');assert mh==digest(manifest)
inputs=read(STAGE/'inputs.json');contract=read(STAGE/'contract.json')
assert digest(inputs)==manifest['inputs_hash'] and digest(contract)==manifest['contract_hash']
bindings=manifest['source_files']+manifest['code_files'];drift=[x for x in bindings if file_sha(x['path'])!=x['sha256']];assert not drift
reference=read(BASE/'reference/source-reference.json');pre=read(BASE/'reference/prefreeze-obligations.json')
assert inputs['namespace']['content']==reference['original_namespace_counterexample']['raw_source_content']
expected={}
for record in reference['positive_source_control']['records']:
 row=record['row'];expected[(row['start'],row['end'])]=row
sample_reports={};captured={};stage_files={}
for sample,terminalname in (('namespace','completion'),('actual','failure')):
 root=STAGE/sample;terminal=read(root/(terminalname+'.json'));th=terminal.pop('terminal_hash');assert th==digest(terminal)
 assert terminal['sample']==sample
 assert all(file_sha(x['path'])==x['sha256'] for x in terminal['sealed_files'])
 actions=[(p,read(p)) for p in sorted(root.glob('action-*.json'))]
 views=[(p,read(p)) for p in sorted(root.glob('view-*.json'))]
 requests={};physical=[]
 for p in sorted((root/'requests').glob('*.json')):
  record=read(p);req=record['request'];h=record['request_hash'];assert h==p.stem==digest(req)
  view=json.loads(next(m['content'] for m in req['messages'] if m['role']=='user'))
  wire='\n'.join(m['content'] for m in req['messages'])
  assert '0000800457' not in wire and 'cik_0000800457' not in wire
  cost=len(canonical(req['messages']))+req['max_output_tokens']
  assert cost<=contract['limits']['max_request_tokens']
  item={'request_hash':h,'path':str(p),'file_sha256':file_sha(p),'logical_reservation':cost,'last_action':view.get('last_action_result',{}).get('action'),'read_progress_fact_refs':[x['fact_ref'] for x in view.get('structured_read_progress',{}).get('items',[])],'known_fact_ref_count':len(view.get('known_fact_refs',())),'has_inbox':(root/'exchange/inbox'/p.name).exists(),'has_receipt':(root/'exchange/receipts'/p.name).exists()}
  receiptpath=root/'exchange/receipts'/p.name
  if receiptpath.exists():
   receipt=read(receiptpath);inboxpath=root/'exchange/inbox'/p.name;rawpath=root/'exchange/outbox'/(h+'.txt');cachepath=root/'cache/responses'/p.name
   inbox=read(inboxpath);raw=rawpath.read_text();body=json.loads(raw);cache=read(cachepath)
   assert receipt['request_hash']==h==inbox['request_hash']==cache['request_hash']
   assert receipt['inbox_sha256']==file_sha(inboxpath) and receipt['raw_output_sha256']==file_sha(rawpath)
   assert inbox['messages']==req['messages'] and inbox['max_output_tokens']==req['max_output_tokens']
   assert cache['raw_output']==raw and cache['json_output']==body and cache['usage']['accounting_tokens']==cost
   matches=[i for i,(ap,a) in enumerate(actions) if a==body]
   assert len(matches)==1
   index=matches[0];canonicalview=views[index][1]
   # Anonymous egress transforms local document handles, not fact/period/value identity.
   vp=canonicalview.get('structured_read_progress',{}).get('items',[]);wp=view.get('structured_read_progress',{}).get('items',[])
   assert [x['fact'] for x in vp]==[x['fact'] for x in wp]
   assert [x['fact_ref'] for x in vp]==[x['fact_ref'] for x in wp]
   physical.append({'position':index+1,'request_hash':h,'agent_id':receipt['agent_id'],'raw_output_path':str(rawpath),'raw_output_sha256':file_sha(rawpath),'action':body,'logical_reservation':cost,'simultaneous_read_fact_bindings':[{'fact_ref':x['fact_ref'],'fact':x['fact'],'content_hash':x['content_hash'],'available_at':x['available_at']} for x in wp]})
   captured[(sample,index+1)]={'wireview':view,'raw':body,'canonicalview':canonicalview,'request_hash':h}
  requests[h]=item
 physical.sort(key=lambda x:x['position'])
 assert len(physical)==len(actions)
 assert len({x['agent_id'] for x in physical})==len(physical)
 artifact=read(root/('boundary.json' if sample=='namespace' else 'failed-controller.json'))
 ledger=artifact['ledger']['entries'];invalid=[x for x in ledger if x['action'] in ('invalid_action','mechanical_repair') or x.get('terminal_disposition') in ('technical_failure',)]
 assert not invalid
 for lp in ledger:
  if lp['action']=='read_span':
   ref=lp['evidence_refs'][0]
   receipts=[v.get('last_action_result',{}) for _,v in views if v.get('last_action_result',{}).get('action')=='read_span' and v['last_action_result'].get('fact_ref')==ref]
   assert receipts
   receipt={k:v for k,v in receipts[0].items() if k!='action'}
   assert digest(receipt)==lp['output_hash']
 fetch=read(root/'controlled-fetch.json');facts=fetch['facts'];target=[f for f in facts if f['concept']==inputs[sample]['concept']];assert len(target)==2
 if sample=='actual':
  source=read(reference['positive_source_control']['source_path'])
  assert source['content_hash']==reference['positive_source_control']['content_sha256']
  for f in target:
   row=json.loads(f['exact_span']);assert row==expected[(row['start'],row['end'])]
   assert f['exact_span'] in source['content'] and f['content_hash']==source['content_hash'] and f['taxonomy']=='us-gaap' and f['unit']=='USD'
 else:
  assert {f['taxonomy'] for f in target}=={'namespace-a','namespace-b'}
  for f in target:assert f['exact_span'] in inputs[sample]['content'] and f['content_hash']==reference['original_namespace_counterexample']['raw_source_content_sha256']
  assert not [r for r in artifact['relations'] if r['kind']=='same_concept_period_pair']
 answered=sum(x['logical_reservation'] for x in physical);prepared=sum(x['logical_reservation'] for x in requests.values())
 sample_reports[sample]={'terminal_state':terminal['state'],'terminal_record_hash':th,'terminal_path':str(root/(terminalname+'.json')),'terminal_file_sha256':file_sha(root/(terminalname+'.json')),'terminal_sealed_bindings_verified':len(terminal['sealed_files']),'fresh_physical_responses':len(physical),'corrections':0,'actions':[x['action']['action'] for x in physical],'answered_logical_reservation':answered,'prepared_logical_reservation':prepared,'requests':list(requests.values()),'fresh_action_chain':physical,'ledger_actions':[x['action'] for x in ledger],'target_facts':target,'controlled_fetch_fact_count':len(facts),'controlled_fetch_excluded_documents':fetch['receipt']['excluded_document_ids'],'native_domain_terminal_executed':artifact.get('native_domain_terminal_executed',False),'terminal_error':terminal.get('error')}
 for p in root.rglob('*'):
  if p.is_file() and p.name!='.dispatch.lock':stage_files[str(p)]=file_sha(p)
# Namespace source/semantic judgment follows frozen A05; no new arithmetic recital duty.
ns=captured[('namespace',3)];assert ns['raw']['action']=='record_deferred'
assert len(ns['wireview']['structured_read_progress']['items'])==2
# Actual proof of lost source locator: opaque ref remains in inventory, mapping vanishes.
act2=captured[('actual',2)];act3=captured[('actual',3)];act4=captured[('actual',4)]
concept=inputs['actual']['concept'];prior='fact-2f898adb2d25e349';current='fact-3d4faa09011f777b'
assert act2['wireview']['last_action_result']['groups']['control']['concepts'][concept]['comparable_prior']['case-008']['fact_ref']==prior
assert prior in act3['wireview']['known_fact_refs']
assert act3['wireview']['last_action_result']['action']=='read_span'
assert [x['fact_ref'] for x in act3['wireview']['structured_read_progress']['items']]==[current]
assert act3['raw']['action']=='compare_groups'
assert act4['wireview']['last_action_result']['groups']['control']['concepts'][concept]['comparable_prior']['case-008']['fact_ref']==prior
assert act4['raw']['action']=='read_span' and act4['raw']['fact_ref']==prior
blocked=[x for x in sample_reports['actual']['requests'] if not x['has_receipt']];assert len(blocked)==1 and not blocked[0]['has_inbox']
assert sample_reports['actual']['prepared_logical_reservation']>contract['limits']['max_case_tokens']
assert sample_reports['actual']['answered_logical_reservation']<=contract['limits']['max_case_tokens']
cache=read(BASE/'cache-reconstruction.json');assert cache['verification_script']['sha256']==file_sha(cache['verification_script']['path'])
report={
 'schema_version':'mining-taxonomy-fresh-consumer-independent-final-review-v1',
 'disposition':'fixed_module_first_endpoint_acceptance_1_of_2_actual_locator_budget_failure_retained',
 'scope':'Read-only sealed formal stage requests, original raw responses, receipts/cache/actions/tool-return views/ledger, source bindings and frozen reference. No runner/advance/model/API execution, no product/source/stage/reference mutation, no business LabelStore/check/LockedTest reads. All writes are new independent/fresh-consumer-* files.',
 'frozen_integrity':{'manifest_hash':mh,'contract_sha256':file_sha(STAGE/'contract.json'),'manifest_file_sha256':file_sha(STAGE/'manifest.json'),'inputs_file_sha256':file_sha(STAGE/'inputs.json'),'source_bindings_verified':len(manifest['source_files']),'code_bindings_verified':len(manifest['code_files']),'drift':drift,'source_reference_sha256':file_sha(BASE/'reference/source-reference.json'),'prefreeze_obligations_sha256':file_sha(BASE/'reference/prefreeze-obligations.json'),'reviewer_executed_production_calls':0},
 'fixed_denominator':{'samples':2,'first_endpoint_semantic_accepted':1,'full_module_semantic_result':'1/2','namespace':'1/1 first module endpoint,3fresh responses0corrections','actual':'0/1: aggregate-budget terminal before final author endpoint,4fresh responses0corrections','physical_fresh_responses':7,'prepared_native_requests':8,'blocked_unanswered_requests':1,'note':'Intermediate source-field correctness does not turn actual into a completed semantic endpoint. No correction or appended response is used to change this denominator.'},
 'samples':sample_reports,
 'namespace_semantic_review':{'accepted':True,'exact_source':'Preserved explicitly synthetic parent source namespace-a MetricUSD120 at2024-06-30 and namespace-b MetricUSD100 at2023-06-30. Both complete actual fact-read receipts, parent context and identity were simultaneously in the final wire, and all fields match the frozen reference.','fresh_consumption':'The second fresh response retains prior namespace-b from actual receipt; the first module endpoint explicitly binds both refs/taxonomies/units/values/end dates and declines automatic same-concept comparable measurement. No fabricated mapping, positive/control contrast, source absence or domain research completion.','generic_arithmetic_question':{'literal_text':'A year-over-year difference or ratio is therefore unestablished; no statistic is warranted from these operands.','assessment':'Read in its surrounding measurement-equivalence/source-scope rationale, this declines a warranted YoY statistic. It does not explicitly claim generic compute_statistic is illegal, arithmetic120/100 impossible, or request a tool ban. Frozen A05 does not require computing1.2 or reciting generic arithmetic permissions. Do not add that duty retrospectively.','scope_limit':'No compute was performed; generic arithmetic branch consumption is untested. The broad wording is not accepted as a general rule forbidding explicit arithmetic. If a later consumer treats it as such, that later semantic promotion requires separate review.'},'source_unknowns_preserved':'Namespace mapping/entity measurement equivalence and additional duration scope are not established by this synthetic source. Same case and USD alone do not resolve namespace identity. The sample is not a dev8 natural discovery.','stop':'Boundary saved before executing record_deferred; raw endpoint expressly denies evidence_unavailable/no-pattern interpretation.'},
 'actual_partial_vs_module':{'module_accepted':False,'source_field_consumption_supported':'Fresh response3 correctly states us-gaap operating cash flow USD9506313 for2011-01-01 through2011-06-30, pre-cutoff availability and single-control historical scope. Response4 selects the actual prior source fact for a direct read.','not_yet_consumed':'The2010H1 prior full receipt is produced after response4. It is in local view005 and blocked fifth request, but no fifth inbox/author exists. No fresh final consumer has jointly interpreted both complete operands; this remains unclosed.','available_evidence':'Actual read tools successfully produced both original0671 complete rows with matching content hash, namespace/USD/value/period bindings. Tool execution and local field presence are not final author semantic consumption.','stop_reason':'LocalRoleBudgetExhausted at the existing aggregate cap, not missing issuer facts, no-pattern, exhaustion of heavy actions or research completion.','budget':{'answered_first4':90772,'remaining_before_fifth':7532,'blocked_fifth':26243,'prepared_total':117015,'cap':98304,'fifth_inbox':False,'fifth_receipt':False,'per_request_cap_satisfied':True}},
 'new_general_connection_gap':{'id':'G01_COMPARE_LOCATOR_LOST_ACROSS_ACTIONS','finding':'Previously disclosed compare operand locator/role mapping does not survive an intervening fact read in a stateless fresh author view. Already-read receipt progress solves read history only.','precise_observation':'The prior ref is not literally removed from known_fact_refs: it remains one of19opaque strings. Its mapping to targetOCF/concept/comparable-prior role is absent after current read. Current adjacent raw excerpt contains prior start/value but lacks its full period; it cannot safely replace a direct prior read.','causal_chain':['Response1 compare_groups obtains current/prior ref mappings in actual request2.','Response2 reads current. Actual request3 preserves only current full receipt in structured_read_progress, while compare locator is overwritten as last_action_result.','Response3 correctly refuses to infer full prior period from the neighboring fragment and reissues compare_groups to recover the prior operand locator.','Response4 receives the mapping again and reads prior.','The fifth request containing both complete receipts would need26243 with only7532remaining and is rejected before inbox; no module endpoint can be authored.'],'classification':'Producer working-view connection failure with correct conservative intermediate source behavior; not evidence that the model ignored an available full prior locator, and not a reason to enlarge/reset frozen budget.','minimal_repair_direction':'Retain already-issued complete compare/operand locator units or equivalent source-bound lookup visibility across later actions, with stable refs, target concept/role, qualifiers/unresolved cases, deterministic bounded omissions, current-source binding and ordinary budgets. Avoid silently disclosing unread fact contents, automatic new measurement inference or new tool/admission authority. Requires a new spec-first frozen attempt, not hot repair/reentry of this terminal stage.'},
 'controlled_preflight_claim_correction':{'prior_artifact':'independent/reachable-order-budget-addendum.json plus preparation-audit-addendum.json','what_remains_true':'The controlled sequence compare→two reads→stop envelopes fit93486/93444 under unchanged cap, and real native wires/source hashes were checked.','overclaim_corrected':'The script chose and retained refs from private controller._facts between steps. That establishes envelope feasibility given externally retained locators, not autonomous/stateless fresh-author reachability. The earlier label real reachable path was too strong and is superseded by the actual lost-locator trace.','why_old_controls_missed':'Eight progress tests and both controlled path probes preselected fact refs outside later author views; they tested preservation of read units, not continued accessibility of a not-yet-read operand locator after an intervening action. No expected source answer or arithmetic policy is changed.'},
 'reconstruction_review':{'artifact':str(BASE/'cache-reconstruction.json'),'artifact_sha256':file_sha(BASE/'cache-reconstruction.json'),'script_sha256':file_sha(BASE/'verify-cache-reconstruction.py'),'scope_read':'Read the script/result/log without executing it. It builds explicit pending-operation fixtures from copies, removes terminal business artifacts and actual blocked fifth journal in the copy, asserts allow_dispatch=False for each cache receive, reconstructs the same final artifacts/failure, compares all nonterminal files and original stage hashes.','reported':cache,'supported':'Consistent evidence of7original receipt-only receives,62nonterminal equal files, blocked journal recreation and64original files unchanged; no original terminal reentry, new handoff or OS/process-kill/whole-loop recovery proof. This does not change semantic1/2.'},
 'prior_evidence_error_preserved':{'artifact':'independent/stage-budget-original-overwrite-disclosure.json','limitation':'Reviewer overwrote the first pre-answer budget-failure JSON during recheck. Original bytes/hash unavailable; only historical tool stdout fields and parent acknowledgment retain the first failure. The misleading old path now contains recheck bytes and is not cited as immutable original. No existing report or counterexample was modified by this fresh audit.'},
 'anonymity_budget_ownership':'Actual persisted messages contain anonymous document handles and no known raw CIK/companyid; local canonical provenance remains intact. No new business label was read/authored; only frozen opaque group map. Local logical reservations are serialized message UTF8 bytes plus output allowance, not actual internal model token/cost accounting.',
 'non_closures':['No actual source final2operand semantic endpoint','No fresh generic arithmetic branch test','No unknown-leaf imported legacy fresh sample beyond separately frozen source control','No candidate/Signal publication/admission/reuse, S3/S4, whole-Mining or independent gain claim'],
 'artifact_sha256':{str(p):file_sha(p) for p in [STAGE/'namespace/completion.json',STAGE/'namespace/boundary.json',STAGE/'actual/failure.json',STAGE/'actual/failed-controller.json',BASE/'cache-reconstruction.json',BASE/'cache-reconstruction.log',BASE/'verify-cache-reconstruction.py',BASE/'independent/stage-budget-original-overwrite-disclosure.json']},
 'all_formal_stage_file_sha256_at_review':stage_files
}
with OUT.open('x') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'path':str(OUT),'sha256':file_sha(OUT),'module_result':'1/2','namespace_responses':3,'actual_responses':4,'source_bindings_verified':len(manifest['source_files']),'code_bindings_verified':len(manifest['code_files']),'actual_budget_terminal':True},indent=2))
