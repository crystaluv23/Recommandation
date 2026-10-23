"""Future seed fixtures execute with explicit issuer identity; history stays put."""

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import tempfile
from unittest import TestCase
from unittest.mock import patch

from scripts.evolve_information_schemes import validate_catalog
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry, SignalExecutionStatus, SignalExecutor, SignalRegistry,
    SignalSpec, SignalValue, _audit_deterministic_fixture,
)


CATALOG = Path(__file__).resolve().parents[1] / "configs/signals_v1.json"
EXPECTED_MEASUREMENTS = {
    "revenue_growth_yoy": 0.3,
    "revenue_acceleration": 0.25,
    "gross_margin_change": 0.1,
    "operating_cash_flow_margin": 0.2,
    "net_share_retirement_yoy": 0.05,
    "cash_reserves": 150_000_000,
}


def financial_entries(catalog):
    """Return the six source-controlled financial capability positives."""
    return [item for item in catalog["signals"]
            if item["spec"]["signal_id"] in EXPECTED_MEASUREMENTS]


def execute_fixture(spec, fixture, *, company_id="capability_fixture"):
    """Run the real executor on explicit fixture documents in an in-memory store."""
    documents = tuple(RawInfoDocument.create(
        document_id=f"seed-{spec.signal_id}-{index}", company_id=company_id,
        source_type=raw["source_type"],
        published_at=datetime.fromisoformat(raw.get("published_at", raw["available_at"])),
        available_at=datetime.fromisoformat(raw["available_at"]),
        content=raw["content"], metadata=raw.get("metadata", {}),
    ) for index, raw in enumerate(fixture["documents"]))
    snapshot = FrozenSignalRegistry(1, "offline-seed-fixture", (spec,), {})
    return SignalExecutor(snapshot, RawInfoStore(documents=documents)).execute_batch(
        (spec.ref,), company_id=company_id,
        as_of=datetime.fromisoformat(fixture["as_of"]),
    ).results[0]


def tree_hashes(root):
    """Bind temporary Registry membership and every persisted byte."""
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


class SeedFixtureIssuerBindingTests(TestCase):
    def setUp(self):
        self.catalog = json.loads(CATALOG.read_text())
        self.guard = ExitStack()
        self.addCleanup(self.guard.close)
        for target, method in ((socket, "socket"), (socket, "create_connection"),
                               (LabelStore, "load"), (LabelStore, "record")):
            self.guard.enter_context(patch.object(
                target, method, side_effect=AssertionError("offline fixtures only")))

    def test_native_install_audit_freeze_and_validate_catalog_expose_all_fourteen(self):
        expected = {SignalSpec.from_dict(item["spec"]).ref
                    for item in self.catalog["signals"] if item.get("enabled", True)}
        self.assertEqual(len(expected), 14)
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            self.assertEqual(registry.install_catalog(CATALOG), 14)
            audit = registry.audit_capabilities()
            self.assertTrue(audit.passed, audit.to_dict())
            self.assertEqual(set(audit.enabled_refs), expected)
            self.assertEqual({spec.ref for spec in registry.freeze().specs}, expected)
        result = validate_catalog(CATALOG)
        self.assertTrue(result["valid"])
        self.assertEqual((result["installed"], result["signal_count"]), (14, 14))

    def test_six_financial_positives_reach_original_numeric_measurements(self):
        entries = financial_entries(self.catalog)
        self.assertEqual(len(entries), 6)
        for item in entries:
            spec = SignalSpec.from_dict(item["spec"])
            for index, fixture in enumerate(item["tests"]):
                with self.subTest(ref=spec.ref):
                    for raw in fixture["documents"]:
                        self.assertEqual(raw["metadata"]["cik"],
                                         json.loads(raw["content"])["cik"])
                    _audit_deterministic_fixture(spec, fixture, index=index)
                    result = execute_fixture(spec, fixture)
                    self.assertEqual(result.execution_status, SignalExecutionStatus.SUCCESS)
                    self.assertEqual(result.value, SignalValue.POSITIVE)
                    self.assertAlmostEqual(result.measurement.value,
                                           EXPECTED_MEASUREMENTS[spec.signal_id])
                    self.assertTrue(result.supporting_evidence)

    def test_missing_mismatched_and_malformed_bindings_stay_technical_failures(self):
        for item in financial_entries(self.catalog):
            spec = SignalSpec.from_dict(item["spec"])
            for variant in ("no_metadata", "no_body_cik", "body_mismatch",
                            "metadata_mismatch", "body_bool", "metadata_float"):
                fixture = deepcopy(item["tests"][0])
                raw = fixture["documents"][0]
                payload = json.loads(raw["content"])
                if variant == "no_metadata":
                    raw.pop("metadata")
                elif variant == "no_body_cik":
                    payload.pop("cik")
                elif variant == "body_mismatch":
                    payload["cik"] = "0000000002"
                elif variant == "metadata_mismatch":
                    raw["metadata"]["cik"] = "0000000002"
                elif variant == "body_bool":
                    payload["cik"] = True
                else:
                    raw["metadata"]["cik"] = 1.0
                raw["content"] = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                with self.subTest(ref=spec.ref, variant=variant):
                    result = execute_fixture(spec, fixture)
                    self.assertEqual(result.value, SignalValue.UNAVAILABLE)
                    self.assertEqual(result.execution_status,
                                     SignalExecutionStatus.VALIDATION_FAILED)
                    self.assertIn("SEC Company Facts", result.execution_error_message)
                    with self.assertRaisesRegex(ValidationError, "technical execution failure: validation_failed"):
                        _audit_deterministic_fixture(spec, fixture, index=0)

    def test_canonical_company_conflict_cannot_be_masked_by_matching_fixture_bindings(self):
        item = financial_entries(self.catalog)[0]
        result = execute_fixture(SignalSpec.from_dict(item["spec"]), item["tests"][0],
                                 company_id="cik_0000000002")
        self.assertEqual(result.execution_status, SignalExecutionStatus.VALIDATION_FAILED)
        self.assertIn("metadata issuer mismatch", result.execution_error_message)

    def test_corrected_catalog_replay_leaves_existing_bad_versions_byte_identical(self):
        legacy = deepcopy(self.catalog)
        for item in financial_entries(legacy):
            for fixture in item["tests"]:
                for raw in fixture["documents"]:
                    raw.pop("metadata")
                    payload = json.loads(raw["content"])
                    payload.pop("cik")
                    raw["content"] = json.dumps(payload, separators=(",", ":"))
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            old_catalog = base / "unbound-seed.json"
            old_catalog.write_text(json.dumps(legacy))
            registry = SignalRegistry(base / "signals")
            self.assertEqual(registry.install_catalog(old_catalog), 14)
            before = tree_hashes(registry.root)
            self.assertEqual(registry.install_catalog(CATALOG), 0)
            self.assertEqual(tree_hashes(registry.root), before)
            audit = registry.audit_capabilities()
            self.assertEqual(set(audit.disabled),
                             {f"{signal_id}:v1" for signal_id in EXPECTED_MEASUREMENTS})
            with self.assertRaisesRegex(ValidationError, "capability audit failed"):
                registry.freeze()
            self.assertEqual(tree_hashes(registry.root), before)

    def test_valid_catalog_replay_preserves_every_version_file_and_frozen_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(CATALOG)
            snapshot = registry.freeze()
            before = tree_hashes(registry.root)
            self.assertEqual(registry.install_catalog(CATALOG), 0)
            self.assertEqual(registry.freeze().registry_hash, snapshot.registry_hash)
            self.assertEqual(tree_hashes(registry.root), before)
