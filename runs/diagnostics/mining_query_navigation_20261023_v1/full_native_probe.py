"""Offline old-action reconstruction plus explicit hypothetical query/read probe.

Never advances the sealed stage or treats recorded replies as fresh model output.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import MethodType, SimpleNamespace
from unittest.mock import patch

import run_icfr_native_capability_stage as d
from stock_opportunity_agent.research.scheme_evolution import EvolutionControlFlow
from stock_opportunity_agent.research.stage_contracts import json_bytes

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
STAGE = ROOT / 'runs/diagnostics/icfr_native_capability_20261023_v1/stage-v3'


def read(path):
    """Read retained source/fixture data; no remote acquisition."""
    return json.loads(Path(path).read_text())


def sha(path):
    """Bind exact retained bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sealed_files():
    """Verify that every old stage file remains untouched."""
    return {str(p.relative_to(STAGE)): sha(p) for p in sorted(STAGE.rglob('*')) if p.is_file()}


class PrefixStopped(EvolutionControlFlow):
    """Stop before any eleventh response or external/cache execution."""


class InputCaptured(EvolutionControlFlow):
    """Stop at request_ready, before a new exchange inbox exists."""


def main():
    """Probe the real factory and tools only in an isolated temporary copy."""
    before = sealed_files(); manifest = read(STAGE / 'manifest.json')
    completion = read(STAGE / 'completion.json')
    assert all(before[key] == value for key, value in completion['files'].items())
    sources = [row for row in manifest['source_bindings'] if 'document_id' in row]
    assert len(sources) == 263 and all(sha(row['path']) == row['sha256'] for row in sources)
    source_bindings = deepcopy(sources)
    records = sorted((read(p) for p in (STAGE / 'exchange/receipts').glob('*.json')),
                     key=lambda row: int(row['agent_id'].rsplit('h', 1)[1]))
    assert len(records) == 10
    answers = [read(STAGE / 'exchange/outbox' / (row['request_hash'] + '.txt')) for row in records]
    original_observation = max((read(p) for p in (STAGE / 'seeds/hypothesis/observations').glob('*.json')),
                               key=lambda row: len(row['ledger']['entries']))
    assert len(original_observation['ledger']['entries']) == 10

    class ReplayCaller(d.Caller):
        def __init__(self, **kwargs):
            super().__init__(**kwargs); self.index = 0; self.budget = SimpleNamespace(scope='mining')
        def _complete_json_request(self, **kwargs):
            if self.index == 10:
                raise PrefixStopped()
            answer = deepcopy(answers[self.index]); self.index += 1
            return answer, d.AgentUsage(llm_calls=1, tokens=0, cost=0), None

    class ProbeEngine(d.SignalEvolutionEngine):
        def _new_mining_controller(self, **kwargs):
            kwargs['model'].request_limits.update(total_limit=12 * d.MIB, call_limit=80)
            self.controller = super()._new_mining_controller(**kwargs)
            return self.controller

    captures = []
    def observe(event):
        if event.get('event_type') == 'request_ready':
            request = read(event['request_path'])['request']
            captures.append(request)
            raise InputCaptured()

    with TemporaryDirectory() as temporary, d.guards(), patch.object(d.LocalRoleExchange, 'receive', side_effect=AssertionError('receive forbidden')):
        temp = Path(temporary); work = temp / 'workspace'; shutil.copytree(STAGE / 'workspace', work)
        dev_data = read(STAGE / 'inputs/dev.json')
        identities = tuple(SimpleNamespace(**{**row, 'prediction_time': datetime.fromisoformat(row['prediction_time'])})
                           for row in read(STAGE / 'inputs/identities.json')['identities'])
        by_id = {case.case_id: case for case in identities}
        dev = tuple(SimpleNamespace(**{**vars(by_id[row['case_id']]),
                    'ground_truth': SimpleNamespace(is_surge=dev_data['groups'][row['case_ref']] == 'positive')})
                    for row in dev_data['cases'])
        store = d.RawInfoStore(documents=[d.RawInfoDocument.from_dict(read(row['path'])) for row in sources])
        registry = d.SignalRegistry(work / 'signals', candidate_root=work / 'signals_candidates')
        history = read(work / 'slow_history/manifest.json')['manifest']
        meta = d.PlanMetaMemory(entries=d._rebased_history_meta_entries(d.RoundMetaEntry.from_dict(row)
                    for row in history['fast_context']['meta_entries']))
        common = dict(registration=d.get_model('independent-subagent'), contract=d.StageContract(read(STAGE / 'contract.json')),
                      ledger=d.ExternalAttemptLedger(temp / 'unused.json', max_attempts=1, max_total_cost=.01),
                      allow_external=False, environ={})
        replay = ReplayCaller(workspace=temp / 'old-actions-only', **common)
        engine = ProbeEngine(registry=registry, raw_info_store=store, discovery_cases=dev, identity_cases=identities,
            workspace=d.EvolutionWorkspace(work), meta_memory=meta, mining_model=d.LLMSignalMiningModel(replay),
            update_model=d.LLMSignalUpdateModel(replay), llm_signal_runner=d.StructuredLLMSignalRunner(replay))
        engine.mining_model.set_request_token_budget(262144)
        engine._active_slow_input = read(STAGE / 'inputs/slow_input.json')
        engine._active_slow_memory = read(STAGE / 'inputs/slow_memory.json')
        engine._active_sampling_manifest = engine._active_slow_input['sampling_manifest']
        engine._mining_memory_index = engine._controller_memory_index()
        baseline = read(STAGE / 'inputs/baseline.json'); factory = read(STAGE / 'inputs/factory.json')
        context = {'stable_signal_cards': [{'signal_ref': s['signal_id'] + ':v' + str(s['version']),
                    'description': s['definition']['description']} for s in baseline['specs']],
                   'capability_backlog': {'signal_need_items': factory['backlog_needs']},
                   'prior_modality_footprints': factory['prior_modality_footprints'], 'meta_info': factory['meta_memory_briefs'],
                   'slow_method_memory': factory['slow_method_memory'], 'meta_memory_disclosures': factory['meta_memory_disclosures']}
        engine._mining_context = MethodType(lambda self, **kwargs: deepcopy(context), engine)
        try:
            engine._run_controller_mining_axis(cycle_id=1, axis_id='surge_direction', research_axis=factory['research_axis'],
                dev_cases=dev, check_cases=(), labels_by_case_id={row['case_id']: dev_data['groups'][row['case_ref']] for row in dev_data['cases']})
        except PrefixStopped:
            pass
        else:
            raise AssertionError('did not stop before any new response')
        controller = engine.controller
        assert replay.index == 10
        assert controller.ledger.to_dict() == original_observation['ledger']
        live_evidence = controller.materialization_evidence()
        # Persisted JSON uses arrays for dataclass tuple operands. Compare its
        # canonical JSON bytes (still distinguishes bool/int/float and order),
        # rather than Python tuple-vs-list container identity.
        evidence_json = json.loads(json.dumps(live_evidence, ensure_ascii=False))
        assert evidence_json == original_observation['evidence']
        assert d.digest(live_evidence) == d.digest(original_observation['evidence'])
        assert controller._last_action_result == original_observation['last_action_result']
        # This is a deterministic hypothetical tool probe, not an authored next
        # answer, and is never submitted to the original exchange or a new stage.
        query = {'action': 'fetch_evidence', 'case_refs': ['case-005'], 'source_families': ['filing'],
                 'max_documents': 3, 'query': 'internal control financial reporting material weakness',
                 'rationale': ['Offline fixture: locate the existing query selection without new source reads.']}
        old_heavy, old_browse = controller._heavy_used, controller._browse_used
        old_reads = controller._narrative_reads; old_evidence = deepcopy(controller.materialization_evidence())
        controller._validate_action_shape(query); controller._execute('fetch_evidence', query)
        assert controller._heavy_used == old_heavy + 1 and controller._browse_used == old_browse
        assert controller._narrative_reads == old_reads
        assert controller.materialization_evidence() == old_evidence
        page = controller._model_view()['query_navigation']
        assert page['items'] and all(row['source_snapshot_matches'] for row in page['items'])
        selected = next(row for row in page['items'] if row['origin_status'] == 'located')
        for row in page['items']:
            if row['origin_status'] == 'located':
                source = controller._document_by_ref(row['document_ref'])
                assert hashlib.sha256(source.content[row['raw_start']:row['raw_end']].encode()).hexdigest() == row['raw_span_sha256']
        caller = d.Caller(workspace=temp / 'capture', local_role_exchange=d.LocalRoleExchange(temp / 'exchange', max_calls=1),
                          on_progress=observe, **common)
        caller.budget = SimpleNamespace(scope='mining')
        controller.model.caller = caller
        # Preserve original paid/logical consumption in the prospective capture.
        controller.model.reserved_tokens = 2055941; controller.model.reserved_calls = 10
        for phase in ('after_hypothetical_query', 'after_hypothetical_read'):
            if phase.endswith('_read'):
                action = {'action': 'read_span', 'document_ref': selected['document_ref'], 'offset': selected['raw_start'],
                          'length': selected['read_length'], 'rationale': ['Offline fixture: consume only disclosed exact coordinates.']}
                controller._validate_action_shape(action); controller._execute('read_span', action)
                assert controller._browse_used == old_browse + 1 and controller._narrative_reads == old_reads + 1
            try:
                controller.model.next_action(controller._model_view())
            except InputCaptured:
                pass
            else:
                raise AssertionError('expected capture before exchange preparation')
            request = captures[-1]; payload = json.loads(request['messages'][1]['content'])
            required = json_bytes(request['messages']) + request['max_output_tokens']
            assert required <= 262144 and int(payload['request_budget']['this_request']) == required
            assert payload['request_budget']['calls_used'] == 10 and payload['request_budget']['used'] == 2055941
            (OUT / (phase + '-request.json')).write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
        assert controller.model.reserved_tokens == 2055941 and controller.model.reserved_calls == 10
        assert not list((temp / 'exchange/inbox').glob('*.json')) and not list((temp / 'exchange/receipts').glob('*.json'))
        result = {'proof_scope': 'offline old-action reconstruction plus explicit hypothetical query/read; not fresh behavior or stage continuation',
            'old_prefix_ledger_evidence_exact': True, 'original_saved_answers_replayed': 10, 'fresh_answers': 0,
            'full_sources': len(sources), 'baseline_versions': len(baseline['refs']), 'backlog_needs': len(factory['backlog_needs']),
            'known_facts': len(controller._facts), 'known_relations': len(controller._relations),
            'navigation_available': page['counts']['available'], 'navigation_shown': len(page['items']),
            'costs': [json_bytes(request['messages']) + request['max_output_tokens'] for request in captures],
            'single_limit': 262144, 'original_spent_preserved': [10, 2055941], 'new_inboxes': 0, 'new_receipts': 0,
            'api_network_labels_business_calls': 0, 'hypothetical_tool_charges': {'heavy': 1, 'browse': 1},
            'query_navigation': page, 'read_result': controller._last_action_result,
            'tested_files': [{'path': row['path'], 'sha256': sha(row['path'])} for row in manifest['code']]}
    assert sealed_files() == before and all(sha(row['path']) == row['sha256'] for row in source_bindings)
    result.update(sealed_files_unchanged=len(before), sealed_hash_table_matches=len(completion['files']), source_bindings_unchanged=263)
    (OUT / 'full-native-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ('tested_files', 'query_navigation', 'read_result')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
