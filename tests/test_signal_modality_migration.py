from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from scripts.migrate_signal_modalities import migrate_registry
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    SignalExecutionType,
    SignalModality,
    SignalRegistry,
    SignalSpec,
)


AS_OF = "2025-02-01T00:00:00+00:00"


def _financial_document(content: str) -> dict[str, object]:
    return {
        "document_id": "fixture",
        "source_type": "financials",
        "published_at": "2025-01-20T00:00:00+00:00",
        "available_at": "2025-01-20T00:00:00+00:00",
        "content": content,
    }


class SignalModalityMigrationTests(TestCase):
    def test_complete_plan_builds_explicit_audited_successor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = SignalRegistry(root / "source" / "signals")
            source.register_stable(
                SignalSpec(
                    signal_id="cash_reserves",
                    version=1,
                    category="financial",
                    description="Read cash.",
                    execution_type=SignalExecutionType.DETERMINISTIC,
                    source_types=("financials",),
                    function="financial.cash_reserves",
                    parameters={"positive_min": 100, "negative_max": 10},
                ),
                tests=(
                    {
                        "name": "cash",
                        "as_of": AS_OF,
                        "expected": "positive",
                        "documents": (
                            _financial_document(
                                '{"schema_version":"sec-company-facts-document-v1",'
                                '"filing_date":"2025-01-20","form":"10-Q",'
                                '"facts":[{"end":"2024-12-31","start":null,'
                                '"tag":"CashAndCashEquivalentsAtCarryingValue",'
                                '"taxonomy":"us-gaap","unit":"USD","value":150}]}'
                            ),
                        ),
                    },
                ),
            )
            source.register_stable(
                SignalSpec(
                    signal_id="guidance_acceleration",
                    version=1,
                    category="management",
                    description="Interpret guidance changes.",
                    execution_type=SignalExecutionType.LLM,
                    source_types=("financials",),
                    skill_file="skill.md",
                ),
                skill="Compare current and prior guidance.",
                tests=(
                    {
                        "name": "guidance",
                        "expected": "neutral",
                        "documents": (_financial_document("Guidance was unchanged."),),
                    },
                ),
            )
            source.register_stable(
                SignalSpec(
                    signal_id="cash_to_current_liabilities_ratio",
                    version=1,
                    category="financial",
                    description="Interpret the cash ratio.",
                    execution_type=SignalExecutionType.LLM,
                    source_types=("financials",),
                    skill_file="skill.md",
                    parameters={"positive_min": 1.0, "negative_max": 1.0},
                ),
                skill="Compute cash divided by current liabilities.",
                tests=(
                    {
                        "name": "legacy",
                        "expected": "negative",
                        "documents": (_financial_document("cash 50 liabilities 100"),),
                    },
                ),
            )
            source_snapshot = source.freeze()
            replacement = {
                "name": "ratio",
                "as_of": AS_OF,
                "expected": "negative",
                "documents": (
                    _financial_document(
                        '{"schema_version":"sec-company-facts-document-v1",'
                        '"filing_date":"2025-01-20","form":"10-Q","facts":['
                        '{"end":"2024-12-31","start":null,'
                        '"tag":"CashAndCashEquivalentsAtCarryingValue",'
                        '"taxonomy":"us-gaap","unit":"USD","value":50},'
                        '{"end":"2024-12-31","start":null,'
                        '"tag":"LiabilitiesCurrent","taxonomy":"us-gaap",'
                        '"unit":"USD","value":100}]}'
                    ),
                ),
            }
            plan = {
                "schema_version": "signal-modality-migration-plan-v1",
                "source_registry_version": source_snapshot.version,
                "source_registry_hash": source_snapshot.registry_hash,
                "signals": [
                    {
                        "source_ref": "cash_reserves:v1",
                        "modality": "structured",
                    },
                    {
                        "source_ref": "guidance_acceleration:v1",
                        "modality": "narrative",
                    },
                    {
                        "source_ref": "cash_to_current_liabilities_ratio:v1",
                        "modality": "structured",
                        "execution": {
                            "type": "deterministic",
                            "function": "financial.cash_to_current_liabilities_ratio",
                        },
                        "replacement_tests": [replacement],
                    },
                ],
            }

            target_root = root / "target" / "signals"
            result = migrate_registry(
                source_root=source.root,
                target_root=target_root,
                plan=plan,
            )
            target = SignalRegistry(target_root)

            self.assertEqual(result["source_registry_hash"], source_snapshot.registry_hash)
            self.assertEqual(result["target_registry_version"], 2)
            self.assertEqual(result["modality_counts"], {"structured": 2, "narrative": 1})
            self.assertTrue(result["capability_audit"]["passed"])
            self.assertEqual(source.version, 1)
            self.assertIsNone(source.latest_spec("cash_reserves").modality)
            self.assertEqual(
                target.latest_spec("cash_reserves").modality,
                SignalModality.STRUCTURED,
            )
            self.assertEqual(
                target.latest_spec("guidance_acceleration").modality,
                SignalModality.NARRATIVE,
            )
            ratio = target.latest_spec("cash_to_current_liabilities_ratio")
            self.assertEqual(ratio.modality, SignalModality.STRUCTURED)
            self.assertEqual(ratio.execution_type, SignalExecutionType.DETERMINISTIC)
            self.assertEqual(
                ratio.function, "financial.cash_to_current_liabilities_ratio"
            )

    def test_plan_must_match_source_hash_and_cover_every_current_ref(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = SignalRegistry(root / "source" / "signals")
            source.register_stable(
                SignalSpec(
                    signal_id="guidance_acceleration",
                    version=1,
                    category="management",
                    description="Interpret guidance changes.",
                    execution_type=SignalExecutionType.LLM,
                    source_types=("financials",),
                    skill_file="skill.md",
                ),
                skill="Compare guidance.",
                tests=(
                    {
                        "name": "guidance",
                        "expected": "neutral",
                        "documents": (_financial_document("No change."),),
                    },
                ),
            )
            snapshot = source.freeze()
            base = {
                "schema_version": "signal-modality-migration-plan-v1",
                "source_registry_version": snapshot.version,
                "source_registry_hash": snapshot.registry_hash,
                "signals": [],
            }
            with self.assertRaisesRegex(ValidationError, "coverage mismatch"):
                migrate_registry(
                    source_root=source.root,
                    target_root=root / "missing" / "signals",
                    plan=base,
                )
            wrong_hash = {
                **base,
                "source_registry_hash": "0" * 64,
                "signals": [
                    {
                        "source_ref": "guidance_acceleration:v1",
                        "modality": "narrative",
                    }
                ],
            }
            with self.assertRaisesRegex(ValidationError, "source identity mismatch"):
                migrate_registry(
                    source_root=source.root,
                    target_root=root / "stale" / "signals",
                    plan=wrong_hash,
                )
