"""Temporary exact-cache replay catches original budget errors; zero new dispatch."""
from pathlib import Path
import json, shutil, tempfile
from unittest.mock import patch
import run_reviewed_fast_prefix as prefix
from stock_opportunity_agent.research.evolution_core import RuntimeBudgetExceeded
source=Path('runs/diagnostics/reviewed_fast_prefix_20261019_v2').resolve()
before=prefix._immutable_artifacts(source)
with tempfile.TemporaryDirectory() as tmp,patch('socket.socket',side_effect=AssertionError('network forbidden')):
    root=Path(tmp)/'reconstruction'
    shutil.copytree(source,root)
    for name in ['completion.json','progress.json','execution_summary.json']:
        (root/name).unlink(missing_ok=True)
    blocked=[]
    original=prefix.StructuredRoleClient.complete_json
    original_receive=prefix.LocalRoleExchange.receive
    def receive(exchange,request,**kwargs):
        digest=prefix.canonical_json_hash(request)
        if not (exchange.root/'inbox'/f'{digest}.json').exists():
            raise AssertionError('new dispatch forbidden in diagnostic replay')
        return original_receive(exchange,request,**kwargs)
    def complete(client,**kwargs):
        try:
            return original(client,**kwargs)
        except RuntimeBudgetExceeded as exc:
            digest=client.request_hash_trace[-1]
            record=prefix.read_json(root/'requests'/f'{digest}.json')['request']
            required=len(json.dumps(record['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))+record['max_output_tokens']
            blocked.append({'stage':kwargs['stage'],'request_hash':digest,'required_reservation':required,
                'remaining_request_budget':kwargs.get('max_request_tokens'),'error_type':type(exc).__name__,
                'error':str(exc),'inbox_exists':(root/'exchange/inbox'/f'{digest}.json').exists()})
            raise
    with patch.object(prefix.StructuredRoleClient,'complete_json',new=complete),patch.object(prefix.LocalRoleExchange,'receive',new=receive):
        result=prefix.resume(root)
    output={'scope':'One root-external temporary historical-cache native replay, not formal completed re-execution or fresh model behavior',
        'blocked_requests':blocked,'result_status':result['status'],'new_inboxes':len(list((root/'exchange/inbox').glob('*.json')))-3,
        'new_receipts':len(list((root/'exchange/receipts').glob('*.json')))-3,
        'formal_immutable_unchanged':prefix._immutable_artifacts(source)==before,
        'ground_truth_reads':0,'readonly_data_requests':0,'external_llm_calls':0,'new_role_answers':0}
    print(json.dumps(output,ensure_ascii=False,indent=2))
