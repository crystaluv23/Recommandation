"""Pure JSON/byte audit of completed zero-answer native preflight; no product imports."""
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
import hashlib,json,re,math
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/gpre_native_initial_20261021_v1';O=D/'independent-preflight';T=D/'driver/temp-native-preflight-v2';S=T/'stage'
def read(p):return json.loads(p.read_text())
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bind(p):return {'path':str(p.relative_to(R)),'sha256':h(p),'bytes':p.stat().st_size}
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def save(n,v):
 p=O/n;assert not p.exists(),n;p.write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n');return bind(p)
result=read(T/'result.json');boot=read(S/'samples/h01/bootstrap.json');inp=read(S/'inputs.json');man=read(S/'manifest.json');contract=read(S/'contract.json');oracle=read(O/'pre-answer-source-oracle.json')
assert h(O/'pre-answer-source-oracle.json')=='0bce2212dfad502f8ad7adf8ac36661ff3da8bc43cb735cef633f9f9663d8189'
assert result['status']=='native_pending_connection_passed' and result['author_responses']==0
assert not (D/'stage').exists()
assert len(man['source_files'])==1827 and len(man['code_files'])==103
for row in man['source_files']+man['code_files']+[man['expectations']]:assert h(Path(row['path']))==row['sha256'],row['path']
x={k:v for k,v in man.items() if k!='manifest_hash'};assert digest(x)==man['manifest_hash']
assert digest(inp)==man['inputs_hash'] and digest(contract)==man['contract_hash']
assert contract['limits']=={'max_request_tokens':131072,'max_case_tokens':256000,'max_local_role_calls':2,'max_structured_corrections':1,'structured_reasoning_token_reserve':0}
assert boot['plan']==inp['plan']
view=Path(inp['sources']['gpre']['root']);vm=read(view/'reviewed_snapshot.json');assert len(vm['documents'])==1780
byid={row['document_id']:row for row in vm['documents']};cache={}
def doc(did):
 if did not in cache:
  row=byid[did];p=view/row['path'];assert h(p)==row['sha256'];cache[did]=read(p)
 return cache[did]
cutoff=datetime.fromisoformat(inp['sample']['prediction_time']);selected=[];rawspans=0
for rr in boot['bundle']['requests']:
 for dr in rr['documents']:
  d=doc(dr['document_id']);assert d['content_hash']==dr['content_hash']
  assert dr['available_at']==d['available_at'] and datetime.fromisoformat(dr['available_at'])<=cutoff
  selected.append({'request_id':rr['request']['request_id'],**dr,'file':bind(view/byid[dr['document_id']]['path'])})
 for span in rr['context_spans']:
  d=doc(span['document_id']);assert d['content_hash']==span['content_hash'];assert d['content'][span['start']:span['end']]==span['exact_text'];rawspans+=1
