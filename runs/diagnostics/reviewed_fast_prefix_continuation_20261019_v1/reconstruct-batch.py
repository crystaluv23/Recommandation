"""Root-external temporary reconstruction; exact old answers, deny every new role."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import run_reviewed_fast_prefix as prefix

parent=Path('runs/diagnostics/reviewed_fast_prefix_20261019_v1').resolve()
with patch('socket.socket',side_effect=AssertionError('network forbidden')),TemporaryDirectory() as tmp:
    root=Path(tmp)/'continuation'
    prefix.prepare(root,Path('reports/reviewed-fast-prefix-expectations-20261019.json'),
        parent_root=parent,parent_commit='1acfd2a4f1cd41c5837206211a911c5f32abc662')
    denied=[]
    original=prefix.LocalRoleExchange.receive
    def deny_new(exchange,request,**kwargs):
        digest=prefix.canonical_json_hash(request)
        if not (exchange.root/'inbox'/f'{digest}.json').exists():
            denied.append({'stage':request['stage'],'request_hash':digest})
            raise prefix.EvolutionControlFlow('diagnostic deny new independent role')
        return original(exchange,request,**kwargs)
    with patch.object(prefix.LocalRoleExchange,'receive',new=deny_new):
        result=prefix.resume(root)
    value={'scope':'Post-failure native temporary reconstruction, historical exact reuse only; not original lost batch or formal v2',
        'result':result,'denied_new_dispatches':denied,'code_bindings':prefix._code_bindings(),'batches':{path.name:prefix.read_json(path) for path in (root/'observations').glob('signal_group*.json')},
        'parent_failure':prefix.binding(parent/'failure.json'),
        'parent_bytes_preserved':prefix._immutable_artifacts(parent)==prefix.read_json(root/'manifest.json')['continuation']['parent_files'],
        'new_inboxes':len(list((root/'exchange/inbox').glob('*.json')))-2,
        'new_receipts':len(list((root/'exchange/receipts').glob('*.json')))-2}
    print(json.dumps(value,ensure_ascii=False,indent=2))
