"""Temporary controls only; never calls the real S1 export."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import importlib.util
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('export_history_candidate', ROOT / 'export_history.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class PrewriteControls(unittest.TestCase):
    def test_revision_script_control_and_existing_stage_before_marker(self):
        with tempfile.TemporaryDirectory() as raw:
            stage = Path(raw) / 'stage'
            script_sha = runner.sha(runner.__file__)
            control_sha = runner.sha(runner.CONTROL)
            with patch.object(runner, 'STAGE', stage), patch.object(runner.subprocess, 'check_output', return_value='revision\n'), patch.object(runner.subprocess, 'run'), patch.object(runner, 'source_authorities', side_effect=AssertionError('must not read authority')):
                for rev, control, script in [('other', control_sha, script_sha), ('revision', 'wrong', script_sha), ('revision', control_sha, 'wrong')]:
                    with self.subTest(rev=rev, control=control, script=script), self.assertRaises(runner.ScopeStop):
                        runner.execute(rev, control, script)
                    self.assertFalse(stage.exists())
                stage.mkdir()
                before = list(stage.iterdir())
                with self.assertRaises(runner.ScopeStop):
                    runner.execute('revision', control_sha, script_sha)
                self.assertEqual(list(stage.iterdir()), before)

    def test_fixed_authority_and_metadata_shape(self):
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw)
            files = {'run_contract.json': {'contract_hash': 'contract'}, 'state.json': {}, 'cycle_state.json': {}, 'signals/registry.json': {'version': 12}}
            for name, body in files.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(body))
            meta = source / 'meta/round-0001.json'; meta.parent.mkdir(); meta.write_text('{}')
            cp = source / 'experiments/round-0001/checkpoint.json'; cp.parent.mkdir(parents=True)
            cp.write_text(json.dumps({'round_id': 1, 'run_contract_hash': 'contract', 'plan_ids': ['plan1'], 'meta_ref': str(meta)}))
            hashes = {name: runner.sha(source / name) for name in files}
            with patch.object(runner, 'SOURCE', source), patch.object(runner, 'SOURCE_AUTHORITY_SHAS', hashes):
                self.assertTrue(runner.source_authorities()['checkpoint']['run_contract_hash_matches'])
                original = (source / 'state.json').read_bytes()
                (source / 'state.json').write_text('{"coherent_replacement":true}')
                with self.assertRaises(runner.ScopeStop): runner.source_authorities()
                (source / 'state.json').write_bytes(original)
                body = json.loads(cp.read_text()); body.pop('run_contract_hash'); cp.write_text(json.dumps(body))
                with self.assertRaises(runner.ScopeStop): runner.source_authorities()

    def test_write_and_actual_operation_guards(self):
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw).resolve(); source = temp / 'source'; source.mkdir(); stage = temp / 'stage'; stage.mkdir()
            with patch.object(runner, 'SOURCE', source), patch.object(runner, 'STAGE', stage):
                with runner.source_only() as (audit, _):
                    runner.save(stage / 'allowed.json', {'allowed': True})
                    for target in (source / 'bad.json', temp / 'global.json'):
                        with self.subTest(target=str(target)), self.assertRaises(runner.ScopeStop): runner.save(target, {})
                    for method, args in ((runner.library.SignalRegistry.freeze, (None,)), (runner.library.SignalExecutor.execute_batch, (None,)), (runner.LabelStore, ())):
                        with self.subTest(method=str(method)), self.assertRaises(runner.ScopeStop): method(*args)
                self.assertEqual(audit['forbidden_calls'], 3)
                self.assertEqual(len(audit['blocked_writes']), 2)
                self.assertFalse((source / 'bad.json').exists())
                self.assertFalse((temp / 'global.json').exists())

    def test_actual_metadata_shape_read_only(self):
        before = {name: runner.sha(runner.SOURCE / name) for name in runner.SOURCE_AUTHORITY_SHAS}
        authority = runner.source_authorities()
        self.assertEqual(before, {name: runner.sha(runner.SOURCE / name) for name in before})
        self.assertFalse(runner.STAGE.exists())
        self.assertTrue(authority['checkpoint']['run_contract_hash_matches'])
        self.assertTrue(Path(authority['meta']['path']).is_file())
        with (ROOT / 'source-metadata-shape-check.json').open('x') as handle:
            json.dump({'scope': 'Read only four authorities and checkpoint metadata; no native export or outcome output.', 'source': authority, 'unchanged': True}, handle, indent=2, sort_keys=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
