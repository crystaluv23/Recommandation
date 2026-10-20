"""Offline capture identity, legacy reconstruction and reviewed-view boundaries."""
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
from stock_opportunity_agent.data import acquisition, backfill, reviewed_snapshot as reviewed
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore, capture_document_id
from stock_opportunity_agent.data.resolution import RawInfoRequest, _deduplicate_documents
from stock_opportunity_agent.data.sec_company_facts import (
    CAPTURE_IDENTITY_POLICY, LEGACY_IDENTITY_POLICY, materialize_company_fact_documents,
)
from stock_opportunity_agent.models import ValidationError
from tests.test_reviewed_companyfacts_profile import CompanyFactsProfileFixture, write_bound
from tests.test_data_backfill import (
    _one_company_submissions_plan, _managed_company_facts_client, FakeSecJsonTransport,
)
from stock_opportunity_agent.data.sources.state import RawDataCache


PROFILE = "sec_companyfacts_capture_filed_next_utc_day_v1"
ROOT = Path(__file__).resolve().parents[1]


def capture_fixture(base, *, capture_raw=False):
    fixture = CompanyFactsProfileFixture(base)
    old_records = [p.to_dict() for p in fixture.products]
    fixture.products, _ = materialize_company_fact_documents(fixture.body, item=fixture.item,
        selection=fixture.selection, provenance=fixture.normalization["provenance"],
        retrieved_at=datetime.fromisoformat(fixture.normalization["normalized_at"]),
        identity_policy=CAPTURE_IDENTITY_POLICY)
    if capture_raw:
        fixture.raw = fixture.raw.as_capture()
        RawInfoStore(fixture.oracle).append(fixture.raw)
        fixture.raw_binding = fixture.find_original(fixture.raw.document_id)
    store = RawInfoStore(fixture.oracle)
    for product in fixture.products:
        store.append(product)
    fixture.normalization.update(schema_version="sec-companyfacts-normalization-v2",
        normalizer_profile=PROFILE, identity_policy=CAPTURE_IDENTITY_POLICY,
        expected_products=[fixture.product_identity(p.to_dict()) for p in fixture.products])
    fixture.review["records"] = [fixture.row(p) for p in fixture.products]
    for row in fixture.review["records"]:
        row["proof_profile"] = PROFILE
    return fixture, old_records


