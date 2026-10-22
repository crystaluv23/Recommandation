"""Offline controls for reading authority, budgets and executor dependencies."""

import json
import re
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import EvidenceResolver, RawInfoRequest, RawInfoResolution
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.research.signal_source_reading import SignalSourceSession, catalog_signature
from stock_opportunity_agent.research.scheme_evolution import RuntimeBudgetExceeded
from stock_opportunity_agent.signal_library import FrozenSignalRegistry, SignalExecutor, SignalExecutionStatus
from tests.test_signal_edge_correction import AS_OF, CLAUSE, document, signal_input, result
from tests.test_mining_fact_semantics import document as fact_document, pair_rows


def sources(count=11):
    return tuple(RawInfoDocument.create(document_id=f"source-{i:02d}", company_id="issuer",
        source_type="filing", published_at=AS_OF - timedelta(days=i), available_at=AS_OF - timedelta(days=i),
        content=f"Disclosure {i:02d}. " + (CLAUSE if i == 10 else "Guidance coverage notice without any revised amounts.")) for i in range(count))


def item_for(docs):
    return replace(signal_input(docs[0]), documents=docs[:10], eligible_documents=docs)


def catalog_groups(catalog, card):
    """Independently decode the public page-local coordinate representation."""
    if 'fact_group_terms' not in catalog:
        return card.get('fact_groups', [])
    return [dict(zip(catalog['fact_group_fields'],
        [catalog['fact_group_terms'][value] for value in row[:4]] + row[4:], strict=True))
        for row in card.get('fact_groups', [])]


