"""S4 and the real S5 handoff share case-bound readable-source prerequisites."""
from dataclasses import replace
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research.mining_controller import InvalidMiningAction
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from tests import test_mining_controller as support


def execute(controller, action, **kwargs):
    """Use native action shape validation and the native tool boundary."""
    raw = dict(action=action, rationale=['Offline citation-prerequisite control.'], **kwargs)
    controller._validate_action_shape(raw)
    return controller._execute(action, raw)


def candidate(ref, family='news'):
    """Return an explicitly synthetic measurement; never a production answer."""
    return {'measurement': {'observable': 'synthetic_dated_order', 'value_kind': 'boolean',
        'normalization': 'confirmed order disclosure within supplied dated source',
        'predicate': {'modality': 'narrative', 'source_families': [family],
            'semantic_condition': 'a confirmed purchase agreement'}},
        'falsifiers': [{'condition': 'only a hypothetical agreement',
            'expected_observation': 'not confirmed'}], 'evidence_refs': [ref]}


def fixture(*, hidden=False, shared=False, model=None):
    """Build real fetched graph nodes with independently scoped observations."""
    interface = support.NarrativeInterfaceTests()
    cases, store = interface._fixture()
    if hidden:
        documents = list(store.documents)
        original = next(d for d in documents if d.document_id == 'narr_news_1')
        documents.remove(original)
        documents.append(RawInfoDocument.create(document_id=original.document_id,
            company_id=original.company_id, source_type='sec_filing',
            published_at=original.published_at, available_at=original.available_at,
            content='<script>UNREAD_HIDDEN</script><p>Visible confirmed purchase agreement.</p>'))
        store = RawInfoStore(documents=documents)
    if shared:
        cases[1] = replace(cases[1], company_id=cases[0].company_id)
        store = RawInfoStore(documents=[d for d in store.documents
            if d.company_id == cases[0].company_id])
    controller = interface._controller(model or object(), cases, store, seed='discovery')
    if model is None:
        execute(controller, 'fetch_evidence', case_refs=['case-001', 'case-002'],
            source_families=['news', 'company_facts'] + (['filing'] if hidden else []),
            max_documents=2)
    return controller


def event(controller, case_ref):
    """Select only the current synthetic runtime case binding."""
    return next(e for e in controller._events.values() if e.case_ref == case_ref)


class NarrativeCitationReadinessTests(TestCase):
    def test_unrelated_read_cannot_authorize_an_unread_citation(self):
        controller = fixture()
        execute(controller, 'read_span', event_ref=event(controller, 'case-001').event_ref,
            offset=0, length=4000)
        ref = event(controller, 'case-002').event_ref
        self.assertNotIn(ref, controller.materialization_evidence())
        count = len(controller.ledger.entries)
        with self.assertRaisesRegex(InvalidMiningAction, 'executed readable window'):
            execute(controller, 'propose_candidate', candidate=candidate(ref))
        self.assertEqual(controller._state, 'evidence_ready')
        self.assertEqual(len(controller.ledger.entries), count)

    def test_matching_document_read_supports_event_and_exact_s5_unit(self):
        for target in ('event_ref', 'document_ref'):
            with self.subTest(target=target):
                controller = fixture()
                item = event(controller, 'case-002')
                ref = getattr(item, target)
                execute(controller, 'read_span', document_ref=item.document_ref, offset=0, length=4000)
                result = execute(controller, 'propose_candidate', candidate=candidate(ref))
                self.assertEqual(result[0], 'candidate')
                rows = SignalEvolutionEngine._controller_evidence_excerpts(
                    candidate(ref), controller.materialization_evidence())
                row = next(row for row in rows if row.get('ref') == ref)
                self.assertEqual(row['read_windows'][0]['case_refs'], ['case-002'])
                self.assertIn('purchase', row['read_windows'][0]['readable_text'])

    def test_hidden_only_window_cannot_borrow_another_read(self):
        controller = fixture(hidden=True)
        execute(controller, 'read_span', event_ref=event(controller, 'case-001').event_ref,
            offset=0, length=4000)
        item = event(controller, 'case-002')
        execute(controller, 'read_span', event_ref=item.event_ref, offset=0, length=28)
        with self.assertRaisesRegex(InvalidMiningAction, 'executed readable window'):
            execute(controller, 'propose_candidate', candidate=candidate(item.event_ref, 'filing'))
        execute(controller, 'read_span', event_ref=item.event_ref, offset=31, length=200)
        self.assertEqual(execute(controller, 'propose_candidate',
            candidate=candidate(item.event_ref, 'filing'))[0], 'candidate')

    def test_event_read_does_not_broadcast_to_another_case_on_shared_document(self):
        controller = fixture(shared=True)
        first, second = event(controller, 'case-001'), event(controller, 'case-002')
        self.assertEqual(first.document_ref, second.document_ref)
        execute(controller, 'read_span', event_ref=first.event_ref, offset=0, length=4000)
        with self.assertRaisesRegex(InvalidMiningAction, 'executed readable window'):
            execute(controller, 'propose_candidate', candidate=candidate(second.event_ref))
        execute(controller, 'read_span', document_ref=second.document_ref, offset=0, length=4000)
        self.assertEqual(execute(controller, 'propose_candidate',
            candidate=candidate(second.event_ref))[0], 'candidate')

    def test_native_invalid_feedback_allows_read_then_same_candidate_without_late_s5_failure(self):
        def read_first(view):
            return {'action': 'read_span', 'event_ref': sorted(view['known_event_refs'])[0],
                'offset': 0, 'length': 4000, 'rationale': ['Read the first source.']}
        def propose_second(view):
            return {'action': 'propose_candidate',
                'candidate': candidate(sorted(view['known_event_refs'])[1]),
                'rationale': ['Use the second source.']}
        def correct_by_read(view):
            self.assertIn('executed readable window', view['last_invalid_action']['issue'])
            return {'action': 'read_span', 'event_ref': sorted(view['known_event_refs'])[1],
                'offset': 0, 'length': 4000, 'rationale': ['Read the cited source before proposing.']}
        model = support.ScriptedMiningDecisionModel([
            {'action': 'fetch_evidence', 'case_refs': ['case-001', 'case-002'],
                'source_families': ['news', 'company_facts'], 'max_documents': 2,
                'rationale': ['Fetch both classes.']}, read_first, propose_second,
            correct_by_read, propose_second])
        controller = fixture(model=model)
        result = controller.run()
        self.assertEqual(result.terminal_kind, 'candidate')
        self.assertEqual(result.model_calls, 5)
        self.assertFalse(model.actions)
        self.assertEqual(sum(e.action == 'propose_candidate' and not e.note for e in result.ledger), 1)
