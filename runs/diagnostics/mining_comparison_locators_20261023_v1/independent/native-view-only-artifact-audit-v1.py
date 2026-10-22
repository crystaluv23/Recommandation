"""Read-only native artifact audit; never imports the production runner or dispatches."""
import json,hashlib,subprocess
from pathlib import Path
ROOT=Path('/Users/l/Project/Recommandation')
BASE=ROOT/'runs/diagnostics/mining_comparison_locators_20261023_v1'
NATIVE=BASE/'native-view-only'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def bind(p):return {'path':str(p),'sha256':sha(p)}
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def budget(x):return len(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
frozen=load(NATIVE/'source-and-code-before.json'); checks=[]
for kind in ('sources','code'):
 mismatches=[b for b in frozen[kind] if sha(b['path'])!=b['sha256']]
 assert not mismatches
 checks.append({'kind':kind,'bindings_checked':len(frozen[kind]),'mismatches':mismatches})
docpath=ROOT/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/0671.json'
doc=load(docpath);assert hashlib.sha256(doc['content'].encode()).hexdigest()==doc['content_hash']
assert doc['metadata']['symbol']=='DGICA'; assert doc['metadata']['cik']=='0000800457'
expected={
 'fact-2f898adb2d25e349':{'value':'4342261','period':{'start':'2010-01-01','end':'2010-06-30'},'offset':[57043,57546],'row_hash':'1ba26ebb8ecab8c367dd2178646fd045340e71df36591e4cd551e42bed8eee86'},
 'fact-3d4faa09011f777b':{'value':'9506313','period':{'start':'2011-01-01','end':'2011-06-30'},'offset':[57547,58050],'row_hash':'4ddbe4f40edfc3364932f8b81df96eccb4c6f8fb5ce5b419d0d0c7d573140544'}}
for x in expected.values():
 x['literal']=doc['content'][slice(*x['offset'])]
 assert hashlib.sha256(x['literal'].encode()).hexdigest()==x['row_hash']
 raw=json.loads(x['literal']);assert str(raw['value'])==x['value']
 assert {'start':raw['start'],'end':raw['end']}==x['period'];assert raw['taxonomy']=='us-gaap'
 assert 'including discontinued operations' in raw['description']
concept='NetCashProvidedByUsedInOperatingActivities'
def select_from_current_only(v,role):
 p=v.get('comparison_progress',{})
 if p.get('snapshot_status')=='current':
  for item in p['items']:
   if item['concept']==concept:
    return next(row[role][case]['fact_ref'] for row in item['groups'].values() for case in sorted(row[role]))
 last=v.get('last_action_result',{})
 if last.get('action')=='compare_groups' and 'groups' in last:
  return next(row['concepts'][concept][role][case]['fact_ref'] for row in last['groups'].values() for case in sorted(row['concepts'][concept][role]))
 raise LookupError('current payload has no locator')
limits=load(NATIVE/'result.json')['limits']
assert limits['max_request_tokens']==32768 and limits['max_case_tokens']==98304
out=[]; wire_aliases=('0000800457','cik_0000800457','cik_0000800457:20250731','DGICA','DGICB')
for name,roles in (('current-first',('latest','comparable_prior')),('prior-first',('comparable_prior','latest'))):
 pairs=[]
 for suffix in ('','-reconstructed'):
  root=NATIVE/(name+suffix); rows=[]
  for index in range(1,5):
   selection=load(root/f'selected-{index:03}.json')
   p=Path(selection['input']['path']);assert sha(p)==selection['input']['sha256']
   journal=load(p);q=journal['request'];assert hashlib.sha256(canon(q)).hexdigest()==journal['request_hash']
   assert journal['request_hash']==p.stem
   v=json.loads(next(m['content'] for m in q['messages'] if m['role']=='user'))
   wire=json.dumps(q['messages'],ensure_ascii=False);assert all(s not in wire for s in wire_aliases)
   reservation=budget(q['messages'])+q['max_output_tokens']
   assert reservation<=32768 and q['max_output_tokens']==2000
   action=selection['action']
   if index==1:
    assert action['action']=='compare_groups' and action['concepts']==[concept]
    assert 'comparison_progress' not in v
   elif index in (2,3):
    assert action['action']=='read_span'
    assert action['fact_ref']==select_from_current_only(v,roles[index-2])
    assert action['fact_ref'] in expected
   else:
    assert action['action']=='record_deferred'
    receipts=v['structured_read_progress']['items']
    assert {r['fact_ref'] for r in receipts}==set(expected)
    for receipt in receipts:
     e=expected[receipt['fact_ref']]
     assert receipt['masked'] in doc['content'] and e['literal'] in receipt['masked']
     assert receipt['fact']=={'concept':concept,'taxonomy':'us-gaap','unit':'USD','value':e['value'],'period':e['period']}
     assert receipt['content_hash']==doc['content_hash']
     assert receipt['available_at']==doc['available_at'] and receipt['read_count']==1
     assert '[ANON_ID_0000]' in receipt['document_ref'] and '0000800457' not in receipt['document_ref']
   if index>1:
    cp=v['comparison_progress'];assert cp['snapshot_status']=='current' and cp['selection_is_exhaustive']
    assert len(cp['items'])==1 and cp['items'][0]['groups']['control']['case_count']==1
    assert cp['items'][0]['groups']['positive']=={'case_count':0,'available_cases':[],'latest':{},'comparable_prior':{},'unresolved_basis_cases':{}}
    assert cp['items'][0]['groups']['control']['latest']['case-008']=={'fact_ref':'fact-3d4faa09011f777b','value':'9506313'}
    assert cp['items'][0]['groups']['control']['comparable_prior']['case-008']=={'fact_ref':'fact-2f898adb2d25e349','value':'4342261'}
   rows.append({'step':index,'request':bind(p),'reservation':reservation,'selected_action':action['action'],**({'selected_current_payload_ref':action['fact_ref']} if 'fact_ref' in action else {})})
  total=sum(x['reservation'] for x in rows);assert total<=98304
  assert not list(root.rglob('inbox/*.json')) and not list(root.rglob('receipts/*.json')) and not list(root.rglob('cache/*.json'))
  view=load(root/'final-view.json'); ledger=load(root/'final-ledger.json')
  assert view['budget']['heavy_remaining']==8  # unchanged 12-heavy policy, four executed including controlled fetch
  assert {r['fact_ref'] for r in view['structured_read_progress']['items']}==set(expected)
  pairs.append({'variant':name+suffix,'steps':rows,'total_reservation':total,'headroom':98304-total,'final_view':bind(root/'final-view.json'),'final_ledger':bind(root/'final-ledger.json'),'inboxes':0,'answers':0,'cache_answers':0})
 left=NATIVE/name; right=NATIVE/(name+'-reconstructed')
 for filename in ('final-view.json','final-ledger.json'):
  assert (left/filename).read_bytes()==(right/filename).read_bytes()
 for i in range(1,5):
  a=load(left/f'selected-{i:03}.json');b=load(right/f'selected-{i:03}.json')
  assert Path(a['input']['path']).read_bytes()==Path(b['input']['path']).read_bytes()
 out.extend(pairs)
old=NATIVE/'before-controller.py'
original=subprocess.check_output(['git','show','341b94a5:src/stock_opportunity_agent/research/mining_controller.py'])
assert old.read_bytes()==original
for kind in ('sources','code'):
 assert all(sha(b['path'])==b['sha256'] for b in frozen[kind])
report={
 'scope':'Independent artifact-only verification of actual-source controlled native view-only input paths; no model calls, stage reentry, source acquisition, new business labels or truth.',
 'native_capture':bind(BASE/'capture-view-only.py'),'result':bind(NATIVE/'result.json'),'bindings':checks,
 'additional_current_bindings':[bind(ROOT/'spec/src/stock_opportunity_agent/research/signal_mining_agent.md'),bind(BASE/'independent/preimplementation-review.json')],
 'variants':out,'source':{'binding':bind(docpath),'content_sha256':doc['content_hash'],'source_symbol_from_local_metadata':doc['metadata']['symbol'],'cik_from_local_metadata':doc['metadata']['cik'],'operands':[{k:v for k,v in e.items() if k!='literal'} for e in expected.values()],'qualifications':['Historical 2011 filing/source, 2025 case cutoff; not current2025 funding or performance.','H1 cumulative operating cash flow; description includes discontinued operations.','Source extraction is retrospective and requires primary filing audit; new locator retention does not remove source qualification.','Controlled one-document selection is not autonomous retrieval or all-source absence proof.']},
 'identity_harness_limitation':{'original_capture_checks_wrong_snapshot_aliases':['GPRE','Green Plains'],'independent_actual_alias_absence_checks':list(wire_aliases),'all_actual_native_messages_pass':True,'DGICA_supported_by_local_source_metadata':True,'DGICB_only_supplementary_string_check':True,'Donegal_name_not_asserted_from_unread_external_evidence':True,'canonical_handles_preserved':True},
 'reconstruction_scope':'Four zero-inbox input-only builds repeat current-view selector choices and byte-identical native journals/final view/ledger. No cache answers exist; not cached-answer replay, pending LocalRoleExchange recovery, OS interruption recovery or fresh author obedience.',
 'old_negative':{'exact_341b94a5_implementation_preserved':bind(old),'root_reported_missing_locator_after_first_read':True,'independent_binding_of_old003_and_raw3_in_preimplementation_review':True},
 'semantic_acceptance':'Not measured. Old fixed fresh module result1/2 remains unchanged; no production authors answered in this task.',
 'all_checks_pass':True}
with (BASE/'independent/native-view-only-artifact-audit-v1.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'all_checks_pass':True,'source_bindings':len(frozen['sources']),'code_bindings':len(frozen['code']),'variants':[{'variant':x['variant'],'total':x['total_reservation'],'headroom':x['headroom']} for x in out]},indent=2))
