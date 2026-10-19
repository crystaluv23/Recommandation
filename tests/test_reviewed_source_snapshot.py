"""Actual four-source proof admission and immutable store/resolver boundaries."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import (
    materialize_reviewed_snapshot, open_raw_info_store, ReviewedRawInfoStore, ReviewedSourceRejected,
)
from stock_opportunity_agent.data.resolution import EvidenceResolver, RawInfoRequest, DataAcquisitionPolicy
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_control import _build_evidence_resolver, _validate_cycle_execution_request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
REVIEW = ROOT / "reports/local-trusted-source-review-20261019.json"


class ReviewedSourceSnapshotTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.binding = materialize_reviewed_snapshot(REVIEW, self.base / "snapshot")
        self.store = open_raw_info_store(self.binding["root"], reviewed_snapshot=self.binding)
        self.review = json.loads(REVIEW.read_text())

    def relocated_review(self, name):
        """Copy originals into an isolated oracle before destructive counterexamples."""
        review = deepcopy(self.review)
        original_root = Path(review["oracle_identity"]["path"]).parent
        copied_root = self.base / name
        copied_root.mkdir()
        identity = copied_root / "oracle.json"
        identity.write_bytes(Path(review["oracle_identity"]["path"]).read_bytes())
        review["oracle_identity"]["path"] = str(identity)
        for row in review["records"]:
            original = Path(row["original_record"]["path"])
            copied = copied_root / original.relative_to(original_root)
            copied.parent.mkdir(parents=True, exist_ok=True)
            copied.write_bytes(original.read_bytes())
            row["original_record"]["path"] = str(copied)
        return review

    def test_actual_four_source_denominator_and_all_public_read_interfaces(self):
        self.assertEqual([row["verdict"] for row in self.review["records"]], ["admitted", "admitted", "excluded", "unknown"])
        admitted = {row["document_id"] for row in self.review["records"] if row["verdict"] == "admitted"}
        self.assertEqual({doc.document_id for doc in self.store.documents}, admitted)
        cutoff = datetime.fromisoformat(self.review["scope"]["as_of"])
        self.assertEqual({doc.document_id for doc in self.store.search("cik_0001830043", as_of=cutoff)}, admitted)
        self.assertIsInstance(self.store.snapshot(), ReviewedRawInfoStore)
        self.assertEqual(self.store.snapshot().documents, self.store.documents)
        self.assertEqual(self.store.refresh(), 0)
        for row in self.review["records"]:
            if row["verdict"] != "admitted":
                with self.assertRaises(ValidationError):
                    self.store.load(row["document_id"], as_of=cutoff)
        for doc in self.store.documents:
            self.assertFalse(self.store.append(doc))
            self.assertEqual(self.store.load(doc.document_id, as_of=doc.available_at), doc)
            with self.assertRaises(ValidationError):
                self.store.load(doc.document_id, as_of=doc.available_at - timedelta(seconds=1))

    def test_real_resolver_exact_time_and_unknown_is_gap(self):
        resolver = EvidenceResolver(self.store)
        cutoff = datetime.fromisoformat(self.review["scope"]["as_of"])
        for source in ("news", "earnings_call"):
            resolved = resolver.resolve(RawInfoRequest("missing-" + source, "Read actual original material", (source,)),
                company_id="cik_0001830043", identity={}, as_of=cutoff)
            self.assertIsNotNone(resolved.gap)
            self.assertEqual(resolved.documents, ())
        result = resolver.resolve(RawInfoRequest("sec", "Read disclosed guidance", ("filing",), query="second quarter 2025"),
            company_id="cik_0001830043", identity={}, as_of=cutoff, include_context=True)
        self.assertTrue(result.documents)
        self.assertTrue(all(row.document_id.startswith("sec:") for row in result.documents))
        self.assertIn("$244", json.dumps(result.to_dict()))

    def test_snapshot_replay_append_and_acquisition_cannot_widen(self):
        excluded = RawInfoDocument.from_dict(json.loads(Path(self.review["records"][2]["original_record"]["path"]).read_text()))
        for store in (self.store, self.store.snapshot()):
            with self.assertRaises(ReviewedSourceRejected):
                store.append(excluded)
            with self.assertRaises(ReviewedSourceRejected):
                store.append(replace(store.documents[0], available_at=store.documents[0].available_at + timedelta(seconds=1)))
            with self.assertRaises(ReviewedSourceRejected):
                EvidenceResolver(store, adapters=(object(),), policy=DataAcquisitionPolicy(enabled=True,
                    allowed_providers=("*",), allowed_capabilities=("*",), allowed_source_types=("*",),
                    max_requests_per_cycle=1, max_requests_per_run=1))
            self.assertEqual(len(store.documents), 2)

    def test_explicit_binding_rejects_downgrade_root_hash_and_added_file(self):
        root = Path(self.binding["root"])
        with self.assertRaises(ReviewedSourceRejected):
            open_raw_info_store(root)
        with self.assertRaises(ValidationError):
            RawInfoStore(root)
        for changed in ({**self.binding, "store_type": "plain"}, {**self.binding, "manifest_sha256": "0" * 64},
                        {**self.binding, "root": str(ROOT / "runs/cold_start/data/global-raw-info-oracle-v1")}):
            with self.assertRaises(ReviewedSourceRejected):
                open_raw_info_store(root, reviewed_snapshot=changed)
        marker = root / "reviewed_snapshot.json"
        renamed = root / "renamed.json"
        marker.rename(renamed)
        with self.assertRaises(ReviewedSourceRejected):
            open_raw_info_store(root, reviewed_snapshot=self.binding)
        renamed.rename(marker)
        (root / "extra.json").write_text("{}")
        for action in (self.store.refresh, self.store.snapshot):
            with self.assertRaises(ReviewedSourceRejected):
                action()
        self.assertEqual(len(self.store.documents), 2)

    def test_proof_drift_rechecked_without_touching_originals(self):
        review = deepcopy(self.review)
        proof = review["records"][0]["proofs"][0]["artifact"]
        copied = self.base / "proof.json"
        copied.write_bytes(Path(proof["path"]).read_bytes())
        proof["path"] = str(copied)
        review["manifest_hash"] = canonical_json_hash({k: v for k, v in review.items() if k != "manifest_hash"})
        review_path = self.base / "copied-review.json"
        review_path.write_text(json.dumps(review))
        binding = materialize_reviewed_snapshot(review_path, self.base / "copy-snapshot")
        copied.write_text("{}")
        with self.assertRaises(ReviewedSourceRejected):
            open_raw_info_store(binding["root"], reviewed_snapshot=binding)

    def test_source_shape_metadata_availability_and_duplicate_proofs_are_rejected(self):
        for change in ("source_type", "metadata", "availability", "duplicate_proof", "missing_proof_field"):
            with self.subTest(change=change):
                review = self.relocated_review(change + "-oracle")
                row = review["records"][0]
                record = json.loads(Path(row["original_record"]["path"]).read_text())
                if change == "source_type":
                    record["source_type"] = "news"
                elif change == "metadata":
                    record["metadata"]["accession_number"] = "different-accession"
                elif change == "availability":
                    record["available_at"] = "2025-06-25T12:20:34+00:00"
                elif change == "duplicate_proof":
                    row["proofs"].append(deepcopy(row["proofs"][0]))
                else:
                    del row["proofs"][0]["endpoint"]
                copied = Path(row["original_record"]["path"])
                copied.write_text(json.dumps(record))
                row["original_record"] = {"path": str(copied), "sha256": hashlib.sha256(copied.read_bytes()).hexdigest()}
                review["manifest_hash"] = canonical_json_hash({k: v for k, v in review.items() if k != "manifest_hash"})
                path = self.base / (change + "-review.json")
                path.write_text(json.dumps(review))
                with self.assertRaises(ReviewedSourceRejected):
                    materialize_reviewed_snapshot(path, self.base / (change + "-snapshot"))

    def test_minimal_input_verification_cannot_drop_reviewed_binding(self):
        import run_minimal_rounds as minimal
        frozen = {"reviewed_source_snapshot": self.binding,
            "source_files": [{"source_path": str(path), "sha256": minimal._hash_file(path)}
                for path in (self.store.root / "documents").glob("*.json")],
            "approved_manifest_hash": minimal._hash_file(minimal.APPROVED),
            "label_manifest_hash": minimal._hash_file(minimal.LABELS / "manifest.json"),
            "label_records_hash": minimal._hash_file(minimal.LABELS / "labels.jsonl"),
            "source_integrity_review_hash": minimal._hash_file(minimal.SOURCE_REVIEW)}
        workspace = self.base / "input"
        workspace.mkdir()
        manifest = workspace / "input_manifest.json"
        manifest.write_text(json.dumps(frozen))
        self.assertEqual(minimal._verify_inputs(workspace)["reviewed_source_snapshot"], self.binding)
        del frozen["reviewed_source_snapshot"]
        manifest.write_text(json.dumps(frozen))
        with self.assertRaisesRegex(ValidationError, "reviewed binding missing"):
            minimal._verify_inputs(workspace)

    def test_production_resolver_factory_rejects_enabled_contract_even_without_external_flag(self):
        policy = DataAcquisitionPolicy(enabled=True, allowed_providers=("*",), allowed_capabilities=("*",),
            allowed_source_types=("*",), max_requests_per_cycle=1, max_requests_per_run=1)
        contract = SimpleNamespace(executable=True, limits={"reviewed_source_snapshot": self.binding}, data_acquisition=policy)
        with self.assertRaises(ReviewedSourceRejected):
            _validate_cycle_execution_request(contract, allow_data_external=False)
        with self.assertRaises(ReviewedSourceRejected):
            _build_evidence_resolver(self.base / "runtime", self.store, contract=contract,
                allow_data_external=False, environ={}, cycle_id=1)

    def test_submissions_endpoint_must_match_sec_issuer(self):
        for endpoint in ("https://example.invalid/submissions/CIK0001830043.json",
                         "https://data.sec.gov/submissions/CIK0000000001.json", ""):
            with self.subTest(endpoint=endpoint):
                review = deepcopy(self.review)
                proof = review["records"][0]["proofs"][1]["artifact"]
                value = json.loads(Path(proof["path"]).read_text())
                value["endpoint"] = endpoint
                copied = self.base / "submissions.json"
                copied.write_text(json.dumps(value))
                proof.update(path=str(copied), sha256=hashlib.sha256(copied.read_bytes()).hexdigest())
                review["manifest_hash"] = canonical_json_hash({k: v for k, v in review.items() if k != "manifest_hash"})
                path = self.base / "submissions-review.json"
                path.write_text(json.dumps(review))
                with self.assertRaisesRegex(ReviewedSourceRejected, "endpoint"):
                    materialize_reviewed_snapshot(path, self.base / "bad-submissions-snapshot")

    def test_materialization_cannot_write_inside_original_oracle_even_via_symlink(self):
        review = self.relocated_review("oracle")
        original_root = self.base / "oracle"
        review["manifest_hash"] = canonical_json_hash({k: v for k, v in review.items() if k != "manifest_hash"})
        path = self.base / "oracle-copy-review.json"
        path.write_text(json.dumps(review))
        alias = self.base / "oracle-symlink"
        alias.symlink_to(original_root, target_is_directory=True)
        for target in (original_root / "nested", alias / "nested"):
            with self.subTest(target=target), self.assertRaisesRegex(ReviewedSourceRejected, "outside"):
                materialize_reviewed_snapshot(path, target)
            self.assertFalse(target.exists())

    def test_declared_oracle_identity_cannot_be_relocated_without_original_records(self):
        review = deepcopy(self.review)
        copied_identity = self.base / "identity-only.json"
        copied_identity.write_bytes(Path(review["oracle_identity"]["path"]).read_bytes())
        review["oracle_identity"]["path"] = str(copied_identity)
        review["manifest_hash"] = canonical_json_hash({k: v for k, v in review.items() if k != "manifest_hash"})
        path = self.base / "relocated-identity-review.json"
        path.write_text(json.dumps(review))
        with self.assertRaisesRegex(ReviewedSourceRejected, "outside the declared"):
            materialize_reviewed_snapshot(path, self.base / "identity-only-snapshot")

    def test_fresh_narrow_cli_freeze_restores_view_and_preserves_full_readiness_failure(self):
        from diagnose_reviewed_source_snapshot import diagnose, restore_inputs
        result = diagnose(REVIEW, self.base / "diagnostic")
        self.assertEqual(result["minimal_full_preflight"]["status"], "full_readiness_rejected")
        self.assertTrue(result["original_records_unchanged"])
        self.assertEqual(len(result["admitted_document_ids"]), 2)
        path = self.base / "diagnostic/input_manifest.json"
        value = json.loads(path.read_text())
        value["reviewed_source_snapshot"]["root"] = str(ROOT / "runs/cold_start/data/global-raw-info-oracle-v1")
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ReviewedSourceRejected, "freeze changed"):
            restore_inputs(path, result["input_manifest_hash"])
