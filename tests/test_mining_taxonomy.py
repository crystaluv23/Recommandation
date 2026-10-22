"""Namespace lineage through native projection, selection and fact-read ledger."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.research.mining_agent_tools import (
    EvidenceFact, project_facts_from_documents, build_same_concept_relations,
    _unique_latest_fact, _unique_period_pair, compute_statistic,
)
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController, MiningLedger
from tests.test_mining_fact_semantics import NOW, document, pair_rows


class MiningTaxonomyTests(TestCase):
    def original(self):
        path = Path(__file__).resolve().parents[1] / 'runs/diagnostics/mining_fact_semantics_repair_20261021_v1/root/namespace-before.json'
        saved = json.loads(path.read_text())
        doc = RawInfoDocument.create(document_id='namespace-control-only', company_id='probe-issuer',
            source_type='sec_company_facts', published_at=NOW, available_at=NOW, content=saved['content'])
        return saved, project_facts_from_documents((doc,), case_ref='synthetic')

    def test_original_legacy_namespace_false_pair_is_rejected_without_rehash(self):
        saved, facts = self.original()
        self.assertEqual([f.fact_ref for f in facts], [f['fact_ref'] for f in saved['facts']])
        self.assertEqual({f.taxonomy for f in facts}, {'namespace-a', 'namespace-b'})
        self.assertEqual(build_same_concept_relations(facts), ())
        self.assertIsNone(_unique_latest_fact(facts))
        self.assertIsNone(_unique_period_pair(facts))

    def test_both_source_shapes_keep_known_namespace_and_valid_pair(self):
        for typed in (True, False):
            with self.subTest(typed=typed):
                rows = pair_rows() if typed else [{**r, 'val': r['value'], 'filed': '2024-08-01'} for r in pair_rows()]
                doc = document('known', rows, typed=typed)
                facts = project_facts_from_documents((doc,), case_ref='case')
                self.assertEqual({f.taxonomy for f in facts}, {'us-gaap'})
                self.assertIsNotNone(_unique_period_pair(facts))
                self.assertTrue(all(f.exact_span in doc.content for f in facts))
                restored = tuple(EvidenceFact(**json.loads(json.dumps(asdict(f)))) for f in facts)
                self.assertEqual(restored, facts)
                self.assertEqual(build_same_concept_relations(restored), build_same_concept_relations(facts))

    def test_old_unknown_legacy_facts_readable_but_not_automatic_measurement(self):
        saved, _ = self.original()
        old = tuple(EvidenceFact(**r) for r in saved['facts'])
        self.assertEqual(build_same_concept_relations(old), ())
        self.assertIsNone(_unique_latest_fact(old))
        result = compute_statistic('latest_over_comparable_prior', [f.fact_ref for f in old], facts=old)
        self.assertEqual(result.value, '1.200000')

    def test_old_typed_literal_still_establishes_namespace_and_conflict_does_not(self):
        facts = project_facts_from_documents((document('typed', pair_rows()),), case_ref='case')
        old = tuple(EvidenceFact(**{k: v for k, v in asdict(f).items() if k != 'taxonomy'}) for f in facts)
        self.assertIsNotNone(_unique_period_pair(old))
        bad = tuple(replace(f, taxonomy='other-namespace') for f in facts)
        self.assertEqual(build_same_concept_relations(bad), ())
        self.assertIsNone(_unique_latest_fact(bad))

    def test_actual_fact_read_exposes_provenance_and_binds_ledger_hash(self):
        _, facts = self.original()
        controller = LabelAwareMiningController.__new__(LabelAwareMiningController)
        controller._facts = {f.fact_ref: f for f in facts}
        controller._documents = {}
        controller.identity_aliases = {}
        controller.ledger = MiningLedger(cycle_id='test-cycle', seed_id='test-seed')
        controller._heavy_used = 0
        controller._model_calls = 0
        controller._read_fact_span({'action': 'read_span', 'fact_ref': facts[0].fact_ref})
        entry = controller._last_action_result
        self.assertEqual(entry['fact']['taxonomy'], facts[0].taxonomy)
        self.assertEqual(entry['fact']['unit'], facts[0].unit)
        self.assertEqual(entry['fact']['period'], dict(facts[0].period))
        payload = {k: v for k, v in entry.items() if k != 'action'}
        self.assertEqual(controller.ledger.entries[-1].output_hash, canonical_json_hash(payload))
