"""Run explicit connected selectors; forbid real acquisition/labels/full prepare."""
import contextlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research import evolution_runtime
from tests import evolution_runtime_test_support

ROOT = Path(__file__).resolve().parents[3]
SELECTORS = ['tests.test_candidate_fixture_authoring_contract', 'tests.test_seed_fixture_issuer_binding', 'tests.test_signal_financials', 'tests.test_numeric_measurement_contract', 'tests.test_mining_tool_contracts', 'tests.test_signal_evolution_engine.DualLoopTests.test_v147_materialization_modules_reuse_accepted_siblings', 'tests.test_signal_evolution_engine.SignalEvolutionTests.test_fixture_unavailable_does_not_hide_technical_failure', 'tests.test_signal_evolution_engine.SignalEvolutionTests.test_fixture_failure_reports_pre_execution_coverage_gap', 'tests.test_signal_evolution_engine.SignalEvolutionTests.test_candidate_identity_guard_preserves_ticker_case', 'tests.test_signal_evolution_engine.SignalEvolutionTests.test_update_contract_preserves_complete_retrieval_and_rejects_empty_diff', 'tests.test_signal_evolution_engine.SignalEvolutionTests.test_signal_update_uses_one_induction_call_and_local_holdout_gate', 'tests.test_signal_evolution_engine.SignalEvolutionTests.test_controller_mining_dispatch_stages_materialized_candidate', 'tests.test_signal_evolution_engine.SignalEvolutionTests.test_candidate_validation_rejects_leakage_duplicate_and_bad_version']
hits = dict(network=0, subprocess=0, labels=0, persistent_append=0, full_prepare=0)


def reject(kind):
    def guard(*args, **kwargs):
        hits[kind] += 1
        raise AssertionError('Forbidden diagnostic operation: ' + kind)
    return guard


original_append = RawInfoStore.append


def safe_append(store, document):
    if store.root is not None and Path(store.root).resolve().is_relative_to(ROOT):
        return reject('persistent_append')()
    return original_append(store, document)


with contextlib.ExitStack() as stack:
    stack.enter_context(patch.object(socket.socket, 'connect', reject('network')))
    stack.enter_context(patch.object(socket, 'create_connection', reject('network')))
    stack.enter_context(patch.object(subprocess, 'Popen', reject('subprocess')))
    stack.enter_context(patch.object(LabelStore, 'load', reject('labels')))
    stack.enter_context(patch.object(LabelStore, 'ground_truth', reject('labels')))
    stack.enter_context(patch.object(RawInfoStore, 'append', safe_append))
    for module in (evolution_runtime, evolution_runtime_test_support):
        for name in ('prepare_dataset_proposal', 'prepare_expanded_dataset_proposal'):
            if hasattr(module, name):
                stack.enter_context(patch.object(module, name, reject('full_prepare')))
    suite = unittest.defaultTestLoader.loadTestsFromNames(SELECTORS)
    print('Explicit selectors: ' + json.dumps(SELECTORS), flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
print('Diagnostic tripwires: ' + json.dumps(hits), flush=True)
sys.exit(0 if result.wasSuccessful() and not any(hits.values()) else 1)
