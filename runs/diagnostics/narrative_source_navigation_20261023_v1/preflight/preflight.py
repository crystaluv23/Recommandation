"""Inspect one qualified actual source session and stop before model dispatch."""
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import patch

from diagnose_executed_answer_scope import StageContract
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_core import EvolutionControlFlow
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange
from stock_opportunity_agent.research.signal_source_reading import SignalSourceSession
from stock_opportunity_agent.signal_library import SignalRegistry, SignalExecutor, LLMSignalBatchInput

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
REF = 'financing_listing_action:v5'


def read(path):
    return json.loads(Path(path).read_bytes())


def bound(path):
    p = Path(path).resolve()
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


class Captured(EvolutionControlFlow):
    """No cache receive, inbox, model answer or source acquisition is allowed."""


def stop(event):
    if event.get('event_type') == 'request_ready':
        raise Captured(event)


attempts = []
def forbidden(*args, **kwargs):
    attempts.append('forbidden')
    raise AssertionError('actual-source preflight is read-only and network-free')


if __name__ == '__main__':
    plan_path = REPO/'runs/diagnostics/measurement_input_selection_20261021_v1/plan.json'
    initial_path = REPO/'runs/diagnostics/gpre_native_initial_20261021_v1/stage/inputs.json'
    plan = read(plan_path)
    sample = read(initial_path)['sample']
    group = next(g for g in plan['groups'] if g['name'] == 'latest_v12')
    cutoff = datetime.fromisoformat(sample['prediction_time'])
    with ExitStack() as guards:
        for target, name in ((socket, 'create_connection'), (socket.socket, 'connect'),
                             (RawInfoStore, 'append'), (LabelStore, '__init__'), (LabelStore, 'load')):
            guards.enter_context(patch.object(target, name, side_effect=forbidden))
        store = open_raw_info_store(plan['reviewed_source_snapshot']['root'], reviewed_snapshot=plan['reviewed_source_snapshot'])
        registry = SignalRegistry(group['root']).snapshot_from_refs(group['version'], tuple(group['refs']))
        assert registry.registry_hash == group['registry_hash']
        spec = registry.load_spec(REF)
        executor = SignalExecutor(registry, store)
        resolution = executor.prepare_inputs((REF,), company_id=sample['company_id'],
            identity=sample['identity'], as_of=cutoff)[0]
        selected = executor.resolver.load_documents(resolution, as_of=cutoff)
        pool = executor.resolver.eligible_documents(resolution.request, company_id=sample['company_id'],
            identity=sample['identity'], as_of=cutoff)
        item = LLMSignalBatchInput(spec, selected, registry.skills[REF], pool)
        session = SignalSourceSession(item, cutoff)
        first = session.catalog()
        dimensions = [{'document_id': d.document_id, 'source_type': d.source_type,
            'raw_characters': len(d.content), 'normalized_characters': len(session.views[h][0]),
            'available_at': d.available_at.isoformat()}
            for h, d in session.sources.items()]
        captured = {}
        def capture(event):
            if event.get('event_type') == 'request_ready':
                captured.update(event)
                raise Captured()
        root = OUT/'wire-capture'
        client = StructuredRoleClient(registration=get_model('independent-subagent'),
            contract=StageContract({'limits':{'max_request_tokens':131072,'max_structured_corrections':1}}),
            workspace=root, ledger=ExternalAttemptLedger(root/'unused.json',max_attempts=1,max_total_cost=.01),
            local_role_exchange=LocalRoleExchange(root/'exchange',max_calls=4),
            allow_external=False,environ={},on_progress=capture)
        runner = StructuredLLMSignalRunner(client)
        runner.set_request_token_budget(131072)
        runner.set_identity_cases((SimpleNamespace(case_id='r01',company_id=sample['company_id'],basic_info=sample['identity']),))
        try:
            runner.execute_with_source_reading((item,),cutoff)
        except Captured:
            pass
        request = read(captured['request_path'])['request']
        wire = json.loads(request['messages'][-1]['content'])
        reservation = len(json.dumps(request['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+request['max_output_tokens']
        report = {'scope':'one exact current-v12 qualitative Signal; source/initial-wire preflight only',
            'registry_hash':registry.registry_hash,'source_view':len(store.documents),'eligible':len(pool),
            'selected':len(selected),'source_dimensions':dimensions, 'narrative_sections': [{'source_ref':c['source_ref'],'group_count':c.get('section_group_count'), 'visible':len(c.get('section_groups',())), 'next_cursor':c.get('next_group_cursor')} for c in wire['source_catalog']['cards']],
            'actual_initial_catalog_cards':len(wire['source_catalog']['cards']),
            'exact_initial_reservation':reservation,'request_cap':131072,
            'inboxes':len(list(root.rglob('inbox/*.json'))),
            'network_or_label_or_append_attempts':len(attempts),
            'bindings':[bound(plan_path),bound(initial_path),bound(__file__),bound(captured['request_path'])]}
        (OUT/'preflight-result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
