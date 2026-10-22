"""Native reversible egress/cache roundtrip with one explicit offline response fixture."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'/Users/l/Project/Recommandation/scripts')
import run_mining_taxonomy_consumer_stage as stage
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange,LocalRoleRequestPending
BASE=Path('/Users/l/Project/Recommandation/runs/diagnostics/mining_taxonomy_consumer_20261023_v1')
root=BASE/'independent/identity-roundtrip-fixture';assert not root.exists();root.mkdir()
view=json.loads((BASE/'independent/identity-wire-capture/view-001.json').read_text())
canonical=view['structured_read_progress']['items'][0]['document_ref']
with stage.guards():
 client=stage.make_client(root,{'concept':'NetCashProvidedByUsedInOperatingActivities'},{'limits':stage.LIMITS})
 model=MiningAgentRoleModel(client,identity_aliases=('cik_0000800457:20250731','cik_0000800457'),max_output_tokens=2000)
 try:model.next_action(view)
 except LocalRoleRequestPending as exc:pending=exc.pending
 else:raise AssertionError('Expected one local offline pending fixture')
 inbox=json.loads(Path(pending['inbox_path']).read_text());wireview=json.loads(next(m['content'] for m in inbox['messages'] if m['role']=='user'))
 opaque=wireview['structured_read_progress']['items'][0]['document_ref']
 assert opaque!=canonical and '0000800457' not in json.dumps(inbox)
 raw={'action':'record_deferred','rationale':['Explicit offline inverse fixture source handle: '+opaque]}
 with Path(pending['outbox_path']).open('x') as f:f.write(json.dumps(raw))
 receipt=LocalRoleExchange(root/'exchange',max_calls=6).submit(pending['request_hash'],agent_id='explicit-offline-identity-roundtrip-fixture-not-a-model')
 result=model.next_action(view)
 assert canonical in result['rationale'][0] and opaque not in result['rationale'][0]
 again=model.next_action(view);assert again==result
 cached=list((root/'cache').rglob('*.json')) if (root/'cache').exists() else []
 report={'schema':'independent-native-identity-roundtrip-fixture-v1','scope':'One explicit locally written raw action fixture, no fresh model answer or external API. The module terminal action was never executed.','request_hash':pending['request_hash'],'wire_document_ref':opaque,'canonical_local_document_ref':canonical,'wire_has_raw_cik':False,'response_restore_matches_original':True,'cache_reexecution_equal':True,'offline_fixture_receipts':len(list((root/'exchange/receipts').glob('*.json'))),'offline_fixture_inboxes':len(list((root/'exchange/inbox').glob('*.json'))),'fresh_model_answers':0,'production_stage_inboxes_created':0,'domain_terminal_executed':False,'source_sha256':hashlib.sha256(Path(stage.__file__).read_bytes()).hexdigest(),'receipt':receipt,'wire_inbox_sha256':hashlib.sha256(Path(pending['inbox_path']).read_bytes()).hexdigest(),'qualification':'Native persisted request, exact local receipt/raw fixture and cached replay were exercised. This proves reversible source-handle restoration, not a fresh author result or all identity variants.'}
 p=BASE/'independent/identity-roundtrip-addendum.json'
 with p.open('x') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('canonical_local_document_ref','receipt')},indent=2))
