"""Synthetic evaluation-only loader counterexamples. Never reads a real label store."""
from pathlib import Path
from datetime import date,timedelta
from copy import deepcopy
import tempfile,json,hashlib,socket
import argparse,sys,importlib.util
from importlib.machinery import SourceFileLoader
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--loader',type=Path,default=Path(__file__).with_name('original_label_store.py.txt'))
parser.add_argument('--calculator',type=Path,default=Path(__file__).with_name('original_outcomes.py.txt'))
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.output.exists():raise RuntimeError('Preserve prior evidence: output must be new')
def load(name,path):
 loader=SourceFileLoader(name,str(path.resolve()));spec=importlib.util.spec_from_loader(name,loader);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;loader.exec_module(module);return module
import stock_opportunity_agent  # initialize the ordinary package before frozen module substitution
calculator_module=load('stock_opportunity_agent.cases.outcomes',args.calculator)
module=load('independent_label_store_under_audit',args.loader)
LabelStore,build_label_records,write_label_store,UnknownLabelError=module.LabelStore,module.build_label_records,module.write_label_store,module.UnknownLabelError
six_month_smoothed_multiple=calculator_module.six_month_smoothed_multiple
from scripts.replay_incremental_reflection_memory import deny_network
repo=Path('/Users/l/Project/Recommandation');asof=date(2025,1,15);company='cik_00000042';bars=[];day=date(2025,1,6)
while day<=date(2025,7,15):
 if day.weekday()<5:bars.append({'as_of_date':day.isoformat(),'adjusted_close':220.0 if date(2025,4,28)<=day<=date(2025,5,2) else 100.0})
 day+=timedelta(days=1)
archive={'schema_version':'synthetic-price-archive-fixture','bars_by_symbol':{'DEMO':bars}}
calculated=six_month_smoothed_multiple(bars,asof);assert calculated['realized_max_multiple']==2.2
records,exclusions=build_label_records(archive['bars_by_symbol'],[(company,asof.isoformat())],{company:'DEMO'});assert not exclusions and len(records)==1
cases=[]
def attempt(name,kind,manifest_change=None,record_change=None,archive_change=None,extra_line=False,lookup_unknown=False):
 with tempfile.TemporaryDirectory(prefix='independent-label-loader-') as td:
  base=Path(td);ap=base/'archive.json';ap.write_text(json.dumps(archive,sort_keys=True));archive_sha=hashlib.sha256(ap.read_bytes()).hexdigest();root=base/'store'
  write_label_store(root,records=records,archive_path=ap,archive_sha256=archive_sha,created_at='2026-10-20T00:00:00+00:00')
  m=json.loads((root/'manifest.json').read_text());r=json.loads((root/'labels.jsonl').read_text())
  if manifest_change:manifest_change(m,ap)
  if record_change:record_change(r)
  (root/'manifest.json').write_text(json.dumps(m,sort_keys=True));(root/'labels.jsonl').write_text(json.dumps(r,sort_keys=True)+'\n')
  if extra_line:(root/'labels.jsonl').write_text((root/'labels.jsonl').read_text()*2)
  if archive_change:archive_change(ap)
  row={'case':name,'kind':kind,'expected': 'accept' if kind=='positive' else 'reject','manifest_changes':{k:v for k,v in m.items() if k not in ('archive_path','created_at')},'record_changes':{k:v for k,v in r.items() if records[0].to_dict().get(k)!=v}}
  try:
   store=LabelStore.load(root)
   truth=store.ground_truth(company,'2099-01-01' if lookup_unknown else asof)
   row.update(actual='accepted',returned_truth=truth,returned_record=store.record(company,asof).to_dict())
  except Exception as e:row.update(actual='rejected',error_type=type(e).__name__,error=str(e).replace(str(base),'@TMP@'))
  row['expected_behavior_met']=row['actual']==('accepted' if kind=='positive' else 'rejected');cases.append(row)
