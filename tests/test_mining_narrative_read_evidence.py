"""Whole executed narrative windows survive native decisions; no fresh role claim."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel, MiningRequestBudgetExhausted
from stock_opportunity_agent.research.scheme_evolution import EvolutionControlFlow
from stock_opportunity_agent.research.stage_contracts import json_bytes
from stock_opportunity_agent.llm import get_model
from tests.evolution_runtime_test_support import ScriptedRoleCaller
from tests.scheme_evolution_test_support import make_case, NOW
from tests.test_mining_controller import FACTS_CONTENT

REPO = Path(__file__).resolve().parents[1]


class Captured(EvolutionControlFlow):
    pass


class Contract:
    limits = {'max_structured_corrections': 1, 'structured_reasoning_token_reserve': 0}
    contract_hash = 'a' * 64


class MiningNarrativeReadEvidenceTests(TestCase):
    def controller(self, contents=('First exact statement.', 'Second exact statement.'), *, shared=False, ids=None):
        case = make_case('narrative_owner', 1.1)
        cases = [case]
        if shared:
            cases.append(SimpleNamespace(case_id='same-owner-later', company_id=case.company_id,
                prediction_time=case.prediction_time, ground_truth=case.ground_truth))
        docs = [RawInfoDocument.create(document_id=(ids or [f'narrative-{i}' for i in range(len(contents))])[i],
            company_id=case.company_id, source_type='filing', published_at=NOW, available_at=NOW,
            content=body, metadata={'undisclosed_note': 'UNREAD_PRIVATE_METADATA'}) for i, body in enumerate(contents)]
        docs.append(RawInfoDocument.create(document_id='facts', company_id=case.company_id,
            source_type='company_facts', published_at=NOW, available_at=NOW, content=FACTS_CONTENT))
        controller = LabelAwareMiningController(store=RawInfoStore(documents=docs), model=object(),
            case_pairs=[(f'case-{i+1:03d}', c) for i, c in enumerate(cases)],
            measurable_evidence_manifest={}, signal_catalog=[], seed='discovery', browse_limit=40)
        controller._execute_fetch({'action': 'fetch_evidence', 'rationale': ['Controlled test sources.'],
            'case_refs': [r for r, _ in controller.case_pairs], 'source_families': ['filing', 'company_facts'],
            'max_documents': 10})
        return controller, docs[:-1]

    def read(self, controller, doc, offset=0, length=4000, *, target=None):
        raw = {'action': 'read_span', 'rationale': ['Read exact test window.'],
               'offset': offset, 'length': length}
        raw.update(target or {'document_ref': 'document-' + doc.document_id})
        controller._execute_read_span(raw)

    def page(self, controller):
        return controller._model_view()['narrative_read_evidence']

    def test_two_documents_survive_catalog_and_compute_in_native_payload(self):
        controller, docs = self.controller()
        for doc in docs:
            self.read(controller, doc)
        handoff, ledger = controller.materialization_evidence(), controller.ledger.to_dict()
        controller._execute('inspect_catalog', {'action': 'inspect_catalog', 'scope': 'evidence',
            'rationale': ['Navigate after actual reads.']})
        refs = list(controller._facts)[:2]
        controller._execute_compute({'action': 'compute_statistic', 'rule': 'latest_minus_comparable_prior',
            'fact_refs': refs, 'rationale': ['Compute after narrative reads.']})
        caller = ScriptedRoleCaller([{'action': 'record_deferred', 'rationale': ['End synthetic test.']}])
        MiningAgentRoleModel(caller).next_action(controller._model_view())
        page = caller.calls[0]['payload']['narrative_read_evidence']
        self.assertEqual([r['readable_text'] for r in page['items']], [d.content for d in reversed(docs)])
        self.assertIn('narrative_read_evidence', caller.calls[0]['system_prompt'])
        self.assertEqual(caller.calls[0]['payload']['last_action_result']['action'], 'compute_statistic')
        for row, doc in zip(page['items'], reversed(docs)):
            self.assertEqual(row['content_hash'], doc.content_hash)
            self.assertEqual(row['source_type'], 'filing')
            self.assertEqual(row['available_at'], doc.available_at.isoformat())
            self.assertEqual(row['published_at'], doc.published_at.isoformat())
            self.assertEqual(row['verbatim_hash'], hashlib.sha256(doc.content.encode()).hexdigest())
            self.assertEqual(row['read_targets'][0]['case_refs'], ['case-001'])
        # Working projection cannot alter canonical old units/ledger rows.
        for ref, unit in handoff.items():
            self.assertEqual(controller.materialization_evidence()[ref], unit)
        self.assertEqual(controller.ledger.to_dict()['entries'][:len(ledger['entries'])], ledger['entries'])

    def test_two_maximum_unicode_windows_coexist_and_survive_view_mutation(self):
        controller, docs = self.controller(('长' * 4000, '🧪' * 4000))
        for doc in docs:
            self.read(controller, doc)
        before = controller.materialization_evidence()
        page = self.page(controller)
        self.assertEqual(len(page['items']), 2)
        self.assertLessEqual(json_bytes(page['items']), 40000)
        self.assertEqual({r['readable_text'] for r in page['items']}, {d.content for d in docs})
        page['items'][0]['readable_text'] = 'MUTATED'
        page['items'][0]['read_targets'][0]['case_refs'].append('UNREAD_CASE')
        self.assertEqual(controller.materialization_evidence(), before)
        restored = self.page(controller)
        self.assertNotIn('MUTATED', json.dumps(restored))
        self.assertNotIn('UNREAD_CASE', json.dumps(restored))

    def test_repeat_reorders_counts_and_charges_without_new_source_units(self):
        controller, docs = self.controller()
        for doc in (*docs, docs[0]):
            self.read(controller, doc)
        page = self.page(controller)
        self.assertEqual([r['document_ref'] for r in page['items']], ['document-' + d.document_id for d in docs])
        self.assertEqual([r['read_count'] for r in page['items']], [2, 1])
        self.assertEqual(len(controller._materialization_reads), 2)
        self.assertEqual(controller._browse_used, 3)
        self.assertEqual(sum(e.action == 'read_span' for e in controller.ledger.entries), 3)
        self.assertEqual(self.page(controller), page)

    def test_hidden_unread_and_undisclosed_metadata_do_not_become_working_evidence(self):
        hidden = '<html><head><script>HIDDEN_SCRIPT_SECRET</script></head><body><p>Visible body only.</p></body></html>'
        controller, docs = self.controller((hidden, 'UNREAD_DOCUMENT_BODY'))
        self.assertNotIn('narrative_read_evidence', controller._model_view())
        self.read(controller, docs[0], 0, hidden.index('<body>'))
        self.assertFalse(self.page(controller)['items'][0]['has_readable_text'])
        self.assertEqual(self.page(controller)['items'][0]['readable_text'], '')
        start = hidden.index('Visible body only.')
        self.read(controller, docs[0], start, len('Visible body only.'))
        page = self.page(controller)
        text = json.dumps(page)
        for forbidden in ('HIDDEN_SCRIPT_SECRET', 'UNREAD_DOCUMENT_BODY', 'UNREAD_PRIVATE_METADATA'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(page['items'][0]['readable_text'], 'Visible body only.')

    def test_event_and_document_coalescing_unions_only_actual_read_scopes(self):
        controller, docs = self.controller(shared=True)
        doc = docs[0]
        events = {event.case_ref: ref for ref, event in controller._events.items()
                  if event.document_ref == 'document-' + doc.document_id}
        self.read(controller, doc, target={'event_ref': events['case-001']})
        first = self.page(controller)['items'][0]
        self.assertEqual(first['case_refs'], ['case-001'])
        self.assertEqual(first['read_targets'], [{'target': 'event_ref', 'ref': events['case-001'], 'case_refs': ['case-001']}])
        self.assertNotIn(events['case-002'], json.dumps(first))
        self.read(controller, doc)
        row = self.page(controller)['items'][0]
        self.assertEqual(row['case_refs'], ['case-001', 'case-002'])
        self.assertEqual(row['read_count'], 2)
        self.assertEqual(len(self.page(controller)['items']), 1)
        self.assertEqual(len(row['read_targets']), 2)
        self.assertNotIn(events['case-002'], json.dumps(row['read_targets']))
        self.read(controller, doc, target={'event_ref': events['case-002']})
        self.assertEqual(len(self.page(controller)['items'][0]['read_targets']), 3)
        self.assertEqual(len(controller._materialization_reads), 3)

    def test_count_and_byte_omissions_are_whole_explicit_and_revisitable(self):
        controller, docs = self.controller((' '.join('window' + str(i) for i in range(20)),))
        doc = docs[0]
        for offset in range(13):
            self.read(controller, doc, offset, 5)
        page = self.page(controller)
        self.assertEqual(len(page['items']), 12)
        self.assertEqual(page['counts']['available'], 13)
        self.assertFalse(page['selection_is_exhaustive'])
        self.assertEqual(page['omitted_entries'][0]['offset'], 0)
        self.assertGreater(page['omitted_entries'][0]['required_bytes'], 0)
        self.assertIn('read_span', page['revisit_action'])
        # Long source IDs are legal; disclosure must not clip or let an oversized first unit hide a small one.
        large, docs = self.controller(('small', 'large source id'), ids=['small', 'x' * 41000])
        for doc in docs:
            self.read(large, doc)
        page = self.page(large)
        self.assertEqual([r['readable_text'] for r in page['items']], ['small'])
        self.assertEqual(page['counts']['oversized'], 1)
        self.assertGreater(page['oversized_entries'][0]['required_bytes'], 40000)
        self.assertEqual(page['oversized_entries'][0]['offset'], 0)
        self.assertIn('document_ref', page['oversized_entries'][0])

    def test_identity_native_estimator_and_actual_wire_include_full_working_page(self):
        controller, docs = self.controller(('Hidden Holder Inc. confirms exact conclusion. ' + '长' * 3800,
                                            'Second full window. ' + '🧪' * 3800))
        controller.identity_aliases = ('Hidden Holder Inc.',)
        for doc in docs:
            self.read(controller, doc)
        controller._execute('inspect_catalog', {'action': 'inspect_catalog', 'scope': 'signals', 'rationale': ['Navigate.']})
        canonical = deepcopy(controller.materialization_evidence())
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            captured = []
            def observe(event):
                if event.get('event_type') == 'request_ready':
                    captured.append(json.loads(Path(event['request_path']).read_text())['request'])
                    raise Captured()
            client = StructuredRoleClient(registration=get_model('independent-subagent'), contract=Contract(),
                workspace=root, ledger=ExternalAttemptLedger(root / 'unused.json', max_attempts=1, max_total_cost=.01),
                local_role_exchange=LocalRoleExchange(root / 'exchange', max_calls=1),
                allow_external=False, environ={}, on_progress=observe)
            model = MiningAgentRoleModel(client, identity_aliases=('Hidden Holder Inc.',),
                max_request_tokens=262144, max_total_tokens=1048576, max_calls=10)
            with patch.object(LocalRoleExchange, 'receive', side_effect=AssertionError('must not receive')):
                with self.assertRaises(Captured):
                    model.next_action(controller._model_view())
            wire = captured[0]
            payload = json.loads(wire['messages'][1]['content'])
            cost = json_bytes(wire['messages']) + wire['max_output_tokens']
            self.assertEqual(int(payload['request_budget']['this_request']), cost)
            self.assertEqual(len(payload['narrative_read_evidence']['items']), 2)
            self.assertNotIn('Hidden Holder Inc.', json.dumps(wire))
            self.assertTrue(any('长' * 3800 in row['readable_text'] for row in payload['narrative_read_evidence']['items']))
            self.assertEqual(controller.materialization_evidence(), canonical)
            self.assertFalse(list((root / 'exchange/inbox').glob('*.json')))
            before = list((root / 'requests').glob('*.json'))
            limited = MiningAgentRoleModel(client, max_request_tokens=20000)
            with self.assertRaises(MiningRequestBudgetExhausted):
                limited.next_action(controller._model_view())
            self.assertEqual(list((root / 'requests').glob('*.json')), before)

    def test_actual_old_abc_source_windows_reach_new_page_after_catalog(self):
        frontier = REPO / 'runs/diagnostics/icfr_native_capability_20261023_v1/stage/actual-read-frontier'
        fixed = json.loads((frontier / 'fixed10-evidence.json').read_text())
        bound = json.loads((frontier / 'bindings.json').read_text())['files']
        observation_path = Path(fixed['runtime_observation']['path'])
        self.assertEqual(hashlib.sha256(observation_path.read_bytes()).hexdigest(), bound[str(observation_path)])
        observation = json.loads(observation_path.read_text())
        originals = {(r['content_hash'], r['offset'], r['length']): r for unit in observation['evidence'].values()
                     for r in unit.get('read_windows', ())}
        material = json.loads((REPO / 'runs/diagnostics/mining_capability_frontier_20261023_v1/independent/material-obligations-frozen.json').read_text())
        selected = [row for row in fixed['body_presence_matrix']]
        hashes = {row['content_hash'] for row in selected}
        bindings = {r['content_hash']: r for r in material['source_document_bindings'] if r['content_hash'] in hashes}
        for row in bindings.values():
            self.assertEqual(hashlib.sha256(Path(row['path']).read_bytes()).hexdigest(), row['sha256'])
        docs = [RawInfoDocument.from_dict(json.loads(Path(row['path']).read_text())) for row in bindings.values()]
        dev = {r['case_ref']: r for r in material['dev8']}
        case_refs = sorted({case_ref for r in selected for case_ref in r['case_refs']})
        pairs = [(ref, SimpleNamespace(case_id=dev[ref]['case_id'], company_id=dev[ref]['case_id'].split(':')[0],
                 prediction_time=datetime.fromisoformat(dev[ref]['cutoff']),
                 ground_truth=SimpleNamespace(is_surge=material['authorized_original_group_map'][ref] == 'positive')))
                 for ref in case_refs]
        controller = LabelAwareMiningController(store=RawInfoStore(documents=docs), model=object(),
            case_pairs=pairs, measurable_evidence_manifest={}, signal_catalog=[], seed='discovery')
        controller._execute_fetch({'action': 'fetch_evidence', 'rationale': ['Replay only already-read fixed source windows.'],
            'case_refs': case_refs, 'source_families': ['filing'], 'max_documents': 10})
        by_hash = {d.content_hash: d for d in docs}
        for row in selected:
            self.read(controller, by_hash[row['content_hash']], row['offset'], row['length'])
        controller._execute('inspect_catalog', {'action': 'inspect_catalog', 'scope': 'evidence', 'rationale': ['Original intervening navigation.']})
        caller = ScriptedRoleCaller([{'action': 'record_deferred', 'rationale': ['End bounded old-source regression.']}])
        MiningAgentRoleModel(caller).next_action(controller._model_view())
        page = caller.calls[0]['payload']['narrative_read_evidence']
        self.assertEqual(len(page['items']), 3)
        for row in page['items']:
            original = originals[(row['content_hash'], row['offset'], row['length'])]
            self.assertEqual(row['readable_text'], original['readable_text'])
            self.assertEqual(row['verbatim_hash'], original['verbatim_hash'])
        # Frozen fixed10 proves the old subsequent catalog view contained neither A nor B.
        for row in selected:
            if row['window'] in {'case003-A', 'case003-B'}:
                self.assertEqual(next(p for p in row['presence'] if p['role'] == 9)['exact_full_body_paths'], [])

    def test_byte_cap_discloses_omitted_whole_windows_and_revisit_reorders(self):
        controller, docs = self.controller(('🧪' * 4000,) * 4)
        for doc in docs:
            self.read(controller, doc)
        page = self.page(controller)
        self.assertLess(len(page['items']), 4)
        self.assertLessEqual(json_bytes(page['items']), 40000)
        self.assertTrue(page['omitted_entries'])
        for row in page['items']:
            self.assertEqual(row['readable_text'], '🧪' * 4000)
        missing = page['omitted_entries'][-1]
        self.assertNotIn('readable_text', missing)
        self.assertGreater(missing['required_bytes'], 16000)
        self.read(controller, docs[0])
        newer = self.page(controller)
        self.assertEqual(newer['items'][0]['document_ref'], 'document-' + docs[0].document_id)
        self.assertEqual(newer['items'][0]['read_count'], 2)
        self.assertEqual(controller._browse_used, 5)
        self.assertEqual(len(controller._materialization_reads), 4)

    def test_structured_document_reads_do_not_turn_into_narrative_body_units(self):
        controller, _ = self.controller()
        controller._execute_read_span({'action': 'read_span', 'document_ref': 'document-facts',
            'offset': 0, 'length': 4000, 'rationale': ['Read structured document as a document.']})
        self.assertEqual(self.page(controller)['counts']['available'], 0)
        self.assertEqual(controller._browse_used, 1)
        self.assertIn('document-facts', controller.materialization_evidence())
