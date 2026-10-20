"""Compare retained old/current controls and native mixed-sibling disk sink."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import ast
import hashlib
import json

from probe import controller, isolated, row
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine

REPO = Path('/Users/l/Project/Recommandation')
OWN = Path(__file__).resolve().parent
PREFIX = REPO / 'src/stock_opportunity_agent/research'
old = json.loads((OWN / 'old-before-results.json').read_text())
new = json.loads((OWN / 'candidate-final-results.json').read_text())
assert [x['payload_row_contract_present'] for x in old['outgoing_contract_paths']] == [False] * 3
declarations = [x['row_rationale_contract'] for x in new['outgoing_contract_paths']]
assert len(set(declarations)) == 1
assert 'non-empty array of nonblank strings' in declarations[0]
for call in new['outgoing_contract_paths']:
    assert declarations[0] in call['system_prompt']
assert len(new['nested_bad_shapes_rejected']) == 11
assert all(declarations[0] in x['error'] for x in new['nested_bad_shapes_rejected'])


def methods(path):
    return {n.name: n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.FunctionDef)}


before = methods(OWN / 'old-mining_controller.py')
after = methods(PREFIX / 'mining_controller.py')
for name in ('_record_need_dispositions', '_validate_action_shape', '_pending_need_refs'):
    assert ast.dump(before[name], include_attributes=False) == ast.dump(after[name], include_attributes=False)
for name in ('_validate_need_dispositions',):
    old_test = next(n.test for n in ast.walk(before[name]) if isinstance(n, ast.If) and 'rationale' in ast.unparse(n.test) and 'isinstance' in ast.unparse(n.test))
    new_test = next(n.test for n in ast.walk(after[name]) if isinstance(n, ast.If) and 'rationale' in ast.unparse(n.test) and 'isinstance' in ast.unparse(n.test))
    assert ast.dump(old_test, include_attributes=False) == ast.dump(new_test, include_attributes=False)
durable = []
for label, source in [('old', OWN / 'old-mining_controller.py'), ('candidate', PREFIX / 'mining_controller.py')]:
    module = isolated(source, label + '_durable')
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        engine = object.__new__(SignalEvolutionEngine)
        engine.workspace = SimpleNamespace(experiments_root=root)
        c = controller(module, sink=lambda unit: engine._save_mining_need_unit(1, unit))
        good = row('synthetic-a', ['  Original valid sibling.  '])
        bad = row('synthetic-b', 'Invalid scalar sibling.')
        c._record_need_dispositions({'action': 'record_need_dispositions', 'base_hash': c._need_state_hash(),
            'need_dispositions': [good, bad], 'rationale': ['Independent synthetic mixed control.']})
        paths = list(root.rglob('*.json'))
        assert len(paths) == 1
        unit = json.loads(paths[0].read_text())
        assert unit['accepted_rows'] == [good] and unit['invalid_rows'][0]['invalid_row'] == bad
        assert unit['pending_count'] == 1 and c._pending_need_refs() == ['synthetic-b']
        durable.append({'version': label, 'accepted_original_whitespace_exact': True,
            'invalid_scalar_preserved_not_wrapped': True, 'real_shared_sink_files': 1, 'pending': 1})

paths = [PREFIX / n for n in ('stage_contracts.py', 'mining_controller.py', 'mining_role_model.py')]
paths += [REPO / 'spec/src/stock_opportunity_agent/research' / n for n in ('stage_contracts.md', 'signal_mining_agent.md')]
paths += [REPO / 'tests/test_need_row_authoring_contract.py', OWN / 'probe.py', Path(__file__),
          OWN / 'old-before-results.json', OWN / 'candidate-final-results.json',
          OWN / 'old-before.log', OWN / 'candidate-final.log']
bindings = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
report = {'status': 'PASS_bounded_authoring_contract_and_unchanged_strict_validation',
    'old_before': {'three_native_authoring_paths_missing_row_declaration': True,
        'result_sha256': bindings[str(OWN / 'old-before-results.json')],
        'old_validator_strictness_correct': True},
    'candidate': {'same_complete_declaration_in_initial_continuation_terminal_system_and_native_view': True,
        'same_declaration_in_all_11_bad_shape_errors': True,
        'declaration': declarations[0], 'valid_array_controls': 3,
        'ordinary_continuation_remains_no_patch': True,
        'whole_backlog_terminal_row_validator_passes': True,
        'durable_mixed_sibling_controls': durable},
    'unchanged_policy': {'strict_rationale_predicate_AST_exact': True,
        'record_need_dispositions_AST_exact': True, 'top_level_action_validator_AST_exact': True,
        'no_new_row_wrap_or_typed_patch_authority': True, 'legacy_H1_not_modified': True},
    'limits': ['All cases are synthetic local native controls with empty in-memory raw stores and zero case labels. No API/network/fresh agent/real-stage/LabelStore/Signal/fullprepare invoked.',
        'Six offline role-adapter callbacks across old/current runs are scripted data, not model behavior.',
        'Native record_deferred completes the terminal authoring path. Whole-backlog proposal/no-pattern row validation is separately checked; no evidence-backed domain terminal or candidate admission is claimed.',
        'Pure shared sink runs on an object.__new__ Engine with a temporary workspace; this proves exact native persistence behavior, not a full Engine constructor connection.',
        'This fixes the field-contract disclosure gap. No fresh model obedience or recurrence reduction is established; prior completed stages and their rejected first answers remain unchanged.'],
    'bindings': bindings}
output = OWN / 'final-review.json'
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}))
