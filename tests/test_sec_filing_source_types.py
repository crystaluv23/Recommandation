"""Per-filing requested aliases survive native acquisition, storage and qualification."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
from unittest import TestCase

from stock_opportunity_agent.data.acquisition import SecFilingAdapter
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.resolution import EvidenceResolver, RawInfoRequest
from stock_opportunity_agent.data.reviewed_snapshot import (
    materialize_reviewed_snapshot, open_raw_info_store, ReviewedSourceRejected,
)
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
from tests.test_reviewed_sec_response_profile import SecResponseFixture, bound

COMPANY = "cik_0000000001"
CUTOFF = datetime(2025, 7, 31, tzinfo=timezone.utc)


class OfflineFilingClient(SecEdgarClient):
    """Use native SEC array parsing but return bodies from a counted local fixture."""

    def __init__(self):
        super().__init__("Offline alias test", transport=object())
        self.calls = []
        self.failures = set()
        self.arrays = {"accessionNumber": ["0000000002-25-000001", "0000000002-25-000002"],
            "filingDate": ["2025-05-05", "2025-05-06"], "form": ["10-K", "10-Q"],
            "primaryDocument": ["primary.htm", "primary.htm"], "reportDate": ["2024-12-31", "2025-03-31"],
            "acceptanceDateTime": ["2025-05-05T20:00:00Z", "2025-05-06T20:00:00Z"]}

    def submissions(self, cik):
        return {"cik": 1, "filings": {"recent": deepcopy(self.arrays), "files": []}}

    def filing_document_text(self, filing):
        self.calls.append(filing.accession_number)
        if filing.accession_number in self.failures:
            raise RuntimeError("offline missing body")
        return "<html>Whole " + filing.form + " operating source.</html>"


class SecFilingSourceTypeTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def acquire(self, sources, *, client=None, maximum=2, cutoff=CUTOFF):
        client = client or OfflineFilingClient()
        result = SecFilingAdapter(client).acquire(
            RawInfoRequest("read", "Read complete filing", sources, lookback_days=730, max_documents=maximum),
            company_id=COMPANY, identity={"cik": "0000000001"}, as_of=cutoff)
        return result, client

    def qualifier(self, document, name):
        fixture = SecResponseFixture(self.base / name, linked=False)
        client = OfflineFilingClient()
        index = client.arrays["accessionNumber"].index(document.metadata["accession_number"])
        fixture.root["filings"]["recent"] = {key: [values[index]] for key, values in client.arrays.items()}
        fixture.root_proof.update(accession_number=document.metadata["accession_number"],
            form=document.metadata["form"], accepted_at=document.available_at.isoformat(),
            primary_document="primary.htm", filing_date=client.arrays["filingDate"][index])
        body = next(proof for proof in fixture.proofs if proof["kind"] == "sec_static_archive_body_response")
        body.update(endpoint=document.metadata["source_url"], expected_content_hash=document.content_hash)
        entry = next(row for row in fixture.receipt["requests"] if row["name"] == "body")
        raw = fixture.base / "body.raw"
        raw.write_bytes(document.content.encode())
        entry.update(url=document.metadata["source_url"], response_url=document.metadata["source_url"],
            raw_sha256=bound(raw)["sha256"], bytes=len(raw.read_bytes()))
        body["raw_response"] = bound(raw)
        fixture.original.unlink()
        fixture.document, fixture.content = document, document.content
        RawInfoStore(fixture.oracle).append(document)
        fixture.original = next(path for path in fixture.oracle.rglob("*.json") if path.name != "oracle.json")
        row = fixture.review["records"][0]
        row.update(document_id=document.document_id, original_record=bound(fixture.original),
            content_hash=document.content_hash, reviewed_available_at=document.available_at.isoformat())
        return fixture

    def test_mixed_exact_request_labels_each_actual_form_instead_of_first_type(self):
        result, client = self.acquire(("10-k", "10-q"))
        self.assertEqual([(d.metadata["form"], d.source_type) for d in result.documents], [("10-Q", "10-q"), ("10-K", "10-k")])
        self.assertEqual(client.calls, ["0000000002-25-000002", "0000000002-25-000001"])
        for document in result.documents:
            accession = document.metadata["accession_number"]
            self.assertEqual(document.document_id, "sec:" + COMPANY + ":" + accession.replace("-", ""))
            self.assertEqual(document.available_at, document.published_at)
            self.assertEqual(document.available_at, datetime(2025, 5, 6 if document.source_type == "10-q" else 5, 20, tzinfo=timezone.utc))

    def test_reversed_exact_order_has_same_per_form_types_and_source_order(self):
        forward, a = self.acquire(("10-k", "10-q"))
        backward, b = self.acquire(("10-q", "10-k"))
        self.assertEqual([d.to_dict() for d in forward.documents], [d.to_dict() for d in backward.documents])
        self.assertEqual(a.calls, b.calls)

    def test_first_compatible_requested_generic_alias_keeps_its_priority(self):
        for sources, expected in ((("filing_body", "sec_filing", "filing"), "filing_body"),
                (("sec_filing", "filing"), "sec_filing"), (("filing", "10-k", "10-q"), "filing")):
            with self.subTest(sources=sources):
                result, _client = self.acquire(sources)
                self.assertEqual([d.source_type for d in result.documents], [expected, expected])
        # Earlier exact aliases retain priority only for their matching filing.
        result, _client = self.acquire(("10-k", "10-q", "filing"))
        self.assertEqual([d.source_type for d in result.documents], ["10-q", "10-k"])

    def test_single_exact_form_filter_still_excludes_other_forms_before_body_get(self):
        for alias, accession in (("10-k", "0000000002-25-000001"), ("10-q", "0000000002-25-000002")):
            with self.subTest(alias=alias):
                result, client = self.acquire((alias,))
                self.assertEqual(client.calls, [accession])
                self.assertEqual([d.source_type for d in result.documents], [alias])
        result, client = self.acquire(("20-f",))
        self.assertEqual(result.documents, ())
        self.assertEqual(client.calls, [])

    def test_no_requested_supported_compatible_alias_never_gets_body_or_invents_source(self):
        for sources in (("news",), ("my_filing",), ("10-k-summary",)):
            with self.subTest(sources=sources):
                result, client = self.acquire(sources)
                self.assertEqual(result.documents, ())
                self.assertEqual(client.calls, [])
                self.assertEqual(result.events[-1].kind, "sec_history_scan")
                local = EvidenceResolver(RawInfoStore()).resolve(
                    RawInfoRequest("gap", "Read missing source", sources), company_id=COMPANY, identity={}, as_of=CUTOFF)
                self.assertEqual(local.documents, ())
                self.assertIsNotNone(local.gap)

    def test_document_limit_failed_body_fallback_and_accepted_boundary_are_preserved(self):
        client = OfflineFilingClient()
        client.failures.add("0000000002-25-000002")
        result, _ = self.acquire(("10-k", "10-q"), client=client, maximum=1)
        self.assertEqual(client.calls, ["0000000002-25-000002", "0000000002-25-000001"])
        self.assertEqual([d.source_type for d in result.documents], ["10-k"])
        at = datetime(2025, 5, 6, 20, tzinfo=timezone.utc)
        early, _ = self.acquire(("10-q",), cutoff=at - timedelta(microseconds=1))
        exact, _ = self.acquire(("10-q",), cutoff=at)
        self.assertEqual(early.documents, ())
        self.assertEqual(len(exact.documents), 1)
        limited, limited_client = self.acquire(("10-k", "10-q"), maximum=1)
        self.assertEqual(len(limited.documents), 1)
        self.assertEqual(len(limited_client.calls), 1)

    def test_actual_produced_records_persist_restart_and_native_qualifier_worker_keep_types(self):
        result, _ = self.acquire(("10-k", "10-q"))
        root = self.base / "stored"
        store = RawInfoStore(root)
        for document in result.documents:
            self.assertTrue(store.append(document))
        restarted = RawInfoStore(root)
        for index, document in enumerate(result.documents):
            self.assertEqual(restarted.load(document.document_id, as_of=CUTOFF).to_dict(), document.to_dict())
            fixture = self.qualifier(document, str(index))
            binding = materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
            for restored in (open_raw_info_store(binding["root"], reviewed_snapshot=binding),
                    open_raw_info_store(binding["root"], reviewed_snapshot=binding).snapshot()):
                self.assertEqual(restored.documents[0].to_dict(), document.to_dict())
                resolver = EvidenceResolver(restored)
                for requested in ("filing", document.source_type):
                    resolved = resolver.resolve(RawInfoRequest("read", "Read source", (requested,)),
                        company_id=COMPANY, identity={}, as_of=CUTOFF)
                    self.assertEqual([d.document_id for d in resolved.documents], [document.document_id])

    def test_original_wrong_first_type_shape_remains_rejected_by_unchanged_qualifier(self):
        result, _ = self.acquire(("10-k", "10-q"))
        quarter = next(d for d in result.documents if d.metadata["form"] == "10-Q")
        fixture = self.qualifier(replace(quarter, source_type="10-k"), "wrong-original-shape")
        with self.assertRaises(ReviewedSourceRejected):
            materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
