"""SEC source aliases retain exact originals through proof and read-only restore."""
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import tempfile
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.filing_orientation import exact_document_form, filing_source_matches_form
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.resolution import EvidenceResolver, RawInfoRequest
from stock_opportunity_agent.data.reviewed_snapshot import (
    materialize_reviewed_snapshot, open_raw_info_store, ReviewedSourceRejected,
)
from stock_opportunity_agent.models import ValidationError
from tests.test_reviewed_sec_response_profile import SecResponseFixture, bound, write


class ReviewedSecSourceAliasTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.counter = 0

    def fixture(self, source_type="filing", form="10-Q", *, exhibit=False):
        self.counter += 1
        fixture = SecResponseFixture(self.base / str(self.counter), linked=False, exhibit=exhibit)
        fixture.form = form
        fixture.arrays["form"][0] = fixture.root["filings"]["recent"]["form"][0] = form
        fixture.root_proof["form"] = form
        metadata = dict(fixture.document.metadata, form=form)
        if exhibit:
            metadata["parent_form"] = form
        fixture.document = replace(fixture.document, source_type=source_type, metadata=metadata)
        fixture.original.unlink()
        RawInfoStore(fixture.oracle).append(fixture.document)
        fixture.original = next(p for p in fixture.oracle.rglob("*.json") if p.name != "oracle.json")
        fixture.review["records"][0]["original_record"] = bound(fixture.original)
        return fixture

    def review_path(self, fixture, *, legacy=False):
        path = fixture.save()
        if legacy:
            acceptance = {k: v for k, v in fixture.root_proof.items() if k != "kind"}
            acceptance["kind"] = "sec_submissions_acceptance"
            body = {"kind": "sec_static_archive_body", "endpoint": fixture.body_url,
                "expected_content_hash": fixture.document.content_hash,
                "artifact": write(fixture.base / "legacy-body.json", {"endpoint": fixture.body_url, "body": fixture.content})}
            row = fixture.review["records"][0]
            row.update(proof_profile="sec_archive_acceptance_v1", proofs=[body, acceptance])
            fixture.review["manifest_hash"] = canonical_json_hash({k: v for k, v in fixture.review.items() if k != "manifest_hash"})
            write(path, fixture.review)
        return path

    def restored(self, fixture, *, legacy=False):
        binding = materialize_reviewed_snapshot(self.review_path(fixture, legacy=legacy), fixture.base / "view")
        store = open_raw_info_store(binding["root"], reviewed_snapshot=binding)
        for current in (store, store.snapshot(), open_raw_info_store(binding["root"], reviewed_snapshot=binding)):
            self.assertEqual([doc.to_dict() for doc in current.documents], [fixture.document.to_dict()])
            self.assertFalse(current.append(fixture.document))
            self.assertEqual(current.load(fixture.document.document_id, as_of=fixture.document.available_at), fixture.document)
            with self.assertRaises(ValidationError):
                current.load(fixture.document.document_id, as_of=fixture.document.available_at - timedelta(microseconds=1))
        return binding, store

    def test_shared_predicate_keeps_generic_scope_and_exact_operating_forms_separate(self):
        for alias in ("filing", "sec_filing", "filing_body"):
            for form in ("S-1", "10-K/A", "6-K/A", "10-Q"):
                self.assertTrue(filing_source_matches_form(alias, form))
        for form in ("10-K", "10-Q", "8-K", "20-F", "40-F", "6-K"):
            self.assertTrue(filing_source_matches_form(form.lower(), form))
            for wrong in (form + "/A", "S-1", "news"):
                self.assertFalse(filing_source_matches_form(form.lower(), wrong))
        for alias in ("news", "sec_company_facts", "market_data", "earnings_call", "my_filing", "filing_body_extra", "10-k/a", "10-k-summary", "", None):
            self.assertFalse(filing_source_matches_form(alias, "10-K"))
        fixture = self.fixture("sec_filing", "S-1")
        self.assertIsNone(exact_document_form(fixture.document))
        self.assertFalse(filing_source_matches_form("filing", ""))

    def test_legacy_managed_pair_preserves_generic_and_all_six_exact_aliases(self):
        cases = [(alias, "10-Q") for alias in ("filing", "sec_filing", "filing_body")]
        cases += [(form.lower(), form) for form in ("10-K", "10-Q", "8-K", "20-F", "40-F", "6-K")]
        for alias, form in cases:
            with self.subTest(alias=alias, form=form):
                self.restored(self.fixture(alias, form), legacy=True)

    def test_http_primary_preserves_aliases_at_generic_and_exact_native_lookup(self):
        cases = [(alias, "10-Q") for alias in ("filing", "sec_filing", "filing_body")]
        cases += [(form.lower(), form) for form in ("10-K", "10-Q", "8-K", "20-F", "40-F", "6-K")]
        for alias, form in cases:
            with self.subTest(alias=alias, form=form):
                fixture = self.fixture(alias, form)
                _binding, store = self.restored(fixture)
                resolver = EvidenceResolver(store.snapshot())
                for requested in ("filing", "sec_filing", form.lower()):
                    result = resolver.resolve(RawInfoRequest("read", "Read source", (requested,)),
                        company_id=fixture.company, identity={}, as_of=fixture.document.available_at)
                    self.assertEqual([r.document_id for r in result.documents], [fixture.document.document_id])
                wrong = "10-q" if form != "10-Q" else "10-k"
                result = resolver.resolve(RawInfoRequest("wrong-form", "Read source", (wrong,)),
                    company_id=fixture.company, identity={}, as_of=fixture.document.available_at)
                self.assertEqual(result.documents, ())

    def test_generic_nonoperating_and_amendments_remain_qualified(self):
        for legacy in (False, True):
            for form in ("S-1", "10-K/A"):
                for alias in ("filing", "sec_filing", "filing_body"):
                    with self.subTest(legacy=legacy, form=form, alias=alias):
                        self.restored(self.fixture(alias, form), legacy=legacy)

    def test_http_exhibit_preserves_source_and_real_parent_form(self):
        for form in ("40-F", "6-K"):
            for alias in ("filing", "sec_filing", "filing_body", form.lower()):
                with self.subTest(form=form, alias=alias):
                    fixture = self.fixture(alias, form, exhibit=True)
                    self.restored(fixture)
                    self.assertEqual(fixture.document.metadata["parent_form"], form)
                    self.assertEqual(fixture.document.source_type, alias)

    def test_wrong_form_unsupported_or_substring_source_reject_even_with_rehashed_original(self):
        for legacy, exhibit in ((True, False), (False, False), (False, True)):
            for alias in ("news", "market_data", "financials", "earnings_call", "my_filing", "10-q-extra", "10-k", "10-q-summary"):
                with self.subTest(legacy=legacy, exhibit=exhibit, alias=alias):
                    fixture = self.fixture(alias, "10-Q", exhibit=exhibit)
                    with self.assertRaises(ReviewedSourceRejected):
                        materialize_reviewed_snapshot(self.review_path(fixture, legacy=legacy), fixture.base / "view")
                    self.assertFalse((fixture.base / "view").exists())

    def test_aliases_do_not_relax_cutoff_or_proof_form_identity(self):
        for legacy in (False, True):
            for change in ("cutoff", "metadata_form", "proof_form"):
                with self.subTest(legacy=legacy, change=change):
                    fixture = self.fixture("10-q")
                    if change == "cutoff":
                        fixture.review["scope"]["as_of"] = (fixture.document.available_at - timedelta(microseconds=1)).isoformat()
                    elif change == "metadata_form":
                        record = fixture.document.to_dict()
                        record["metadata"]["form"] = "10-K"
                        fixture.review["records"][0]["original_record"] = write(fixture.original, record)
                    else:
                        fixture.root_proof["form"] = "10-K"
                    with self.assertRaises(ReviewedSourceRejected):
                        materialize_reviewed_snapshot(self.review_path(fixture, legacy=legacy), fixture.base / "view")

    def test_rehashed_materialized_type_change_cannot_replace_admitted_original_on_restore(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                fixture = self.fixture("10-q")
                binding, store = self.restored(fixture, legacy=legacy)
                marker = Path(binding["root"]) / "reviewed_snapshot.json"
                manifest = json.loads(marker.read_text())
                row = manifest["documents"][0]
                materialized = Path(binding["root"]) / row["path"]
                record = json.loads(materialized.read_text())
                record["source_type"] = "sec_filing"  # legal alias, still a different exact original
                row["sha256"] = write(materialized, record)["sha256"]
                altered = dict(binding, manifest_sha256=write(marker, manifest)["sha256"])
                with self.assertRaises(ReviewedSourceRejected):
                    open_raw_info_store(altered["root"], reviewed_snapshot=altered)
                for action in (store.refresh, store.snapshot):
                    with self.assertRaises(ReviewedSourceRejected): action()
                with self.assertRaises(ReviewedSourceRejected):
                    store.append(replace(fixture.document, source_type="sec_filing"))
