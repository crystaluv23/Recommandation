"""Bind all terminal stage files and exact audit commands; no business execution."""
from pathlib import Path
from collections import Counter
import hashlib,json
P=Path(__file__).resolve().parent;S=P/'stage';report=P/'independent-actual-consumer-review.json'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
terminal=P/'terminal-file-bindings.json';assert sha(terminal)=='c46b681e5b65c77b4d9ceb140a0cc869ebf4fd22d86fa1c2889b42c5cd2a0336';tb=json.loads(terminal.read_bytes())['files'];assert len(tb)==3027
for b in tb:assert sha(b['path'])==b['sha256'],b['path']
assert {str(p.resolve()) for p in S.rglob('*') if p.is_file()}=={b['path'] for b in tb}
R=json.loads(report.read_bytes());gaps={};groups=json.loads((S/'plan.json').read_bytes())['groups'];cases=json.loads(Path(json.loads(Path(json.loads((S/'plan.json').read_bytes())['bundle']['path']).read_bytes())['projection']['path']).read_bytes())['cases']
for group in groups:
 rows=[];refs=Counter()
 for case in cases:
  data=json.loads((S/group['name']/(case['case_id']+'.json')).read_bytes())
  for item in data['exact_signal_input_resolutions']:
   r=item['resolution']
   if r['status']=='unresolved':
    refs[item['signal_ref']]+=1;rows.append({'case_id':case['case_id'],'company_id':case['company_id'],'cutoff':case['prediction_time'],'signal_ref':item['signal_ref'],'reason':r['data_gap']['reason'],'message':r['data_gap']['message'],'coverage':r['coverage']})
 assert len(rows)==50;gaps[group['name']]={'count_by_exact_ref':dict(refs),'unresolved_rows':rows}
R['terminal_stage_file_bindings']={'manifest':bind(terminal),'file_count':3027,'complete_membership_and_all_bytes_equal':True};R['signal_input_exact_unresolved_rows']=gaps
R['input_manifest']=bind(S/'input_manifest.json');assert R['input_manifest']['sha256']=='853be82912ec717f4b7779d6b0562b3d1792d6ed88602b3c9eb58076498edc73'
R['execution_summary']=bind(P/'execution-summary.json');assert R['execution_summary']['sha256']=='89aca88d41025ed9e76cc05fa67620eb6de4f177d9c24a4c85f619a7b913753d'
R['limits'].append('Worker/restart claim is actual snapshot()+reopen same canonical/type, not OS process/crash recovery.')
report.write_text(json.dumps(R,indent=2)+'\n')
command='PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:scripts /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3.12 '
receipt={'schema_version':'independent-actual-audit-command-record-v1','scope':'Read-only completed-artifact audit; no producer prepare/execute rerun.','commands':[command+str(P/'independent-actual-consumer-review.py'),command+str(P/'finalize-independent-actual-review.py')],'audit_helper':bind(P/'independent-actual-consumer-review.py'),'finalization_helper':bind(__file__),'original_harness_failure_log':bind(P/'independent-actual-consumer-original-harness.log'),'original_harness_failure':'Oldbaseline summary fields differ from newstage fields; reviewer KeyError corrected after reading original baseline schema. Product execute remained exit0 and unchanged.','successful_main_audit_log':bind(P/'independent-actual-consumer-review.log'),'result':bind(report),'terminal_stage_bindings':bind(terminal)}
p=P/'independent-actual-audit-command-record.json';p.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'result':bind(report),'command_record':bind(p),'stage_files_verified':3027,'all_checks_passed':True,'gap_exact_refs':{k:v['count_by_exact_ref'] for k,v in gaps.items()}}))
