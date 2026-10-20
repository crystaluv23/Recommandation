"""Fixed independent synthetic boundaries; no live source or research execution."""
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import shutil
import socket
import tempfile
import unittest

from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent import signal_library
from stock_opportunity_agent.research import signal_evolution as native
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from tests.test_imported_slow_method_memory import (
    ALL, PROFILE, imported_fixture, memory, header, hashes, write,
    rebind_authored_input, ImportedSlowMethodMemoryTests,
)

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
SOURCE = REPO / 'src/stock_opportunity_agent/research/signal_evolution.py'
EXPECTED = '1e87ae7c63964ea7feda9414b2e5d4815fc318cebc839f25bdb3c7a9cda8b092'
CHECKS = []


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_rows(rows, scopes):
    return native.validate_slow_input({
        'schema_version': 'slow-input-v1', 'cycle_id': 1, 'contract_hash': 'a'*64,
        'registry_hash': 'b'*64, 'source_cutoff': {}, 'feedback_rows': rows,
        'source_manifest': scopes,
        'feedback_hash': native._canonical_hash({'feedback_rows': rows}),
        'sampling_manifest': {'schema_version': 'slow-sampling-manifest-v1',
            'dev_case_ids': [], 'check_case_ids': [], 'issuer_groups': {}},
        'previous_memory_head': None, 'previous_memory_hash': '',
    })


def produce(root, raw, **kwargs):
    owner = imported_fixture(root, raw, **kwargs)
    before = hashes(root)
    rows, scopes = owner._imported_slow_feedback()
    validate_rows(rows, scopes)
    assert hashes(root) == before
    return owner, rows, scopes


def rejected(function):
    try:
        function()
    except native.ValidationError:
        return
    raise AssertionError('expected native ValidationError')


