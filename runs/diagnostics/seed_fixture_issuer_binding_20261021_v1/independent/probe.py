"""Independent synthetic catalog fixture migration checks; only temporary Registry writes."""
from pathlib import Path
from copy import deepcopy
from contextlib import ExitStack
from unittest.mock import patch
import tempfile,json,hashlib,subprocess,socket
from stock_opportunity_agent.signal_library import SignalRegistry
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.cases.label_store import LabelStore
from evolve_information_schemes import validate_catalog
R=Path('/Users/l/Project/Recommandation');O=R/'runs/diagnostics/seed_fixture_issuer_binding_20261021_v1/independent';CAT=R/'configs/signals_v1.json'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
bind=lambda p:{'path':str(Path(p).resolve()),'sha256':sha(p)}
current=json.loads(CAT.read_text());oldbytes=subprocess.check_output(['git','show','HEAD:configs/signals_v1.json']);old=json.loads(oldbytes)
original_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
(O/'original-catalog.json').write_bytes(oldbytes)
changed=[];stripped=deepcopy(current)
for prior,new,item in zip(old['signals'],current['signals'],stripped['signals'],strict=True):
 if digest(prior)==digest(new):continue
 changed.append(new['spec']['signal_id'])
 assert len(prior['tests'])==len(new['tests'])==1
 before=prior['tests'][0]['documents'][0];after=new['tests'][0]['documents'][0]
 a=json.loads(before['content']);z=json.loads(after['content'])
 assert 'cik' not in a and z.pop('cik')=='0000000001' and digest(a)==digest(z)
 assert after['metadata']=={'cik':'0000000001'} and 'metadata' not in before
 row=item['tests'][0]['documents'][0];row.pop('metadata');row['content']=before['content']
assert len(changed)==6 and digest(stripped)==digest(old)
sourcepaths=[CAT,R/'src/stock_opportunity_agent/signal_library.py',R/'src/stock_opportunity_agent/data/sec_company_facts.py',R/'src/stock_opportunity_agent/data/raw_info.py',R/'scripts/evolve_information_schemes.py',R/'spec/src/stock_opportunity_agent/signal_library.md',R/'spec/src/stock_opportunity_agent/data/sec_company_facts.md']
beforebindings=[bind(p) for p in sourcepaths]
forbidden=[]
def block(*args,**kwargs):forbidden.append('forbidden');raise AssertionError('No network/model/labels in fixture audit')
def tree(path):return {str(p.relative_to(path)):sha(p) for p in path.rglob('*') if p.is_file()}
controls=[]
with ExitStack() as guards, tempfile.TemporaryDirectory(prefix='independent-seed-issuer-') as tmp:
 guards.enter_context(patch('socket.socket',block));guards.enter_context(patch('socket.create_connection',block))
 for method in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores'):guards.enter_context(patch.object(StructuredRoleClient,method,block))
 for method in ('load','record','ground_truth','keys','label_contract'):guards.enter_context(patch.object(LabelStore,method,block))
 tmp=Path(tmp);fresh=SignalRegistry(tmp/'fresh/signals');installed=fresh.install_catalog(CAT);audit=fresh.audit_capabilities();assert audit.passed
 snapshot=fresh.freeze();assert installed==len(snapshot.specs)==14
 check=validate_catalog(CAT);assert check['valid'] is True and check['signal_count']==check['installed']==14
 controls.append({'case':'fresh_native_install_audit_freeze_validate_catalog','installed':installed,'audit_passed':audit.passed,'snapshot_ref_count':len(snapshot.specs),'validate_catalog':check})
 # Replaying the corrected template must not migrate any previously published file.
 legacy_catalog=tmp/'old-catalog.json';legacy_catalog.write_bytes(oldbytes)
 legacy=SignalRegistry(tmp/'legacy/signals');assert legacy.install_catalog(legacy_catalog)==14
 prior_audit=legacy.audit_capabilities();assert not prior_audit.passed
 legacybefore=tree(tmp/'legacy');assert legacy.install_catalog(CAT)==0;assert tree(tmp/'legacy')==legacybefore
 assert legacy.audit_capabilities().to_dict()==prior_audit.to_dict()
 controls.append({'case':'published_legacy_not_migrated','install_new_template_count':0,'published_tree_sha_equal':True,'still_fails_legacy_identity_audit':True,'disabled_refs':sorted(prior_audit.disabled_refs) if hasattr(prior_audit,'disabled_refs') else prior_audit.to_dict()})
 for name in ('missing_body_cik','missing_metadata_cik','mismatched_metadata_cik'):
  variant=deepcopy(current);item=variant['signals'][0];raw=item['tests'][0]['documents'][0];payload=json.loads(raw['content'])
  if name=='missing_body_cik':payload.pop('cik')
  elif name=='missing_metadata_cik':raw.pop('metadata')
  else:raw['metadata']['cik']='0000000002'
  raw['content']=json.dumps(payload,separators=(',',':'))
  path=tmp/(name+'.json');path.write_text(json.dumps(variant))
  registry=SignalRegistry(tmp/name/'signals');assert registry.install_catalog(path)==14
  audit=registry.audit_capabilities();assert not audit.passed
  errors={}
  for operation,call in [('freeze',registry.freeze),('validate_catalog',lambda:validate_catalog(path))]:
   try:call()
   except Exception as e:errors[operation]={'type':type(e).__name__,'message':str(e)}
   else:raise AssertionError(name+' unexpectedly passed '+operation)
  controls.append({'case':name,'native_audit_passed':False,'errors':errors})
assert not forbidden and beforebindings==[bind(p) for p in sourcepaths]
out={'verdict':'PASS_future_fixture_identity_only_no_published_migration','code_and_inputs':beforebindings,'original_catalog_commit':original_commit,'original_catalog_sha256':hashlib.sha256(oldbytes).hexdigest(),'changed_fixture_ids':changed,'entire_catalog_equal_after_removing_only_body_and_metadata_CIK':True,'values_tags_units_periods_expected_and_specs_unchanged':True,'controls':controls,'forbidden_calls':forbidden,'limits':['Synthetic CIK0000000001 is fixture identity only, not a real-source qualification. All Registry and fixture execution writes were in temporary directories.','Native install_catalog publishes and freezes future valid fixtures only; an existing invalid published version remains unchanged and invalid. Fixing that history requires an explicit successor.','Capability audit/fixture arithmetic here does not prove fresh model behavior, Mining usefulness, research benefit, full F5 or MVP. No production source/Registry/old stage was modified or reentered.']}
(O/'results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='controls'},indent=2));print('CONTROLS',[(x['case'],x.get('native_audit_passed',x.get('audit_passed'))) for x in controls])
