"""Isolated Company Facts proof/reconstruction and immutable-view boundaries."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoOracle, RawInfoStore, content_sha256
from stock_opportunity_agent.data import reviewed_snapshot as reviewed
from stock_opportunity_agent.data.sec_company_facts import (
    STANDARD_FORMS, STANDARD_TAXONOMIES, materialize_company_fact_documents,
)
from stock_opportunity_agent.models import ValidationError


PROFILE = "sec_companyfacts_filed_next_utc_day_v1"


def write_bound(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class CompanyFactsProfileFixture:
    """Build real native products in a temporary oracle, with no external input."""

    def __init__(self, base, *, cutoff="2025-07-31T00:00:00+00:00", normalized_at="2026-10-20T00:00:00+00:00"):
        self.base = Path(base)
        self.oracle = self.base / "oracle"
        RawInfoOracle.load_or_create(self.oracle)
        self.item = {"cik": "0000000001", "company_id": "cik_0000000001", "symbol": "FIXTURE",
            "source_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"}
        self.selection = {"period_end_from": "0001-01-01",
            "period_end_through": datetime.fromisoformat(cutoff).astimezone(timezone.utc).date().isoformat(),
            "available_at_through": cutoff, "taxonomy_allowlist": list(STANDARD_TAXONOMIES),
            "form_allowlist": list(STANDARD_FORMS)}
        self.body = {"cik": 1, "entityName": "Current name é", "facts": {"us-gaap": {
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                {"accn": "0000000002-25-000001", "filed": "2025-01-20", "form": "10-K",
                 "end": "2010-12-31", "val": 10},
                {"accn": "0000000002-25-000002", "filed": "2025-05-05", "form": "10-Q",
                 "end": "2025-03-31", "val": 20},
                {"accn": "0000000002-25-000003", "filed": "2025-07-31", "form": "10-Q",
                 "end": "2025-06-30", "val": 30}]}}}}}
        self.cache = {"endpoint": self.item["source_url"], "params": [["method", "GET"]],
            "source_key": "sec_edgar", "capability": "financial_statements", "payload_kind": "json",
            "retrieved_at": "2026-08-01T00:00:00+00:00", "body": self.body}
        self.cache_binding = write_bound(self.base / "cache.json", self.cache)
        raw_content = json.dumps(self.body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        raw_clock = datetime(2026, 8, 1, 0, 0, 1, tzinfo=timezone.utc)
        self.raw = RawInfoDocument.create(
            document_id="sec_edgar:cik_0000000001:sec_company_facts_raw_response:" + content_sha256(raw_content)[:24],
            company_id=self.item["company_id"], source_type="sec_company_facts_raw_response",
            published_at=raw_clock, available_at=raw_clock, content=raw_content,
            metadata={"cik": self.item["cik"], "provider": "sec_edgar"})
        store = RawInfoStore(self.oracle)
        store.append(self.raw)
        self.raw_binding = self.find_original(self.raw.document_id)
        provenance = {"acquisition_policy_hash": canonical_json_hash({
            "schema_version": "sec-company-facts-acquisition-v1", "selection": self.selection}),
            "acquisition_selection": self.selection}
        self.products, _stats = materialize_company_fact_documents(self.body, item=self.item,
            selection=self.selection, provenance=provenance, retrieved_at=datetime.fromisoformat(normalized_at))
        for product in self.products:
            store.append(product)
        self.normalization = {"schema_version": "sec-companyfacts-normalization-v1",
            "normalizer_profile": PROFILE, "source_cache": self.cache_binding, "raw_response": self.raw_binding,
            "item": self.item, "selection": self.selection, "provenance": provenance,
            "normalized_at": normalized_at, "expected_products": [self.product_identity(product.to_dict())
                for product in self.products]}
        self.normalization_binding = write_bound(self.base / "normalization.json", self.normalization)
        self.review = {"schema_version": "reviewed-raw-info-snapshot-v1",
            "oracle_identity": self.find_original(None),
            "scope": {"as_of": cutoff, "company_ids": [self.item["company_id"]], "acquisition_allowed": False},
            "records": [self.row(product) for product in self.products]}

    def find_original(self, document_id):
        for path in self.oracle.rglob("*.json"):
            value = json.loads(path.read_text())
            if (document_id is None and path.name == "oracle.json") or value.get("document_id") == document_id:
                return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        raise AssertionError("fixture original missing")

    @staticmethod
    def product_identity(record):
        return {"document_id": record["document_id"], "content_hash": record["content_hash"],
            "canonical_record_hash": canonical_json_hash(record)}

    def row(self, document):
        return {"document_id": document.document_id, "company_id": document.company_id,
            "content_hash": document.content_hash, "original_record": self.find_original(document.document_id),
            "verdict": "admitted", "reason": "Isolated original reconstructed from exact retained SEC XBRL.",
            "proof_profile": PROFILE, "reviewed_available_at": document.available_at.isoformat(),
            "proofs": [{"kind": kind, "artifact": binding} for kind, binding in (
                ("sec_companyfacts_cache", self.cache_binding),
                ("sec_companyfacts_raw_response", self.raw_binding),
                ("sec_companyfacts_normalization", self.normalization_binding))]}

    def save(self):
        self.normalization["source_cache"] = self.cache_binding
        self.normalization["raw_response"] = self.raw_binding
        self.normalization_binding = write_bound(self.base / "normalization.json", self.normalization)
        for row in self.review["records"]:
            for proof in row["proofs"]:
                proof["artifact"] = {"sec_companyfacts_cache": self.cache_binding,
                    "sec_companyfacts_raw_response": self.raw_binding,
                    "sec_companyfacts_normalization": self.normalization_binding}[proof["kind"]]
        self.review["manifest_hash"] = canonical_json_hash({k: v for k, v in self.review.items() if k != "manifest_hash"})
        path = self.base / "review.json"
        write_bound(path, self.review)
        return path


class ReviewedCompanyFactsProfileTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def rejected(self, fixture):
        with self.assertRaises(reviewed.ReviewedSourceRejected):
            reviewed.materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
        self.assertFalse((fixture.base / "view").exists())

    def test_native_materialize_restore_worker_and_explicit_subset(self):
        fixture = CompanyFactsProfileFixture(self.base)
        binding = reviewed.materialize_reviewed_snapshot(fixture.save(), self.base / "view")
        store = reviewed.open_raw_info_store(binding["root"], reviewed_snapshot=binding)
        self.assertEqual(store.documents, tuple(fixture.products))
        self.assertEqual(len(store.snapshot().documents), 2)
        self.assertEqual(store.refresh(), 0)
        for product in fixture.products:
            self.assertTrue(product.metadata["retrospective_api_extraction"])
            self.assertTrue(product.metadata["requires_primary_filing_audit"])
            self.assertFalse(store.append(product))
            self.assertEqual(store.load(product.document_id, as_of=product.available_at), product)
            with self.assertRaises(ValidationError):
                store.load(product.document_id, as_of=product.available_at - timedelta(microseconds=1))
        self.assertIn('"end":"2010-12-31"', fixture.products[0].content)
        with self.assertRaises(reviewed.ReviewedSourceRejected):
            store.append(fixture.raw)
        fixture.review["records"] = fixture.review["records"][:1]
        subset = reviewed.materialize_reviewed_snapshot(fixture.save(), self.base / "subset")
        self.assertEqual(len(reviewed.open_raw_info_store(subset["root"], reviewed_snapshot=subset).documents), 1)

    def test_per_review_decode_and_normalizer_reuse_never_crosses_refresh(self):
        fixture = CompanyFactsProfileFixture(self.base)
        path = fixture.save()
        with patch.object(reviewed, "_read_bound", wraps=reviewed._read_bound) as read, patch.object(
                reviewed, "materialize_company_fact_documents", wraps=materialize_company_fact_documents) as normalize:
            binding = reviewed.materialize_reviewed_snapshot(path, self.base / "view")
            self.assertEqual(normalize.call_count, 1)
            cache_reads = [call for call in read.call_args_list if call.args[0] == fixture.cache_binding]
            self.assertEqual(len(cache_reads), 1)
            store = reviewed.open_raw_info_store(binding["root"], reviewed_snapshot=binding)
            store.refresh()
            store.snapshot()
            self.assertEqual(normalize.call_count, 4)
            cache_reads = [call for call in read.call_args_list if call.args[0] == fixture.cache_binding]
            self.assertEqual(len(cache_reads), 4)
        Path(fixture.cache_binding["path"]).write_text("{}")
        for action in (store.refresh, store.snapshot):
            with self.assertRaises(reviewed.ReviewedSourceRejected):
                action()

    def test_rehashed_managed_request_and_provider_identity_fail_closed(self):
        changes = {
            "endpoint": lambda c: c.update(endpoint=c["endpoint"].replace("0000000001", "0000000002")),
            "post": lambda c: c.update(params=[["method", "POST"]]),
            "duplicate_get": lambda c: c.update(params=[["method", "GET"], ["method", "GET"]]),
            "extra_param": lambda c: c.update(params=[["method", "GET"], ["date", "2025-01-20"]]),
            "source": lambda c: c.update(source_key="other"),
            "capability": lambda c: c.update(capability="filings"),
            "kind": lambda c: c.update(payload_kind="text"),
            "wrong_cik": lambda c: c["body"].update(cik=2),
            "malformed_cik": lambda c: c["body"].update(cik="CIK0000000001"),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                fixture = CompanyFactsProfileFixture(self.base / name)
                change(fixture.cache)
                fixture.cache_binding = write_bound(fixture.base / "cache.json", fixture.cache)
                self.rejected(fixture)

    def test_rehashed_original_values_units_periods_filed_times_and_flags_reject(self):
        for variant in ("value", "value_as_float", "unit", "period", "filed", "early", "flag", "flag_as_int", "count_as_float"):
            with self.subTest(variant=variant):
                fixture = CompanyFactsProfileFixture(self.base / variant)
                row = fixture.review["records"][0]
                record = json.loads(Path(row["original_record"]["path"]).read_text())
                content = json.loads(record["content"])
                if variant in {"value", "value_as_float", "unit", "period"}:
                    key, value = {"value": ("value", 999), "value_as_float": ("value", 10.0),
                        "unit": ("unit", "CAD"), "period": ("end", "2011-12-31")}[variant]
                    content["facts"][0][key] = value
                elif variant == "filed":
                    content["filing_date"] = "2025-01-19"
                elif variant == "early":
                    record["available_at"] = record["published_at"]
                elif variant == "flag":
                    record["metadata"]["requires_primary_filing_audit"] = False
                elif variant == "flag_as_int":
                    record["metadata"]["requires_primary_filing_audit"] = 1
                else:
                    record["metadata"]["fact_count"] = float(record["metadata"]["fact_count"])
                record["content"] = json.dumps(content, sort_keys=True, separators=(",", ":"))
                record["content_hash"] = content_sha256(record["content"])
                row["original_record"] = write_bound(Path(row["original_record"]["path"]), record)
                row["content_hash"] = record["content_hash"]
                row["reviewed_available_at"] = record["available_at"]
                if variant not in {"flag_as_int", "count_as_float", "value_as_float"}:
                    fixture.normalization["expected_products"][0] = fixture.product_identity(record)
                self.rejected(fixture)

    def test_numeric_json_type_changes_reject_exact_replay_and_rehashed_restore(self):
        for variant in ("flag_as_int", "count_as_float", "value_as_float"):
            with self.subTest(variant=variant):
                fixture = CompanyFactsProfileFixture(self.base / variant)
                binding = reviewed.materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
                store = reviewed.open_raw_info_store(binding["root"], reviewed_snapshot=binding)
                original = fixture.products[0]
                metadata, content = dict(original.metadata), original.content
                if variant == "flag_as_int": metadata["requires_primary_filing_audit"] = 1
                elif variant == "count_as_float": metadata["fact_count"] = float(metadata["fact_count"])
                else:
                    body = json.loads(content)
                    body["facts"][0]["value"] = float(body["facts"][0]["value"])
                    content = json.dumps(body, sort_keys=True, separators=(",", ":"))
                changed = replace(original, metadata=metadata, content=content, content_hash=content_sha256(content))
                self.assertNotEqual(canonical_json_hash(original.to_dict()), canonical_json_hash(changed.to_dict()))
                with self.assertRaises(reviewed.ReviewedSourceRejected):
                    store.append(changed)
                root = Path(binding["root"])
                manifest = json.loads((root / "reviewed_snapshot.json").read_text())
                entry = manifest["documents"][0]
                entry["sha256"] = write_bound(root / entry["path"], changed.to_dict())["sha256"]
                marker = write_bound(root / "reviewed_snapshot.json", manifest)
                rebound = {**binding, "manifest_sha256": marker["sha256"]}
                with self.assertRaises(reviewed.ReviewedSourceRejected):
                    reviewed.open_raw_info_store(root, reviewed_snapshot=rebound)

    def test_selection_scope_provenance_and_complete_membership_are_enforced(self):
        for variant in ("lower_cap", "future_period", "late_selection", "taxonomies", "forms",
                        "provenance", "missing", "extra", "duplicate", "late_review_row"):
            with self.subTest(variant=variant):
                fixture = CompanyFactsProfileFixture(self.base / variant)
                if variant == "lower_cap": fixture.selection["period_end_from"] = "2022-07-27"
                elif variant == "future_period": fixture.selection["period_end_through"] = "2025-08-01"
                elif variant == "late_selection": fixture.selection["available_at_through"] = "2025-08-01T00:00:00Z"
                elif variant == "taxonomies": fixture.selection["taxonomy_allowlist"] = ["us-gaap"]
                elif variant == "forms": fixture.selection["form_allowlist"] = ["10-K"]
                elif variant == "provenance": fixture.normalization["provenance"]["acquisition_policy_hash"] = "0" * 64
                elif variant == "missing": fixture.normalization["expected_products"].pop()
                elif variant == "extra": fixture.normalization["expected_products"].append({"document_id": "invented"})
                elif variant == "duplicate": fixture.normalization["expected_products"].append(deepcopy(fixture.normalization["expected_products"][0]))
                else: fixture.review["scope"]["as_of"] = "2025-01-21T00:00:00+00:00"
                self.rejected(fixture)

    def test_clocks_and_equivalent_offsets_preserve_utc_cutoff(self):
        for index, cutoff in enumerate(("2025-07-31T00:00:00Z", "2025-07-30T20:00:00-04:00", "2025-07-31T23:59:59Z", "2025-08-01T00:00:00Z")):
            fixture = CompanyFactsProfileFixture(self.base / str(index), cutoff=cutoff,
                normalized_at="2026-10-19T20:00:00-04:00")
            binding = reviewed.materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")
            store = reviewed.open_raw_info_store(binding["root"], reviewed_snapshot=binding)
            self.assertEqual(len(store.documents), 3 if index == 3 else 2)
        for variant in ("old_normalization", "late_cache", "naive", "raw_clock"):
            with self.subTest(variant=variant):
                fixture = CompanyFactsProfileFixture(self.base / variant)
                if variant == "old_normalization": fixture.normalization["normalized_at"] = "2026-08-01T00:00:00Z"
                elif variant == "late_cache":
                    fixture.cache["retrieved_at"] = "2026-08-02T00:00:00Z"
                    fixture.cache_binding = write_bound(fixture.base / "cache.json", fixture.cache)
                elif variant == "naive": fixture.normalization["normalized_at"] = "2026-10-20T00:00:00"
                else:
                    raw = fixture.raw.to_dict()
                    raw["published_at"] = "2026-08-01T00:00:00Z"
                    fixture.raw_binding = write_bound(Path(fixture.raw_binding["path"]), raw)
                self.rejected(fixture)

    def test_whole_raw_legacy_aggregate_and_missing_or_cross_bound_proofs_reject(self):
        for variant in ("whole_raw", "legacy", "missing_proof", "duplicate_proof", "cross_bound"):
            with self.subTest(variant=variant):
                fixture = CompanyFactsProfileFixture(self.base / variant)
                if variant in {"whole_raw", "legacy"}:
                    raw = fixture.raw.to_dict()
                    if variant == "legacy":
                        raw.update(source_type="financials", document_id="legacy-aggregate")
                    record_binding = write_bound(fixture.oracle / (variant + ".json"), raw)
                    row = fixture.review["records"][0]
                    row.update(original_record=record_binding, document_id=raw["document_id"],
                        content_hash=raw["content_hash"], reviewed_available_at=raw["available_at"])
                elif variant == "missing_proof": fixture.review["records"][0]["proofs"].pop()
                elif variant == "duplicate_proof": fixture.review["records"][0]["proofs"].append(deepcopy(fixture.review["records"][0]["proofs"][0]))
                else:
                    fixture.normalization["item"]["company_id"] = "cik_0000000002"
                self.rejected(fixture)

    def test_manifest_original_root_and_worker_membership_drift_fail(self):
        fixture = CompanyFactsProfileFixture(self.base)
        path = fixture.save()
        with self.assertRaises(reviewed.ReviewedSourceRejected):
            reviewed.materialize_reviewed_snapshot(path, fixture.oracle / "nested")
        self.assertFalse((fixture.oracle / "nested").exists())
        binding = reviewed.materialize_reviewed_snapshot(path, self.base / "view")
        store = reviewed.open_raw_info_store(binding["root"], reviewed_snapshot=binding)
        (Path(binding["root"]) / "extra.json").write_text("{}")
        with self.assertRaises(reviewed.ReviewedSourceRejected):
            store.snapshot()
        (Path(binding["root"]) / "extra.json").unlink()
        self.review_changed(path)
        with self.assertRaises(reviewed.ReviewedSourceRejected):
            store.refresh()

    @staticmethod
    def review_changed(path):
        review = json.loads(path.read_text())
        review["scope"]["company_ids"].append("cik_0000000002")
        write_bound(path, review)
