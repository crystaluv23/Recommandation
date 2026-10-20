"""Synthetic restore graph only; never opens the actual historical source."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from tests.evolution_runtime_test_support import make_contract
from tests.scheme_evolution_test_support import make_record
from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace
from stock_opportunity_agent.research.evolution_core import RoundMetaEntry

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('history_export_v2', ROOT / 'export_history.py')
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, sort_keys=True))


def tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


class NativeRestoreControls(unittest.TestCase):
    def test_native_constructor_archive_meta_and_prediction_graph(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw).resolve(); source = repo / 'runs/source'; stage = repo / 'runs/stage'
            contract = make_contract(); contract.freeze(source / 'run_contract.json')
            workspace = EvolutionWorkspace(source)
            record = make_record('committed_plan', 1.0, (1.0,))
            workspace.commit_round(round_id=1, records=(record,),
                meta_entry=RoundMetaEntry(round_id=1, evidence_refs=(record.plan_id,)),
                signal_registry_version=1, signal_registry_hash=contract.initial_signal_registry_hash,
                run_contract_hash=contract.contract_hash)
            write(source / 'cycle_state.json', {'last_completed_cycle': 1, 'active_cycle': None})
            for name in ('slow_input.json', 'slow_memory.json', 'slow_experiments.json', 'slow_loop_validation.json', 'slow_loop_result.json'):
                write(source / 'experiments/cycles/cycle-0001' / name, {})
            # A high runtime sequence and uncommitted debug payload are not research evidence.
            (source / 'experiments/trajectory.jsonl').write_text(json.dumps({'sequence': 99999,
                'round_id': 2, 'message': 'UNCOMMITTED_DEBUG_DECOY'}) + '\n')
            future = make_record('uncommitted_plan', 0.0, (0.0,), round_id=2)
            write(source / 'plans/uncommitted_plan/record.json', future.to_dict())
            write(source / 'experiments/round-0002/checkpoint.json', {'round_id': 2})
            write(source / 'meta/round-0002.json', {'round_id': 2})
            write(source / 'experiments/trajectories/round2-case.json', {'decoy': True})
            before = tree(source)
            with patch.object(runner, 'REPO', repo), patch.object(runner, 'SOURCE', source), patch.object(runner, 'STAGE', stage):
                with runner.source_only() as (audit, declare):
                    declare(contract)
                    restored = EvolutionWorkspace(source)
                    self.assertEqual(restored._event_sequence, 99999)
                    archive = restored.restore_archive(expected_run_contract_hash=contract.contract_hash)
                    self.assertEqual([r.round_id for r in archive.records], [1])
                    self.assertEqual([e.round_id for e in restored.restore_meta().entries], [1])
                    self.assertEqual(len(restored.committed_prediction_observations()), 1)
                    self.assertEqual(restored.imported_prediction_observations(), [])
                    context = runner.control._load_slow_fast_context(source, contract)
                    self.assertEqual([e['round_id'] for e in context['meta_entries']], [1])
                    self.assertEqual(len(context['prediction_observations']), 1)
                    self.assertNotIn('UNCOMMITTED_DEBUG_DECOY', json.dumps(context))
                    self.assertNotIn('uncommitted_plan', json.dumps(context))
                    for path in (source / 'meta/round-0002.json', source / 'plans/uncommitted_plan/record.json',
                                 source / 'experiments/round-0002/checkpoint.json', source / 'experiments/trajectories/round2-case.json',
                                 source / 'experiments/other-log.jsonl'):
                        with self.subTest(read=path.name), self.assertRaises(runner.ScopeStop): runner.read(path)
                    with self.assertRaises(runner.ScopeStop): runner.save(source / 'source-write.json', {})
            self.assertEqual(before, tree(source))
            self.assertIn(str(source / 'experiments/trajectory.jsonl'), audit['reads'])
            self.assertEqual(audit['forbidden_calls'], 0)
            self.assertEqual(len(audit['blocked_reads']), 5)
            self.assertEqual(len(audit['blocked_writes']), 1)
            self.assertFalse(stage.exists())

    def test_native_sequence_and_export_functions_unchanged(self):
        previous = ROOT.parent / 'reviewed_slow_history_export_20261021_v1/export_history.py'
        old = ast.parse(previous.read_text()); new = ast.parse((ROOT / 'export_history.py').read_text())
        # The only function-body delta declares the one exact sidecar. Native calls unchanged.
        old_execute = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == 'execute')
        new_execute = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == 'execute')
        self.assertEqual(ast.dump(old_execute), ast.dump(new_execute))
        old_guard = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == 'source_only')
        new_guard = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == 'source_only')
        delta = next(i for i,n in enumerate(new_guard.body) if isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'add'
            and ast.unparse(n.value) == "permitted.add(SOURCE / 'experiments/trajectory.jsonl')")
        new_guard.body.pop(delta)
        self.assertEqual(ast.dump(old_guard), ast.dump(new_guard))
        lineage = json.loads((ROOT / 'harness-lineage.json').read_text())
        for field in ('previous_script', 'previous_terminal_failure'):
            binding = lineage[field]
            self.assertEqual(runner.sha(binding['path']), binding['sha256'])
        self.assertFalse(runner.STAGE.exists())


if __name__ == '__main__': unittest.main(verbosity=2)
