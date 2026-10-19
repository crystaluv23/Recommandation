import sys,json,tempfile,socket,argparse,importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
sys.path[:0]=['/Users/l/Project/Recommandation/src','/Users/l/Project/Recommandation/tests']
from test_reviewed_market_profile import REVIEW,rebound_proof,save_review
parser=argparse.ArgumentParser(description='Rehashed market proof counterexamples; no network or role calls.')
parser.add_argument('--reader',type=Path,default=Path(__file__).with_name('original_reader_source.py.txt'))
parser.add_argument('--output',type=Path,default=None)
args=parser.parse_args()
loader=SourceFileLoader('market_reader_under_audit',str(args.reader.resolve()))
spec=importlib.util.spec_from_loader(loader.name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module)
materialize_reviewed_snapshot=module.materialize_reviewed_snapshot
ReviewedSourceRejected=module.ReviewedSourceRejected
open_raw_info_store=module.open_raw_info_store
socket.socket=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden'))
results=[]
def run(name, kind=None, body_change=lambda _x:None, request_change=lambda _x:None, change=lambda _r:None):
 with tempfile.TemporaryDirectory(prefix='market-proof-audit-') as directory:
  base=Path(directory);review=json.loads(REVIEW.read_text());change(review)
  if kind:rebound_proof(base,review,kind,body_change,request_change)
  try:
   binding=materialize_reviewed_snapshot(save_review(base,review),base/'view');store=open_raw_info_store(binding['root'],reviewed_snapshot=binding);outcome='admitted';detail=len(store.documents)
  except ReviewedSourceRejected as exc:outcome='rejected';detail=str(exc)
  results.append(dict(name=name,outcome=outcome,detail=detail));print(json.dumps(results[-1]),flush=True)
run('original_positive')
run('without_optional_235_overlap',change=lambda r:r['records'][-1].update(proofs=[p for p in r['records'][-1]['proofs'] if p['kind']!='massive_unadjusted_overlap']))
for kind in ('massive_daily_origin','massive_historical_issuer','massive_no_post_cutoff_splits'):
 for value in (0,False,[],{}):
  def mutate(b,value=value,kind=kind):
   (b['body'] if kind=='massive_daily_origin' else b)['next_url']=value
  run(kind+'_next_url_'+repr(value),kind,mutate)
for field,val in [('t',True),('t',0),('t',1750000000000.0),('c',True),('v',True),('c',float('nan')),('c',float('inf'))]:
 run('origin_'+field+'_'+repr(val),'massive_daily_origin',lambda b,field=field,val=val:b['body']['results'][0].update({field:val}))
for val in (None,{},False):run('split_results_'+repr(val),'massive_no_post_cutoff_splits',lambda b,val=val:b.update(results=val))
run('split_get_before_old_fetch','massive_no_post_cutoff_splits',request_change=lambda r:r.update(retrieved_at='2026-08-16T07:28:08.040000+00:00'))
run('split_get_equivalent_offset','massive_no_post_cutoff_splits',request_change=lambda r:r.update(retrieved_at='2026-10-19T17:24:32.570826+08:00'))
run('normalization_clock_equivalent_offset',change=lambda r:next(p for p in r['records'][-1]['proofs'] if p['kind']=='massive_daily_origin').update(normalization_retrieved_at='2026-08-16T15:28:08.042545+08:00',provider_retrieved_at='2026-08-16T15:28:08.034427+08:00'))
if args.output is not None:
 if args.output.exists(): raise SystemExit('result exists; refuse overwrite')
 args.output.write_text(json.dumps(results,indent=2)+'\n')
