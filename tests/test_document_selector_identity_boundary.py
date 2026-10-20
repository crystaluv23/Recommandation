"""Native local selector identity and callback-isolation controls, with no I/O."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, content_sha256
from stock_opportunity_agent.data.resolution import (
    EvidenceResolver, RawInfoRequest, _DocumentSelectionError,
)


STAMP = datetime(2025, 1, 1, tzinfo=timezone.utc)


class FixtureCorpus:
    """Only immutable fixture candidates; never constructs or writes a Store."""
    acquisition_allowed = False

    def __init__(self, *documents):
        self.documents = documents

    def search(self, company_id, *, as_of):
        return [d for d in self.documents if d.company_id == company_id and d.available_at <= as_of]

    def load(self, document_id, *, as_of):
        return next(d for d in self.documents if d.document_id == document_id and d.available_at <= as_of)


def source(*, value=True, capture=False, suffix='one'):
    document = RawInfoDocument.create(document_id='legacy-' + suffix, company_id='issuer', source_type='filing',
        published_at=STAMP, available_at=STAMP, content='Complete retained disclosure ' + suffix + '.',
        metadata={'selection': {'value': value}, 'items': [{'scope': 'original'}]})
    return document.as_capture() if capture else document


class DocumentSelectorIdentityBoundaryTests(TestCase):
    def request(self, limit=1):
        return RawInfoRequest('selector', 'Retain source disclosure.', ('filing',), max_documents=limit)

    def resolve(self, corpus, callback, *, limit=1):
        return EvidenceResolver(corpus).resolve(self.request(limit), company_id='issuer', identity={},
            as_of=STAMP, include_context=True, select_documents=callback)

    def assert_unchanged(self, corpus, before):
        self.assertEqual([canonical_json_hash(d.to_dict()) for d in corpus.documents], before)

    def test_unchanged_and_cloned_returns_remap_to_original_eligible_objects(self):
        for capture in (False, True):
            for clone in (False, True):
                with self.subTest(capture=capture, clone=clone):
                    original = source(capture=capture)
                    corpus = FixtureCorpus(original)
                    seen = []
                    def select(pool, request):
                        self.assertIsNot(pool[0], original)
                        self.assertIsNot(pool[0].metadata['items'], original.metadata['items'])
                        seen.append(pool[0])
                        return (deepcopy(pool[0]) if clone else pool[0],)
                    selected, _, _ = EvidenceResolver(corpus)._local_documents(self.request(), company_id='issuer',
                        identity={}, as_of=STAMP, select_documents=select)
                    self.assertIs(selected[0], original)
                    resolution = self.resolve(corpus, select)
                    self.assertEqual(resolution.status, 'resolved')
                    self.assertEqual(resolution.context_spans[0].exact_text, original.content)
                    self.assertIs(EvidenceResolver(corpus).load_documents(resolution, as_of=STAMP)[0], original)

    def test_python_equal_metadata_clone_changes_are_not_record_identity(self):
        for before_value, after_value in ((True, 1), (1, 1.0)):
            original = source(value=before_value)
            changed = replace(original, metadata={**deepcopy(original.metadata), 'selection': {'value': after_value}})
            self.assertEqual(original, changed)  # The old guard equated these records.
            self.assertNotEqual(canonical_json_hash(original.to_dict()), canonical_json_hash(changed.to_dict()))
            corpus = FixtureCorpus(original)
            before = [canonical_json_hash(original.to_dict())]
            with self.assertRaises(_DocumentSelectionError):
                self.resolve(corpus, lambda pool, request: (changed,))
            self.assert_unchanged(corpus, before)

    def test_selected_nested_mutation_rejects_without_poisoning_legacy_or_capture_store(self):
        for capture in (False, True):
            for before_value, after_value in ((True, 1), (1, 1.0)):
                with self.subTest(capture=capture, before=before_value):
                    original = source(value=before_value, capture=capture)
                    corpus = FixtureCorpus(original)
                    before = [canonical_json_hash(original.to_dict())]
                    def select(pool, request):
                        pool[0].metadata['selection']['value'] = after_value
                        pool[0].metadata['items'][0]['scope'] = 'changed'
                        return pool
                    with self.assertRaises(_DocumentSelectionError):
                        self.resolve(corpus, select)
                    self.assert_unchanged(corpus, before)

    def test_unselected_and_later_callback_alias_mutation_never_reaches_store_or_consumer(self):
        for capture in (False, True):
            first, second = source(capture=capture), source(capture=capture, suffix='two')
            corpus = FixtureCorpus(first, second)
            before = [canonical_json_hash(d.to_dict()) for d in corpus.documents]
            held = []
            def select(pool, request):
                held.extend(pool)
                pool[1].metadata['selection']['value'] = 'unselected mutation'
                return (pool[0],)
            selected, _, _ = EvidenceResolver(corpus)._local_documents(self.request(), company_id='issuer',
                identity={}, as_of=STAMP, select_documents=select)
            self.assertIn(selected[0], corpus.documents)
            self.assertTrue(any(selected[0] is d for d in corpus.documents))
            for alias in held:
                alias.metadata['items'][0]['scope'] = 'later mutation'
                alias.metadata['selection']['value'] = 'later mutation'
            self.assert_unchanged(corpus, before)
            self.assertEqual(selected[0].metadata['items'][0]['scope'], 'original')
            resolution = self.resolve(corpus, lambda pool, request: (pool[0],))
            self.assertEqual(resolution.status, 'resolved')
            self.assert_unchanged(corpus, before)

    def test_wrong_id_body_company_source_or_time_are_local_contract_errors(self):
        changes = (
            {'document_id': 'invented'}, {'company_id': 'other'}, {'source_type': 'news'},
            {'content': 'Changed disclosure.', 'content_hash': content_sha256('Changed disclosure.')},
            {'published_at': STAMP - timedelta(days=1)}, {'available_at': STAMP + timedelta(days=1)},
        )
        for change in changes:
            with self.subTest(change=change):
                original = source()
                corpus = FixtureCorpus(original)
                before = [canonical_json_hash(original.to_dict())]
                with self.assertRaises(_DocumentSelectionError):
                    self.resolve(corpus, lambda pool, request: (replace(pool[0], **change),))
                self.assert_unchanged(corpus, before)

    def test_limit_unique_and_pre_filtered_eligibility_stay_in_force(self):
        eligible = source()
        hidden = replace(source(suffix='hidden'), available_at=STAMP + timedelta(days=1))
        other_source = replace(source(suffix='other'), source_type='news')
        corpus = FixtureCorpus(eligible, hidden, other_source)
        for returned in ((eligible, eligible), (eligible, hidden), (other_source,), (hidden,)):
            with self.subTest(ids=[d.document_id for d in returned]):
                def select(pool, request):
                    self.assertEqual([d.document_id for d in pool], [eligible.document_id])
                    return returned
                with self.assertRaises(_DocumentSelectionError):
                    self.resolve(corpus, select)

    def test_empty_subset_and_legacy_json_policy_remain_compatible(self):
        original = replace(source(), metadata={'legacy_tuple': (True, 1, 1.0)})
        corpus = FixtureCorpus(original)
        resolved = self.resolve(corpus, lambda pool, request: (deepcopy(pool[0]),))
        self.assertEqual(resolved.status, 'resolved')
        empty = self.resolve(corpus, lambda pool, request: ())
        self.assertEqual(empty.status, 'unresolved')
        self.assertFalse(empty.documents)
        self.assertEqual(original.metadata, {'legacy_tuple': (True, 1, 1.0)})

    def test_callback_failure_remains_contract_error_not_domain_unavailability(self):
        corpus = FixtureCorpus(source())
        def broken(pool, request):
            raise RuntimeError('invalid local selector')
        with self.assertRaisesRegex(_DocumentSelectionError, 'Local document selection failed'):
            self.resolve(corpus, broken)
        with self.assertRaises(_DocumentSelectionError):
            self.resolve(corpus, lambda pool, request: ({'document_id': 'not-a-document'},))
