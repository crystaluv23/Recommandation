from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_benefit import (
    BenefitArm,
    CapabilityCaseResult,
    ConfirmationCohortLedger,
    EvolutionBenefitEvaluator,
    EvolutionBenefitProtocol,
    EvolutionLifecycleEvidence,
    SystemCaseResult,
    SlowMemoryAblationManifest,
    write_evolution_benefit_report,
)
from stock_opportunity_agent.signal_library import (
    SignalEvidence,
    SignalExecutionStatus,
    SignalValue,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class EvolutionBenefitTests(TestCase):
    def test_ablation_manifest_requires_all_frozen_conditions(self) -> None:
        manifest = SlowMemoryAblationManifest(
            ablation_id="slow_memory_v1",
            fast_start_hash=digest("fast"),
            registry_start_hash=digest("registry"),
            seed=7,
            model_hash=digest("model"),
            budget_hash=digest("budget"),
            generated_registry_hashes={
                "no_memory": digest("none"),
                "episodes_only": digest("episodes"),
                "episodes_and_lessons": digest("lessons"),
            },
            allowed_comparisons=(("episodes_only", "episodes_and_lessons"),),
        )

        self.assertEqual(len(manifest.manifest_hash), 64)

    def test_confirmation_ledger_rejects_same_issuer_at_new_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = ConfirmationCohortLedger(Path(directory) / "ledger.json")
            first = self.protocol(protocol_id="first")
            ledger.reserve(first)
            second = replace(
                first,
                protocol_id="second",
                case_ids=("new_1", "new_2", "new_3", "new_4"),
                issuer_by_case={
                    "new_1": "issuer_1",
                    "new_2": "issuer_5",
                    "new_3": "issuer_6",
                    "new_4": "issuer_7",
                },
                candidate_capability_case_ids=("new_measurement",),
                candidate_capability_issuer_by_case={
                    "new_measurement": "issuer_8"
                },
            )

            with self.assertRaisesRegex(ValidationError, "issuers were already"):
                ledger.reserve(second)

    def test_confirmation_ledger_allows_only_frozen_ablation_group_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = ConfirmationCohortLedger(Path(directory) / "ledger.json")
            manifest = SlowMemoryAblationManifest(
                ablation_id="slow_memory_group",
                fast_start_hash=digest("fast"),
                registry_start_hash=digest("registry"),
                seed=7,
                model_hash=digest("model"),
                budget_hash=digest("budget"),
                generated_registry_hashes={
                    "no_memory": digest("none"),
                    "episodes_only": digest("episodes"),
                    "episodes_and_lessons": digest("lessons"),
                },
                allowed_comparisons=(
                    ("no_memory", "episodes_only"),
                    ("episodes_only", "episodes_and_lessons"),
                ),
            )
            first = self.protocol(protocol_id="group_first")
            second = replace(first, protocol_id="group_second")

            self.assertTrue(
                ledger.reserve(
                    first,
                    ablation_manifest=manifest,
                    comparison=("no_memory", "episodes_only"),
                )
            )
            self.assertTrue(
                ledger.reserve(
                    second,
                    ablation_manifest=manifest,
                    comparison=("episodes_only", "episodes_and_lessons"),
                )
            )
            with self.assertRaisesRegex(ValidationError, "not frozen"):
                ledger.reserve(
                    replace(first, protocol_id="group_forbidden"),
                    ablation_manifest=manifest,
                    comparison=("no_memory", "episodes_and_lessons"),
                )

    def protocol(
        self, *, protocol_id: str = "confirmation_v1"
    ) -> EvolutionBenefitProtocol:
        return EvolutionBenefitProtocol(
            protocol_id=protocol_id,
            case_ids=("case_1", "case_2", "case_3", "case_4"),
            issuer_by_case={
                "case_1": "issuer_1",
                "case_2": "issuer_2",
                "case_3": "issuer_3",
                "case_4": "issuer_4",
            },
            replicate_ids=("replicate_1", "replicate_2"),
            candidate_capability_case_ids=("measurement_1",),
            candidate_capability_issuer_by_case={
                "measurement_1": "issuer_1",
            },
            baseline_plan_hash=digest("a"),
            candidate_plan_hash=digest("b"),
            baseline_registry_hash=digest("c"),
            candidate_registry_hash=digest("d"),
            model_hash=digest("e"),
            budget_hash=digest("f"),
            projection_hash=digest("1"),
            minimum_case_count=4,
            minimum_issuer_count=4,
            minimum_primary_f1_gain=0.5,
            minimum_cluster_interval_lower_bound=0.0,
            maximum_coverage_drop=0.0,
            maximum_failure_rate=0.0,
            maximum_cost_increase_ratio=0.2,
            minimum_candidate_independent_fixtures=1,
            minimum_candidate_measurement_accuracy=1.0,
            bootstrap_samples=100,
            bootstrap_seed=7,
            current_look=1,
            maximum_looks=1,
        )

    def system_results(self, protocol: EvolutionBenefitProtocol):
        labels = {
            "case_1": True,
            "case_2": True,
            "case_3": False,
            "case_4": False,
        }
        predictions = {
            BenefitArm.BASELINE_PLAN_BASELINE_REGISTRY: {
                case_id: False for case_id in labels
            },
            BenefitArm.CANDIDATE_PLAN_BASELINE_REGISTRY: {
                **{case_id: False for case_id in labels},
                "case_1": True,
            },
            BenefitArm.BASELINE_PLAN_CANDIDATE_REGISTRY: {
                **{case_id: False for case_id in labels},
                "case_2": True,
            },
            BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY: dict(labels),
        }
        arm_hashes = {
            BenefitArm.BASELINE_PLAN_BASELINE_REGISTRY: (
                protocol.baseline_plan_hash,
                protocol.baseline_registry_hash,
            ),
            BenefitArm.CANDIDATE_PLAN_BASELINE_REGISTRY: (
                protocol.candidate_plan_hash,
                protocol.baseline_registry_hash,
            ),
            BenefitArm.BASELINE_PLAN_CANDIDATE_REGISTRY: (
                protocol.baseline_plan_hash,
                protocol.candidate_registry_hash,
            ),
            BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY: (
                protocol.candidate_plan_hash,
                protocol.candidate_registry_hash,
            ),
        }
        rows = []
        for arm in BenefitArm:
            for case_id in protocol.case_ids:
                for replicate_id in protocol.replicate_ids:
                    plan_hash, registry_hash = arm_hashes[arm]
                    rows.append(
                        SystemCaseResult(
                            arm=arm,
                            case_id=case_id,
                            issuer_id=protocol.issuer_by_case[case_id],
                            replicate_id=replicate_id,
                            plan_hash=plan_hash,
                            registry_hash=registry_hash,
                            model_hash=protocol.model_hash,
                            budget_hash=protocol.budget_hash,
                            projection_hash=protocol.projection_hash,
                            source_corpus_hash=digest(case_id[-1]),
                            actual_surge=labels[case_id],
                            predicted_surge=predictions[arm][case_id],
                            contract_valid=True,
                            coverage=1.0,
                            execution_failed=False,
                            input_hash=digest(
                                f"{list(BenefitArm).index(arm)}{case_id[-1]}"
                            ),
                            response_id=(
                                f"response_{replicate_id}_{arm.value}_{case_id}"
                            ),
                            llm_calls=1,
                            tokens=100,
                            cost=(
                                1.1
                                if arm
                                is BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY
                                else 1.0
                            ),
                            executed_signal_refs=("signal:v2",),
                            cited_signal_refs=("signal:v2",),
                        )
                    )
        return rows

    def capability_results(self):
        evidence = (
            SignalEvidence(
                document_id="document_1",
                exact_span="Revenue grew by 20 percent year over year.",
                timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
        )
        return (
            CapabilityCaseResult(
                "baseline",
                "signal:v1",
                "measurement_1",
                "issuer_1",
                "independent",
                digest("7"),
                SignalValue.POSITIVE,
                SignalValue.NEGATIVE,
                SignalExecutionStatus.SUCCESS,
                True,
                True,
                evidence,
                (),
                True,
            ),
            CapabilityCaseResult(
                "candidate",
                "signal:v2",
                "measurement_1",
                "issuer_1",
                "independent",
                digest("7"),
                SignalValue.POSITIVE,
                SignalValue.POSITIVE,
                SignalExecutionStatus.SUCCESS,
                True,
                True,
                evidence,
                (),
                True,
            ),
            CapabilityCaseResult(
                "candidate",
                "signal:v2",
                "author_fixture",
                "fixture_issuer",
                "author_written",
                digest("8"),
                SignalValue.POSITIVE,
                SignalValue.POSITIVE,
                SignalExecutionStatus.SUCCESS,
                True,
                True,
                evidence,
                (),
            ),
        )

    def test_four_arm_report_separates_measurement_lifecycle_and_benefit(self) -> None:
        protocol = self.protocol()
        lifecycle = EvolutionLifecycleEvidence(
            candidate_ref="signal:v2",
            candidate_hash=digest("9"),
            promotion_evaluation_key=digest("a"),
            promoted_registry_hash=protocol.candidate_registry_hash,
            downstream_registry_hash=protocol.candidate_registry_hash,
            executed_case_ids=("case_1", "case_2"),
            cited_case_ids=("case_1",),
        )

        report = EvolutionBenefitEvaluator().evaluate(
            protocol,
            self.system_results(protocol),
            capability_results=self.capability_results(),
            lifecycle_evidence=(lifecycle,),
        )

        self.assertEqual(report.outcome, "gain_confirmed")
        self.assertEqual(report.paired_comparison["primary_f1_gain"], 1.0)
        self.assertGreater(report.paired_comparison["plan_only_f1_gain"], 0.0)
        self.assertGreater(report.paired_comparison["registry_only_f1_gain"], 0.0)
        self.assertEqual(
            report.capability_evaluation["by_variant"]["candidate"][
                "independent_fixtures"
            ],
            1,
        )
        self.assertEqual(
            report.capability_evaluation["by_variant"]["candidate"][
                "author_written_fixtures"
            ],
            1,
        )
        self.assertTrue(report.lifecycle_evaluation[0]["promoted"])
        self.assertTrue(report.lifecycle_evaluation[0]["executed_downstream"])
        self.assertTrue(report.lifecycle_evaluation[0]["cited_downstream"])
        self.assertEqual(len(report.system_case_results), 32)
        self.assertEqual(len(report.capability_case_results), 3)

    def test_promoted_candidate_with_no_system_gain_reports_no_gain(self) -> None:
        protocol = self.protocol()
        rows = self.system_results(protocol)
        baseline = {
            (row.case_id, row.replicate_id): row.predicted_surge
            for row in rows
            if row.arm is BenefitArm.BASELINE_PLAN_BASELINE_REGISTRY
        }
        rows = [
            SystemCaseResult(
                **{
                    **row.__dict__,
                    "predicted_surge": baseline[(row.case_id, row.replicate_id)],
                }
            )
            if row.arm is BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY
            else row
            for row in rows
        ]

        report = EvolutionBenefitEvaluator().evaluate(
            protocol,
            rows,
            capability_results=self.capability_results(),
        )

        self.assertEqual(report.outcome, "no_gain")
        self.assertFalse(report.criteria["minimum_primary_f1_gain"])

    def test_missing_arm_stays_in_denominator_and_makes_report_incomplete(self) -> None:
        protocol = self.protocol()
        rows = self.system_results(protocol)[:-1]

        report = EvolutionBenefitEvaluator().evaluate(protocol, rows)

        self.assertEqual(report.outcome, "incomplete")
        self.assertEqual(len(report.missing_result_keys), 1)
        combined = report.arm_metrics[
            BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY.value
        ]
        self.assertEqual(combined["expected_case_replicates"], 8)
        self.assertEqual(combined["missing_case_replicates"], 1)
        self.assertEqual(combined["failure_count"], 1)

    def test_changed_registry_requires_independent_capability_confirmation(
        self,
    ) -> None:
        protocol = self.protocol()

        report = EvolutionBenefitEvaluator().evaluate(
            protocol, self.system_results(protocol)
        )

        self.assertEqual(report.outcome, "incomplete")
        self.assertEqual(report.missing_capability_case_ids, ("measurement_1",))
        self.assertFalse(
            report.criteria["minimum_candidate_independent_fixtures"]
        )
        with self.assertRaisesRegex(ValidationError, "changed Registry requires"):
            EvolutionBenefitProtocol(
                **{
                    **protocol.__dict__,
                    "minimum_candidate_independent_fixtures": 0,
                }
            )

    def test_rejects_cross_arm_corpus_drift_and_replicate_cache_reuse(self) -> None:
        protocol = self.protocol()
        rows = self.system_results(protocol)
        drifted = SystemCaseResult(
            **{**rows[0].__dict__, "source_corpus_hash": digest("0")}
        )
        with self.assertRaisesRegex(ValidationError, "source corpus differs"):
            EvolutionBenefitEvaluator().evaluate(protocol, (drifted, *rows[1:]))

        reused = []
        for row in rows:
            if (
                row.case_id == "case_1"
                and row.arm is BenefitArm.BASELINE_PLAN_BASELINE_REGISTRY
            ):
                reused.append(
                    SystemCaseResult(
                        **{**row.__dict__, "response_id": "same_invocation"}
                    )
                )
            else:
                reused.append(row)
        with self.assertRaisesRegex(ValidationError, "independent replicates"):
            EvolutionBenefitEvaluator().evaluate(protocol, reused)

    def test_confirmation_ledger_and_report_are_immutable(self) -> None:
        protocol = self.protocol()
        report = EvolutionBenefitEvaluator().evaluate(
            protocol, self.system_results(protocol)
        )
        with self.assertRaises(TypeError):
            protocol.issuer_by_case["case_1"] = "changed"
        with self.assertRaises(TypeError):
            report.arm_metrics[
                BenefitArm.BASELINE_PLAN_BASELINE_REGISTRY.value
            ]["binary_f1"] = 1.0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = ConfirmationCohortLedger(root / "confirmation-ledger.json")
            self.assertTrue(ledger.reserve(protocol))
            self.assertFalse(ledger.reserve(protocol))
            other = self.protocol(protocol_id="confirmation_v2")
            with self.assertRaisesRegex(ValidationError, "already reserved"):
                ledger.reserve(other)

            report_path = root / "report.json"
            self.assertTrue(write_evolution_benefit_report(report_path, report))
            self.assertFalse(write_evolution_benefit_report(report_path, report))
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            saved["report_hash"] = digest("0")
            report_path.write_text(json.dumps(saved), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "other content"):
                write_evolution_benefit_report(report_path, report)

    def test_protocol_round_trip_requires_explicit_criteria(self) -> None:
        protocol = self.protocol()

        self.assertEqual(
            EvolutionBenefitProtocol.from_dict(protocol.to_dict()), protocol
        )
        with self.assertRaisesRegex(ValidationError, "case minimum"):
            EvolutionBenefitProtocol(
                **{**protocol.__dict__, "minimum_case_count": 5}
            )
