"""Native need-row authoring disclosure; no production roles or source changes."""
from copy import deepcopy
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_core import AgentUsage
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController, InvalidMiningAction
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
from stock_opportunity_agent.research import stage_contracts

CONTRACT = ('rationale must be a non-empty array of nonblank strings; '
            'a single reason uses a one-element array.')


class RecordingCaller:
    """Observe the real role adapter output without invoking any model service."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def complete_json(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        response = self.responses.pop(0)
        return (response(kwargs['payload']) if callable(response) else response), AgentUsage()


def row(ref='a', rationale=None):
    return {'need_refs': [ref], 'disposition': 'deferred_measurement', 'signal_refs': [],
            'rationale': ['Retain the fixture need.'] if rationale is None else rationale}


def controller(model=None, sink=None):
    return LabelAwareMiningController(store=RawInfoStore(), model=model, case_pairs=(),
        measurable_evidence_manifest={}, signal_catalog=(), seed='hypothesis',
        backlog_needs=({'need_ref': 'a'}, {'need_ref': 'b'}), label_map={}, need_progress_sink=sink)


def action(view, rows):
    return {'action': 'record_need_dispositions', 'base_hash': view['need_disposition_contract']['base_hash'],
            'need_dispositions': rows, 'rationale': ['Record one fixture intent.']}


class NeedRowAuthoringContractTests(TestCase):
    def test_actual_first_and_correction_requests_share_explicit_nested_contract(self):
        saved = []
        caller = RecordingCaller([
            lambda view: action(view, [row(rationale='A scalar fixture reason.')]),
            lambda view: action(view, [row()]),
            {'action': 'record_deferred', 'rationale': ['Stop this fixture without claiming completion.']},
        ])
        tool = controller(MiningAgentRoleModel(caller), saved.append)
        result = tool.run()
        self.assertEqual(len(caller.requests), 3)
        for request in caller.requests:
            self.assertIn(CONTRACT, request['system_prompt'])
            self.assertEqual(request['payload']['need_disposition_contract'].get('row_rationale'), CONTRACT)
        correction = caller.requests[1]['payload']
        self.assertIn(CONTRACT, correction['last_invalid_action']['issue'])
        self.assertNotIn('output_patch_contract', correction['last_invalid_action'])
        self.assertEqual(correction['need_disposition_contract']['pending_count'], 2)
        self.assertEqual(saved[0]['accepted_rows'], [row()])
        self.assertEqual(result.pending_need_refs, ('b',))
        self.assertEqual(len(saved), 1)

    def test_actual_terminal_row_authoring_uses_the_same_contract(self):
        terminal = {'action': 'record_no_pattern', 'need_dispositions': [row(), row('b')],
                    'rationale': ['Fixture terminal row shape only.']}
        caller = RecordingCaller([terminal])
        tool = controller(MiningAgentRoleModel(caller))
        result = tool.model.next_action(tool._model_view())
        self.assertEqual(result, terminal)
        self.assertIn(CONTRACT, caller.requests[0]['system_prompt'])
        self.assertEqual(caller.requests[0]['payload']['need_disposition_contract'].get('row_rationale'), CONTRACT)
        self.assertEqual(tool._validate_need_dispositions(result), tuple(terminal['need_dispositions']))

    def test_runtime_description_matches_shared_pure_declaration(self):
        self.assertEqual(getattr(stage_contracts, 'NEED_ROW_RATIONALE_CONTRACT', None), CONTRACT)
        tool = controller()
        before = tool._need_state_hash()
        self.assertEqual(tool._model_view()['need_disposition_contract'].get('row_rationale'), CONTRACT)
        self.assertEqual(tool._need_state_hash(), before)

    def test_scalar_empty_nested_and_wrong_members_stay_invalid_without_progress(self):
        for value in ('one reason', '', [], [''], ['  '], [['nested']], [1], [None], True, 7):
            with self.subTest(value=value):
                saved = []
                tool = controller(sink=saved.append)
                before = tool._need_state_hash()
                with self.assertRaises(InvalidMiningAction) as caught:
                    tool._record_need_dispositions(action(tool._model_view(), [row(rationale=value)]))
                self.assertIn(CONTRACT, str(caught.exception))
                self.assertEqual(tool._need_state_hash(), before)
                self.assertEqual(tool._pending_need_refs(), ['a', 'b'])
                self.assertEqual(saved, [])

    def test_valid_siblings_keep_original_unit_and_hash_semantics(self):
        saved = []
        tool = controller(sink=saved.append)
        before = tool._need_state_hash()
        tool._record_need_dispositions(action(tool._model_view(), [row(), row('b', 'bad scalar')]))
        self.assertEqual(len(saved), 1)
        unit = saved[0]
        self.assertEqual(unit['accepted_rows'], [row()])
        self.assertEqual(unit['base_hash'], before)
        self.assertEqual(unit['result_hash'], tool._need_state_hash())
        self.assertEqual(unit['pending_count'], 1)
        self.assertEqual(unit['invalid_rows'][0]['row_index'], 1)
        self.assertNotIn('row_rationale', unit)
        self.assertEqual(set(unit), {'schema_version', 'backlog_hash', 'axis_id', 'seed', 'base_hash',
                                    'result_hash', 'accepted_rows', 'pending_count', 'invalid_rows'})
        self.assertEqual(tool._pending_need_refs(), ['b'])

    def test_existing_top_level_scalar_wrap_does_not_wrap_a_need_row(self):
        caller = RecordingCaller([{'action': 'record_need_dispositions', 'rationale': 'Top-level scalar.',
            'need_dispositions': [row(rationale='Nested scalar remains invalid.')]}])
        tool = controller(MiningAgentRoleModel(caller))
        result = tool._decide(tool._model_view())
        self.assertEqual(result['rationale'], ['Top-level scalar.'])
        self.assertIsInstance(result['need_dispositions'][0]['rationale'], str)
        self.assertEqual(tool.ledger.entries[0].action, 'mechanical_repair')

    def test_legacy_h1_existing_all_rationale_obligation_is_unchanged(self):
        from stock_opportunity_agent.research.evolution_signal_roles import _SIGNAL_MINING_HYPOTHESES_V3_OUTPUT
        self.assertIn('Every rationale field is a non-empty array of short strings.',
                      _SIGNAL_MINING_HYPOTHESES_V3_OUTPUT)