class ReadingCaller:
    """Scripted transport only; no fresh-model or semantic acceptance claim."""

    def __init__(self, wanted_hash, *, bad_first=False, wrong_evidence=False):
        self.wanted_hash = wanted_hash
        self.calls = []
        self.bad_first = bad_first
        self.wrong_evidence = wrong_evidence

    def complete_json(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        p = kwargs["payload"]
        if "source_catalog" in p:
            if kwargs["stage"].endswith("next"):
                action = {"finalize": True}
            else:
                card = next(c for c in p["source_catalog"]["cards"] if c["content_hash"] == self.wanted_hash)
                action = {"reads": [{"source_ref": card["source_ref"], "offset": 0,
                                      "length": card["coordinate_length"]}]}
            return action, AgentUsage(llm_calls=1, tokens=30)
        refs = p["batch_signal_refs"]
        rows = []
        for ref in refs:
            view = next(r for r in p["source_projection"] if r["content_hash"] == self.wanted_hash)
            projection = "invented" if self.wrong_evidence else view["projection_id"]
            row = result(ref, projection, "Disclosure 00." if self.wrong_evidence else CLAUSE)
            if self.bad_first and not kwargs["stage"].endswith("correction"):
                row["result"]["version"] = 999
            rows.append(row)
        return {"results": rows}, AgentUsage(llm_calls=1, tokens=30)


class HeadingCaller(ReadingCaller):
    """Script only catalog-based navigation; this is not a fresh-model claim."""

    def complete_json(self, **kwargs):
        if 'source_catalog' not in kwargs['payload']:
            return super().complete_json(**kwargs)
        self.calls.append(deepcopy(kwargs))
        if kwargs['stage'].endswith('next'):
            return {'finalize':True}, AgentUsage(llm_calls=1,tokens=30)
        card, group=next((c,g) for c in kwargs['payload']['source_catalog']['cards']
            for g in c.get('section_groups',()) if 'Guidance discussion' in g['heading'])
        return {'reads':[{'source_ref':card['source_ref'],'offset':max(0,group['offset']-100),
                          'length':1500}]}, AgentUsage(llm_calls=1,tokens=30)


def executor(docs, caller):
    item = item_for(docs)
    snapshot = FrozenSignalRegistry(version=1, registry_hash=canonical_json_hash([item.spec.to_dict()]),
        specs=(item.spec,), skills={item.spec.ref: item.skill})
    return SignalExecutor(snapshot, RawInfoStore(documents=docs), llm_runner=StructuredLLMSignalRunner(caller))


class SignalSourceReadingTests(TestCase):
    def test_narrative_sections_share_normalized_coordinates_with_actual_reads(self):
        content = '<ix:header>' + 'hidden metadata ' * 5000 + '</ix:header><p>Cover.</p>'
        content += '<p>' + 'Background context. ' * 4000 + '</p><h2>ITEM 7. Guidance discussion.</h2><p>' + CLAUSE + '</p>'
        d = RawInfoDocument.create(document_id='long-filing', company_id='issuer',source_type='filing',
            published_at=AS_OF, available_at=AS_OF, content=content)
        s = SignalSourceSession(item_for((d,)), AS_OF)
        catalog = s.catalog()
        card = catalog['cards'][0]
        section = next(g for g in card['section_groups'] if 'ITEM 7.' in g['heading'])
        self.assertGreater(section['offset'], 32000)
        self.assertNotEqual(section['offset'], content.index('ITEM 7.'))
        text = s.views[card['source_ref']][0]
        self.assertTrue(text[section['offset']:].startswith('ITEM 7.'))
        self.assertEqual(s.documents, ())
        self.assertEqual(s.rows, [])
        self.assertEqual(s.characters, len(card['preview']) + sum(len(g['heading']) for g in card['section_groups']))
        out = s.apply({'reads':[{'source_ref':card['source_ref'],'offset':section['offset']-100,'length':1000}]})
        self.assertIn(CLAUSE, ' '.join(r['exact_text'] for r in out['source_projection']))
        self.assertEqual(s.documents, (d,))
        self.assertTrue(card['section_index_is_partial'])

    def test_narrative_section_pages_use_existing_exchange_budget_and_do_not_recharge(self):
        text = ' '.join(f'ITEM {i}. Topic {i}. ' + 'Context disclosure. ' * 12 for i in range(31))
        d = RawInfoDocument.create(document_id='many-sections',company_id='issuer',source_type='filing',
            published_at=AS_OF, available_at=AS_OF,content=text)
        s = SignalSourceSession(item_for((d,)), AS_OF)
        card = s.catalog()['cards'][0]
        self.assertEqual(card['section_group_count'],31)
        self.assertEqual(len(card['section_groups']),20)
        self.assertEqual(card['omitted_section_group_count'],11)
        before=s.characters
        self.assertEqual(s.catalog()['cards'][0],card)
        self.assertEqual(s.characters,before)
        page=s.apply({'catalog_source_ref':card['source_ref'],'group_cursor':20})
        self.assertEqual(len(page['section_groups']),11)
        self.assertIsNone(page['next_group_cursor'])
        self.assertEqual(s.characters,before+sum(len(g['heading']) for g in page['section_groups']))
        self.assertEqual(s.trace()['navigation_characters'],s.characters-len(card['preview']))
        target=page['section_groups'][-1]
        s.apply({'reads':[{'source_ref':card['source_ref'],'offset':target['offset'],'length':target['length']}]})
        self.assertEqual(s.exchanges,2)
        with self.assertRaises(ValidationError):
            s.apply({'catalog_source_ref':card['source_ref'],'group_cursor':0})

    def test_narrative_heading_page_overflow_rejects_all_metadata_atomically(self):
        text='B. '*11000 + ' '.join(f'ITEM {i}. Topic {i}. ' + 'Context disclosure. '*12 for i in range(25))
        d=RawInfoDocument.create(document_id='heading-budget',company_id='issuer',source_type='filing',
            published_at=AS_OF,available_at=AS_OF,content=text)
        s=SignalSourceSession(item_for((d,)),AS_OF)
        card=s.catalog()['cards'][0]
        length=(32000-s.characters-1)//3*3
        s.apply({'reads':[{'source_ref':card['source_ref'],'offset':0,'length':length}]})
        self.assertLess(32000-s.characters,10)
        before=(s.trace(),set(s.catalogued_sections))
        with self.assertRaisesRegex(ValidationError,'character ceiling'):
            s.apply({'catalog_source_ref':card['source_ref'],'group_cursor':20})
        self.assertEqual((s.trace(),set(s.catalogued_sections)),before)

    def test_registry_loaded_immutable_spec_and_nested_source_metadata_are_isolated(self):
        from stock_opportunity_agent.signal_library import SignalSpec
        d = replace(document(CLAUSE), metadata={'nested': {'values': [1, 1.0, True]}})
        item = item_for((d,))
        item = replace(item, spec=replace(item.spec, parameters={'positive_min': 1.0,
            'negative_max': 1.0, 'routing_need_phrases': ['guidance updates']}))
        loaded = SignalSpec.from_dict(item.spec.to_dict())
        frozen_input = replace(item, spec=loaded)
        before = canonical_json_hash({'spec': loaded.to_dict(), 'source': d.to_dict()})
        s = SignalSourceSession(frozen_input, AS_OF)
        self.assertEqual(catalog_signature(frozen_input, AS_OF), s.signature)
        copied = s.item.eligible_documents[0]
        self.assertEqual(before, canonical_json_hash({'spec': s.item.spec.to_dict(), 'source': copied.to_dict()}))
        d.metadata['nested']['values'].append('after-freeze')
        self.assertEqual(copied.metadata['nested']['values'], [1, 1.0, True])
        with self.assertRaises(TypeError):
            s.item.spec.parameters['added'] = 1

    def test_resolver_pool_uses_original_filters_and_is_isolated(self):
        docs = sources(12)
        wrong = replace(docs[0], document_id="wrong", company_id="other")
        future = replace(docs[0], document_id="future", available_at=AS_OF + timedelta(days=1))
        store = RawInfoStore(documents=(*docs, wrong, future))
        resolver = EvidenceResolver(store)
        request = RawInfoRequest(request_id="read", description="filings", source_types=("filing",), max_documents=10)
        pool = resolver.eligible_documents(request, company_id="issuer", identity={}, as_of=AS_OF)
        resolved = resolver.resolve(request, company_id="issuer", identity={}, as_of=AS_OF)
        self.assertEqual(len(pool), 12)
        self.assertEqual([d.document_id for d in pool[:10]], [d.document_id for d in resolved.documents])
        pool[0].metadata["changed"] = True
        self.assertNotIn("changed", store.load(pool[0].document_id, as_of=AS_OF).metadata)

    def test_rank_eleven_is_read_citable_and_owns_resolution_and_fingerprint(self):
        docs = sources()
        caller = ReadingCaller(docs[-1].content_hash)
        ex = executor(docs, caller)
        prepared = ex.prepare_inputs(("guidance:v1",), company_id="issuer", as_of=AS_OF)
        self.assertNotIn(docs[-1].document_id, [d.document_id for d in prepared[0].documents])
        batch = ex.execute_batch(("guidance:v1",), company_id="issuer", as_of=AS_OF)
        self.assertEqual(batch.results[0].execution_status, SignalExecutionStatus.SUCCESS)
        self.assertEqual(batch.results[0].supporting_evidence[0].document_id, docs[-1].document_id)
        self.assertEqual([d.document_id for d in batch.resolutions[0].documents], [docs[-1].document_id])
        self.assertEqual(batch.document_fingerprints["guidance:v1"][1:], (f"{docs[-1].document_id}:{docs[-1].content_hash}",))
        restored = RawInfoResolution.from_dict(json.loads(json.dumps(batch.resolutions[0].to_dict())))
        self.assertEqual(restored.to_dict(), batch.resolutions[0].to_dict())
        self.assertEqual(batch.usage.llm_calls, 3)
        self.assertEqual(len(caller.calls), 3)

    def test_catalog_change_invalidates_skip_but_unseen_periods_not_claimed_on_skip(self):
        docs = sources()
        caller = ReadingCaller(docs[-1].content_hash)
        ex = executor(docs, caller)
        first = ex.execute_batch(("guidance:v1",), company_id="issuer", as_of=AS_OF)
        second = ex.execute_batch(("guidance:v1",), company_id="issuer", as_of=AS_OF,
            prior_fingerprints=first.document_fingerprints)
        self.assertEqual(second.skipped_unchanged_refs, ("guidance:v1",))
        self.assertEqual(len(caller.calls), 3)
        self.assertFalse(second.resolutions[0].coverage.contract_satisfied)
        changed = RawInfoDocument.create(document_id="new-unread", company_id="issuer", source_type="filing",
            published_at=AS_OF, available_at=AS_OF, content="Another unrelated filing.")
        third = executor((*docs, changed), caller).execute_batch(("guidance:v1",), company_id="issuer", as_of=AS_OF,
            prior_fingerprints=first.document_fingerprints)
        self.assertFalse(third.skipped_unchanged_refs)
        self.assertEqual(len(caller.calls), 6)
        self.assertNotEqual(first.document_fingerprints, third.document_fingerprints)

    def test_legacy_fingerprint_does_not_skip_reading(self):
        docs = sources()
        caller = ReadingCaller(docs[-1].content_hash)
        batch = executor(docs, caller).execute_batch(("guidance:v1",), company_id="issuer", as_of=AS_OF,
            prior_fingerprints={"guidance:v1": tuple(sorted(f"{d.document_id}:{d.content_hash}" for d in docs[:10]))})
        self.assertFalse(batch.skipped_unchanged_refs)
        self.assertEqual(len(caller.calls), 3)

    def test_two_signals_keep_small_shared_execution(self):
        docs = (document(CLAUSE),)
        a, b = item_for(docs), replace(item_for(docs), spec=replace(item_for(docs).spec, signal_id="guidance_peer"))
        caller = ReadingCaller(docs[0].content_hash)
        outcome = StructuredLLMSignalRunner(caller).execute_with_source_reading((a, b), AS_OF)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(set(outcome.results), {a.spec.ref, b.spec.ref})
        self.assertTrue(all(r.execution_status is SignalExecutionStatus.SUCCESS for r in outcome.results.values()))

    def test_bad_final_has_only_one_correction_on_identical_closed_source(self):
        docs = sources()
        caller = ReadingCaller(docs[-1].content_hash, bad_first=True)
        outcome = StructuredLLMSignalRunner(caller).execute_with_source_reading((item_for(docs),), AS_OF)
        self.assertEqual(len(caller.calls), 4)
        self.assertEqual(outcome.results["guidance:v1"].execution_status, SignalExecutionStatus.SUCCESS)
        self.assertEqual(caller.calls[-1]["payload"]["source_projection"], caller.calls[-2]["payload"]["source_projection"])

    def test_unknown_projection_cannot_cite_unread_catalog(self):
        docs = sources()
        caller = ReadingCaller(docs[-1].content_hash, wrong_evidence=True)
        outcome = StructuredLLMSignalRunner(caller).execute_with_source_reading((item_for(docs),), AS_OF)
        self.assertEqual(len(caller.calls), 4)
        self.assertEqual(outcome.results["guidance:v1"].execution_status, SignalExecutionStatus.VALIDATION_FAILED)

    def test_pages_and_fact_pages_consume_same_two_exchanges(self):
        s = SignalSourceSession(item_for(sources(45)), AS_OF)
        self.assertEqual(len(s.catalog()["cards"]), 20)
        self.assertEqual(s.catalog()["next_cursor"], 20)
        page = s.apply({"catalog_cursor": 20})
        self.assertEqual(len(page["cards"]), 20)
        self.assertEqual(page["limits"]["remaining_exchanges"], page["remaining_exchanges"])
        self.assertEqual(s.history[-1]["result"]["limits"]["remaining_exchanges"], 1)
        card = page["cards"][-1]
        s.apply({"reads": [{"source_ref": card["source_ref"], "offset": 0, "length": card["coordinate_length"]}]})
        self.assertEqual(s.exchanges, 2)
        with self.assertRaises(ValidationError):
            s.apply({"catalog_cursor": 40})

    def test_page_summaries_expose_direct_navigation_without_disclosing_extra_cards(self):
        docs = sources(57)[::-1]
        s = SignalSourceSession(item_for(docs), AS_OF)
        catalog = s.catalog()
        self.assertEqual(len(catalog['cards']), 20)
        self.assertEqual([p['cursor'] for p in catalog['pages']], [0, 20, 40])
        self.assertEqual(sum(p['count'] for p in catalog['pages']), 57)
        newest_page = max(catalog['pages'], key=lambda p:p['newest_available_at'])
        self.assertEqual(newest_page['cursor'], 40)
        self.assertEqual(newest_page['newest_available_at'], AS_OF.isoformat())
        self.assertEqual(s.exchanges, 0)
        self.assertEqual(s.rows, [])
        later = s.apply({'catalog_cursor': newest_page['cursor']})
        self.assertEqual(len(later['cards']), 17)
        self.assertEqual(s.exchanges, 1)

    def test_catalog_preview_overflow_is_rejected_without_disclosure_or_mutation(self):
        docs = tuple(RawInfoDocument.create(document_id=d.document_id, company_id=d.company_id,
            source_type=d.source_type, published_at=d.published_at, available_at=d.available_at,
            content=('A' * 29199 + '.') if i == 0 else 'B' * 139 + '.')
            for i, d in enumerate(sources(21)))
        s = SignalSourceSession(item_for(docs), AS_OF)
        first = s.catalog()
        self.assertEqual(s.characters, 2800)
        s.apply({'reads':[{'source_ref': first['cards'][0]['source_ref'], 'offset':0, 'length':29200}]})
        self.assertEqual(s.characters, 32000)
        before = (s.trace(), set(s.catalogued_handles), deepcopy(s.history))
        with self.assertRaisesRegex(ValidationError, 'character ceiling'):
            s.apply({'catalog_cursor':20})
        self.assertEqual((s.trace(), set(s.catalogued_handles), s.history), before)
        self.assertEqual(s.catalog()['limits']['remaining_source_characters'], 0)

    def test_catalog_all_new_previews_fit_together_or_none_are_committed(self):
        for count in (21, 22):
            with self.subTest(count=count):
                docs = tuple(RawInfoDocument.create(document_id=d.document_id, company_id=d.company_id,
                    source_type=d.source_type, published_at=d.published_at, available_at=d.available_at,
                    content=('A' * 29059 + '.') if i == 0 else 'B' * 139 + '.')
                    for i, d in enumerate(sources(count)))
                s = SignalSourceSession(item_for(docs), AS_OF)
                first = s.catalog()
                s.apply({'reads':[{'source_ref':first['cards'][0]['source_ref'],'offset':0,'length':29060}]})
                self.assertEqual(s.characters, 31860)
                if count == 21:
                    page = s.apply({'catalog_cursor':20})
                    self.assertEqual(s.characters, 32000)
                    self.assertEqual(page['limits']['remaining_source_characters'], 0)
                else:
                    before = (s.trace(), set(s.catalogued_handles))
                    with self.assertRaisesRegex(ValidationError, 'character ceiling'):
                        s.apply({'catalog_cursor':20})
                    self.assertEqual((s.trace(), set(s.catalogued_handles)), before)

    def test_catalog_coordinate_sharing_is_lossless_for_all_cards_and_periods(self):
        rows = [{**row, 'tag': 'FinancialComponentWithLongSourceName'+str(i)}
                for i in range(20) for row in pair_rows()]
        docs = tuple(fact_document('grouped-'+str(i), rows) for i in range(20))
        s = SignalSourceSession(item_for(docs), AS_OF)
        catalog = s.catalog()
        ordinary = []
        for card in catalog['cards']:
            expected = s._group_page(card['source_ref'], 0)['fact_groups']
            decoded = catalog_groups(catalog, card)
            self.assertEqual(decoded, expected)
            ordinary.append({**card, 'fact_groups': expected})
        self.assertIn('fact_group_terms', catalog)
        self.assertLess(len(json.dumps(catalog)), .65 * len(json.dumps({**catalog, 'cards':ordinary})))
        self.assertEqual(sum(len(catalog_groups(catalog,c)) for c in catalog['cards']), 400)

    def test_two_exchanges_allow_ten_distinct_documents_and_no_more(self):
        s = SignalSourceSession(item_for(sources(15)), AS_OF)
        cards = s.catalog()["cards"]
        for offset in (0, 5):
            s.apply({"reads": [{"source_ref": c["source_ref"], "offset": 0,
                "length": c["coordinate_length"]} for c in cards[offset:offset+5]]})
        self.assertEqual(len(s.documents), 10)
        self.assertEqual(s.exchanges, 2)
        self.assertLessEqual(s.characters, 32000)

    def test_separate_signals_share_case_budget_and_preserve_accepted_sibling(self):
        docs = sources()
        a = item_for(docs)
        b = replace(a, spec=replace(a.spec, signal_id="guidance_peer"))
        caller = ReadingCaller(docs[-1].content_hash, bad_first=True)
        runner = StructuredLLMSignalRunner(caller)
        runner.set_request_token_budget(1000)
        outcome = runner.execute_with_source_reading((a, b), AS_OF)
        self.assertEqual(len(caller.calls), 8)
        self.assertEqual(outcome.usage.tokens, 240)
        self.assertEqual([c["max_request_tokens"] for c in caller.calls], list(range(1000, 760, -30)))
        self.assertTrue(all(r.execution_status is SignalExecutionStatus.SUCCESS for r in outcome.results.values()))

    def test_unknown_runner_keeps_legacy_static_contract(self):
        docs = sources()
        item = item_for(docs)
        class LegacyRunner:
            def execute_many(self, inputs, as_of):
                self.inputs = inputs
                from stock_opportunity_agent.signal_library import SignalResult
                row = result(item.spec.ref, "unused", "Disclosure 00.")["result"]
                row["evidence"]["supporting"] = [{"document_id": docs[0].document_id,
                    "content_hash": docs[0].content_hash, "exact_span": "Disclosure 00.",
                    "timestamp": docs[0].available_at.isoformat()}]
                return {item.spec.ref: SignalResult.from_dict(row)}, AgentUsage()
        legacy = LegacyRunner()
        ex = executor(docs, ReadingCaller(docs[-1].content_hash))
        ex.llm_runner = legacy
        batch = ex.execute_batch((item.spec.ref,), company_id="issuer", as_of=AS_OF)
        self.assertEqual(len(legacy.inputs[0].documents), 10)
        self.assertIsNone(legacy.inputs[0].eligible_documents)
        self.assertFalse(any(p.startswith("source_catalog:") for p in batch.document_fingerprints[item.spec.ref]))

    def test_invalid_actions_are_atomic_and_integer_strict(self):
        s = SignalSourceSession(item_for(sources()), AS_OF)
        card = s.catalog()["cards"][0]
        valid = {"source_ref": card["source_ref"], "offset": 0, "length": card["coordinate_length"]}
        actions = [{"finalize": 1}, {"reads": [dict(valid, offset=True)]}, {"reads": [dict(valid, source_ref="other")]},
                   {"reads": [valid, dict(valid, source_ref="other")]}, {"reads": [valid] * 6}]
        for action in actions:
            with self.subTest(action=action), self.assertRaises(ValidationError):
                s.apply(action)
            self.assertEqual(s.exchanges, 0)
            self.assertEqual(s.rows, [])
        s.apply({"reads": [valid]})
        with self.assertRaises(ValidationError):
            s.apply({"reads": [valid]})

    def test_character_budget_includes_previews_and_never_clips_long_sentence(self):
        d = document("A" * 33000 + ".")
        s = SignalSourceSession(item_for((d,)), AS_OF)
        card = s.catalog()["cards"][0]
        with self.assertRaises(ValidationError):
            s.apply({"reads": [{"source_ref": card["source_ref"], "offset": 0, "length": len(d.content)}]})
        self.assertEqual(s.rows, [])
        empty = s.apply({"reads": [{"source_ref": card["source_ref"], "offset": 0, "length": 100}]})
        self.assertEqual(empty["source_projection"], [])
        self.assertEqual(empty["windows"][0]["next_offset"], 0)

    def test_structured_read_preserves_prior_currency_and_same_period_conflicts(self):
        rows = pair_rows()
        rows += [{**rows[0], "value": 999}, {**rows[0], "unit": "EUR", "value": 5}]
        d = fact_document("facts", rows)
        s = SignalSourceSession(item_for((d,)), AS_OF)
        card = s.catalog()["cards"][0]
        first = catalog_groups(s.catalog(), card)[0]
        s.apply({"reads": [{"source_ref": card["source_ref"], "offset": first["offset"], "length": first["length"]}]})
        chosen_unit = first["unit"]
        visible = [json.loads(r["exact_text"]) for r in s.rows]
        self.assertTrue(all(r["unit"] == chosen_unit for r in visible))
        expected = [r for r in rows if r["unit"] == chosen_unit]
        self.assertCountEqual(visible, expected)
        self.assertTrue(all(r["exact_text"] in d.content for r in s.rows))
        self.assertEqual(s.visible_documents[0].metadata, {})

    def test_partial_source_cannot_count_unseen_periods_or_observations(self):
        from stock_opportunity_agent.data.resolution import _retrieval_contract_coverage
        d = document(CLAUSE)
        d = replace(d, metadata={"rows": [{"date": "2024-01-01"}, {"date": "2025-01-01"}]})
        s = SignalSourceSession(item_for((d,)), AS_OF)
        c = s.catalog()["cards"][0]
        s.apply({"reads": [{"source_ref": c["source_ref"], "offset": 0, "length": len(d.content)}]})
        request = RawInfoRequest(request_id="read", description="proof", source_types=("filing",), minimum_distinct_periods=2)
        self.assertTrue(_retrieval_contract_coverage((d,), request)["contract_satisfied"])
        self.assertFalse(_retrieval_contract_coverage(s.visible_documents, request)["contract_satisfied"])

    def test_older_original_period_is_readable_in_both_shapes_without_default_displacement(self):
        from tests.test_mining_fact_semantics import typed_row
        from stock_opportunity_agent.research.evolution_core import _company_facts_context

        rows = pair_rows() + [typed_row(80, '2022-01-01', '2022-06-30'),
            typed_row(81, '2022-01-01', '2022-06-30'),
            typed_row(70, '2021-01-01', '2021-06-30'),
            typed_row(1000, '2026-01-01', '2026-06-30')]
        for typed in (True, False):
            with self.subTest(typed=typed):
                source_rows = rows if typed else [{**r, 'val': r['value']} for r in rows]
                d = fact_document('older', source_rows, typed=typed)
                default = _company_facts_context(d, max_content_chars=32000, query=None)
                self.assertFalse(any(json.loads(r['exact_span'])['end'] == '2022-06-30'
                    for c in default['concepts'] for r in c['records']))
                s = SignalSourceSession(item_for((d,)), AS_OF)
                card = s.catalog()['cards'][0]
                literal = next(m for m in re.finditer(r'\{[^{}]*\}', d.content)
                    if json.loads(m.group(0)).get('end') == '2022-06-30')
                s.apply({'reads': [{'source_ref': card['source_ref'], 'offset': literal.start(), 'length': literal.end() - literal.start()}]})
                selected = [json.loads(r['exact_text']) for r in s.rows]
                self.assertEqual({r['end'] for r in selected}, {'2022-06-30', '2021-06-30'})
                self.assertEqual(len(selected), 3)
                self.assertTrue(all(r['exact_text'] in d.content for r in s.rows))
                self.assertTrue(all('2026' not in r['exact_text'] for r in s.rows))
                self.assertIn('2022-06-30', [g['period_end'] for g in catalog_groups(s.catalog(), card)])

    def test_expanded_pair_does_not_block_unread_interleaved_concept(self):
        from tests.test_mining_fact_semantics import typed_row
        rows = pair_rows()
        other = {**rows[0], 'tag': 'OtherFact', 'value': 9}
        d = fact_document('interleaved', [rows[0], other, rows[1]])
        s = SignalSourceSession(item_for((d,)), AS_OF)
        card = s.catalog()['cards'][0]
        groups = {g['concept']: g for g in catalog_groups(s.catalog(), card)}
        first = groups[rows[0]['tag']]
        # Address only the latest row; its earlier comparable expands across
        # an unrelated row without claiming that intervening text was read.
        row_literal = next(r for c in s.groups[card['source_ref']]['concepts'] if c['concept'] == rows[0]['tag']
            for r in c['records'] if json.loads(r['exact_span'])['end'] == '2024-06-30')
        s.apply({'reads': [{'source_ref': card['source_ref'], 'offset': row_literal['start'],
                            'length': row_literal['end'] - row_literal['start']}]})
        second = groups['OtherFact']
        s.apply({'reads': [{'source_ref': card['source_ref'], 'offset': second['offset'], 'length': second['length']}]})
        self.assertEqual(len(s.rows), 3)

    def test_original_fresh_distinct_windows_merge_only_implicit_comparables(self):
        root = Path(__file__).resolve().parents[1] / 'runs/diagnostics/source_reading_20261022_v1/history-native'
        inputs = json.loads((root/'inputs.json').read_text())
        docs = tuple(RawInfoDocument.from_dict(d) for d in inputs['documents'])
        action = json.loads(next((root/'exchange/outbox').glob('*.txt')).read_text())
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                s = SignalSourceSession(item_for(docs), AS_OF)
                s.catalog()
                previews = s.characters
                reads = action['reads'][::-1] if reverse else action['reads']
                out = s.apply({'reads': reads})
                self.assertEqual(len(out['source_projection']), 2)
                self.assertEqual(len(s.lineage), 2)
                self.assertEqual(s.characters, previews + sum(len(r['exact_text']) for r in s.rows))
                self.assertEqual({json.loads(r['exact_text'])['end'] for r in s.rows}, {'2022-06-30','2021-06-30'})
                with self.assertRaises(ValidationError):
                    s.apply(action)
                self.assertEqual(s.exchanges, 1)
        for reads in ([action['reads'][0]] * 2,
                      [action['reads'][0], {**action['reads'][0], 'offset': action['reads'][0]['offset']+1}]):
            s = SignalSourceSession(item_for(docs), AS_OF)
            with self.assertRaises(ValidationError):
                s.apply({'reads': reads})
            self.assertEqual(s.rows, [])
            self.assertEqual(s.exchanges, 0)

    def test_budget_stop_retains_prior_usage_and_prevents_final_call(self):
        docs = sources()
        class BudgetCaller(ReadingCaller):
            def complete_json(self, **kwargs):
                if len(self.calls) == 1:
                    raise RuntimeBudgetExceeded("exact reservation refused")
                return super().complete_json(**kwargs)
        caller = BudgetCaller(docs[-1].content_hash)
        outcome = StructuredLLMSignalRunner(caller).execute_with_source_reading((item_for(docs),), AS_OF)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(outcome.usage.llm_calls, 1)
        self.assertEqual(outcome.results["guidance:v1"].execution_status, SignalExecutionStatus.BUDGET_BLOCKED)

    def test_native_interruption_restore_uses_exact_inbox_cache_and_receipts(self):
        docs = sources()
        self._assert_native_restore(docs, ReadingCaller(docs[-1].content_hash))

    def test_native_long_narrative_navigation_restores_exact_closed_projection(self):
        d = document('<p>'+'Background. '*6000+'</p><h2>ITEM 7. Guidance discussion.</h2><p>'+CLAUSE+'</p>')
        self._assert_native_restore((d,), HeadingCaller(d.content_hash))

    def _assert_native_restore(self, docs, scripted):
        from diagnose_executed_answer_scope import StageContract
        from stock_opportunity_agent.llm import get_model
        from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
        from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending

        with TemporaryDirectory() as directory:
            root = Path(directory)
            exchange = LocalRoleExchange(root / "exchange", max_calls=4)
            def reopen():
                caller = StructuredRoleClient(registration=get_model("independent-subagent"),
                    contract=StageContract({"limits": {"max_structured_corrections": 1}}),
                    workspace=root, ledger=ExternalAttemptLedger(root / "unused.json", max_attempts=1, max_total_cost=.01),
                    local_role_exchange=exchange, allow_external=False, environ={})
                return executor(docs, caller)
            pending_hashes = []
            for _ in range(3):
                with self.assertRaises(LocalRoleRequestPending) as pending:
                    reopen().execute_batch(("guidance:v1",), company_id="issuer", as_of=AS_OF)
                record = pending.exception.pending
                digest = record["request_hash"]
                pending_hashes.append(digest)
                inbox = json.loads(Path(record["inbox_path"]).read_text())
                p = json.loads(inbox["messages"][-1]["content"])
                output, _usage = scripted.complete_json(stage=record["stage"], payload=p)
                Path(record["outbox_path"]).write_text(json.dumps(output))
                exchange.submit(digest, agent_id="offline-scripted-test-not-fresh-model")
            completed = reopen().execute_batch(("guidance:v1",), company_id="issuer", as_of=AS_OF)
            self.assertEqual(completed.results[0].execution_status, SignalExecutionStatus.SUCCESS)
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            restored = reopen().execute_batch(("guidance:v1",), company_id="issuer", as_of=AS_OF)
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(completed, restored)
            self.assertEqual(len(set(pending_hashes)), 3)
            self.assertEqual(len(list((root / "exchange/inbox").glob("*.json"))), 3)
            self.assertEqual(len(list((root / "cache/responses").glob("*.json"))), 3)