def controls(base):
    # Public actual reads, hidden offered directory: neither all-reject nor disclosure.
    public = [f'public-{i}' for i in range(3)]
    hidden = [f'target-hidden-{i}' for i in range(126)]
    remaining = [f'unread-public-{i}' for i in range(3518-129)]
    refs = [*public, *hidden, *remaining]
    raw = memory(refs=refs)
    raw['model_view_manifest'] = {'included_refs': public, 'requested_refs': refs,
        'deferred': [{'ref': r, 'reason': 'item_limit'} for r in refs[3:]]}
    raw['failure_ref'] = 'A technical reflection failure followed the three included inputs.'
    source_scopes = {r: ALL for r in public + remaining}
    source_scopes.update({r: ['reflection', 'Update'] for r in hidden})
    _, rows, scopes = produce(base/'public', raw, scopes=source_scopes)
    compact = header(rows)
    catalog = native._slow_feedback_source_catalog(rows, scopes)
    selected, manifest = native.read_slow_sources([compact['feedback_ref']],
        role_scope='H1', source_catalog=catalog, budget_bytes=64000)
    assert len(selected) == 1 and manifest['included_count'] == 1
    encoded = json.dumps(compact['artifact'])
    assert all(r not in encoded for r in refs)
    assert native._canonical_hash(refs) not in encoded
    assert 'original_ref' not in encoded and 'slow-memory:1:' not in encoded
    assert compact['artifact']['source_memory_hash'] == native._canonical_hash(raw)
    original = next(r for r in rows if r['feedback_ref'].endswith(':slow_memory:summary'))
    rejected(lambda: native.read_slow_sources([original['feedback_ref']],
        role_scope='H1', source_catalog=catalog, budget_bytes=64000))
    assert raw['processed_feedback_refs'] == [] and len(raw['pending_feedback_refs']) == 3518
    CHECKS.append('3 public actual reads / 3518 pending / 126 H1-hidden: header readable; raw summary hidden; no directory leakage')

    # Exact source type ceiling applies even to an erroneously broad declared scope.
    limited = deepcopy(raw)
    limited['model_view_manifest']['included_refs'] = [hidden[0]]
    _, limited_rows, limited_scopes = produce(base/'limited', limited, scopes=source_scopes)
    limited_catalog = native._slow_feedback_source_catalog(limited_rows, limited_scopes)
    rejected(lambda: native.read_slow_sources([header(limited_rows)['feedback_ref']],
        role_scope='H1', source_catalog=limited_catalog, budget_bytes=64000))
    CHECKS.append('actually included hidden source blocks H1 header')

    # Complete oversized fields are never clipped or disguised as available.
    for field in ('status', 'failure_ref'):
        large = memory(); large[field] = '\u754c' * 40000
        _, rr, _ = produce(base/field, large)
        h = header(rr)['artifact']
        assert h['projection_status'] == 'deferred' and h['reason'] == 'whole_header_budget'
        assert 'view' not in h and len(json.dumps(h).encode()) < 32000
    for cycle in (2, None, True):
        wrong = memory(); wrong['cycle_id'] = cycle
        _, rr, _ = produce(base/f'cycle-{cycle}', wrong)
        h = header(rr)['artifact']
        assert h['projection_status'] == 'deferred' and h['reason'] == 'unreviewed_memory_identity'
    CHECKS.append('oversized status/cause and manifest-vs-raw cycle conflicts: explicit bounded deferred, never available')

    # Legacy existing-scope compatibility is a producer -> admission positive.
    legacy_root = base/'legacy'
    owner = imported_fixture(legacy_root, memory())
    input_path = legacy_root/'slow_history/source-one/experiments/cycles/cycle-0001/slow_input.json'
    body = json.loads(input_path.read_text()); body.pop('source_manifest'); write(input_path, body)
    rebind_authored_input(legacy_root)
    rr, ss = owner._imported_slow_feedback()
    validate_rows(rr, ss)
    assert not any(r.get('artifact', {}).get('schema_version') == PROFILE for r in rr)
    assert all(s['visible_to'] == ALL for s in ss)
    CHECKS.append('legacy no source manifest preserves old roles and validates whole Slow input; adds no unproved header')

    # Stable authored ids in two namespaces do not generate naked cycle-only handles.
    episode = {'episode_ref': 'same-episode', 'source_refs': ['r'], 'reflection': 'Exact full text.',
        'brief': 'Exact brief.', 'kind': 'fact'}
    originals = []
    for ns in ('A', 'B'):
        _, rr, _ = produce(base/ns, memory(refs=('r',), episodes=[episode]), namespace=ns)
        originals.append(header(rr))
        assert ':slow_memory:method-header-v1' in originals[-1]['feedback_ref']
        assert 'original_ref' not in json.dumps(originals[-1]['artifact'])
    assert originals[0]['feedback_ref'] != originals[1]['feedback_ref']
    CHECKS.append('two namespace cycle1 / same authored episode id: namespaced header refs, no unresolvable bare alias')

    first = base/'origin'
    _, rr, _ = produce(first, memory(), namespace='origin')
    original = header(rr)
    # Native copied-namespace behavior, then carry exact original unit once.
    destination = base/'next'
    shutil.copytree(first/'slow_history/origin', destination/'slow_history/origin')
    _, rr, _ = produce(destination, memory(status='reused'), namespace='next', carried=[original])
    copies = [r for r in rr if r.get('artifact', {}).get('projection_identity') == original['artifact']['projection_identity']]
    assert copies == [original]
    third = base/'third'
    shutil.copytree(destination/'slow_history/origin', third/'slow_history/origin')
    _, rr, _ = produce(third, memory(status='reused'), namespace='third', carried=copies)
    assert [r for r in rr if r.get('artifact', {}).get('projection_identity') == original['artifact']['projection_identity']] == [original]
    CHECKS.append('identical carried projection once across native-style namespace copy: no extra observation/ref')

    # Single-variable carried data/provenance forgeries must reject before dedup.
    for variant in ('body', 'locator', 'identity', 'original-file', 'input-file', 'fake-schema'):
        target = base/variant
        shutil.copytree(first/'slow_history/origin', target/'slow_history/origin')
        changed = deepcopy(original)
        if variant == 'body': changed['artifact']['view']['memory_deltas'][0]['failure_ref'] = 'forged'
        elif variant == 'locator': changed['artifact']['source']['json_locator'] = '/failure_ref'
        elif variant == 'identity': changed['artifact']['projection_identity'] = 'f'*64
        elif variant == 'original-file':
            p=target/'slow_history/origin/experiments/cycles/cycle-0001/slow_memory.json'; p.write_text(p.read_text()+' ')
        elif variant == 'input-file':
            p=target/'slow_history/origin/experiments/cycles/cycle-0001/slow_input.json'; p.write_text('{}')
        else:
            changed['artifact'] = {'schema_version': PROFILE,
                'projection_identity': original['artifact']['projection_identity']}
        owner=imported_fixture(target, memory(), namespace='next', carried=[changed, original])
        rejected(owner._imported_slow_feedback)
    CHECKS.append('6 carried-header single-variable body/locator/identity/source/input/fake-schema changes rejected before shadow/dedup')


if __name__ == '__main__':
    assert sha(SOURCE) == EXPECTED
    calls=[]
    def forbidden(*args, **kwargs):
        calls.append('forbidden'); raise AssertionError('forbidden live dependency')
    with ExitStack() as stack:
        for owner,name in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'load'),
                (LabelStore,'__init__'),(RawInfoStore,'__init__'),(signal_library.SignalExecutor,'execute_batch'),
                (signal_library.SignalRegistry,'freeze'),(signal_library.SignalRegistry,'audit_capabilities'),
                (StructuredRoleClient,'complete_json'),(StructuredRoleClient,'complete_json_with_token_scores'),
                (StructuredRoleClient,'complete_binary_token_with_scores')):
            stack.enter_context(patch.object(owner,name,forbidden))
        with tempfile.TemporaryDirectory() as tmp:
            controls(Path(tmp).resolve())
        suite=unittest.TestSuite(ImportedSlowMethodMemoryTests(name) for name in (
            'test_native_reflection_payload_persistence_and_next_method_view',
            'test_target_kind_ceiling_is_not_widened_by_legacy_allrole_manifest',
        ))
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        assert result.wasSuccessful()
    assert calls == [] and sha(SOURCE) == EXPECTED
    output={'status':'PASS_fixed_independent_synthetic_boundaries','source_sha256':EXPECTED,
        'independent_groups':CHECKS,'independent_group_count':len(CHECKS),
        'additional_native_temp_methods':2,'forbidden_calls':0,
        'live_models':0,'Signal_apply':0,'GET':0,'LabelStore':0,
        'scope':'Synthetic fixtures / native pure input validator / deterministic offline Reflector; not fresh model obedience or real-stage execution.'}
    (ROOT/'results.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))