old=read(R/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/basic-info.json')['model']
new=boot['model_context'];assert len(new['requests'])==4
assert [len(r['projections']) for r in new['requests']]==[15,0,1,1]
visibility=[]
for nr,orr in zip(new['requests'],old['requests']):
 assert nr['projections']==orr['projections']
 differences=[k for k in nr if nr[k]!=orr.get(k)]
 assert differences==(['data_gap'] if nr['request']['request_id']=='orientation.v1.scoped_news' else [])
 visibility.append({'request_id':nr['request']['request_id'],'status':nr['status'],'projection_status':nr['projection_status'],
  'selected_document_ids':[d['document_id'] for rr in boot['bundle']['requests'] if rr['request']['request_id']==nr['request']['request_id'] for d in rr['documents']],
  'visible_projection_count':nr['visible_projection_count'],'available_projection_count':nr['available_projection_count'],
  'omitted_projection_count':nr['omitted_projection_count'],'omission_marker_count':len(nr['omitted_context_markers']),
  'source_context_truncated':nr['source_context_truncated'],'projection_context_truncated':nr['projection_context_truncated'],
  'effective_context_truncated':nr['effective_context_truncated'],'actual_data_gap':nr['data_gap']})
lineage={e['projection_id']:e for e in boot['projection_lineage']['entries']};assert len(lineage)==17
for req in new['requests']:
 for p in req['projections']:
  l=lineage[p['projection_id']];d=doc(p['document_id']);assert l['document_id']==p['document_id'] and l['content_hash']==d['content_hash'] and l['projection_text']==p['exact_text']
  for a,b,c,e in l['raw_offset_runs']:
   assert 0<=a<=b<=len(p['exact_text']) and 0<=c<=e<=len(d['content'])
anchor=boot['evaluation_anchor'];expected=oracle['private_anchor_crosscheck']
assert anchor['status']=='available' and anchor['method']==expected['method'] and anchor['trading_dates']==expected['trading_dates']
assert math.isclose(anchor['mean_adjusted_close'],float(Decimal(expected['mean_adjusted_close_decimal'])),rel_tol=0,abs_tol=1e-12)
assert math.isclose(anchor['doubling_threshold'],float(Decimal(expected['doubling_threshold_decimal'])),rel_tol=0,abs_tol=1e-12)
assert str(anchor['recent_close'])==expected['recent_close_literal'] and anchor['recent_close_date']==expected['recent_close_date']
assert boot['document_channel_set_by_core'] is True and len(boot['computed_metrics'])==1
assert boot['evaluation_context']['prediction_time']==inp['sample']['prediction_time']
assert boot['evaluation_context']['evaluation_anchor']==anchor
qpaths=list((S/'requests').glob('*.json'));inboxes=list((S/'exchange/inbox').glob('*.json'));assert len(qpaths)==len(inboxes)==1
q=read(qpaths[0]);request=q['request'];ib=read(inboxes[0]);assert ib['messages']==request['messages'] and ib['request_hash']==q['request_hash']
assert digest(request)==q['request_hash']
assert request['stage']=='research_controller_initialize'
wire=json.loads(request['messages'][1]['content']);assert set(wire)=={'initial_research_skill','basic_info','evaluation_context','evaluation_anchor','computed_metrics','validation_feedback'}
canonical_user={'initial_research_skill':boot['plan']['initial_research_skill'],'basic_info':new,'evaluation_context':boot['evaluation_context'],'evaluation_anchor':anchor,'computed_metrics':boot['computed_metrics'],'validation_feedback':None}
tokens={}
def reconcile(original,masked):
 if isinstance(original,dict):
  assert set(original)==set(masked)
  for k in original:reconcile(original[k],masked[k])
 elif isinstance(original,list):
  assert isinstance(masked,list) and len(original)==len(masked)
  for a,b in zip(original,masked):reconcile(a,b)
 elif isinstance(original,str):
  assert isinstance(masked,str)
  parts=re.split(r'(\[ANON_ID_\d+\])',masked)
  if len(parts)==1:assert original==masked;return
  pattern='';names=[]
  for part in parts:
   if re.fullmatch(r'\[ANON_ID_\d+\]',part):pattern+='(.*?)';names.append(part)
   else:pattern+=re.escape(part)
  m=re.fullmatch(pattern,original,flags=re.S);assert m,(original[:80],masked[:80])
  for key,val in zip(names,m.groups()):
   assert val
   if key in tokens:assert tokens[key]==val
   tokens[key]=val
 else:assert type(original) is type(masked) and original==masked
reconcile(canonical_user,wire)
def restore(v):
 if isinstance(v,str):return re.sub(r'\[ANON_ID_\d+\]',lambda m:tokens[m.group()],v)
 if isinstance(v,list):return [restore(i) for i in v]
 if isinstance(v,dict):return {k:restore(i) for k,i in v.items()}
 return v
assert restore(wire)==canonical_user
for token,value in tokens.items():
 assert any(mark in value.casefold() for mark in ('1309402','green plains','gpre')), (token,value)
text=canonical(request['messages'])
for forbidden in ('cik_0001309402','0001309402','1309402','GREEN PLAINS','GPRE','gpreinc','0001309402-25-000089','000130940225000089','0001309402-25-000008','000130940225000008','gpre-20250331','gpre-20241231','sec.gov/Archives/edgar/data/1309402','pre-answer-source-oracle','source_fact_boundaries_not_required_answer','private_anchor_crosscheck',oracle['sources'][0]['sha256']):
 assert forbidden.casefold() not in text.casefold(),forbidden
assert not re.findall(r'https?://[^\s"<>]+',text)
reservation=len(canonical(request['messages']).encode())+request['max_output_tokens'];assert reservation==61888 and reservation<=131072
reserves=read(S/'request-reservations.json');assert reserves['total']==reservation and len(reserves['requests'])==1
assert not list((S/'exchange/receipts').glob('*.json')) and not list((S/'exchange/outbox').glob('*'))
assert not (S/'completion.json').exists() and not (S/'failure.json').exists()
report={'status':'PASS_PREPARE_READY_NOT_H_INIT_ACCEPTED','audited_at_utc':datetime.now(timezone.utc).isoformat(),
 'source_only_oracle':bind(O/'pre-answer-source-oracle.json'),'native_visibility_addendum':{'actual_17_projection_ids_text_available_at_exact_old':True,'requests':visibility,
 'news_gap_changed':'Old external_not_authorized/alpha_vantage becomes native no_matching_documents/provider null with no acquisitionadapter. Both coverage only, no event-absence implication. No oracle fact/gold change.',
 'full_source_presence_not_visibility':True,'no_six_signal_results_added':True},
 'preflight':bind(T/'result.json'),'bootstrap':bind(S/'samples/h01/bootstrap.json'),'manifest':bind(S/'manifest.json'),
 'inputs':bind(S/'inputs.json'),'contract':bind(S/'contract.json'),'journal':bind(qpaths[0]),'native_inbox':bind(inboxes[0]),
 'source_bindings_current_equal':1827,'code_bindings_current_equal':103,'selected_documents':selected,'context_spans_exact_raw_checked':rawspans,'lineage_entries_checked':17,
 'core_anchor':'Native baseline matches independent full171bar Decimal last5 check within1e-12; not handfilled. Provider historicaladjustment truth not newlyauthenticated.',
 'native_computed_cards':boot['computed_metrics'],'wire':{'canonical_user_whole_exact_after_identity_inverse':True,'opaque_token_count':len(tokens),
 'projection_ids_order_periods_units_dates_and_omission_flags_unchanged':True,'padded_unpadded_CIK_legalname_ticker_accession_URL_website_literal_leaks':[],
 'private_oracle_data_in_payload':False,'messages_utf8_bytes':reservation-request['max_output_tokens'],'output_reservation':request['max_output_tokens'],'logical_reservation':reservation},
 'corrected_driver_summary_issue':'Original result.bundle_statuses.documents=0 reads nonexistentdocument_ids key; rawbundle has documents2/0/2/1. Summaryerror, not sourcefailure; original retained.',
 'counts':{'native_pending_receive_attempt_from_driver':1,'model_responses':0,'dispatch':0,'journal':1,'reviewer_nativecalls':0,'reviewer_Store':0,'network':0,'labels':0},
 'gates_remaining':['Formalprepare must bind this opaque review as expectations and parent independentlyverify nestedoracle/addendumbindings.','Fresh actor must only receive neutralbyteexact nativeinbox copy/outbox; bindingandrawbytehandoffreview afteractualdelivery. No actor handoff exists yet.','FreshacceptedH_init raw→nativeparse/correction/mechanicaldisposition→persist/reread semanticreview andterminalseal remainunexercised.'],
 'scope':'Nativezero-answerpreflight only. DefaultmanualPlan notvalidatedresearchstrategy; noacceptedprior/H_init/needownership/Reflect/Predictor/Signal/freshbenefit. Noformalstage exists atreview.'}
rb=save('pre-answer-native-review.json',report)
save('native-preflight-audit-result.json',{'status':'PASS','review':rb,'probe':bind(Path(__file__)),'oracle_unchanged':bind(O/'pre-answer-source-oracle.json')})
print(json.dumps({'status':'PASS','review':rb,'boundfiles':1930,'selected_documents_counts':[len(r['documents']) for r in boot['bundle']['requests']],'visible':17,'reservation':reservation,'token_count':len(tokens)},indent=2))
