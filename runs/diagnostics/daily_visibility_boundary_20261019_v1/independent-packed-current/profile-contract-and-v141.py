import json,hashlib,copy
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent.research.basic_info_visibility import pack_critic_visibility
import stock_opportunity_agent.research.evolution_plan_roles as roles
from scripts.replay_incremental_reflection_memory import HistoricalSources,deny_network,_reflection_consumer_sizes
base={'request_id':'same','source_types':['market'],'status':'resolved','source_context_truncated':None,'projection_context_truncated':False,'effective_context_truncated':None,'omitted_context_markers':['one','two'],'available_projection_count':3,'visible_projection_count':2,'omitted_projection_count':1,'projection_ids':['p2','p1','p1']}
variants=[base,{**base,'projection_ids':['q','q','r']},{**base,'omitted_context_markers':['two','one']},{**base,'omitted_context_markers':['one','two','two']},{**base,'source_context_truncated':False},{**base,'request_id':'different'},{k:v for k,v in base.items() if k!='source_context_truncated'},{k:v for k,v in base.items() if k!='projection_ids'},{**base,'projection_ids':[]},{**base,'extra':{'nullable':None,'false':False,'nested':['x','x']}}]
original=[{'case_index':1,'basic_info_source_index':variants[:5]},{'case_index':2,'basic_info_source_index':variants[5:]}]
before=copy.deepcopy(original)
def expand(packed,profiles):
 out=copy.deepcopy(packed)
 for t in out:
  t['basic_info_source_index']=[{**profiles[r['profile_ref']],**({'projection_ids':copy.deepcopy(r['projection_ids'])} if 'projection_ids' in r else {})} for r in t['basic_info_source_index']]
 return out
packed,profiles=pack_critic_visibility(original)
assert expand(packed,profiles)==original
assert original==before
refs=[r['profile_ref'] for t in packed for r in t['basic_info_source_index']]
assert refs[0]==refs[1]==refs[7]==refs[8]
assert len(set(refs))==7,(refs,profiles)
assert packed[0]['basic_info_source_index'][0]['projection_ids']==['p2','p1','p1']
# Actual native historical consumers, independently decode every packed trajectory.
calls=[]
def verified_pack(trajectories):
 previous=copy.deepcopy(trajectories)
 p,pr=pack_critic_visibility(trajectories)
 assert trajectories==previous and expand(p,pr)==previous
 calls.append({'cases':len(p),'rows':sum(len(t['basic_info_source_index']) for t in p),'profiles':len(pr),'exact_reconstruction':True})
 return p,pr
sources=HistoricalSources()
with deny_network() as network,patch.object(roles,'pack_critic_visibility',verified_pack):
 sizes=_reflection_consumer_sizes(sources)
bindings=sources.verify()
for value in sizes.values():
 assert value['initial_payload_utf8_bytes']<=128000
 assert value['after_disclosure_payload_utf8_bytes']<=176000
repo=Path('/Users/l/Project/Recommandation')
out={'scope':'Ephemeral serialization/native transport sizing only; deterministic scripted disclosure answers; no external model/HTTP or research behavior claim.','variant_rows':len(variants),'distinct_profiles':len(profiles),'variant_refs':refs,'exact_projection_order_duplicates_absence_preserved':True,'input_unchanged':True,'historical_critic_reconstruction':calls,'historical_sizes':sizes,'source_hashes':bindings,'network_attempts':network['network_attempts'],'external_model_calls':0,'code_bindings':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [repo/'src/stock_opportunity_agent/research/basic_info_visibility.py',repo/'src/stock_opportunity_agent/research/evolution_plan_roles.py',repo/'scripts/replay_incremental_reflection_memory.py']}}
Path('/tmp/independent-packed-contract.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('source_hashes','historical_sizes')},indent=2))
print({k:(v['initial_payload_utf8_bytes'],v['after_disclosure_payload_utf8_bytes']) for k,v in sizes.items()})
