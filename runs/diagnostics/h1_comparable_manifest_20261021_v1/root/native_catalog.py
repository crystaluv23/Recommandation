"""One read-only H1 catalog observation on the existing qualified dev8 view."""
import hashlib
import json
from pathlib import Path
import socket
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from stock_opportunity_agent.signal_library import SignalExecutor

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
INVENTORY = REPO / 'runs/diagnostics/mining_positive_frontier_20261021_v1/oracle/static-inventory.json'
SNAPSHOT = REPO / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot'
PLAN = ROOT / 'native-bindings.json'
OUTPUT = ROOT / 'native'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def execute():
    """Call the production metadata method once, never a role or an Engine."""
    plan = json.loads(PLAN.read_text())
    before = {path: sha(path) for path in plan['bindings']}
    if before != plan['bindings'] or sha(__file__) != plan['script_sha256']:
        raise RuntimeError('frozen source/code mismatch before observation')
    if OUTPUT.exists():
        raise RuntimeError('observation already started; no reentry')
    OUTPUT.mkdir()
    (OUTPUT / 'started.json').write_text(json.dumps({'script_sha256': sha(__file__)}))
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('network/model/labels/Signal/source append forbidden')

    try:
        with patch.object(socket, 'socket', forbidden), patch.object(socket, 'create_connection', forbidden), \
             patch.object(LabelStore, '__init__', forbidden), patch.object(LabelStore, 'load', forbidden), \
             patch.object(LabelStore, 'ground_truth', forbidden), patch.object(RawInfoStore, 'append', forbidden), \
             patch.object(StructuredRoleClient, 'complete_json', forbidden), \
             patch.object(SignalExecutor, 'execute_batch', forbidden):
            inventory = json.loads(INVENTORY.read_text())
            metadata = [{key: row[key] for key in ('case_id', 'case_ref', 'cutoff')}
                        for row in inventory['dev8']]
            assert len(metadata) == 8
            pairs = [(row['case_ref'], SimpleNamespace(
                company_id=row['case_id'].split(':', 1)[0],
                prediction_time=datetime.fromisoformat(row['cutoff']))) for row in metadata]
            store = open_raw_info_store(SNAPSHOT, reviewed_snapshot={
                'root': str(SNAPSHOT), 'store_type': 'reviewed',
                'manifest_sha256': plan['snapshot_manifest_sha256']})
            assert len(store.documents) == 1780
            catalog = SignalEvolutionEngine._h1_measurable_evidence_manifest(
                SimpleNamespace(raw_info_store=store), pairs)
            assert catalog['cohort_case_count'] == 8
            assert all(0 <= row['cases_with_comparable_records'] <= row['case_count'] <= 8
                       for row in catalog['structured_financial_concepts'])
            after = {path: sha(path) for path in before}
            assert before == after and not calls
            result = {'status': 'completed_native_value_free_catalog_observation',
                      'scope': 'One unbound production H1 call; qualified1780 and label-free dev8 metadata; no Engine, role, graph, label, GET or old-stage entry.',
                      'old_catalog': inventory['actual_native_measurable_manifest'],
                      'new_catalog': catalog, 'case_metadata': metadata,
                      'bindings_before': before, 'bindings_after': after,
                      'forbidden_calls': len(calls)}
            with (OUTPUT / 'result.json').open('x') as stream:
                json.dump(result, stream, indent=2, sort_keys=True)
                stream.write('\n')
    except Exception as error:
        with (OUTPUT / 'failure.json').open('x') as stream:
            json.dump({'status': 'terminal_failure_no_retry', 'type': type(error).__name__,
                       'message': str(error), 'forbidden_calls': len(calls)}, stream, indent=2)
        raise


if __name__ == '__main__':
    execute()
