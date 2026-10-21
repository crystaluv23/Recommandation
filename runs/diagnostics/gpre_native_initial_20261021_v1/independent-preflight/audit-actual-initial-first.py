"""Read actual raw/receipt/cache/state and sources; no native imports or execution."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/gpre_native_initial_20261021_v1';S=D/'stage';O=D/'independent-preflight'
def read(p):return json.loads(p.read_text())
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def b(p):return {'path':str(p),'sha256':h(p),'bytes':p.stat().st_size}
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'))
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()
req='66c9d73cf10c16c4a70e77165c48c63f9eee3158f4c6aaa577678398c6da2181'
m=read(S/'manifest.json');handoff=read(D/'root/handoff-01.json');rawhandoff=read(D/'root/raw-handoff-01.json');dispatch=read(D/'root/dispatch-01.json')
for row in m['source_files']+m['code_files']+[m['expectations']]:assert h(Path(row['path']))==row['sha256'],row['path']
assert digest({k:v for k,v in m.items() if k!='manifest_hash'})==m['manifest_hash']
assert h(O/'pre-answer-source-oracle.json')=='0bce2212dfad502f8ad7adf8ac36661ff3da8bc43cb735cef633f9f9663d8189'
assert h(O/'pre-answer-native-review.json')=='5df8021c85ac69817491247578409a17a11a26c7d9499bdea8af08766dfae463'
assert h(O/'formal-preanswer-review.json')=='53bfc9203a0b61db544debbe5ceebe2fadd33767daf40be40930bd63762dd743'
preservation=read(D/'root/before-preservation.json')
for row in preservation['files']:assert h(R/row['path'])==row['sha256']
rawpath=S/'exchange/outbox'/f'{req}.txt';neutral=Path(rawhandoff['neutral_outbox']);raw=read(rawpath)
assert rawpath.read_bytes()==neutral.read_bytes() and h(rawpath)==rawhandoff['raw_sha256']=='687ae13a4e3385e7442a38de00705e8b9f10992e12faf0babc2ddd0eb8dccde1'
receiptpath=S/'exchange/receipts'/f'{req}.json';receipt=read(receiptpath)
assert receipt['agent_id']==dispatch['agent_id']==rawhandoff['agent_id']=='/root/exact_initial_87'
assert receipt['raw_output_sha256']==h(rawpath) and receipt['inbox_sha256']==h(Path(handoff['native_inbox']))==h(Path(handoff['neutral_inbox']))
assert receipt['request_hash']==req
parsed=read(S/'samples/h01/parsed_step.json');persisted=read(S/'samples/h01/initial_state.json');cachepath=S/'cache/responses'/f'{req}.json';cache=read(cachepath)
assert raw==cache['json_output']==parsed['state']==persisted['state']
assert cache['raw_output']==rawpath.read_text()
assert parsed['metadata']==persisted['metadata']=={}
assert parsed['request_hashes']==persisted['request_hashes']==[req]
assert parsed['usage']==persisted['usage']==persisted['native_budget_usage']=={'cost':0.0,'llm_calls':1,'tokens':61888}
assert persisted['state']['decision']=='continue' and len(raw['next_information_needs'])==5
boot=read(S/'samples/h01/bootstrap.json');projections={p['projection_id']:p for r in boot['model_context']['requests'] for p in r['projections']}
assert len(projections)==17
wire=json.loads(read(S/'requests'/f'{req}.json')['request']['messages'][1]['content']);wproj={p['projection_id']:p for r in wire['basic_info']['requests'] for p in r['projections']}
view=Path(read(S/'inputs.json')['sources']['gpre']['root']);vm=read(view/'reviewed_snapshot.json');byid={r['document_id']:r for r in vm['documents']};quoted=[]
for ref in raw['supporting_evidence']:
 p=projections[ref['projection_id']];assert ref['kind']=='basic_info'
 assert ref['exact_text'] in p['exact_text'] and ref['exact_text'] in wproj[ref['projection_id']]['exact_text']
 row=byid[p['document_id']];d=read(view/row['path']);assert h(view/row['path'])==row['sha256'] and d['company_id']=='cik_0001309402'
 assert datetime.fromisoformat(d['available_at'])<=datetime.fromisoformat('2025-05-30T00:00:00+00:00')
 assert ref['claim'] in raw['current_beliefs']+raw['contradictions']
 quoted.append({'projection_id':ref['projection_id'],'document_id':p['document_id'],'available_at':p['available_at'],'exact_quote_start_in_projection':p['exact_text'].index(ref['exact_text']),'claim':ref['claim'],'quote':ref['exact_text']})
assert len(quoted)==4
for hs in raw['hypotheses']:assert hs.startswith('Inference to test:') and 'This fails if' in hs
for need in raw['next_information_needs']:assert 'prediction time' in need
assert len(raw['next_information_needs'])==len(set(raw['next_information_needs']))
assert raw['resolved_questions']==[]
for forbidden in ('GPRE','GREEN PLAINS','1309402','rawcap:v1','cash_to_current_liabilities_ratio','0.546','61888','8.56','4.28'):
 assert forbidden.casefold() not in rawpath.read_text().casefold(),forbidden
assert len(list((S/'exchange/receipts').glob('*.json')))==1 and len(list((S/'exchange/inbox').glob('*.json')))==1 and len(list((S/'requests').glob('*.json')))==1
completion=read(S/'completion.json');assert completion['status']=='accepted_initial_requires_independent_review'
assert completion['initial_state']['sha256']==h(S/'samples/h01/initial_state.json')=='9fdacbae3b14e3cf2cb42de3acabcf20ae584d4a8b18e11414b944f11480cab9'
assert completion['logical_reservation']==61888 and completion['requests']==[{'request_hash':req,'reservation':61888}]
assert all(completion[k]==0 for k in ('routing','Signal_execution','Reflect','Predictor','model_API'))
assert not (S/'failure.json').exists()
semantic=[
 {'field':'current_beliefs[0]','verdict':'PASS','reason':'Exact two-segment/product quote supports business description. The qualification explicitly avoids asserting UHP sales traction from product inclusion.'},
 {'field':'current_beliefs[1]','verdict':'PASS','reason':'Exact Q1 comparability passage identifies January2025 Fairmont idling and early2025 restructuring. It does not quantify savings; answer says benefits unquantified, not that benefits are absent.'},
 {'field':'current_beliefs[2]','verdict':'PASS','reason':'Exact current Q1 forward-looking disclosure establishes ongoing Board review/status/timing/outcome uncertainty only. It does not prove executable transaction or realized value; answer preserves this distinction.'},
 {'field':'contradictions[0]','verdict':'PASS','reason':'Q1 table is USD thousands for three months endedMar31 2025/2024. Ethanol gross margin negative -5692 versus -2643 and consolidated3039 below8367 support weak contemporaneous economics. “Counter-evidence to an already-established turnaround” is read as counter to that proposition, not a factual assertion that turnaround has already occurred. No derived margin percentage, annualization or control-anchor restatement.'},
 {'field':'hypotheses[0]','verdict':'PASS_AS_HYPOTHESIS','reason':'Explicit inference/falsification, conditional cost and co-product commercialization→near-term cash-earnings possibility, not claimed realized savings/premium or guaranteed doubling.'},
 {'field':'hypotheses[1]','verdict':'PASS_AS_HYPOTHESIS','reason':'Explicit inference/falsification with then-disclosed timetable/proceeds/financing prerequisites. “Market distressed expectations” is interpretive framing from weak operating/price-control context, not established market-consensus or valuation evidence; it earns no factual mispricing/benefit credit.'},
 {'field':'open_questions[0]','verdict':'PASS','reason':'Leaves materiality/credibility/expectations unresolved; explicitly price weakness alone cannot establish mispricing.'},
 {'field':'next_information_needs[0]','verdict':'PASS','reason':'Visible passage names initiatives/idling dates, but lacks savings target, cost, implementation details/production effects and realized savings proof. Asks what had been disclosed by cutoff; not post-cutoff realized actuals.'},
 {'field':'next_information_needs[1]','verdict':'PASS','reason':'Visible UHP inclusion does not provide volume/premium/cost/qualification/offtake metrics. Question requests then-published milestones only; no assumed contract or future actuals.'},
 {'field':'next_information_needs[2]','verdict':'PASS','reason':'Visible review reference does not supply specific alternatives/terms/commitments/obstacles/date. It asks missing specificity, rather than repeating whether review exists.'},
 {'field':'next_information_needs[3]','verdict':'PASS','reason':'Actual financial projection is clipped to DEIshares and accounts-payable rows; visible source does not provide unrestricted cash, OCF burn, capex commitments, maturities/covenants/issuance. These are genuine unresolved by-cutoff facts, not synthetic needownership or six Signal results.'},
 {'field':'next_information_needs[4]','verdict':'PASS','reason':'Visible risk/hedging/low-carbon narrative does not quantify cash-earnings sensitivities or contracted margin economics. Requests contemporaneous disclosed quantities/guidance rather than future results or asserting missing source proves absence.'}
]
report={'status':'PASS_ONE_ACTUAL_NATIVE_H_INIT_SOURCE_FAITHFUL','fixed_denominator':{'case':1,'passed':1},'audited_at_utc':datetime.now(timezone.utc).isoformat(),
 'source_oracle':b(O/'pre-answer-source-oracle.json'),'preanswer_visibility_review':b(O/'pre-answer-native-review.json'),'formal_preanswer_review':b(O/'formal-preanswer-review.json'),
 'actual_raw':b(rawpath),'neutral_raw':b(neutral),'receipt':b(receiptpath),'cache':b(cachepath),'parsed_step':b(S/'samples/h01/parsed_step.json'),'persisted_initial_state':b(S/'samples/h01/initial_state.json'),'completion':b(S/'completion.json'),
 'exact_raw_cache_parsed_persisted_state_equal':True,'raw_to_accepted_semantic_deltas':[],'mechanical_loss_or_salvage':False,
 'actual_actor':receipt['agent_id'],'fork_none_handoff':b(D/'root/dispatch-01.json'),'raw_copy_byte_equal':True,
 'native_first_answers':1,'model_corrections':0,'logical_reservation':61888,'host_tokens_and_cost':'unknown; native cost0 means externalAPIcost0 accounting, not measured host cost',
 'semantic_reviews':semantic,'source_quotes':quoted,'needs_count':5,'visible_basic_info_projections_preserved':17,
 'frozen_source_current_equal':len(m['source_files']),'frozen_code_current_equal':len(m['code_files']),'original_preservation_files_current_equal':len(preservation['files']),
 'immutable_oracle_unchanged':True,'news_gap_and_partial_context_not_negative':True,
 'reopen_claim':'Only read persistedJSON files. No Store, constructor, native resume, restoration or interrupted-run recovery executed by reviewer.',
 'scope':['Freshactual H_init only; native default/manualInformationPlan remains manual, not independentlyvalidated strategy.','NoSignalbatch/routingownership/Reflect/Predictor/outcome/independentbenefit or wholeMVP claim.','Marketcondition framing stays hypothesis; historical adjustmenttruth/APIvintage/primaryaudit not re-proven.','No downstream use or terminalrestore has been executed or claimed by this audit.'],
 'reviewer_calls':{'native':0,'Store':0,'GET':0,'model':0,'LabelStore':0},'source_before_and_after_for_this_read_audit':'Current1930frozenbindings+14preservation checked; productflags are corroborated by actualsinglejournal/receipt/raw/cache/parsedfiles, not used alone.'}
p=O/'actual-initial-review.json';assert not p.exists();p.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n');print(json.dumps({'status':'PASS','review':b(p),'quote_count':4,'needs':5,'frozenbindings':1930,'originalpreservation':len(preservation['files'])},indent=2))
