from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_benefit import (
    BenefitArm,
    CapabilityCaseResult,
    EvolutionBenefitEvaluator,
    EvolutionBenefitProtocol,
    EvolutionLifecycleEvidence,
    SystemCaseResult,
)
from stock_opportunity_agent.signal_library import (
    SignalEvidence,
    SignalExecutionStatus,
    SignalValue,
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class EvolutionReliabilityMatrixTests(TestCase):
    def protocol(self) -> EvolutionBenefitProtocol:
        case_ids = tuple(f"case_{index}" for index in range(10))
        capability_ids = tuple(f"capability_{index}" for index in range(10))
        return EvolutionBenefitProtocol(
            protocol_id="reliability_matrix_v1",
            case_ids=case_ids,
            issuer_by_case={
                case_id: (
                    "issuer_shared"
                    if index in {8, 9}
                    else f"issuer_{index}"
                )
                for index, case_id in enumerate(case_ids)
            },
            replicate_ids=("replicate_1",),
            candidate_capability_case_ids=capability_ids,
            candidate_capability_issuer_by_case={
                case_id: f"capability_issuer_{index}"
                for index, case_id in enumerate(capability_ids)
            },
            baseline_plan_hash=_hash("baseline_plan"),
            candidate_plan_hash=_hash("candidate_plan"),
            baseline_registry_hash=_hash("baseline_registry"),
            candidate_registry_hash=_hash("candidate_registry"),
            model_hash=_hash("model"),
            budget_hash=_hash("budget"),
            projection_hash=_hash("projection"),
            minimum_case_count=10,
            minimum_issuer_count=9,
            minimum_primary_f1_gain=0.9,
            minimum_cluster_interval_lower_bound=0.0,
            maximum_coverage_drop=0.2,
            maximum_failure_rate=0.2,
            maximum_cost_increase_ratio=None,
            minimum_candidate_independent_fixtures=10,
            minimum_candidate_measurement_accuracy=0.8,
            bootstrap_samples=200,
            bootstrap_seed=19,
            current_look=1,
            maximum_looks=1,
        )

    def system_results(
        self,
        protocol: EvolutionBenefitProtocol,
        *,
        failed_combined_cases: frozenset[str] = frozenset(),
    ) -> tuple[SystemCaseResult, ...]:
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
        rows: list[SystemCaseResult] = []
        for arm in BenefitArm:
            for index, case_id in enumerate(protocol.case_ids):
                actual = index < 5
                combined = arm is BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY
                failed = combined and case_id in failed_combined_cases
                plan_hash, registry_hash = arm_hashes[arm]
                rows.append(
                    SystemCaseResult(
                        arm=arm,
                        case_id=case_id,
                        issuer_id=protocol.issuer_by_case[case_id],
                        replicate_id="replicate_1",
                        plan_hash=plan_hash,
                        registry_hash=registry_hash,
                        model_hash=protocol.model_hash,
                        budget_hash=protocol.budget_hash,
                        projection_hash=protocol.projection_hash,
                        source_corpus_hash=_hash(f"corpus:{case_id}"),
                        actual_surge=actual,
                        predicted_surge=None if failed else actual if combined else False,
                        contract_valid=not failed,
                        coverage=0.0 if failed else 1.0,
                        execution_failed=failed,
                        input_hash=_hash(f"input:{arm.value}:{case_id}"),
                        response_id=f"response_{arm.value}_{case_id}",
                        llm_calls=1,
                        tokens=100,
                        cost=0.01,
                        executed_signal_refs=("candidate_signal:v2",) if combined else (),
                        cited_signal_refs=("candidate_signal:v2",) if combined else (),
                    )
                )
        return tuple(rows)

    def capability_results(
        self,
        protocol: EvolutionBenefitProtocol,
        *,
        failed_cases: frozenset[str] = frozenset(),
        omit_cases: frozenset[str] = frozenset(),
    ) -> tuple[CapabilityCaseResult, ...]:
        evidence = (
            SignalEvidence(
                document_id="document_1",
                exact_span="The measured value increased by 20 percent.",
                timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
        )
        rows = []
        for case_id in protocol.candidate_capability_case_ids:
            if case_id in omit_cases:
                continue
            failed = case_id in failed_cases
            rows.append(
                CapabilityCaseResult(
                    variant="candidate",
                    signal_ref="candidate_signal:v2",
                    case_id=case_id,
                    issuer_id=protocol.candidate_capability_issuer_by_case[case_id],
                    fixture_origin="independent",
                    source_corpus_hash=_hash(f"capability_corpus:{case_id}"),
                    expected_value=SignalValue.POSITIVE,
                    actual_value=(
                        SignalValue.UNAVAILABLE if failed else SignalValue.POSITIVE
                    ),
                    execution_status=(
                        SignalExecutionStatus.TRANSPORT_FAILED
                        if failed
                        else SignalExecutionStatus.SUCCESS
                    ),
                    contract_valid=not failed,
                    evidence_valid=not failed,
                    supporting_evidence=() if failed else evidence,
                )
            )
        return tuple(rows)

    def test_zero_ten_and_twenty_percent_failures_preserve_valid_siblings(self) -> None:
        protocol = self.protocol()
        distributions = {
            "zero": frozenset(),
            "ten": frozenset({"case_9"}),
            "twenty_distributed": frozenset({"case_7", "case_9"}),
            "twenty_clustered": frozenset({"case_8", "case_9"}),
        }
        for name, failed_cases in distributions.items():
            with self.subTest(name=name):
                capability_failures = frozenset(
                    f"capability_{index}" for index in range(len(failed_cases))
                )
                report = EvolutionBenefitEvaluator().evaluate(
                    protocol,
                    self.system_results(
                        protocol,
                        failed_combined_cases=failed_cases,
                    ),
                    capability_results=self.capability_results(
                        protocol,
                        failed_cases=capability_failures,
                    ),
                )

                combined = report.arm_metrics[
                    BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY.value
                ]
                self.assertEqual(report.outcome, "gain_confirmed")
                self.assertEqual(combined["received_case_replicates"], 10)
                self.assertEqual(combined["failure_count"], len(failed_cases))
                self.assertEqual(
                    report.capability_evaluation["by_variant"]["candidate"][
                        "independent_fixtures"
                    ],
                    10,
                )
                self.assertAlmostEqual(
                    report.capability_evaluation["by_variant"]["candidate"][
                        "measurement_accuracy"
                    ],
                    1.0 - len(failed_cases) / 10,
                )

    def test_supporting_case_failures_reduce_quality_without_cohort_replacement(
        self,
    ) -> None:
        protocol = self.protocol()
        failed = frozenset({"case_0", "case_1"})

        report = EvolutionBenefitEvaluator().evaluate(
            protocol,
            self.system_results(protocol, failed_combined_cases=failed),
            capability_results=self.capability_results(protocol),
        )

        combined = report.arm_metrics[
            BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY.value
        ]
        self.assertEqual(report.outcome, "no_gain")
        self.assertEqual(combined["received_case_replicates"], 10)
        self.assertEqual(combined["evaluable_case_replicates"], 8)
        self.assertEqual(combined["failure_count"], 2)
        self.assertFalse(report.criteria["minimum_primary_f1_gain"])

    def test_missing_capability_failures_cannot_be_deleted_from_frozen_cohort(
        self,
    ) -> None:
        protocol = self.protocol()
        omitted = frozenset({"capability_8", "capability_9"})

        report = EvolutionBenefitEvaluator().evaluate(
            protocol,
            self.system_results(protocol),
            capability_results=self.capability_results(
                protocol,
                omit_cases=omitted,
            ),
        )

        self.assertEqual(report.outcome, "incomplete")
        self.assertEqual(set(report.missing_capability_case_ids), set(omitted))
        self.assertFalse(report.criteria["complete_candidate_capability_cohort"])

    def test_no_learning_and_conflicting_cached_output_cannot_create_gain(self) -> None:
        protocol = self.protocol()
        rows = tuple(
            replace(row, predicted_surge=False)
            for row in self.system_results(protocol)
        )

        report = EvolutionBenefitEvaluator().evaluate(
            protocol,
            rows,
            capability_results=self.capability_results(protocol),
        )

        self.assertEqual(report.outcome, "no_gain")
        self.assertEqual(report.paired_comparison["primary_f1_gain"], 0.0)

        baseline = next(
            row
            for row in self.system_results(protocol)
            if row.arm is BenefitArm.BASELINE_PLAN_BASELINE_REGISTRY
        )
        conflicting = tuple(
            replace(
                row,
                input_hash=baseline.input_hash,
                response_id=baseline.response_id,
            )
            if row.arm is BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY
            and row.case_id == baseline.case_id
            else row
            for row in self.system_results(protocol)
        )
        with self.assertRaisesRegex(ValidationError, "conflicting outputs"):
            EvolutionBenefitEvaluator().evaluate(protocol, conflicting)

    def test_promotion_without_downstream_execution_remains_separate(self) -> None:
        protocol = self.protocol()
        lifecycle = EvolutionLifecycleEvidence(
            candidate_ref="candidate_signal:v2",
            candidate_hash=_hash("candidate_signal"),
            promotion_evaluation_key=_hash("promotion_evaluation"),
            promoted_registry_hash=protocol.candidate_registry_hash,
            downstream_registry_hash=protocol.candidate_registry_hash,
        )

        report = EvolutionBenefitEvaluator().evaluate(
            protocol,
            self.system_results(protocol),
            capability_results=self.capability_results(protocol),
            lifecycle_evidence=(lifecycle,),
        )

        self.assertEqual(report.outcome, "gain_confirmed")
        self.assertTrue(report.lifecycle_evaluation[0]["promoted"])
        self.assertFalse(report.lifecycle_evaluation[0]["executed_downstream"])
        self.assertFalse(report.lifecycle_evaluation[0]["cited_downstream"])

    def test_candidate_cannot_gain_from_a_larger_source_corpus(self) -> None:
        protocol = self.protocol()
        rows = self.system_results(protocol)
        candidate = next(
            row
            for row in rows
            if row.arm is BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY
        )
        drifted = tuple(
            replace(row, source_corpus_hash=_hash("larger_candidate_corpus"))
            if row is candidate
            else row
            for row in rows
        )

        with self.assertRaisesRegex(ValidationError, "source corpus differs"):
            EvolutionBenefitEvaluator().evaluate(protocol, drifted)

    def test_result_order_does_not_change_metrics_or_report_identity(self) -> None:
        protocol = self.protocol()
        rows = self.system_results(protocol)
        capability = self.capability_results(protocol)

        forward = EvolutionBenefitEvaluator().evaluate(
            protocol,
            rows,
            capability_results=capability,
        )
        reversed_order = EvolutionBenefitEvaluator().evaluate(
            protocol,
            reversed(rows),
            capability_results=reversed(capability),
        )

        self.assertEqual(reversed_order.to_dict(), forward.to_dict())
