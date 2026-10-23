"""Independent read-only review: temporary synthetic transport and real sealed prefix."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_icfr_native_capability_stage as s
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.data.raw_info import RawInfoStore

OUT = Path(__file__).resolve().parent
observed = []


def rejects(label, operation, expected=s.StageBudgetStop):
    try:
        operation()
    except expected as error:
        observed.append({'case': label, 'result': 'rejected', 'reason': str(error)})
    else:
        raise AssertionError(label + ' unexpectedly accepted')


def run():
    controls, _ = s._stopped_predecessors()
    prefix = controls[-1]['resource_prefix']
    assert s._terminal_resource_prefix(prefix) == prefix['answered_records']
    assert prefix['answered_usage'] == [10, 2055941]
    observed.append({'case': 'actual-three-old-controls', 'result': 'verified',
                     'usage': [[c['answered_unique_requests'], c['logical_reservations']] for c in controls]})
    for root in (s.STOPPED_STAGE_ROOT, s.STOPPED_STAGE_V2_ROOT, s.SEALED_STAGE_V3_ROOT):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'alias'
            link.symlink_to(root, target_is_directory=True)
            rejects('resolved-old-root-' + root.name, lambda: s._root(link), s.ValidationError)
    for key, value in (('answered_usage', [True, 2055941]), ('answered_usage', [-1, 2055941]),
                       ('answered_usage', [10, 0]), ('answered_records', {})):
        broken = deepcopy(prefix)
        broken[key] = value
        rejects('historical-prefix-' + key + '-' + str(value)[:20],
                lambda broken=broken: s._terminal_resource_prefix(broken), s.ValidationError)
    old_hash = next(iter(prefix['answered_records']))
    broken = deepcopy(prefix)
    broken['answered_records'][old_hash]['scopes'] = ['candidate:other']
    rejects('historical-scope-reassignment', lambda: s._terminal_resource_prefix(broken), s.ValidationError)
    original_files = s._files(s.SEALED_STAGE_V3_ROOT)
    for directory in ('oracle', 'oracle-v2', 'oracle-v3'):
        path = s.BASE / directory / 'acceptance-obligations.json'
        assert path.read_bytes() == subprocess.check_output(['git', 'show', 'HEAD:' + str(path.relative_to(s.REPO))])
    observed.append({'case': 'original-oracles-committed-equality', 'result': 'verified'})

    for scope in ('global', 'mining'):
        for mode in ('exact', 'token-minus-one', 'no-call-remainder'):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                s.save(root / 'contract.json', {'schema_version': 'icfr-native-capability-stage-v4',
                                               'limits': s.LIMITS, 'historical_resource_prefix': prefix})
                capture = s.Budget(root, input_only=True)
                client = s.make_client(root, capture)
                payload = LabelAwareMiningController(store=RawInfoStore(), model=SimpleNamespace(),
                    case_pairs=(), measurable_evidence_manifest={}, signal_catalog=(),
                    seed='discovery', label_map={})._model_view()
                payload['review_synthetic'] = mode
                request = {'stage': 'mining_controller_step', 'system_prompt': 'Boundary-only synthetic review.',
                           'payload': payload, 'allow_outcomes': True, 'max_output_tokens': 100}
                try:
                    client.complete_json(**request)
                except s.InputCaptured as error:
                    captured = json.loads(str(error))
                else:
                    raise AssertionError('input-only did not stop')
                reservation = captured['reservation']
                assert capture.used() == (10, 2055941)
                assert not list((root / 'exchange/inbox').glob('*.json'))
                assert not list((root / 'exchange/receipts').glob('*.json'))
                limits = dict(s.SCOPE_LIMITS)
                limits[scope] = (10 if mode == 'no-call-remainder' else 11,
                                 2055941 + reservation - int(mode == 'token-minus-one'))
                budget = s.Budget(root)
                client = s.make_client(root, budget)
                with patch.object(s, 'SCOPE_LIMITS', limits):
                    if mode != 'exact':
                        rejects(scope + '-' + mode, lambda: client.complete_json(**request))
                        assert not list((root / 'exchange/inbox').glob('*.json'))
                    else:
                        try:
                            client.complete_json(**request)
                        except LocalRoleRequestPending as error:
                            pending = error.pending
                        else:
                            raise AssertionError('exact fit did not reach native inbox')
                        # Invalid content is still a submitted raw answer and consumes the full wire cost.
                        Path(pending['outbox_path']).write_text('this is deliberately invalid JSON')
                        s.LocalRoleExchange(root / 'exchange', max_calls=728).submit(
                            pending['request_hash'], agent_id='/root/independent_synthetic_control')
                        assert budget.used() == (11, 2055941 + reservation)
                        assert budget.consumption()['historical'] == [10, 2055941]
                        assert budget.consumption()['newly_answered'] == [1, reservation]
                        before = budget.used()
                        # Same original wire is an already-accounted request, not another call.
                        budget({'event_type': 'request_ready', 'request_hash': pending['request_hash'],
                                'request_path': captured['request_path']})
                        assert budget.used() == before
                        observed.append({'case': scope + '-exact-fit-invalid-content-and-replay',
                                         'result': 'verified', 'new_cost': reservation})
                assert budget.historical_used('candidate:other') == (0, 0)
    assert s._files(s.SEALED_STAGE_V3_ROOT) == original_files
    assert not s.ORACLE.exists() and not s.STAGE_ROOT.exists()
    observed.append({'case': 'postreview-old-v3-byte-equality-no-v4', 'result': 'verified',
                     'v3_sealed_files': len(original_files)})


if __name__ == '__main__':
    def forbidden(*args, **kwargs):
        raise AssertionError('independent review network tripwire')
    before = {row['path']: row['sha256'] for row in s._code()}
    with patch.object(socket, 'create_connection', forbidden), patch.object(socket.socket, 'connect', forbidden):
        run()
    assert before == {row['path']: row['sha256'] for row in s._code()}
    result = {'review': 'independent original-prefix and synthetic-transport controls',
              'findings': [], 'controls': observed, 'network_calls': 0,
              'fresh_production_answers': 0, 'formal_v4_created': False,
              'source_hashes_unchanged': True,
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT / 'counterreview.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'controls': len(observed), 'findings': [], 'source_hashes_unchanged': True}))
