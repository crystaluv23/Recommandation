"""Small synthetic label-source qualification/freeze probes only."""
from pathlib import Path
from copy import deepcopy
import tempfile,json,hashlib
import run_reviewed_posthoc_stage as stage
from stock_opportunity_agent.cases.label_store import build_label_records,write_label_store
from stock_opportunity_agent.artifacts import canonical_json_hash
from scripts.replay_incremental_reflection_memory import deny_network
OUT=Path(__file__).resolve().parent
archive=json.loads((OUT.parents[1]/'label_store_loader_boundary_20261020_v1/original-counterexamples.json').read_text())['fixture_archive']
rows=[]
with deny_network() as net:
 for name in ['legal_qualified_source_freeze','archive_changed','label_manifest_changed','label_records_changed','missing_archive','parent_prediction_changed','parent_extra_file','code_binding_changed','oracle_changed','qualified_baseline_mismatch','qualified_key_missing']:
  with tempfile.TemporaryDirectory(prefix='independent-posthoc-source-') as td:
   base=Path(td);parent=base/'parent';parent.mkdir();root=base/'stage';root.mkdir();label=base/'label';ap=base/'prices.json';ap.write_text(json.dumps(archive))
   rs,ex=build_label_records(archive['bars_by_symbol'],[('cik_00000042','2025-01-15')],{'cik_00000042':'DEMO'});assert not ex
   write_label_store(label,records=rs,archive_path=ap,archive_sha256=hashlib.sha256(ap.read_bytes()).hexdigest(),created_at='2026-10-20T00:00:00Z')
   saved={'company_id':'cik_00000042','prediction_time':'2025-01-15T00:00:00+00:00','final_context':{'prediction_baseline':{'mean_adjusted_close':rs[0].baseline_mean,'trading_dates':list(rs[0].baseline_dates)}}}
   (parent/'prediction.json').write_text(json.dumps(saved));(parent/'contract.json').write_text(json.dumps({'max_local_calls':8}));stage.LocalRoleExchange(parent/'exchange',max_calls=8)
   s,t,qualification=stage._qualified_truth(parent,label)
   source=base/'bound-code.txt';source.write_text('synthetic frozen code placeholder\n');oracle={'fixture':'synthetic-no-model'}
   inputs={'parent':{'root':str(parent),'files':stage._files(parent),'external_files':[]},'qualification':qualification,'label_root':str(label)}
   contract={'input_hash':canonical_json_hash(inputs),'expectations_hash':canonical_json_hash(oracle)}
   manifest={'contract_hash':canonical_json_hash(contract),'code_files':[stage.binding(source)],'originals':[]};manifest['manifest_hash']=canonical_json_hash(manifest)
   for key,val in [('inputs',inputs),('expectations',oracle),('contract',contract),('manifest',manifest)]: (root/(key+'.json')).write_text(json.dumps(val))
   if name=='archive_changed':ap.write_text('{"bars_by_symbol":{}}')
   elif name=='label_manifest_changed':(label/'manifest.json').write_text('{}')
   elif name=='label_records_changed':(label/'labels.jsonl').write_text('{}\n')
   elif name=='missing_archive':ap.unlink()
   elif name=='parent_prediction_changed':(parent/'prediction.json').write_text('{}')
   elif name=='parent_extra_file':(parent/'unexpected.txt').write_text('extra')
   elif name=='code_binding_changed':source.write_text('changed')
   elif name=='oracle_changed':(root/'expectations.json').write_text('{}')
   elif name=='qualified_baseline_mismatch':
    saved['final_context']['prediction_baseline']['mean_adjusted_close']=99;(parent/'prediction.json').write_text(json.dumps(saved))
   elif name=='qualified_key_missing':
    saved['company_id']='cik_00000043';(parent/'prediction.json').write_text(json.dumps(saved))
   before=stage._files(base)
   row={'case':name,'expected':'accept' if name=='legal_qualified_source_freeze' else 'reject'}
   try:
    if name.startswith('qualified_'):stage._qualified_truth(parent,label)
    else:stage._verify(root)
    row['actual']='accept'
   except Exception as e:row.update(actual='reject',error_type=type(e).__name__,error=str(e).replace(str(base),'@TMP@')[:200])
   row['pass']=row['actual']==row['expected'];assert before==stage._files(base);rows.append(row)
result={'scope':'Synthetic small archive/store, no actual canonical store reads; _verify fixture assumes already-prepared parent, does not claim a synthetic parent is production qualified. Actual parent verification is separate in preflight-checks.','cases':rows,'all_passed':all(x['pass'] for x in rows),'network_attempts':net['network_attempts'],'script_under_test_sha256':hashlib.sha256(Path(stage.__file__).read_bytes()).hexdigest()}
p=OUT/'qualification-freeze-results.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'cases':len(rows),'all_passed':result['all_passed'],'failures':[r for r in rows if not r['pass']]},indent=2))
