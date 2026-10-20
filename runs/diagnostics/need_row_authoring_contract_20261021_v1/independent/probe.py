"""Offline synthetic native Controller authoring/validation controls only."""
from pathlib import Path
from types import ModuleType, SimpleNamespace
from tempfile import TemporaryDirectory
from copy import deepcopy
import argparse
import hashlib
import json
import sys

from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine

OWN = Path(__file__).resolve().parent
REPO = Path('/Users/l/Project/Recommandation')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def isolated(path, suffix):
    name = 'stock_opportunity_agent.research._independent_need_row_' + suffix
    module = ModuleType(name)
    module.__package__ = 'stock_opportunity_agent.research'
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(Path(path).read_text(), str(path), 'exec'), module.__dict__)
    return module


def controller(module, model=None, sink=None):
    return module.LabelAwareMiningController(store=RawInfoStore(), model=model,
        case_pairs=(), measurable_evidence_manifest={}, signal_catalog=(), seed='hypothesis',
        backlog_needs=({'need_ref': 'synthetic-a', 'need': 'Unresolved method dependency.'},
                       {'need_ref': 'synthetic-b', 'need': 'Unresolved method dependency.'}),
        label_map={}, need_progress_sink=sink)


def row(ref, rationale):
    return {'need_refs': [ref], 'disposition': 'repair_dependency', 'signal_refs': [], 'rationale': rationale}


class OfflineCaller:
    def __init__(self, role, decide):
        self.role, self.decide, self.calls = role, decide, []

    def complete_json(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return self.decide(kwargs['payload'], len(self.calls)), self.role.AgentUsage()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('--controller-source', type=Path, required=True)
    parser.add_argument('--role-source', type=Path, required=True)
    args = parser.parse_args()
    before = {str(p): sha(p) for p in (args.controller_source, args.role_source)}
    cmod = isolated(args.controller_source, args.label + '_controller')
    rmod = isolated(args.role_source, args.label + '_role')
    def decide(view, number):
        if number == 1:
            return {'action': 'record_need_dispositions', 'base_hash': view['need_disposition_contract']['base_hash'],
                    'need_dispositions': [row('synthetic-a', 'One scalar reason.')], 'rationale': ['Synthetic first request.']}
        if number == 2:
            return {'action': 'record_need_dispositions', 'base_hash': view['need_disposition_contract']['base_hash'],
                    'need_dispositions': [row('synthetic-a', ['  Exact original reason.  '])], 'rationale': ['Synthetic continuation.']}
        assert number == 3
        return {'action': 'record_deferred', 'rationale': ['Retain the unaddressed need without a capability claim.']}
    offline = OfflineCaller(rmod, decide)
    with TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        engine = object.__new__(SignalEvolutionEngine)
        engine.workspace = SimpleNamespace(experiments_root=temporary / 'experiments')
        c = controller(cmod, rmod.MiningAgentRoleModel(offline), lambda unit: engine._save_mining_need_unit(1, unit))
        result = c.run()
        assert result.state == 'terminal' and len(offline.calls) == 3
        first, continuation, terminal = offline.calls
        assert 'last_invalid_action' not in first['payload']
        assert set(continuation['payload']['last_invalid_action']) == {'action', 'issue'}
        assert 'output_patch_contract' not in continuation['payload']['last_invalid_action']
        assert 'last_invalid_action' not in terminal['payload']
        units = list(temporary.rglob('*.json'))
        assert len(units) == 1
        saved = json.loads(units[0].read_text())
        assert saved['accepted_rows'] == [row('synthetic-a', ['  Exact original reason.  '])]
        assert saved['pending_count'] == 1 and c._pending_need_refs() == ['synthetic-b']
        assert all('choosing one admissible action' in call['system_prompt'] for call in offline.calls)
        disclosure = []
        for name, call in zip(('first', 'ordinary_no_patch_continuation', 'terminal_action_authoring'), offline.calls):
            declaration = call['payload']['need_disposition_contract'].get('row_rationale')
            disclosure.append({'path': name, 'row_rationale_contract': declaration,
                               'system_prompt': call['system_prompt'],
                               'payload_row_contract_present': declaration is not None})
    bad = ['Scalar reason.', '', [], [[]], [''], [' '], [1], [True], ['good', None], None, {'reason': 'no'}]
    rejection = []
    for value in bad:
        c = controller(cmod)
        try:
            c._validate_need_dispositions({'need_dispositions': [row('synthetic-a', value)]}, require_complete=False)
        except cmod.InvalidMiningAction as error:
            rejection.append({'input': value, 'error': str(error)})
        else:
            raise AssertionError(('invalid row accepted', value))
    for value in [['One reason.'], ['One reason.', 'Second reason.'], ['  Exact whitespace.  ']]:
        assert controller(cmod)._validate_need_dispositions({'need_dispositions': [row('synthetic-a', value)]}, require_complete=False) == (row('synthetic-a', value),)
    # Terminal/proposal uses the same whole-backlog row validator, before any
    # separate evidence/terminal preconditions; this is not a successful proposal.
    terminal_rows = [row('synthetic-a', ['First.']), row('synthetic-b', ['Second.'])]
    assert list(controller(cmod)._validate_need_dispositions({'need_dispositions': terminal_rows})) == terminal_rows
    mixed_units = []
    mixed = controller(cmod, sink=lambda unit: mixed_units.append(deepcopy(unit)))
    mixed._record_need_dispositions({'action': 'record_need_dispositions', 'base_hash': mixed._need_state_hash(),
        'need_dispositions': [row('synthetic-a', ['Original valid sibling.']), row('synthetic-b', 'Bad scalar sibling.')],
        'rationale': ['Synthetic mixed sibling control.']})
    assert len(mixed_units) == 1 and mixed_units[0]['accepted_rows'] == [row('synthetic-a', ['Original valid sibling.'])]
    assert len(mixed_units[0]['invalid_rows']) == 1
    assert mixed_units[0]['invalid_rows'][0]['invalid_row'] == row('synthetic-b', 'Bad scalar sibling.')
    assert mixed._pending_need_refs() == ['synthetic-b']
    assert before == {str(p): sha(p) for p in (args.controller_source, args.role_source)}
    report = {'label': args.label, 'source_bindings': before, 'synthetic_offline_role_adapter_callbacks': 3,
        'actual_external_or_fresh_role_calls': 0, 'outgoing_contract_paths': disclosure,
        'nested_bad_shapes_rejected': rejection, 'valid_shapes_whitespace_exact': 3,
        'whole_backlog_terminal_row_validator': True, 'native_no_patch_continuation': True,
        'one_original_sink_unit_after_valid_continuation': True, 'mixed_sibling_unchanged_bad_member_not_wrapped': True,
        'scopes': ['Synthetic empty in-memory store and zero cases; actual Controller and role adapter code, no live-data claim.',
                   'Object.__new__ Engine is used only for the existing pure production sink method; no Engine constructor or full stage is run.',
                   'Three callback requests are offline scripted author values, not API/model/fresh-agent behavior.',
                   'Terminal record_deferred reaches native terminal; whole-backlog proposal/no-pattern row validation is separately exercised without claiming evidence/candidate admission.']}
    output = OWN / (args.label + '-results.json')
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'label': args.label, 'declarations_present': [x['payload_row_contract_present'] for x in disclosure],
        'bad_shapes_rejected': len(rejection), 'sha256': sha(output)}))