class CaptureIdentityTests(TestCase):
    def document(self, metadata=None):
        clock = datetime(2025, 1, 2, tzinfo=timezone.utc)
        return RawInfoDocument.create(document_id="legacy-source", company_id="issuer",
            source_type="sec_company_facts", content="Complete source é", published_at=clock,
            available_at=clock + timedelta(days=1), metadata=metadata or {"capture": {"number": 1}})

    def test_complete_capture_and_recorded_replay_preserve_facts_and_clocks(self):
        old = self.document()
        document = old.as_capture()
        self.assertTrue(document.document_id.startswith("rawcap:v1:"))
        self.assertEqual({k: v for k, v in document.to_dict().items() if k != "document_id"},
                         {k: v for k, v in old.to_dict().items() if k != "document_id"})
        with tempfile.TemporaryDirectory() as directory:
            store = RawInfoStore(directory, documents=(old, document))
            self.assertFalse(store.append(document.as_capture()))
            restored = RawInfoStore(directory)
            self.assertFalse(restored.append(RawInfoDocument.from_dict(document.to_dict())))
            self.assertEqual(restored.load(old.document_id).to_dict(), old.to_dict())
            self.assertEqual(restored.snapshot().load(document.document_id).to_dict(), document.to_dict())
            with self.assertRaises(ValidationError):
                restored.load(document.document_id, as_of=document.available_at - timedelta(microseconds=1))

    def test_every_source_field_and_json_type_participates_in_identity(self):
        old = self.document()
        variants = [replace(old, company_id="other"), replace(old, source_type="other"),
            replace(old, published_at=old.published_at - timedelta(seconds=1)),
            replace(old, available_at=old.available_at + timedelta(seconds=1)),
            replace(old, metadata={"capture": {"number": 1}, "selection": "other"})]
        variants += [replace(old, metadata={"capture": {"number": value}}) for value in (True, 1.0, None, "1")]
        variants += [replace(old, metadata={"capture": {}})]
        ids = [old.as_capture().document_id] + [v.as_capture().document_id for v in variants]
        self.assertEqual(len(ids), len(set(ids)))
        reordered = self.document({"z": [True, 1, 1.0, None], "a": "é"})
        self.assertEqual(reordered.as_capture().document_id,
                         replace(reordered, metadata={"a": "é", "z": [True, 1, 1.0, None]}).as_capture().document_id)

    def test_non_json_and_nonfinite_capture_metadata_reject(self):
        for value in (float("nan"), float("inf"), (1, 2), {1: "number key"}):
            with self.subTest(value=repr(value)), self.assertRaises(ValidationError):
                self.document({"source": value}).as_capture()

    def test_same_claimed_capture_id_rejects_type_and_serialized_field_drift(self):
        document = self.document({"flag": True, "count": 1}).as_capture()
        for field, value in (("flag", 1), ("count", 1.0)):
            record = deepcopy(document.to_dict())
            record["metadata"][field] = value
            with self.assertRaises(ValidationError):
                RawInfoDocument.from_dict(record)
        for change in ({"extra": 1}, {"content": "changed"}, {"document_id": "rawcap:v2:invalid"}):
            record = {**document.to_dict(), **change}
            with self.assertRaises(ValidationError):
                RawInfoDocument.from_dict(record)
        record = document.to_dict()
        del record["metadata"]
        with self.assertRaises(ValidationError):
            RawInfoDocument.from_dict(record)

    def test_nested_mutation_cannot_bypass_append_load_or_refresh(self):
        for action in ("append", "load", "search", "documents", "snapshot"):
            document = self.document().as_capture()
            store = RawInfoStore(documents=(document,))
            document.metadata["capture"]["number"] = 1.0
            with self.assertRaises(ValidationError):
                if action == "append":
                    store.append(document)
                elif action == "load":
                    store.load(document.document_id)
                elif action == "search":
                    store.search(document.company_id, as_of=document.available_at)
                elif action == "documents":
                    _ = store.documents
                else:
                    store.snapshot()
        document = self.document().as_capture()
        with tempfile.TemporaryDirectory() as directory:
            store = RawInfoStore(directory, documents=(document,))
            path = Path(directory) / document.source_type / document.company_id / (document.document_id + ".json")
            record = document.to_dict()
            record["metadata"]["capture"]["number"] = True
            write_bound(path, record)
            for action in (store.refresh, lambda: RawInfoStore(directory)):
                with self.assertRaises(ValidationError):
                    action()

    def test_legacy_same_content_replay_and_content_dedup_remain_unchanged(self):
        old = self.document()
        refetch = replace(old, metadata={"different": "capture"})
        store = RawInfoStore(documents=(old,))
        self.assertFalse(store.append(refetch))
        self.assertEqual(store.load(old.document_id).to_dict(), old.to_dict())
        captures = (old.as_capture(), refetch.as_capture())
        unique, duplicates = _deduplicate_documents(captures)
        self.assertEqual(len(unique), 1)
        self.assertEqual(len(duplicates), 1)
        self.assertEqual({p.document_id for p in captures}, {unique[0].document_id, duplicates[0]})

    def test_actual_gpre_four_conflicts_preserve_old_and_new_captures_in_temp_store(self):
        base = ROOT / "runs/diagnostics/reviewed_frozen_source_snapshot_20261020_v1/stage/cases/cik_0001309402:20250530/products"
        oracle = ROOT / "runs/cold_start/data/global-raw-info-oracle-v1/sec_company_facts/cik_0001309402"
        rows = (
            ("0001309402-24-000092:aa05ed7e72b76d79", "959d933f40ae6fd5f0a5e227263923ac6a7f23c34e31a95f92986ec273e66fcb", "88dcb0c51ac4d2c74bb20874678396d9f06f1300906284b3bd3f7a0e28622011"),
            ("0001309402-24-000114:b0c4c525055d1268", "bf933c3448c23792e6eec867ea946de401839d70d374ae2c742ece195524865c", "52258727ab2e2b7a0701dc0f160b609fae21bba0b434537e5d8eef92bb6a8940"),
            ("0001309402-24-000129:cedad9eff3b39e03", "e45cd385e61a5c0f8057dda6e8fa16058357a7b30924a7f653a359aff10acace", "04439ceea8deb80e326b24608aefdc36e6f78cbea831147f4017b0eec1c17acc"),
            ("0001309402-25-000089:eab48ba69f5ebb47", "f7511fb374afaf01a49ce89726d3a66a73080862c364406f55d5ead6900aa03e", "c4673a4862425ecfda881a5edbbfbcf6619ae890a389e79063a3fb80efa0cc09"))
        bindings = []
        with tempfile.TemporaryDirectory() as directory:
            store = RawInfoStore(directory)
            for suffix, old_hash, new_hash in rows:
                name = "secfacts:0001309402:" + suffix + ".json"
                paths = (oracle / name, base / name)
                for path, expected in zip(paths, (old_hash, new_hash)):
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
                    bindings.append((path, expected))
                old, candidate = [RawInfoDocument.from_dict(json.loads(p.read_bytes())) for p in paths]
                capture = candidate.as_capture()
                self.assertEqual(old.content, capture.content)
                self.assertEqual((old.published_at, old.available_at), (capture.published_at, capture.available_at))
                self.assertNotEqual(old.metadata, capture.metadata)
                self.assertTrue(store.append(old))
                self.assertTrue(store.append(capture))
                self.assertFalse(store.append(capture.as_capture()))
                self.assertEqual(store.load(old.document_id).to_dict(), old.to_dict())
            restored = RawInfoStore(directory)
            self.assertEqual(len(restored.documents), 8)
            self.assertEqual(len(_deduplicate_documents(restored.documents)[0]), 4)
        for path, expected in bindings:
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)


class CompanyFactsCaptureProfileTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def test_capture_profile_native_materialize_worker_restart_and_legacy_raw_proof(self):
        for capture_raw in (False, True):
            base = self.base / str(capture_raw)
            fixture, old_records = capture_fixture(base, capture_raw=capture_raw)
            binding = reviewed.materialize_reviewed_snapshot(fixture.save(), base / "view")
            store = reviewed.open_raw_info_store(binding["root"], reviewed_snapshot=binding)
            self.assertEqual([p.to_dict() for p in store.documents], sorted(
                [p.to_dict() for p in fixture.products], key=lambda p: p["document_id"]))
            self.assertEqual(store.snapshot().documents, store.documents)
            self.assertEqual(store.refresh(), 0)
            for p in fixture.products:
                self.assertFalse(store.append(p))
                self.assertEqual(store.load(p.document_id, as_of=p.available_at).to_dict(), p.to_dict())
            originals = RawInfoStore(fixture.oracle)
            for record in old_records:
                self.assertEqual(originals.load(record["document_id"]).to_dict(), record)

    def test_legacy_profile_reconstructs_same_complete_records_without_capture(self):
        fixture = CompanyFactsProfileFixture(self.base)
        explicit, _ = materialize_company_fact_documents(fixture.body, item=fixture.item,
            selection=fixture.selection, provenance=fixture.normalization["provenance"],
            retrieved_at=datetime.fromisoformat(fixture.normalization["normalized_at"]),
            identity_policy=LEGACY_IDENTITY_POLICY)
        self.assertEqual([p.to_dict() for p in explicit], [p.to_dict() for p in fixture.products])
        binding = reviewed.materialize_reviewed_snapshot(fixture.save(), self.base / "view")
        self.assertTrue(all(p.document_id.startswith("secfacts:") for p in reviewed.ReviewedRawInfoStore(binding).documents))

    def test_capture_profile_full_set_required_even_for_admitted_subset(self):
        fixture, _ = capture_fixture(self.base)
        fixture.review["records"] = fixture.review["records"][:1]
        binding = reviewed.materialize_reviewed_snapshot(fixture.save(), self.base / "subset")
        self.assertEqual(len(reviewed.ReviewedRawInfoStore(binding).documents), 1)
        fixture.normalization["expected_products"].pop()
        with self.assertRaises(reviewed.ReviewedSourceRejected):
            reviewed.materialize_reviewed_snapshot(fixture.save(), self.base / "bad")

    def test_profile_recipe_selection_clock_and_value_changes_reject(self):
        changes = {
            "legacy_recipe": lambda f: f.normalization.update(identity_policy=LEGACY_IDENTITY_POLICY),
            "schema": lambda f: f.normalization.update(schema_version="sec-companyfacts-normalization-v1"),
            "selection": lambda f: f.normalization["selection"].update(period_end_from="2010-01-01"),
            "clock": lambda f: f.normalization.update(normalized_at="2025-01-01T00:00:00+00:00"),
            "missing": lambda f: f.normalization["expected_products"].pop(),
            "extra": lambda f: f.normalization["expected_products"].append(f.normalization["expected_products"][0]),
            "value": lambda f: f.cache["body"]["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"]["units"]["USD"][0].update(val=10.0),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                fixture, _ = capture_fixture(self.base / name)
                change(fixture)
                fixture.cache_binding = write_bound(fixture.base / "cache.json", fixture.cache)
                with self.assertRaises(reviewed.ReviewedSourceRejected):
                    reviewed.materialize_reviewed_snapshot(fixture.save(), fixture.base / "view")

    def test_rehashed_complete_record_type_drift_and_worker_proof_drift_reject(self):
        fixture, _ = capture_fixture(self.base)
        binding = reviewed.materialize_reviewed_snapshot(fixture.save(), self.base / "view")
        store = reviewed.ReviewedRawInfoStore(binding)
        path = Path(fixture.review["records"][0]["original_record"]["path"])
        value = json.loads(path.read_bytes())
        value["metadata"]["requires_primary_filing_audit"] = 1
        fixture.review["records"][0]["original_record"] = write_bound(path, value)
        with self.assertRaises(reviewed.ReviewedSourceRejected):
            reviewed.materialize_reviewed_snapshot(fixture.save(), self.base / "bad")
        for action in (store.refresh, store.snapshot):
            with self.assertRaises(reviewed.ReviewedSourceRejected):
                action()

    def test_acquisition_explicit_capture_and_recorded_clock_replay(self):
        fixture = CompanyFactsProfileFixture(self.base)
        class Client:
            def company_facts(self, cik):
                return deepcopy(fixture.body)
        clock = datetime.fromisoformat(fixture.normalization["normalized_at"])
        class RecordedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock
        request = RawInfoRequest(request_id="facts", description="financials", source_types=("financials",))
        with patch.object(acquisition, "datetime", RecordedClock):
            first = acquisition.SecCompanyFactsAdapter(Client()).acquire(request,
                company_id=fixture.item["company_id"], identity={"cik": fixture.item["cik"], "symbol": "FIXTURE"},
                as_of=datetime.fromisoformat(fixture.selection["available_at_through"])).documents
            second = acquisition.SecCompanyFactsAdapter(Client()).acquire(request,
                company_id=fixture.item["company_id"], identity={"cik": fixture.item["cik"], "symbol": "FIXTURE"},
                as_of=datetime.fromisoformat(fixture.selection["available_at_through"])).documents
        self.assertEqual([p.to_dict() for p in first], [p.to_dict() for p in second])
        self.assertTrue(all(p.document_id == capture_document_id(p.to_dict()) for p in first))
        self.assertEqual(first[0].source_type, "sec_company_facts_raw_response")

    def test_backfill_v2_binds_capture_and_v1_loader_wrapper_stays_legacy(self):
        _one_company_submissions_plan(self.base)
        path = self.base / "facts-plan.json"
        plan = backfill.write_sec_company_facts_backfill_plan(
            acquisition_scope_path=self.base / "acquisition_scope.json", output_path=path)
        self.assertEqual(plan["schema_version"], "sec-company-facts-backfill-plan-v2")
        self.assertEqual(plan["identity_policy"], CAPTURE_IDENTITY_POLICY)
        self.assertEqual(backfill.load_sec_company_facts_backfill_plan(path), plan)
        legacy = deepcopy(plan)
        legacy.update(schema_version="sec-company-facts-backfill-plan-v1")
        legacy.pop("identity_policy")
        legacy["plan_hash"] = canonical_json_hash({k: v for k, v in legacy.items() if k != "plan_hash"})
        write_bound(path, legacy)
        self.assertEqual(backfill.load_sec_company_facts_backfill_plan(path), legacy)
        fixture = CompanyFactsProfileFixture(self.base / "fixture")
        default, _ = backfill._company_fact_documents(fixture.body, item=fixture.item,
            selection=fixture.selection, plan_hash="frozen", retrieved_at=datetime.fromisoformat(fixture.normalization["normalized_at"]))
        explicit, _ = materialize_company_fact_documents(fixture.body, item=fixture.item,
            selection=fixture.selection, provenance={"backfill_plan_hash": "frozen"},
            retrieved_at=datetime.fromisoformat(fixture.normalization["normalized_at"]), identity_policy=LEGACY_IDENTITY_POLICY)
        self.assertEqual([p.to_dict() for p in default], [p.to_dict() for p in explicit])
        for source in (plan, legacy):
            wrong = deepcopy(source)
            wrong["identity_policy"] = LEGACY_IDENTITY_POLICY
            wrong["plan_hash"] = canonical_json_hash({k: v for k, v in wrong.items() if k != "plan_hash"})
            write_bound(path, wrong)
            with self.assertRaises(ValidationError):
                backfill.load_sec_company_facts_backfill_plan(path)


    def test_cached_v2_runner_recovery_and_v1_runner_do_not_mint_new_clocks(self):
        _one_company_submissions_plan(self.base)
        scope_path = self.base / "acquisition_scope.json"
        scope = json.loads(scope_path.read_bytes())
        scope["prediction_dates"] = ["2025-07-31"]
        write_bound(scope_path, scope)
        path = self.base / "plan.json"
        plan = backfill.write_sec_company_facts_backfill_plan(
            acquisition_scope_path=self.base / "acquisition_scope.json", output_path=path)
        fixture = CompanyFactsProfileFixture(self.base / "fixture")
        body = deepcopy(fixture.body)
        body["cik"] = 1234
        cache = RawDataCache(self.base / "cache")
        inner = FakeSecJsonTransport(body)
        client = _managed_company_facts_client(self.base, cache, inner)
        def run(name, limit):
            return backfill.run_sec_company_facts_backfill(plan_path=path, cache=cache,
                progress_path=self.base / (name + "-progress.json"),
                raw_info_root=self.base / name, client=client, max_network_requests=limit,
                now=lambda: datetime(2040, 1, 1, tzinfo=timezone.utc))
        first = run("first", 1)
        self.assertEqual(first["status"], "completed")
        recovered = run("recovered", 0)
        self.assertEqual(recovered["status"], "completed")
        self.assertEqual(inner.calls, 1)
        records = [p.to_dict() for p in RawInfoStore(self.base / "first").documents]
        self.assertTrue(records)
        self.assertTrue(all(p["document_id"].startswith("rawcap:v1:") for p in records))
        self.assertEqual(records, [p.to_dict() for p in RawInfoStore(self.base / "recovered").documents])
        self.assertTrue(all(p["metadata"]["retrieved_at"] != "2040-01-01T00:00:00+00:00" for p in records))
        legacy = deepcopy(plan)
        legacy["schema_version"] = "sec-company-facts-backfill-plan-v1"
        legacy.pop("identity_policy")
        legacy["plan_hash"] = canonical_json_hash({k: v for k, v in legacy.items() if k != "plan_hash"})
        write_bound(path, legacy)
        old = run("legacy", 0)
        self.assertEqual(old["status"], "completed")
        self.assertEqual(inner.calls, 1)
        self.assertTrue(all(p.document_id.startswith("secfacts:") for p in RawInfoStore(self.base / "legacy").documents))
