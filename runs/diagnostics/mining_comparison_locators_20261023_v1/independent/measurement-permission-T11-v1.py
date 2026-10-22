"""T11 independent mismatch/unknown boundaries; no new author or source acquisition."""
import json, hashlib
from pathlib import Path
from dataclasses import replace
from tests.test_mining_controller import _fixture_store, _controller
from tests.test_mining_taxonomy import MiningTaxonomyTests
from stock_opportunity_agent.research.mining_agent_tools import EvidenceFact, build_same_concept_relations
BASE=Path(__file__).parent;ROOT=Path('/Users/l/Project/Recommandation')
paths=['src/stock_opportunity_agent/research/mining_controller.py','src/stock_opportunity_agent/research/mining_role_model.py','src/stock_opportunity_agent/research/mining_agent_tools.py','runs/diagnostics/mining_fact_semantics_repair_20261021_v1/root/namespace-before.json']
hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
saved, projected=MiningTaxonomyTests().original(); out=[]
for kind,original in [('known_mismatch',projected),('unknown_legacy',tuple(EvidenceFact(**r) for r in saved['facts']))]:
 cases,store=_fixture_store();c=_controller(store,cases,object(),seed='discovery',heavy_action_limit=30)
 c._state='evidence_ready'
 facts=tuple(replace(f,case_ref='case-001') for f in original)
 c._facts={f.fact_ref:f for f in facts}
 c._execute_compare({'action':'compare_groups','concepts':['Metric'],'rationale':['Synthetic namespace qualification.']})
 view=c._model_view(); unit=view['comparison_progress']['items'][0]
 assert unit['concept']=='Metric'
 assert unit['groups']['control']['latest']=={}
 assert unit['groups']['control']['comparable_prior']=={}
 assert 'case-001' in unit['groups']['control']['unresolved_basis_cases']
 assert build_same_concept_relations(facts)==()
 before=c._comparison_snapshot
 # Explicit operand selection is a separate generic arithmetic control, not automatic comparability.
 c._execute_compute({'action':'compute_statistic','rule':'latest_over_comparable_prior','fact_refs':[f.fact_ref for f in facts],'rationale':['Explicit generic arithmetic fixture; no measurement equivalence asserted.']})
 assert c._last_action_result['value']=='1.200000'
 assert c._model_view()['comparison_progress']['snapshot_status']=='current'
 assert c._comparison_snapshot==before
 assert c._model_view()['comparison_progress']['items'][0]==unit
 out.append({'kind':kind,'taxonomies':[f.taxonomy for f in facts],'no_automatic_latest_or_pair':True,'unresolved_basis':unit['groups']['control']['unresolved_basis_cases'],'explicit_ratio':'1.200000','comparison_snapshot_preserved_after_compute':True})
report={'scope':'Independent deterministic namespace control, not mandatory fresh-author arithmetic or a new accepted measurement.','source_hashes':hashes,'checks':out,'all_pass':len(out)==2,'new_tools':False,'new_measurement_permissions':False,'fresh_model_calls':0}
with (BASE/'measurement-permission-T11-v1.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'all_pass':report['all_pass'],'checks':out},indent=2))
