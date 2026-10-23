"""Offline source-bound catalog regressions; never a fresh production actor."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
FILES = [ROOT / p for p in (
    'spec/src/stock_opportunity_agent/research/signal_mining_agent.md',
    'src/stock_opportunity_agent/research/mining_controller.py',
    'src/stock_opportunity_agent/research/mining_role_model.py',
    'tests/test_mining_catalog_working_context.py',
)]


def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in FILES}


def main():
    before = hashes()
    from tests import test_mining_catalog_working_context as tests
    archive = ROOT / 'runs/diagnostics/icfr_native_capability_20261023_v1/frozen-runtime-98147bc1.tar.gz'
    names = [
        'test_evidence_directory_survives_two_reads_and_reaches_next_page',
        'test_signal_cards_and_whole_originals_survive_compute',
        'test_all_four_scopes_remain_exact_and_view_is_isolated',
        'test_backlog_visible_matching_pending_originals_authorize_current_base_only',
        'test_native_wire_counts_complete_cache_and_rejects_before_receive',
    ]
    current = tests.LabelAwareMiningController
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'mining_controller_old.py'
        with tarfile.open(archive) as frozen:
            content = frozen.extractfile('src/stock_opportunity_agent/research/mining_controller.py').read()
        path.write_bytes(content)
        spec = importlib.util.spec_from_file_location('catalog_regression_old_controller', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        tests.LabelAwareMiningController = module.LabelAwareMiningController
        with (HERE / 'old-98147-five-regressions.log').open('w') as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite(
                tests.MiningCatalogWorkingContextTests(name) for name in names))
        tests.LabelAwareMiningController = current
        old = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
               'source_sha256': hashlib.sha256(content).hexdigest(), 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    connections = []
    def forbidden(*args, **kwargs):
        connections.append('forbidden')
        raise AssertionError('network access forbidden')
    suite = unittest.defaultTestLoader.loadTestsFromNames([
        'tests.test_mining_catalog_working_context', 'tests.test_mining_narrative_read_evidence',
        'tests.test_mining_controller', 'tests.test_evolution_reflection_memory',
    ])
    with (HERE / 'associated-final.log').open('w') as stream:
        with patch.object(socket, 'create_connection', forbidden), patch.object(socket.socket, 'connect', forbidden), patch.object(socket.socket, 'connect_ex', forbidden):
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    after = hashes()
    evidence = {'old_five': old, 'associated': {'tests': result.testsRun, 'failures': len(result.failures),
        'errors': len(result.errors), 'successful': result.wasSuccessful()}, 'network_attempts': len(connections),
        'before': before, 'after': after, 'stable': before == after,
        'scope': 'Offline production-entry projections/regressions, not fresh role behavior, candidate or admission.'}
    (HERE / 'check-bindings.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: evidence[k] for k in ('old_five', 'associated', 'network_attempts', 'stable')}, indent=2))
    if not result.wasSuccessful() or before != after or connections or old['failures'] + old['errors'] != 5:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
