import json,hashlib,tempfile,shutil,itertools
from pathlib import Path
import run_reviewed_fast_prefix as h
from scripts.replay_incremental_reflection_memory import deny_network
repo=Path('/Users/l/Project/Recommandation');parent=repo/'runs/diagnostics/reviewed_fast_prefix_20261019_v1';answered='89a34b9d9ffe11a5c749e25787ddb84af249d4a66bf35d1dff0886ea4f92ee45';journal='8b5a557b060b93bc1dbd7e4fbfa791fd0986179adc81eb4b81591cb7022a17f9'
def hashes(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
def checkpoint(root):
 completion={'manifest_hash':'synthetic-checkpoint-fixture','result':{'status':'synthetic_completed_restore_fixture','independent_receipts':2},'immutable_artifacts':h._immutable_artifacts(root)};completion['completion_hash']=h.canonical_json_hash(completion);h.atomic_write_json(root/'completion.json',completion)
def reject(root,label,negatives):
 checkpoint(root)
 try:h._completed_restore(root,'synthetic-checkpoint-fixture',{'max_local_calls':32});raise AssertionError('unexpected admission:'+label)
 except h.ValidationError as e:negatives.append({'case':label,'typed_rejected':True,'error':str(e)})
negatives=[];original=hashes(parent)
with tempfile.TemporaryDirectory(prefix='independent-completed-journal-') as td,deny_network() as network:
 root=Path(td).resolve()/'fixture';root.mkdir()
 for name in ('requests','exchange','cache'):shutil.copytree(parent/name,root/name)
 # This is a restore-validation fixture, not an actual completed prefix or manufactured research trajectory.
 h.atomic_write_json(root/'prediction.json',{'synthetic_restore_fixture':True,'not_model_or_research_result':True});checkpoint(root)
 before=hashes(root);result=h._completed_restore(root,'synthetic-checkpoint-fixture',{'max_local_calls':32});assert result['restored_without_execution'] and hashes(root)==before
 a,u=h._request_inventory(root);assert len(a)==2 and len(u)==1 and u[0]['request_hash']==journal
 directories=[('exchange/inbox','json'),('exchange/outbox','txt'),('exchange/receipts','json'),('cache/responses','json')]
 # All nonempty incomplete shapes for a journal-only request must be rejected even under a rebuilt fixture hash map.
 for mask in range(1,15):
  made=[]
  for index,(directory,suffix) in enumerate(directories):
   if mask&(1<<index):
    p=root/directory/f'{journal}.{suffix}';p.write_bytes((root/directory/f'{answered}.{suffix}').read_bytes());made.append(p)
  reject(root,'undispatched_partial_shape_'+format(mask,'04b'),negatives)
  for p in made:p.unlink()
 # Missing one receipt from an answered request must not become journal-only.
 p=root/'exchange/receipts'/f'{answered}.json';raw=p.read_bytes();p.unlink();reject(root,'answered_missing_receipt',negatives);p.write_bytes(raw)
 # A four-part orphan with no request journal is also forbidden.
 made=[]
 for directory,suffix in directories:
  p=root/directory/('0'*64+'.'+suffix);p.write_bytes((root/directory/f'{answered}.{suffix}').read_bytes());made.append(p)
 reject(root,'orphan_full_response_without_journal',negatives)
 for p in made:p.unlink()
 # Receipt verification must read exact raw bytes, beyond mere complete inventory.
 p=root/'exchange/outbox'/f'{answered}.txt';raw=p.read_bytes();p.write_bytes(raw+b' ');reject(root,'raw_receipt_mismatch',negatives);p.write_bytes(raw)
 checkpoint(root);before=hashes(root);h._completed_restore(root,'synthetic-checkpoint-fixture',{'max_local_calls':32});assert hashes(root)==before
 assert hashes(parent)==original
 out={'scope':'Temporary completed-checkpoint restore mechanics only. Synthetic checkpoint/result/prediction record, exact historical responses copied for verifier input; not actual completed prefix/model behavior.','valid_answered_count':2,'valid_undispatched_journal_count':1,'legal_journal_restore_no_new_dispatch_or_file_bytes':True,'negative_cases':negatives,'partial_shapes_checked':14,'original_v1_all_file_bytes_unchanged':True,'new_model_answers':0,'network_attempts':network['network_attempts'],'code_bindings':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [repo/'scripts/run_reviewed_fast_prefix.py',repo/'spec/scripts/run_reviewed_fast_prefix.md']}}
 Path('/tmp/independent-prefix-completed-journal-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
