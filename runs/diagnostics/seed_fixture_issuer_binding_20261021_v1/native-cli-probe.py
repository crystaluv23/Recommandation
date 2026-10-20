"""Contrast exact legacy and repaired templates through the actual catalog CLI."""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import runpy
import socket
import sys
import tempfile
from time import monotonic
from unittest.mock import patch

import run_minimal_rounds
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.signal_library import SignalRegistry

ROOT = Path('/Users/l/Project/Recommandation')
OUT = Path(__file__).resolve().parent
TEMPLATE = ROOT / 'configs/signals_v1.json'
CLI = ROOT / 'scripts/evolve_information_schemes.py'


def binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    if (OUT / 'native-cli-started.json').exists() or (OUT / 'native-cli-result.json').exists():
        raise RuntimeError('Retain the completed or attempted diagnostic; do not rerun')
    frozen = [binding(p) for p in (Path(__file__), TEMPLATE, CLI, OUT / 'legacy-catalog.json',
              ROOT / 'src/stock_opportunity_agent/signal_library.py',
              ROOT / 'src/stock_opportunity_agent/data/sec_company_facts.py')]
    with (OUT / 'native-cli-started.json').open('x') as handle:
        json.dump({'bindings': frozen, 'cases': ['legacy_template', 'repaired_template']}, handle, indent=2)
        handle.write('\n')
    counts = {key: 0 for key in ('network', 'model', 'labels', 'real_store', 'real_registry', 'fullprepare')}
    def deny(kind):
        def rejected(*args, **kwargs):
            counts[kind] += 1
            raise AssertionError(kind + ' forbidden in catalog-only diagnostic')
        return rejected
    store_constructor, registry_constructor = RawInfoStore.__init__, SignalRegistry.__init__
    def construct_store(self, root=None, *args, **kwargs):
        if root is not None:
            return deny('real_store')()
        return store_constructor(self, root, *args, **kwargs)
    def construct_registry(self, root, *args, **kwargs):
        if not Path(root).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
            return deny('real_registry')()
        return registry_constructor(self, root, *args, **kwargs)
    receipts = []
    with ExitStack() as guards:
        for obj, name, kind in ((socket, 'socket', 'network'), (socket, 'create_connection', 'network'),
                               (LabelStore, '__init__', 'labels'), (LabelStore, 'load', 'labels'),
                               (LabelStore, 'ground_truth', 'labels'), (run_minimal_rounds, 'prepare', 'fullprepare')):
            guards.enter_context(patch.object(obj, name, deny(kind)))
        for name in ('complete_json', 'complete_json_with_token_scores', 'complete_binary_token_with_scores'):
            guards.enter_context(patch.object(StructuredRoleClient, name, deny('model')))
        guards.enter_context(patch.object(RawInfoStore, '__init__', construct_store))
        guards.enter_context(patch.object(SignalRegistry, '__init__', construct_registry))
        for name, catalog in (('legacy_template', OUT / 'legacy-catalog.json'), ('repaired_template', TEMPLATE)):
            stdout, stderr = io.StringIO(), io.StringIO()
            started = monotonic()
            with patch.object(sys, 'argv', [str(CLI), 'validate-catalog', '--catalog', str(catalog)]), redirect_stdout(stdout), redirect_stderr(stderr):
                try:
                    runpy.run_path(str(CLI), run_name='__main__')
                    code = 0
                except SystemExit as exc:
                    code = exc.code
            emitted = stdout.getvalue()
            receipts.append({'case': name, 'exit_code': code, 'stdout': emitted, 'stderr': stderr.getvalue(),
                             'result': json.loads(emitted), 'seconds': monotonic() - started})
    assert not any(counts.values()), counts
    assert receipts[0]['exit_code'] != 0
    assert receipts[1]['exit_code'] == 0
    assert receipts[1]['result']['valid'] is True
    assert receipts[1]['result']['installed'] == receipts[1]['result']['signal_count'] == 14
    assert all(binding(row['path']) == row for row in frozen), 'Bound code/template drift'
    result = {'receipts': receipts, 'tripwires': counts, 'bindings': frozen,
              'limits': 'Actual CLI parsing/materialization/freeze in temporary Registries only; no research run, live Signal, fresh model, published Registry migration, source writes or evidence of Mining/research gain.'}
    with (OUT / 'native-cli-result.json').open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'exit_codes': [row['exit_code'] for row in receipts], 'new_enabled': 14, 'tripwires': counts}))


if __name__ == '__main__':
    main()
