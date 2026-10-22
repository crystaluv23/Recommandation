"""Targeted structured fetches preserve query intent through bounded projection."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research.mining_agent_tools import fetch_case_evidence, project_facts_from_documents


TARGET = "CashFlowsFromUsedInOperatingActivities"


def fetch(document, query=None, *, clock=None):
    """Exercise actual local fetch rather than mocking its structured projector."""
    case = SimpleNamespace(case_id="source-probe", company_id=document.company_id,
        prediction_time=clock or document.available_at)
    return fetch_case_evidence(RawInfoStore(documents=(document,)), case,
        source_families=("sec_company_facts",), query=query, max_documents=1, case_ref="case-001")


def crowded_document(typed):
    rows = [{"taxonomy": "ifrs-full", "tag": concept, "unit": "USD", "start": start,
        "end": end, "value": value, "filed": "2024-08-01"}
        for concept in ["AAAATarget", *[f"ZZZ{i:03}" for i in range(100)]]
        for start, end, value in (("2023-01-01", "2023-06-30", 100), ("2024-01-01", "2024-06-30", 120))]
    if typed:
        payload = {"schema_version": "sec-company-facts-document-v1", "filing_date": "2024-08-01", "facts": rows}
    else:
        concepts = {}
        for row in rows:
            concepts.setdefault(row["tag"], {"units": {"USD": []}})["units"]["USD"].append({
                "start": row["start"], "end": row["end"], "filed": row["filed"], "val": row["value"]})
        payload = {"facts": {"ifrs-full": concepts}}
    payload["unprojected_hint"] = "hiddenhint"
    now = datetime(2024, 8, 2, tzinfo=timezone.utc)
    return RawInfoDocument.create(document_id="typed" if typed else "legacy", company_id="fixture-issuer",
        source_type="sec_company_facts", published_at=now, available_at=now,
        content=json.dumps(payload, separators=(",", ":")))


class MiningQueryProjectionTests(TestCase):
    def test_actual1179_target_reaches_fetch_without_source_or_ref_rewrite(self):
        path = Path(__file__).resolve().parents[1] / "runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/1179.json"
        original = path.read_bytes()
        document = RawInfoDocument.from_dict(json.loads(original))
        before = fetch(document)
        self.assertFalse(any(f.concept == TARGET for f in before.facts))
        result = fetch(document, TARGET)
        target = [f for f in result.facts if f.concept == TARGET]
        self.assertEqual({f.value for f in target}, {"-15122354", "-2378789"})
        self.assertEqual({f.taxonomy for f in target}, {"ifrs-full"})
        self.assertEqual({f.unit for f in target}, {"USD"})
        self.assertEqual({tuple(sorted(f.period.items())) for f in target}, {
            (("end", "2024-06-30"), ("start", "2023-07-01")),
            (("end", "2023-06-30"), ("start", "2022-07-01"))})
        self.assertTrue(all(f.exact_span in document.content and f.content_hash == document.content_hash for f in target))
        self.assertEqual(result.query_coverage, {"matched_terms": [TARGET.lower()], "sufficient": True})
        common = {f.fact_ref: asdict(f) for f in before.facts}
        self.assertTrue(common.keys() & {f.fact_ref for f in result.facts})
        for fact in result.facts:
            if fact.fact_ref in common:
                self.assertEqual(asdict(fact), common[fact.fact_ref])
        self.assertEqual(before.facts, project_facts_from_documents((document,), case_ref="case-001"))
        self.assertEqual(path.read_bytes(), original)

    def test_typed_and_legacy_omitted_concept_uses_existing_query_with_same_literals(self):
        for typed in (True, False):
            with self.subTest(typed=typed):
                document = crowded_document(typed)
                self.assertFalse(any(f.concept == "AAAATarget" for f in fetch(document).facts))
                target = [f for f in fetch(document, "AAAATarget").facts if f.concept == "AAAATarget"]
                self.assertEqual(len(target), 2)
                self.assertEqual({f.value for f in target}, {"100", "120"})
                self.assertTrue(all(f.exact_span in document.content for f in target))
                self.assertEqual({f.taxonomy for f in target}, {"ifrs-full"})

    def test_unprojected_literal_does_not_claim_query_coverage_and_pit_remains_closed(self):
        document = crowded_document(True)
        result = fetch(document, "hiddenhint")
        self.assertEqual(len(result.documents), 1)
        self.assertTrue(result.facts)
        self.assertEqual(result.query_coverage, {"matched_terms": [], "sufficient": False})
        self.assertEqual(fetch(document, "missingxyz").documents, ())
        self.assertEqual(fetch(document, "AAAATarget", clock=datetime(2023, 1, 1, tzinfo=timezone.utc)).facts, ())
