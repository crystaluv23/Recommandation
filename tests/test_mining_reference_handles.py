"""Lossless large-graph wire handles, typed patching and native cache accounting."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_state_patch import apply_state_patch
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel, MiningRequestBudgetExhausted, _MiningReferenceHandles
from stock_opportunity_agent.research.stage_contracts import json_bytes
from tests.test_mining_controller import _controller, _fixture_store
from tests.test_mining_narrative_read_evidence import Contract


def graph(offset=0):
    """Construct typed opaque identities without business labels or real sources."""
    return {"known_fact_refs": [f"fact-{i + offset:016x}" for i in range(400)],
            "known_relation_refs": [f"relation-{i + offset:016x}" for i in range(100)]}


def client(root):
    """Use the native local exchange without any provider fallback."""
    return StructuredRoleClient(registration=get_model('independent-subagent'),
        contract=Contract(), workspace=root / 'native',
        ledger=ExternalAttemptLedger(root / 'unused.json', max_attempts=1, max_total_cost=.01),
        local_role_exchange=LocalRoleExchange(root / 'exchange', max_calls=5),
        allow_external=False, environ={})


class MiningReferenceHandleTests(TestCase):
    def test_small_graph_and_empty_default_keep_existing_wire(self):
        for view in ({}, {"known_fact_refs": ["fact-0000000000000001"]},
                     {"known_fact_refs": ["fact-" + "a" * 16] * 2}):
            with self.subTest(view=view):
                codec = _MiningReferenceHandles(view)
                self.assertFalse(codec.forward)
                self.assertEqual(codec.payload(view), view)
        below = {"known_fact_refs": ["fact-" + f"{i:016x}" for i in range(330)]}
        above = {"known_fact_refs": below['known_fact_refs'] + ['fact-ffffffffffffffff'] * 10}
        # Activation is based on the complete compact index, not request caps.
        for view in (below, above):
            codec = _MiningReferenceHandles(view)
            expected = len(json.dumps({k: view.get(k, []) for k in
                ('known_fact_refs', 'known_relation_refs')}, separators=(',', ':')).encode()) > 8192
            self.assertEqual(bool(codec.forward), expected)

    def test_structural_graph_roundtrip_preserves_every_literal_and_order(self):
        view = graph(); f, g = view['known_fact_refs'][:2]; r = view['known_relation_refs'][0]
        view.update(computed_statistics={'items': [{'relation_ref': r,
            'relation': {'relation_ref': r, 'fact_refs': [g, f], 'value': f},
            'operands': [{'fact_ref': g, 'value': f, 'exact_span': f}, {'fact_ref': f, 'value': '长'}]}]},
            comparison_progress={'items': [{'groups': {'latest': {'case': {'fact_ref': f}}}}]},
            structured_read_progress={'items': [{'fact_ref': f, 'masked': f}]},
            narrative_read_evidence={'items': [{'readable_text': f, 'raw_span': r}]},
            last_action_result={'ref': f, 'fact_refs': [g, f], 'rationale': [f]},
            candidate={'evidence_refs': [r, g], 'measurement': {'semantic_condition': f}})
        original = deepcopy(view); codec = _MiningReferenceHandles(view); wire = codec.payload(view)
        metadata = wire.pop('reference_handles')
        self.assertEqual(metadata['scope_hash'], codec.scope_hash)
        self.assertEqual(codec.transform(wire, restore=True), original)
        self.assertEqual(view, original)
        row = wire['computed_statistics']['items'][0]
        self.assertEqual(row['relation']['fact_refs'], [codec.forward[g], codec.forward[f]])
        self.assertEqual(row['relation']['value'], f)
        self.assertEqual(row['operands'][0]['exact_span'], f)
        self.assertEqual(wire['narrative_read_evidence'], view['narrative_read_evidence'])
        self.assertEqual(wire['last_action_result']['rationale'], [f])
        self.assertLess(json_bytes(wire), json_bytes(view))

    def test_same_shape_different_graph_has_distinct_cache_scope_and_aliases(self):
        first, other = graph(), graph(10000)
        a, b = _MiningReferenceHandles(first), _MiningReferenceHandles(other)
        self.assertNotEqual(a.scope_hash, b.scope_hash)
        self.assertNotEqual(canonical_json_hash(a.payload(first)), canonical_json_hash(b.payload(other)))
        self.assertNotEqual(a.payload(first)['known_fact_refs'], b.payload(other)['known_fact_refs'])
        reordered = {key: list(reversed(values)) for key, values in first.items()}
        self.assertEqual(a.forward, _MiningReferenceHandles(reordered).forward)

    def test_original_json_and_semantic_values_are_opaque_even_with_reference_keys(self):
        view = graph(); f = view['known_fact_refs'][0]
        original = {'fact_ref': f, 'threshold': {'field': 'fact_ref', 'value': f}}
        view.update(meta_memory_disclosures=[{'content': original}],
            slow_method_memory=original, signal_catalog=[{'original': {'spec': original}}],
            catalog_observations={'items': [{'scope': 'memory', 'result': original}]},
            candidate={'measurement': original},
            computed_statistics={'items': [{'operands': [{'fact_ref': f, 'value': original}]}]})
        codec = _MiningReferenceHandles(view); wire = codec.payload(view)
        for key in ('meta_memory_disclosures', 'slow_method_memory', 'signal_catalog',
                    'catalog_observations', 'candidate'):
            self.assertEqual(wire[key], view[key])
        operand = wire['computed_statistics']['items'][0]['operands'][0]
        self.assertEqual(operand['fact_ref'], codec.forward[f])
        self.assertEqual(operand['value'], original)
        self.assertEqual(codec.transform({'threshold': {'field': 'fact_ref', 'value': f}}),
                         {'threshold': {'field': 'fact_ref', 'value': f}})

    def test_index_type_not_ref_spelling_and_whole_semantic_patch_stays_literal(self):
        view = {'known_fact_refs': [f'opaque-fact-{i:016x}' for i in range(400)]}
        codec = _MiningReferenceHandles(view); f = view['known_fact_refs'][0]
        self.assertEqual(codec.transform({'fact_ref': codec.forward[f]}, restore=True), {'fact_ref': f})
        literal = {'fact_ref': codec.forward[f]}
        delta = {'operations': [{'op': 'replace', 'path': 'candidate.measurement', 'value': literal}]}
        self.assertEqual(codec.transform(delta, restore=True), delta)

    def test_manifest_and_default_catalog_originals_keep_identical_repeated_projections(self):
        view = graph(); original = {'fact_ref': view['known_fact_refs'][0]}
        for action in ('inspect_catalog', 'inspect_manifest'):
            with self.subTest(action=action):
                value = {**view, 'last_action_result': {'action': action, 'scope': None, 'result': original},
                         'catalog_observations': {'items': [{'scope': 'signals', 'result': original}]}}
                wire = _MiningReferenceHandles(value).payload(value)
                self.assertEqual(wire['last_action_result'], value['last_action_result'])
                self.assertEqual(wire['catalog_observations'], value['catalog_observations'])

    def test_namespace_collision_and_unknown_wrong_kind_duplicate_keys(self):
        view = graph(); before = _MiningReferenceHandles(view)
        view['literal'] = before.prefix + 'f0 in a literal source object key'
        view['original'] = {before.prefix + 'f1': 'keep'}
        codec = _MiningReferenceHandles(view)
        self.assertNotEqual(codec.prefix, before.prefix)
        self.assertEqual(codec.payload(view)['literal'], view['literal'])
        self.assertEqual(codec.payload(view)['original'], view['original'])
        f = view['known_fact_refs'][0]; r = view['known_relation_refs'][0]
        for field, alias in (('fact_ref', codec.forward[r]), ('relation_ref', codec.forward[f]),
                             ('evidence_refs', codec.prefix + 'ffff')):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                codec.transform({field: alias}, restore=True)
        with self.assertRaisesRegex(ValidationError, 'duplicate key'):
            codec.transform({'fact_refs': {f: 1, codec.forward[f]: 2}}, restore=True)
        # Literal values containing an alias are not implicitly source refs.
        self.assertEqual(codec.transform({'rationale': [codec.forward[f]], 'value': codec.forward[f]},
            restore=True), {'rationale': [codec.forward[f]], 'value': codec.forward[f]})

    def test_typed_patch_keeps_canonical_hash_paths_and_restores_only_reference_values(self):
        view = graph(); f = view['known_fact_refs'][0]
        base = {'candidate': {'evidence_refs': [f]}, 'rationale': ['Old.']}
        contract = {'schema_version': 'structured-state-patch-v1', 'base_hash': canonical_json_hash(base),
            'allowed_operations': [{'op': 'append', 'path': 'candidate.evidence_refs',
                                    'descendants': False, 'exact_value': f},
                                   {'op': 'replace', 'path': 'rationale[0]', 'descendants': False}],
            'append_limits': {}, 'exact_append_limits': {'candidate.evidence_refs': {f: 1}},
            'identity_guards': [{'path': 'candidate', 'field': 'evidence_refs', 'value': [f]}]}
        view['last_invalid_action'] = {'invalid_output': base, 'output_patch_contract': contract,
            'validation_feedback': {'obligations': [{'item_id_field': 'fact_ref', 'item_id': f,
                'allowed_append_values': {'candidate.evidence_refs': [f]}}]}}
        codec = _MiningReferenceHandles(view); wire = codec.payload(view); issued = wire['last_invalid_action']
        self.assertEqual(issued['output_patch_contract']['base_hash'], contract['base_hash'])
        self.assertEqual(issued['output_patch_contract']['identity_guards'][0]['value'], [codec.forward[f]])
        self.assertEqual(codec.transform({k: v for k, v in wire.items() if k != 'reference_handles'},
            restore=True), view)
        delta = {'base_hash': contract['base_hash'], 'operations': [
            {'op': 'append', 'path': 'candidate.evidence_refs', 'value': codec.forward[f]},
            {'op': 'replace', 'path': 'rationale[0]', 'value': codec.forward[f]}]}
        restored = codec.transform(delta, restore=True)
        self.assertEqual(restored['operations'][0]['value'], f)
        self.assertEqual(restored['operations'][1]['value'], codec.forward[f])
        changed = apply_state_patch(base, restored, contract=contract)
        self.assertEqual(changed['candidate']['evidence_refs'], [f, f])
        self.assertEqual(changed['rationale'], [codec.forward[f]])

    def test_native_identity_wire_budget_inverse_cache_and_fresh_reconstruction(self):
        with TemporaryDirectory() as directory, patch('socket.socket.connect', side_effect=AssertionError('network')):
            root = Path(directory)
            cases, store = _fixture_store()
            view = {**_controller(store, cases, object(), seed='discovery')._model_view(), **graph()}
            f = view['known_fact_refs'][0]
            view['source_text'] = 'Hidden Holder Inc. 原文 ' + f
            original = deepcopy(view)
            model = MiningAgentRoleModel(client(root), identity_aliases=('Hidden Holder Inc.',),
                max_request_tokens=262144, max_total_tokens=1048576, max_calls=5)
            with self.assertRaises(LocalRoleRequestPending) as pending:
                model.next_action(view)
            p = pending.exception.pending
            raw = Path(p['inbox_path']).read_bytes(); inbox = json.loads(raw)
            payload = json.loads(inbox['messages'][1]['content'])
            cost = json_bytes(inbox['messages']) + inbox['max_output_tokens']
            self.assertEqual(int(payload['request_budget']['this_request']), cost)
            self.assertNotIn('Hidden Holder Inc.', json.dumps(inbox))
            self.assertIn(f, payload['source_text'])
            alias = payload['known_fact_refs'][0]
            reply = {'action': 'read_span', 'fact_ref': alias, 'rationale': ['Read current binding.']}
            Path(p['outbox_path']).write_text(json.dumps(reply))
            model.caller.local_role_exchange.submit(p['request_hash'], agent_id='explicit-offline-handle-test')
            expected = {**reply, 'fact_ref': f}
            self.assertEqual(model.next_action(view), expected)
            self.assertEqual(model.reserved_tokens, cost)
            rebuilt = MiningAgentRoleModel(client(root), identity_aliases=('Hidden Holder Inc.',),
                max_request_tokens=262144, max_total_tokens=1048576, max_calls=5)
            self.assertEqual(rebuilt.next_action(view), expected)
            self.assertEqual(Path(p['inbox_path']).read_bytes(), raw)
            self.assertEqual(rebuilt.reserved_tokens, cost)
            self.assertEqual(view, original)
            self.assertEqual(len(list((root / 'exchange/receipts').glob('*.json'))), 1)
            limited = MiningAgentRoleModel(client(root), max_request_tokens=100)
            with patch.object(LocalRoleExchange, 'receive', side_effect=AssertionError('must not receive')):
                with self.assertRaises(MiningRequestBudgetExhausted):
                    limited.next_action(view)
            self.assertEqual(limited.reserved_calls, 0)

    def test_actual_next_payload_lossless_projection_retains_all_4221_refs(self):
        path = Path(__file__).resolve().parents[1] / 'runs/diagnostics/mining_catalog_working_context_20261023_v1/terminal-boundary/blocked-offline-native-estimate.json'
        view = json.loads(path.read_text())['payload']; codec = _MiningReferenceHandles(view)
        encoded = codec.payload(view); original_hash = canonical_json_hash(view)
        self.assertEqual(len(codec.forward), 4221)
        self.assertEqual(len(encoded['known_fact_refs']), 2879)
        self.assertEqual(len(encoded['known_relation_refs']), 1342)
        self.assertEqual(codec.transform({k: v for k, v in encoded.items() if k != 'reference_handles'},
            restore=True), view)
        self.assertEqual(canonical_json_hash(view), original_hash)
        self.assertLess(json_bytes(encoded), json_bytes(view) - 30000)

