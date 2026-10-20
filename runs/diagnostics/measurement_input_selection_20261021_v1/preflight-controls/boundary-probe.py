"""Temporary-only preflight rejection controls; never opens a reviewed view."""
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / 'probe.py'
script_before = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
spec = importlib.util.spec_from_file_location('_input_selection_preflight_subject', SCRIPT)
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)
original_read = probe.read


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def tree(root):
    return [(str(p.relative_to(root)), 'dir' if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(root.rglob('*'))]


rows = []
with tempfile.TemporaryDirectory() as directory:
    temporary = Path(directory)
    def control(name, operation, *, marker=None, wrong_out=False, wrong_plan_output=False, authority=None):
        root = temporary / name
        output, old = root / 'output', root / 'old-stage'
        output.mkdir(parents=True)
        old.mkdir()
        if marker:
            write(output / marker, {'preserved': marker})
        if operation == 'run' and not marker:
            plan = {'output_root': str(root / 'other') if wrong_plan_output else str(output), 'bindings': []}
            plan['plan_hash'] = canonical_json_hash(plan)
            write(output / 'plan.json', plan)
            expected = plan['plan_hash']
        else:
            expected = 'unused'
        allowed = set()
        if authority:
            review = old / 'source-review.json'
            write(review, {'fixture': 'review is never deserialized'})
            plan = {'groups': []}
            plan['plan_hash'] = canonical_json_hash(plan)
            result = {'status': 'completed', 'plan_hash': plan['plan_hash'], 'source_review': probe.bind(review)}
            if authority == 'canonical_drift':
                plan['extra_unhashed_field'] = 'drift'
            elif authority == 'pointer_drift':
                result['source_review']['sha256'] = '0' * 64
            write(old / 'plan.json', plan)
            write(old / 'result.json', result)
            allowed = {old / 'plan.json', old / 'result.json'}
            result_sha = probe.bind(old / 'result.json')['sha256']
        else:
            result_sha = 'no-authority-read-permitted'
        calls = {'read': [], 'snapshot': 0, 'write': 0, 'view': 0, 'network': 0, 'labels': 0}
        def stop(kind):
            def forbidden(*args, **kwargs):
                calls[kind] += 1
                raise AssertionError('unexpected later operation: ' + kind)
            return forbidden
        def guarded_read(path):
            path = Path(path)
            calls['read'].append(str(path.relative_to(root)))
            if path not in allowed and not (operation == 'run' and not marker and path == output / 'plan.json'):
                raise AssertionError('unexpected read beyond preflight: ' + str(path))
            return original_read(path)
        before = tree(root)
        with ExitStack() as stack:
            for name_, value in {'OUT': output, 'EXPECTED_OUT': root / 'expected' if wrong_out else output,
                                 'OLD': old, 'ROOT': root, 'RESULT_SHA': result_sha}.items():
                stack.enter_context(patch.object(probe, name_, value))
            stack.enter_context(patch.object(probe, 'read', guarded_read))
            stack.enter_context(patch.object(probe.frozen, '_snapshot', stop('snapshot')))
            stack.enter_context(patch.object(probe, 'write_new', stop('write')))
            stack.enter_context(patch.object(probe, 'open_raw_info_store', stop('view')))
            stack.enter_context(patch.object(socket, 'socket', stop('network')))
            for member in ('load', 'record', 'ground_truth'):
                stack.enter_context(patch.object(LabelStore, member, stop('labels')))
            try:
                probe.freeze() if operation == 'freeze' else probe.run(expected)
            except (RuntimeError, AssertionError) as exc:
                error = {'type': type(exc).__name__, 'message': str(exc)}
            else:
                raise AssertionError('preflight unexpectedly accepted: ' + name)
        assert all(calls[k] == 0 for k in ('snapshot', 'write', 'view', 'network', 'labels')), calls
        assert not calls['read'] if wrong_out or marker else True
        if authority:
            assert set(calls['read']) == {'old-stage/result.json', 'old-stage/plan.json'}, calls
            assert error['type'] == 'AssertionError', error
        elif wrong_plan_output:
            assert calls['read'] == ['output/plan.json'], calls
            assert error['message'] == 'Exact frozen plan required', error
        else:
            assert error['type'] == 'RuntimeError', error
            assert 'diagnostic' in error['message'], error
        assert tree(root) == before, 'temporary directory changed'
        rows.append({'name': name, 'operation': operation, 'expected_rejection': error,
                     'calls': calls, 'temporary_tree_unchanged': True})

    for operation in ('freeze', 'run'):
        control('wrong_root_' + operation, operation, wrong_out=True)
    control('serialized_output_root_mismatch', 'run', wrong_plan_output=True)
    for marker in ('plan.json', 'started.json', 'result.json', 'failure.json', 'default_v6.json', 'latest_v12.json'):
        control('freeze_existing_' + marker, 'freeze', marker=marker)
    for marker in ('started.json', 'result.json', 'failure.json', 'default_v6.json', 'latest_v12.json'):
        control('run_existing_' + marker, 'run', marker=marker)
    for authority in ('canonical_drift', 'pointer_drift'):
        control(authority, 'freeze', authority=authority)

script_after = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
assert script_before == script_after, 'subject changed during review'
result = {'subject': {'path': str(SCRIPT), 'sha256': script_after}, 'controls': rows,
          'count': len(rows), 'all_pass': True,
          'scope': 'Only temporary fixture roots passed to freeze/run; no actual source/view/Registry construction, append, network, models, labels or fullprepare',
          'limits': 'Preflight guards only. Not proof of actual input selection or native source-view success.'}
with (HERE / 'results.json').open('x') as handle:
    json.dump(result, handle, indent=2)
    handle.write('\n')
print(json.dumps({'controls': len(rows), 'all_pass': True, 'subject_sha256': script_after}))