with deny_network() as network:
 attempt('valid_archive_contract_and_record','positive')
 attempt('archive_missing','invalid',archive_change=lambda p:p.unlink())
 attempt('archive_sha_wrong','invalid',manifest_change=lambda m,p:m.update(archive_sha256='0'*64))
 attempt('archive_sha_malformed','invalid',manifest_change=lambda m,p:m.update(archive_sha256='not-a-hash'))
 attempt('archive_body_changed_same_manifest_sha','invalid',archive_change=lambda p:p.write_text('{"bars_by_symbol":{}}'))
 attempt('calculator_renamed','invalid',manifest_change=lambda m,p:m.update(calculator='unapproved.fake_calculator'))
 attempt('label_contract_changed_horizon_and_threshold','invalid',manifest_change=lambda m,p:m['label_contract'].update(horizon='one_calendar_month',binary_threshold=9.0))
 attempt('label_contract_null','invalid',manifest_change=lambda m,p:m.update(label_contract=None))
 attempt('record_internally_coherent_wrong_archive_and_flipped_label','invalid',record_change=lambda r:r.update(future_peak_mean=120.0,realized_max_multiple=1.2,is_surge=False,magnitude=None))
 attempt('record_ratio_disagrees_with_means_but_label_consistent','invalid',record_change=lambda r:r.update(realized_max_multiple=1.2,is_surge=False,magnitude=None))
 attempt('record_baseline_dates_after_prediction','invalid',record_change=lambda r:r.update(baseline_dates=['2025-02-03','2025-02-04','2025-02-05','2025-02-06','2025-02-07']))
 attempt('record_future_peak_before_prediction','invalid',record_change=lambda r:r.update(future_peak_dates=['2025-01-06','2025-01-07','2025-01-08','2025-01-09','2025-01-10']))
 attempt('record_horizon_wrong','invalid',record_change=lambda r:r.update(horizon_end='2025-01-16'))
 attempt('record_symbol_absent_from_archive','invalid',record_change=lambda r:r.update(symbol='NOT_IN_ARCHIVE'))
 attempt('is_surge_string_false_coerces_to_true','invalid',record_change=lambda r:r.update(is_surge='false'))
 attempt('numeric_strings_are_coerced','invalid',record_change=lambda r:r.update(baseline_mean='100',future_peak_mean='220',realized_max_multiple='2.2'))
 attempt('numeric_bool_is_coerced','invalid',record_change=lambda r:r.update(baseline_mean=True))
 attempt('manifest_bool_version_and_count','invalid',manifest_change=lambda m,p:m.update(store_version=True,record_count=True))
 attempt('extra_undeclared_record_field','invalid',record_change=lambda r:r.update(unrecognized_truth_authority='accepted'))
 attempt('magnitude_mismatch_existing_guard','negative_control',record_change=lambda r:r.update(magnitude='3-10x'))
 attempt('missing_symbol_existing_guard','negative_control',record_change=lambda r:r.pop('symbol'))
 attempt('duplicate_key_existing_guard','negative_control',extra_line=True)
 attempt('record_count_mismatch_existing_guard','negative_control',manifest_change=lambda m,p:m.update(record_count=2))
 attempt('unknown_case_key_existing_guard','negative_control',lookup_unknown=True)
expected_record=records[0].to_dict();out={'scope':'Only temporary synthetic legal store/archive, no s01 computation, production label read or blind input modification. All load results checked by actual ground_truth accessor.','calculator_expected':calculated,'positive_record':expected_record,'fixture_archive_sha256':hashlib.sha256(json.dumps(archive,sort_keys=True).encode()).hexdigest(),'fixture_archive':archive,'cases':cases,'false_admissions':[x['case'] for x in cases if not x['expected_behavior_met']],'positive_control_passed':cases[0]['expected_behavior_met'],'negative_controls_rejected':all(x['expected_behavior_met'] for x in cases if x['kind']=='negative_control'),'network_attempts':network['network_attempts'],'module_under_test':{'loader_sha256':hashlib.sha256(args.loader.read_bytes()).hexdigest(),'calculator_sha256':hashlib.sha256(args.calculator.read_bytes()).hexdigest()},'code_bindings':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [repo/'src/stock_opportunity_agent/cases/label_store.py',repo/'src/stock_opportunity_agent/cases/outcomes.py',repo/'spec/src/stock_opportunity_agent/cases/outcomes.md']}}
args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('fixture_archive','cases')},indent=2))
