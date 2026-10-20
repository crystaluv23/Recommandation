"""Read only the authorized historical allowlist; pure native constructor probe."""
from datetime import datetime
import hashlib,json
from pathlib import Path
import run_reviewed_owned_partial_stage as s
from stock_opportunity_agent.research.evolution_core import _basic_info_projection_cards
HERE=Path(__file__).resolve().parent
seed=s.SEED
inputs=s.read(seed/'inputs.json');sample=inputs['sample']
preflight=s.read(seed/'preflight.json');bootstrap=preflight['model_context']
old_basic=s.read(seed/'prediction.json')['final_context']['basic_info']
prior=s.ResearchState.from_dict(s.read(seed/'observations/initialize_00.json')['value'])
selection=s.read(seed/'observations/routing_00.json')['value']
by_ref={r['signal_id']+':v'+str(r['version']):r for name in ('signal_group_00.json','signal_group_01.json') for r in s.read(seed/'observations'/name)['results']}
round_row=s.SignalRound.from_dict({'information_needs':list(prior.next_information_needs),'selections':selection,
 'batch':{'results':[by_ref[r['signal_ref']] for r in selection],'signal_calls':2}})
new=s._assemble_final_context(plan=s.InformationPlan.from_dict(sample['plan']),company_id=sample['company_id'],
 additional_identity_aliases=tuple(sample['identity']['identity_aliases']),basic_info=bootstrap,state=prior,rounds=(round_row,),
 prediction_time=datetime.fromisoformat(sample['prediction_time']))['basic_info']
assert len(old_basic['projection_cards'])==17
assert _basic_info_projection_cards(old_basic)[0]==[]
assert len(new['projection_cards'])==17
assert new==old_basic,[(k,new.get(k)==old_basic.get(k)) for k in set(new)|set(old_basic)]
assert '[ANON_ID_' not in json.dumps(bootstrap) and '[MASKED_COMPANY]' not in json.dumps(bootstrap)
# Exact final-seed extraction now names the canonical, already-frozen source, not anonymous request payload.
source=Path(s.__file__).read_text()
assert "read(SEED/'preflight.json')['model_context']" in source
records=[]
for p in (Path(s.__file__),s.SPEC,Path('tests/test_reviewed_owned_partial_stage.py'),seed/'preflight.json'):
 records.append({'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
out={'scope':'Pure native final constructor; no production prepare/GET/Store/labels/model. Historical prediction envelope source-owner read only for BasicInfo reference.',
 'bindings':records,'old_final_reassembled_cards':0,'canonical_initial_projection_count':17,'new_final_projection_count':17,
 'full_basic_info_equal_old_final':True,'projection_id_text_available_request_id_order_equal':True,
 'source_index_counts_flags_omission_markers_equal':True,'canonical_bootstrap_without_anonymous_wire_tokens':True}
(HERE/'basic-info-final-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
