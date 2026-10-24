"""Offline confirmation of capability, lifecycle, and system evolution benefit."""

from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    SignalEvidence,
    SignalExecutionStatus,
    SignalValue,
)


_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BenefitArm(str, Enum):
    """The fixed two-by-two Plan and Registry comparison arms."""

    BASELINE_PLAN_BASELINE_REGISTRY = "baseline_plan_baseline_registry"
    CANDIDATE_PLAN_BASELINE_REGISTRY = "candidate_plan_baseline_registry"
    BASELINE_PLAN_CANDIDATE_REGISTRY = "baseline_plan_candidate_registry"
    CANDIDATE_PLAN_CANDIDATE_REGISTRY = "candidate_plan_candidate_registry"


@dataclass(frozen=True)
class SlowMemoryAblationManifest:
    """Freeze three Slow-generation memory conditions before confirmation."""

    ablation_id: str
    fast_start_hash: str
    registry_start_hash: str
    seed: int
    model_hash: str
    budget_hash: str
    generated_registry_hashes: Mapping[str, str]
    allowed_comparisons: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require_id(self.ablation_id, "ablation_id")
        for name in (
            "fast_start_hash",
            "registry_start_hash",
            "model_hash",
            "budget_hash",
        ):
            _require_hash(str(getattr(self, name)), name)
        if type(self.seed) is not int:
            raise ValidationError("Slow memory ablation seed must be an integer")
        expected = {"no_memory", "episodes_only", "episodes_and_lessons"}
        hashes = {
            str(key): str(value)
            for key, value in self.generated_registry_hashes.items()
        }
        if set(hashes) != expected:
            raise ValidationError("Slow memory ablation requires all three conditions")
        for value in hashes.values():
            _require_hash(value, "generated_registry_hash")
        comparisons = tuple(
            (str(left), str(right)) for left, right in self.allowed_comparisons
        )
        if not comparisons or any(
            left not in expected or right not in expected or left == right
            for left, right in comparisons
        ):
            raise ValidationError("Slow memory ablation comparisons are invalid")
        object.__setattr__(self, "generated_registry_hashes", hashes)
        object.__setattr__(self, "allowed_comparisons", comparisons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "slow-memory-ablation-manifest-v1",
            "ablation_id": self.ablation_id,
            "fast_start_hash": self.fast_start_hash,
            "registry_start_hash": self.registry_start_hash,
            "seed": self.seed,
            "model_hash": self.model_hash,
            "budget_hash": self.budget_hash,
            "generated_registry_hashes": dict(self.generated_registry_hashes),
            "allowed_comparisons": [list(item) for item in self.allowed_comparisons],
        }

    @property
    def manifest_hash(self) -> str:
        return canonical_json_hash(self.to_dict())


@dataclass(frozen=True)
class EvolutionBenefitProtocol:
    """Fully explicit confirmation cohort, identities, thresholds, and looks."""

    protocol_id: str
    case_ids: tuple[str, ...]
    issuer_by_case: Mapping[str, str]
    replicate_ids: tuple[str, ...]
    candidate_capability_case_ids: tuple[str, ...]
    candidate_capability_issuer_by_case: Mapping[str, str]
    baseline_plan_hash: str
    candidate_plan_hash: str
    baseline_registry_hash: str
    candidate_registry_hash: str
    model_hash: str
    budget_hash: str
    projection_hash: str
    minimum_case_count: int
    minimum_issuer_count: int
    minimum_primary_f1_gain: float
    minimum_cluster_interval_lower_bound: float
    maximum_coverage_drop: float
    maximum_failure_rate: float
    maximum_cost_increase_ratio: float | None
    minimum_candidate_independent_fixtures: int
    minimum_candidate_measurement_accuracy: float
    bootstrap_samples: int
    bootstrap_seed: int
    current_look: int
    maximum_looks: int

    def __post_init__(self) -> None:
        _require_id(self.protocol_id, "protocol_id")
        case_ids = tuple(str(item) for item in self.case_ids)
        replicate_ids = tuple(str(item) for item in self.replicate_ids)
        capability_case_ids = tuple(
            str(item) for item in self.candidate_capability_case_ids
        )
        _require_unique_ids(case_ids, "case_ids")
        _require_unique_ids(replicate_ids, "replicate_ids")
        _require_unique_ids(
            capability_case_ids,
            "candidate_capability_case_ids",
            allow_empty=True,
        )
        issuers = {str(key): str(value) for key, value in self.issuer_by_case.items()}
        if set(issuers) != set(case_ids):
            raise ValidationError("benefit protocol issuer map must match case ids")
        for issuer in issuers.values():
            _require_id(issuer, "issuer_id")
        capability_issuers = {
            str(key): str(value)
            for key, value in self.candidate_capability_issuer_by_case.items()
        }
        if set(capability_issuers) != set(capability_case_ids):
            raise ValidationError(
                "benefit protocol capability issuer map must match case ids"
            )
        for issuer in capability_issuers.values():
            _require_id(issuer, "capability_issuer_id")
        for name in (
            "baseline_plan_hash",
            "candidate_plan_hash",
            "baseline_registry_hash",
            "candidate_registry_hash",
            "model_hash",
            "budget_hash",
            "projection_hash",
        ):
            _require_hash(str(getattr(self, name)), name)
        if (
            type(self.minimum_case_count) is not int
            or self.minimum_case_count < 1
            or len(case_ids) < self.minimum_case_count
        ):
            raise ValidationError("benefit protocol case minimum is not satisfied")
        issuer_count = len(set(issuers.values()))
        if (
            type(self.minimum_issuer_count) is not int
            or self.minimum_issuer_count < 2
            or issuer_count < self.minimum_issuer_count
        ):
            raise ValidationError("benefit protocol issuer minimum is not satisfied")
        for name in (
            "minimum_primary_f1_gain",
            "minimum_cluster_interval_lower_bound",
        ):
            _require_finite_range(getattr(self, name), name, -1.0, 1.0)
        _require_finite_range(
            self.maximum_coverage_drop, "maximum_coverage_drop", 0.0, 1.0
        )
        _require_finite_range(
            self.maximum_failure_rate, "maximum_failure_rate", 0.0, 1.0
        )
        if self.maximum_cost_increase_ratio is not None:
            _require_finite_range(
                self.maximum_cost_increase_ratio,
                "maximum_cost_increase_ratio",
                0.0,
                1_000_000.0,
            )
        if (
            type(self.minimum_candidate_independent_fixtures) is not int
            or self.minimum_candidate_independent_fixtures < 0
            or len(capability_case_ids)
            < self.minimum_candidate_independent_fixtures
        ):
            raise ValidationError(
                "benefit protocol independent fixture minimum must be non-negative"
            )
        if (
            self.baseline_registry_hash != self.candidate_registry_hash
            and self.minimum_candidate_independent_fixtures < 1
        ):
            raise ValidationError(
                "changed Registry requires independent candidate Signal fixtures"
            )
        _require_finite_range(
            self.minimum_candidate_measurement_accuracy,
            "minimum_candidate_measurement_accuracy",
            0.0,
            1.0,
        )
        if type(self.bootstrap_samples) is not int or self.bootstrap_samples < 1:
            raise ValidationError("benefit protocol bootstrap_samples must be positive")
        if type(self.bootstrap_seed) is not int:
            raise ValidationError("benefit protocol bootstrap_seed must be an integer")
        if (
            type(self.current_look) is not int
            or type(self.maximum_looks) is not int
            or not 1 <= self.current_look <= self.maximum_looks
        ):
            raise ValidationError("benefit protocol experiment look is invalid")
        object.__setattr__(self, "case_ids", case_ids)
        object.__setattr__(self, "replicate_ids", replicate_ids)
        object.__setattr__(self, "issuer_by_case", MappingProxyType(issuers))
        object.__setattr__(
            self,
            "candidate_capability_case_ids",
            capability_case_ids,
        )
        object.__setattr__(
            self,
            "candidate_capability_issuer_by_case",
            MappingProxyType(capability_issuers),
        )

    @property
    def protocol_hash(self) -> str:
        """Return the complete immutable protocol identity."""

        return canonical_json_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "evolution-benefit-protocol-v1",
            "protocol_id": self.protocol_id,
            "case_ids": list(self.case_ids),
            "issuer_by_case": dict(self.issuer_by_case),
            "replicate_ids": list(self.replicate_ids),
            "candidate_capability_case_ids": list(
                self.candidate_capability_case_ids
            ),
            "candidate_capability_issuer_by_case": dict(
                self.candidate_capability_issuer_by_case
            ),
            "baseline_plan_hash": self.baseline_plan_hash,
            "candidate_plan_hash": self.candidate_plan_hash,
            "baseline_registry_hash": self.baseline_registry_hash,
            "candidate_registry_hash": self.candidate_registry_hash,
            "model_hash": self.model_hash,
            "budget_hash": self.budget_hash,
            "projection_hash": self.projection_hash,
            "criteria": {
                "minimum_case_count": self.minimum_case_count,
                "minimum_issuer_count": self.minimum_issuer_count,
                "minimum_primary_f1_gain": self.minimum_primary_f1_gain,
                "minimum_cluster_interval_lower_bound": (
                    self.minimum_cluster_interval_lower_bound
                ),
                "maximum_coverage_drop": self.maximum_coverage_drop,
                "maximum_failure_rate": self.maximum_failure_rate,
                "maximum_cost_increase_ratio": self.maximum_cost_increase_ratio,
                "minimum_candidate_independent_fixtures": (
                    self.minimum_candidate_independent_fixtures
                ),
                "minimum_candidate_measurement_accuracy": (
                    self.minimum_candidate_measurement_accuracy
                ),
            },
            "uncertainty": {
                "method": "issuer_cluster_bootstrap",
                "bootstrap_samples": self.bootstrap_samples,
                "bootstrap_seed": self.bootstrap_seed,
            },
            "experiment_look": {
                "current": self.current_look,
                "maximum": self.maximum_looks,
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvolutionBenefitProtocol":
        if data.get("schema_version") != "evolution-benefit-protocol-v1":
            raise ValidationError("unsupported evolution benefit protocol schema")
        criteria = dict(data.get("criteria", {}))
        uncertainty = dict(data.get("uncertainty", {}))
        look = dict(data.get("experiment_look", {}))
        if uncertainty.get("method") != "issuer_cluster_bootstrap":
            raise ValidationError("unsupported evolution benefit uncertainty method")
        return cls(
            protocol_id=str(data["protocol_id"]),
            case_ids=tuple(str(item) for item in data["case_ids"]),
            issuer_by_case=dict(data["issuer_by_case"]),
            replicate_ids=tuple(str(item) for item in data["replicate_ids"]),
            candidate_capability_case_ids=tuple(
                str(item) for item in data["candidate_capability_case_ids"]
            ),
            candidate_capability_issuer_by_case=dict(
                data["candidate_capability_issuer_by_case"]
            ),
            baseline_plan_hash=str(data["baseline_plan_hash"]),
            candidate_plan_hash=str(data["candidate_plan_hash"]),
            baseline_registry_hash=str(data["baseline_registry_hash"]),
            candidate_registry_hash=str(data["candidate_registry_hash"]),
            model_hash=str(data["model_hash"]),
            budget_hash=str(data["budget_hash"]),
            projection_hash=str(data["projection_hash"]),
            minimum_case_count=int(criteria["minimum_case_count"]),
            minimum_issuer_count=int(criteria["minimum_issuer_count"]),
            minimum_primary_f1_gain=float(criteria["minimum_primary_f1_gain"]),
            minimum_cluster_interval_lower_bound=float(
                criteria["minimum_cluster_interval_lower_bound"]
            ),
            maximum_coverage_drop=float(criteria["maximum_coverage_drop"]),
            maximum_failure_rate=float(criteria["maximum_failure_rate"]),
            maximum_cost_increase_ratio=(
                float(criteria["maximum_cost_increase_ratio"])
                if criteria.get("maximum_cost_increase_ratio") is not None
                else None
            ),
            minimum_candidate_independent_fixtures=int(
                criteria["minimum_candidate_independent_fixtures"]
            ),
            minimum_candidate_measurement_accuracy=float(
                criteria["minimum_candidate_measurement_accuracy"]
            ),
            bootstrap_samples=int(uncertainty["bootstrap_samples"]),
            bootstrap_seed=int(uncertainty["bootstrap_seed"]),
            current_look=int(look["current"]),
            maximum_looks=int(look["maximum"]),
        )


@dataclass(frozen=True)
class SystemCaseResult:
    """One case/replicate result for one fixed comparison arm."""

    arm: BenefitArm
    case_id: str
    issuer_id: str
    replicate_id: str
    plan_hash: str
    registry_hash: str
    model_hash: str
    budget_hash: str
    projection_hash: str
    source_corpus_hash: str
    actual_surge: bool
    predicted_surge: bool | None
    contract_valid: bool
    coverage: float
    execution_failed: bool
    input_hash: str | None
    response_id: str | None
    llm_calls: int
    tokens: int
    cost: float
    executed_signal_refs: tuple[str, ...] = ()
    cited_signal_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.arm, BenefitArm):
            object.__setattr__(self, "arm", BenefitArm(self.arm))
        for name in ("case_id", "issuer_id", "replicate_id"):
            _require_id(str(getattr(self, name)), name)
        for name in (
            "plan_hash",
            "registry_hash",
            "model_hash",
            "budget_hash",
            "projection_hash",
            "source_corpus_hash",
        ):
            _require_hash(str(getattr(self, name)), name)
        if self.input_hash is not None:
            _require_hash(self.input_hash, "input_hash")
        if self.response_id is not None:
            _require_id(self.response_id, "response_id")
        if (self.input_hash is None) != (self.response_id is None):
            raise ValidationError(
                "system result input hash and response id must appear together"
            )
        if self.llm_calls > 0 and self.response_id is None:
            raise ValidationError(
                "system result with model calls requires response identity"
            )
        if type(self.actual_surge) is not bool:
            raise ValidationError("system result actual_surge must be boolean")
        if self.predicted_surge is not None and type(self.predicted_surge) is not bool:
            raise ValidationError("system result prediction must be boolean or null")
        if (
            type(self.contract_valid) is not bool
            or type(self.execution_failed) is not bool
        ):
            raise ValidationError("system result status flags must be boolean")
        _require_finite_range(self.coverage, "coverage", 0.0, 1.0)
        if any(
            type(value) is not int or value < 0
            for value in (self.llm_calls, self.tokens)
        ):
            raise ValidationError("system result usage must be non-negative integers")
        _require_finite_range(self.cost, "cost", 0.0, 1_000_000_000.0)
        executed = tuple(str(item) for item in self.executed_signal_refs)
        cited = tuple(str(item) for item in self.cited_signal_refs)
        _require_unique_ids(executed, "executed_signal_refs", allow_empty=True)
        _require_unique_ids(cited, "cited_signal_refs", allow_empty=True)
        if not set(cited).issubset(executed):
            raise ValidationError(
                "cited Signal refs must be executed in the same result"
            )
        object.__setattr__(self, "executed_signal_refs", executed)
        object.__setattr__(self, "cited_signal_refs", cited)

    @property
    def evaluable(self) -> bool:
        return (
            self.predicted_surge is not None
            and self.contract_valid
            and not self.execution_failed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm.value,
            "case_id": self.case_id,
            "issuer_id": self.issuer_id,
            "replicate_id": self.replicate_id,
            "plan_hash": self.plan_hash,
            "registry_hash": self.registry_hash,
            "model_hash": self.model_hash,
            "budget_hash": self.budget_hash,
            "projection_hash": self.projection_hash,
            "source_corpus_hash": self.source_corpus_hash,
            "actual_surge": self.actual_surge,
            "predicted_surge": self.predicted_surge,
            "contract_valid": self.contract_valid,
            "coverage": self.coverage,
            "execution_failed": self.execution_failed,
            "input_hash": self.input_hash,
            "response_id": self.response_id,
            "usage": {
                "llm_calls": self.llm_calls,
                "tokens": self.tokens,
                "cost": self.cost,
            },
            "executed_signal_refs": list(self.executed_signal_refs),
            "cited_signal_refs": list(self.cited_signal_refs),
        }


@dataclass(frozen=True)
class CapabilityCaseResult:
    """One independent or author-written Signal measurement check."""

    variant: str
    signal_ref: str
    case_id: str
    issuer_id: str
    fixture_origin: str
    source_corpus_hash: str
    expected_value: SignalValue
    actual_value: SignalValue
    execution_status: SignalExecutionStatus
    contract_valid: bool
    evidence_valid: bool
    supporting_evidence: tuple[SignalEvidence, ...] = ()
    counter_evidence: tuple[SignalEvidence, ...] = ()
    actual_surge: bool | None = None

    def __post_init__(self) -> None:
        if self.variant not in {"baseline", "candidate"}:
            raise ValidationError("capability result variant is invalid")
        if self.fixture_origin not in {"independent", "author_written"}:
            raise ValidationError("capability fixture origin is invalid")
        for name in ("signal_ref", "case_id", "issuer_id"):
            _require_id(str(getattr(self, name)), name)
        _require_hash(self.source_corpus_hash, "source_corpus_hash")
        if not isinstance(self.expected_value, SignalValue):
            object.__setattr__(self, "expected_value", SignalValue(self.expected_value))
        if not isinstance(self.actual_value, SignalValue):
            object.__setattr__(self, "actual_value", SignalValue(self.actual_value))
        if not isinstance(self.execution_status, SignalExecutionStatus):
            object.__setattr__(
                self,
                "execution_status",
                SignalExecutionStatus(self.execution_status),
            )
        if (
            type(self.contract_valid) is not bool
            or type(self.evidence_valid) is not bool
        ):
            raise ValidationError("capability validation flags must be boolean")
        if self.actual_surge is not None and type(self.actual_surge) is not bool:
            raise ValidationError("capability actual_surge must be boolean or null")
        supporting = tuple(self.supporting_evidence)
        counter = tuple(self.counter_evidence)
        if any(not isinstance(item, SignalEvidence) for item in supporting + counter):
            raise ValidationError("capability evidence must use SignalEvidence")
        if (
            self.evidence_valid
            and self.actual_value is not SignalValue.UNAVAILABLE
            and not supporting
            and not counter
        ):
            raise ValidationError(
                "valid decisive capability measurement requires literal evidence"
            )
        object.__setattr__(self, "supporting_evidence", supporting)
        object.__setattr__(self, "counter_evidence", counter)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "signal_ref": self.signal_ref,
            "case_id": self.case_id,
            "issuer_id": self.issuer_id,
            "fixture_origin": self.fixture_origin,
            "source_corpus_hash": self.source_corpus_hash,
            "expected_value": self.expected_value.value,
            "actual_value": self.actual_value.value,
            "execution_status": self.execution_status.value,
            "contract_valid": self.contract_valid,
            "evidence_valid": self.evidence_valid,
            "supporting_evidence": [
                item.to_dict() for item in self.supporting_evidence
            ],
            "counter_evidence": [
                item.to_dict() for item in self.counter_evidence
            ],
            "actual_surge": self.actual_surge,
        }


@dataclass(frozen=True)
class EvolutionLifecycleEvidence:
    """Exact evidence for promotion and later Fast execution/citation."""

    candidate_ref: str
    candidate_hash: str
    promotion_evaluation_key: str | None
    promoted_registry_hash: str | None
    downstream_registry_hash: str | None
    executed_case_ids: tuple[str, ...] = ()
    cited_case_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.candidate_ref, "candidate_ref")
        _require_hash(self.candidate_hash, "candidate_hash")
        for name in (
            "promotion_evaluation_key",
            "promoted_registry_hash",
            "downstream_registry_hash",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_hash(value, name)
        executed = tuple(str(item) for item in self.executed_case_ids)
        cited = tuple(str(item) for item in self.cited_case_ids)
        _require_unique_ids(executed, "executed_case_ids", allow_empty=True)
        _require_unique_ids(cited, "cited_case_ids", allow_empty=True)
        if not set(cited).issubset(executed):
            raise ValidationError("cited lifecycle cases must be executed cases")
        promotion_fields = (
            self.promotion_evaluation_key,
            self.promoted_registry_hash,
        )
        if any(promotion_fields) and not all(promotion_fields):
            raise ValidationError("lifecycle promotion evidence must be complete")
        object.__setattr__(self, "executed_case_ids", executed)
        object.__setattr__(self, "cited_case_ids", cited)


@dataclass(frozen=True)
class EvolutionBenefitReport:
    """Separated capability, lifecycle, and paired system findings."""

    protocol: EvolutionBenefitProtocol
    outcome: str
    missing_result_keys: tuple[str, ...]
    missing_capability_case_ids: tuple[str, ...]
    system_case_results: tuple[SystemCaseResult, ...]
    capability_case_results: tuple[CapabilityCaseResult, ...]
    arm_metrics: Mapping[str, Mapping[str, Any]]
    paired_comparison: Mapping[str, Any]
    capability_evaluation: Mapping[str, Any]
    lifecycle_evaluation: tuple[Mapping[str, Any], ...]
    criteria: Mapping[str, bool]
    report_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.outcome not in {"gain_confirmed", "no_gain", "incomplete"}:
            raise ValidationError("evolution benefit outcome is invalid")
        object.__setattr__(self, "arm_metrics", _freeze_json(self.arm_metrics))
        object.__setattr__(
            self,
            "paired_comparison",
            _freeze_json(self.paired_comparison),
        )
        object.__setattr__(
            self,
            "capability_evaluation",
            _freeze_json(self.capability_evaluation),
        )
        object.__setattr__(
            self,
            "lifecycle_evaluation",
            tuple(_freeze_json(item) for item in self.lifecycle_evaluation),
        )
        object.__setattr__(self, "criteria", _freeze_json(self.criteria))
        payload = self._payload()
        object.__setattr__(self, "report_hash", canonical_json_hash(payload))

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": "evolution-benefit-report-v1",
            "protocol": self.protocol.to_dict(),
            "protocol_hash": self.protocol.protocol_hash,
            "outcome": self.outcome,
            "missing_result_keys": list(self.missing_result_keys),
            "missing_capability_case_ids": list(
                self.missing_capability_case_ids
            ),
            "system_case_results": [
                item.to_dict() for item in self.system_case_results
            ],
            "capability_case_results": [
                item.to_dict() for item in self.capability_case_results
            ],
            "arm_metrics": _thaw_json(self.arm_metrics),
            "paired_comparison": _thaw_json(self.paired_comparison),
            "capability_evaluation": _thaw_json(self.capability_evaluation),
            "lifecycle_evaluation": _thaw_json(self.lifecycle_evaluation),
            "criteria": _thaw_json(self.criteria),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "report_hash": self.report_hash}


class EvolutionBenefitEvaluator:
    """Validate and summarize one frozen four-arm confirmation experiment."""

    def evaluate(
        self,
        protocol: EvolutionBenefitProtocol,
        system_results: Iterable[SystemCaseResult],
        *,
        capability_results: Iterable[CapabilityCaseResult] = (),
        lifecycle_evidence: Iterable[EvolutionLifecycleEvidence] = (),
    ) -> EvolutionBenefitReport:
        rows = tuple(system_results)
        capability_rows = tuple(capability_results)
        indexed = self._validate_system_rows(protocol, rows)
        _validate_capability_rows(capability_rows)
        candidate_capability_cases = {
            row.case_id
            for row in capability_rows
            if row.variant == "candidate" and row.fixture_origin == "independent"
        }
        unexpected_capability_cases = candidate_capability_cases.difference(
            protocol.candidate_capability_case_ids
        )
        if unexpected_capability_cases:
            raise ValidationError(
                "candidate capability result was not frozen in the protocol: "
                + ", ".join(sorted(unexpected_capability_cases))
            )
        for row in capability_rows:
            if (
                row.fixture_origin == "independent"
                and row.case_id in protocol.candidate_capability_issuer_by_case
                and row.issuer_id
                != protocol.candidate_capability_issuer_by_case[row.case_id]
            ):
                raise ValidationError(
                    "capability result issuer differs from protocol"
                )
        missing_capability_case_ids = tuple(
            sorted(
                set(protocol.candidate_capability_case_ids)
                - candidate_capability_cases
            )
        )
        expected_keys = {
            (arm, case_id, replicate_id)
            for arm in BenefitArm
            for case_id in protocol.case_ids
            for replicate_id in protocol.replicate_ids
        }
        missing_keys = tuple(
            _result_key_text(key) for key in sorted(expected_keys - set(indexed))
        )
        expected_per_arm = len(protocol.case_ids) * len(protocol.replicate_ids)
        arm_metrics = {
            arm.value: _system_metrics(
                (row for key, row in indexed.items() if key[0] is arm),
                expected_count=expected_per_arm,
            )
            for arm in BenefitArm
        }
        paired = _paired_comparison(protocol, indexed, arm_metrics)
        capability = _capability_summary(capability_rows)
        criteria = _benefit_criteria(
            protocol,
            arm_metrics,
            paired,
            capability,
            complete=not missing_keys,
            capability_complete=not missing_capability_case_ids,
        )
        outcome = (
            "incomplete"
            if missing_keys or missing_capability_case_ids
            else "gain_confirmed"
            if all(criteria.values())
            else "no_gain"
        )
        lifecycle = tuple(
            _lifecycle_summary(protocol, item) for item in lifecycle_evidence
        )
        return EvolutionBenefitReport(
            protocol=protocol,
            outcome=outcome,
            missing_result_keys=missing_keys,
            missing_capability_case_ids=missing_capability_case_ids,
            system_case_results=tuple(
                indexed[key] for key in sorted(indexed)
            ),
            capability_case_results=tuple(
                sorted(
                    capability_rows,
                    key=lambda item: (
                        item.variant,
                        item.signal_ref,
                        item.case_id,
                    ),
                )
            ),
            arm_metrics=arm_metrics,
            paired_comparison=paired,
            capability_evaluation=capability,
            lifecycle_evaluation=lifecycle,
            criteria=criteria,
        )

    @staticmethod
    def _validate_system_rows(
        protocol: EvolutionBenefitProtocol,
        rows: tuple[SystemCaseResult, ...],
    ) -> dict[tuple[BenefitArm, str, str], SystemCaseResult]:
        indexed: dict[tuple[BenefitArm, str, str], SystemCaseResult] = {}
        source_by_case: dict[str, str] = {}
        truth_by_case: dict[str, bool] = {}
        expected_hashes = {
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
        for row in rows:
            if row.case_id not in protocol.case_ids:
                raise ValidationError(f"system result uses unknown case: {row.case_id}")
            if row.replicate_id not in protocol.replicate_ids:
                raise ValidationError(
                    f"system result uses unknown replicate: {row.replicate_id}"
                )
            if row.issuer_id != protocol.issuer_by_case[row.case_id]:
                raise ValidationError("system result issuer differs from protocol")
            if (row.plan_hash, row.registry_hash) != expected_hashes[row.arm]:
                raise ValidationError("system result Plan/Registry arm identity differs")
            if (
                row.model_hash != protocol.model_hash
                or row.budget_hash != protocol.budget_hash
                or row.projection_hash != protocol.projection_hash
            ):
                raise ValidationError("system result shared execution identity differs")
            if (
                source_by_case.setdefault(row.case_id, row.source_corpus_hash)
                != row.source_corpus_hash
            ):
                raise ValidationError("system result source corpus differs across arms")
            if (
                truth_by_case.setdefault(row.case_id, row.actual_surge)
                != row.actual_surge
            ):
                raise ValidationError("system result label differs across arms")
            key = (row.arm, row.case_id, row.replicate_id)
            if key in indexed:
                raise ValidationError(
                    f"duplicate system result: {_result_key_text(key)}"
                )
            indexed[key] = row
        _validate_response_reuse(rows)
        return indexed


class ConfirmationCohortLedger:
    """Reserve confirmation cases once without accessing their source content."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def reserve(
        self,
        protocol: EvolutionBenefitProtocol,
        *,
        ablation_manifest: SlowMemoryAblationManifest | None = None,
        comparison: tuple[str, str] | None = None,
    ) -> bool:
        """Append one reservation; group members may share only predeclared cases."""

        if (ablation_manifest is None) != (comparison is None):
            raise ValidationError(
                "ablation reservation requires both manifest and comparison"
            )
        normalized_comparison = (
            None
            if comparison is None
            else (str(comparison[0]), str(comparison[1]))
        )
        if (
            ablation_manifest is not None
            and normalized_comparison not in ablation_manifest.allowed_comparisons
        ):
            raise ValidationError("ablation comparison was not frozen in the group")

        payload = self._load()
        reservations = list(payload["reservations"])
        exact = {
            "protocol_id": protocol.protocol_id,
            "protocol_hash": protocol.protocol_hash,
            "case_ids": list(protocol.case_ids),
            "capability_case_ids": list(protocol.candidate_capability_case_ids),
            "issuer_ids": sorted(set(protocol.issuer_by_case.values())),
            "capability_issuer_ids": sorted(
                set(protocol.candidate_capability_issuer_by_case.values())
            ),
            "comparison_group_hash": (
                ablation_manifest.manifest_hash
                if ablation_manifest is not None
                else None
            ),
            "comparison": (
                list(normalized_comparison)
                if normalized_comparison is not None
                else None
            ),
        }
        for reservation in reservations:
            if reservation["protocol_id"] == protocol.protocol_id:
                if reservation == exact or (
                    reservation.get("protocol_hash") == protocol.protocol_hash
                    and reservation.get("case_ids") == list(protocol.case_ids)
                    and reservation.get("capability_case_ids", ())
                    == list(protocol.candidate_capability_case_ids)
                ):
                    return False
                raise ValidationError("confirmation protocol reservation conflicts")
            reserved_case_ids = set(reservation["case_ids"]).union(
                reservation.get("capability_case_ids", ())
            )
            requested_case_ids = set(protocol.case_ids).union(
                protocol.candidate_capability_case_ids
            )
            overlap = reserved_case_ids.intersection(requested_case_ids)
            same_frozen_group = (
                exact["comparison_group_hash"] is not None
                and reservation.get("comparison_group_hash")
                == exact["comparison_group_hash"]
            )
            if overlap and not same_frozen_group:
                raise ValidationError(
                    "confirmation cases were already reserved: "
                    + ", ".join(sorted(overlap))
                )
            if "issuer_ids" not in reservation:
                raise ValidationError(
                    "historical confirmation issuer isolation is unknown"
                )
            reserved_issuers = set(reservation["issuer_ids"]).union(
                reservation.get("capability_issuer_ids", ())
            )
            requested_issuers = set(exact["issuer_ids"]).union(
                exact["capability_issuer_ids"]
            )
            issuer_overlap = reserved_issuers.intersection(requested_issuers)
            if issuer_overlap and not same_frozen_group:
                raise ValidationError(
                    "confirmation issuers were already reserved: "
                    + ", ".join(sorted(issuer_overlap))
                )
        reservations.append(exact)
        atomic_write_json(
            self.path,
            {
                "schema_version": "confirmation-cohort-ledger-v2",
                "reservations": reservations,
            },
        )
        return True

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema_version": "confirmation-cohort-ledger-v2",
                "reservations": [],
            }
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if (
            data.get("schema_version")
            not in {
                "confirmation-cohort-ledger-v1",
                "confirmation-cohort-ledger-v2",
            }
            or not isinstance(data.get("reservations"), list)
        ):
            raise ValidationError("confirmation cohort ledger is invalid")
        return data


def write_evolution_benefit_report(
    path: str | Path, report: EvolutionBenefitReport
) -> bool:
    """Write an immutable report; return false for exact replay."""

    output = Path(path)
    payload = report.to_dict()
    if output.exists():
        current = json.loads(output.read_text(encoding="utf-8"))
        if current == payload:
            return False
        raise ValidationError(
            "evolution benefit report already exists with other content"
        )
    atomic_write_json(output, payload)
    return True


def _system_metrics(
    rows: Iterable[SystemCaseResult], *, expected_count: int
) -> dict[str, Any]:
    values = tuple(rows)
    evaluable = tuple(row for row in values if row.evaluable)
    unevaluable = tuple(row for row in values if not row.evaluable)
    true_positive = sum(row.predicted_surge and row.actual_surge for row in evaluable)
    false_positive = sum(
        row.predicted_surge and not row.actual_surge for row in evaluable
    )
    true_negative = sum(
        not row.predicted_surge and not row.actual_surge for row in evaluable
    )
    predicted_false_negative = sum(
        not row.predicted_surge and row.actual_surge for row in evaluable
    )
    failed_positive = sum(row.actual_surge for row in unevaluable)
    failed_negative = len(unevaluable) - failed_positive
    false_negative = predicted_false_negative + failed_positive
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    missing = expected_count - len(values)
    failed = missing + len(values) - len(evaluable)
    return {
        "expected_case_replicates": expected_count,
        "received_case_replicates": len(values),
        "evaluable_case_replicates": len(evaluable),
        "missing_case_replicates": missing,
        "failure_count": failed,
        "failure_rate": _ratio(failed, expected_count),
        "coverage": _ratio(sum(row.coverage for row in values), expected_count),
        "cost": sum(row.cost for row in values),
        "llm_calls": sum(row.llm_calls for row in values),
        "tokens": sum(row.tokens for row in values),
        "confusion": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "false_negative": false_negative,
            "technical_failure_on_positive": failed_positive,
            "technical_failure_on_negative": failed_negative,
        },
        "binary_precision": precision,
        "binary_recall": recall,
        "binary_f1": _ratio(2 * precision * recall, precision + recall),
    }


def _paired_comparison(
    protocol: EvolutionBenefitProtocol,
    indexed: Mapping[tuple[BenefitArm, str, str], SystemCaseResult],
    arm_metrics: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    baseline_arm = BenefitArm.BASELINE_PLAN_BASELINE_REGISTRY
    combined_arm = BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY
    plan_arm = BenefitArm.CANDIDATE_PLAN_BASELINE_REGISTRY
    registry_arm = BenefitArm.BASELINE_PLAN_CANDIDATE_REGISTRY

    def f1(arm: BenefitArm) -> float:
        return float(arm_metrics[arm.value]["binary_f1"])

    baseline_f1 = f1(baseline_arm)
    plan_lift = f1(plan_arm) - baseline_f1
    registry_lift = f1(registry_arm) - baseline_f1
    combined_lift = f1(combined_arm) - baseline_f1
    improved = regressed = unchanged = unevaluable = 0
    for case_id in protocol.case_ids:
        for replicate_id in protocol.replicate_ids:
            baseline = indexed.get((baseline_arm, case_id, replicate_id))
            combined = indexed.get((combined_arm, case_id, replicate_id))
            if (
                baseline is None
                or combined is None
                or not baseline.evaluable
                or not combined.evaluable
            ):
                unevaluable += 1
                continue
            baseline_correct = baseline.predicted_surge == baseline.actual_surge
            combined_correct = combined.predicted_surge == combined.actual_surge
            if combined_correct and not baseline_correct:
                improved += 1
            elif baseline_correct and not combined_correct:
                regressed += 1
            else:
                unchanged += 1
    interval = _issuer_cluster_interval(protocol, indexed)
    return {
        "primary": "candidate_plan_candidate_registry_minus_baseline",
        "primary_f1_gain": combined_lift,
        "plan_only_f1_gain": plan_lift,
        "registry_only_f1_gain": registry_lift,
        "interaction_f1_gain": combined_lift - plan_lift - registry_lift,
        "coverage_change": (
            float(arm_metrics[combined_arm.value]["coverage"])
            - float(arm_metrics[baseline_arm.value]["coverage"])
        ),
        "failure_rate_change": (
            float(arm_metrics[combined_arm.value]["failure_rate"])
            - float(arm_metrics[baseline_arm.value]["failure_rate"])
        ),
        "cost_change": (
            float(arm_metrics[combined_arm.value]["cost"])
            - float(arm_metrics[baseline_arm.value]["cost"])
        ),
        "cost_increase_ratio": _cost_increase_ratio(
            float(arm_metrics[baseline_arm.value]["cost"]),
            float(arm_metrics[combined_arm.value]["cost"]),
        ),
        "paired_correctness": {
            "improved": improved,
            "regressed": regressed,
            "unchanged": unchanged,
            "unevaluable": unevaluable,
        },
        "issuer_cluster_interval": interval,
    }


def _issuer_cluster_interval(
    protocol: EvolutionBenefitProtocol,
    indexed: Mapping[tuple[BenefitArm, str, str], SystemCaseResult],
) -> dict[str, Any]:
    issuers = tuple(sorted(set(protocol.issuer_by_case.values())))
    cases_by_issuer = {
        issuer: tuple(
            case_id
            for case_id in protocol.case_ids
            if protocol.issuer_by_case[case_id] == issuer
        )
        for issuer in issuers
    }
    rng = random.Random(protocol.bootstrap_seed)
    deltas: list[float] = []
    for _index in range(protocol.bootstrap_samples):
        selected_issuers = [rng.choice(issuers) for _issuer in issuers]
        baseline_rows: list[SystemCaseResult] = []
        candidate_rows: list[SystemCaseResult] = []
        for issuer in selected_issuers:
            for case_id in cases_by_issuer[issuer]:
                for replicate_id in protocol.replicate_ids:
                    baseline = indexed.get(
                        (
                            BenefitArm.BASELINE_PLAN_BASELINE_REGISTRY,
                            case_id,
                            replicate_id,
                        )
                    )
                    candidate = indexed.get(
                        (
                            BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY,
                            case_id,
                            replicate_id,
                        )
                    )
                    if baseline is not None:
                        baseline_rows.append(baseline)
                    if candidate is not None:
                        candidate_rows.append(candidate)
        baseline_f1 = _system_metrics(
            baseline_rows, expected_count=len(baseline_rows)
        )["binary_f1"]
        candidate_f1 = _system_metrics(
            candidate_rows, expected_count=len(candidate_rows)
        )["binary_f1"]
        deltas.append(float(candidate_f1) - float(baseline_f1))
    deltas.sort()
    return {
        "method": "issuer_cluster_bootstrap",
        "samples": protocol.bootstrap_samples,
        "seed": protocol.bootstrap_seed,
        "lower": _percentile(deltas, 0.025),
        "upper": _percentile(deltas, 0.975),
    }


def _benefit_criteria(
    protocol: EvolutionBenefitProtocol,
    arm_metrics: Mapping[str, Mapping[str, Any]],
    paired: Mapping[str, Any],
    capability: Mapping[str, Any],
    *,
    complete: bool,
    capability_complete: bool,
) -> dict[str, bool]:
    combined = arm_metrics[BenefitArm.CANDIDATE_PLAN_CANDIDATE_REGISTRY.value]
    candidate_capability = capability["by_variant"]["candidate"]
    cost_ratio = paired["cost_increase_ratio"]
    return {
        "complete_four_arm_cohort": complete,
        "complete_candidate_capability_cohort": capability_complete,
        "minimum_primary_f1_gain": (
            paired["primary_f1_gain"] >= protocol.minimum_primary_f1_gain
        ),
        "minimum_cluster_interval_lower_bound": (
            paired["issuer_cluster_interval"]["lower"]
            >= protocol.minimum_cluster_interval_lower_bound
        ),
        "maximum_coverage_drop": (
            paired["coverage_change"] >= -protocol.maximum_coverage_drop
        ),
        "maximum_failure_rate": (
            combined["failure_rate"] <= protocol.maximum_failure_rate
        ),
        "maximum_cost_increase_ratio": (
            True
            if protocol.maximum_cost_increase_ratio is None
            else cost_ratio is not None
            and cost_ratio <= protocol.maximum_cost_increase_ratio
        ),
        "minimum_candidate_independent_fixtures": (
            candidate_capability["independent_fixtures"]
            >= protocol.minimum_candidate_independent_fixtures
        ),
        "minimum_candidate_measurement_accuracy": (
            protocol.minimum_candidate_independent_fixtures == 0
            or candidate_capability["measurement_accuracy"]
            >= protocol.minimum_candidate_measurement_accuracy
        ),
    }


def _capability_summary(rows: tuple[CapabilityCaseResult, ...]) -> dict[str, Any]:
    def metrics(values: tuple[CapabilityCaseResult, ...]) -> dict[str, Any]:
        independent = tuple(
            item for item in values if item.fixture_origin == "independent"
        )
        successful = tuple(
            item
            for item in independent
            if item.execution_status
            in {
                SignalExecutionStatus.SUCCESS,
                SignalExecutionStatus.DOMAIN_UNAVAILABLE,
            }
        )
        association = tuple(
            item
            for item in successful
            if item.actual_surge is not None
            and item.actual_value in {SignalValue.POSITIVE, SignalValue.NEGATIVE}
        )
        association_correct = sum(
            (item.actual_value is SignalValue.POSITIVE) == item.actual_surge
            for item in association
        )
        return {
            "total_fixtures": len(values),
            "independent_fixtures": len(independent),
            "author_written_fixtures": len(values) - len(independent),
            "contract_pass_rate": _ratio(
                sum(item.contract_valid for item in independent), len(independent)
            ),
            "evidence_pass_rate": _ratio(
                sum(item.evidence_valid for item in independent), len(independent)
            ),
            "measurement_accuracy": _ratio(
                sum(
                    item.actual_value is item.expected_value
                    and item.contract_valid
                    and item.evidence_valid
                    for item in independent
                ),
                len(independent),
            ),
            "execution_failure_count": len(independent) - len(successful),
            "outcome_association_diagnostic": {
                "decisive_count": len(association),
                "directionally_aligned": association_correct,
                "directionally_opposed": len(association) - association_correct,
            },
        }

    by_variant = {
        variant: metrics(tuple(item for item in rows if item.variant == variant))
        for variant in ("baseline", "candidate")
    }
    return {
        "claim_scope": (
            "measurement accuracy uses independent fixtures only; outcome "
            "association is diagnostic and is not a system-benefit claim"
        ),
        "by_variant": by_variant,
        "candidate_minus_baseline_measurement_accuracy": (
            by_variant["candidate"]["measurement_accuracy"]
            - by_variant["baseline"]["measurement_accuracy"]
        ),
    }


def _validate_capability_rows(rows: tuple[CapabilityCaseResult, ...]) -> None:
    keys: set[tuple[str, str]] = set()
    case_identity: dict[str, tuple[str, str, str, SignalValue, bool | None]] = {}
    for row in rows:
        key = (row.variant, row.case_id)
        if key in keys:
            raise ValidationError("duplicate capability result")
        keys.add(key)
        identity = (
            row.issuer_id,
            row.fixture_origin,
            row.source_corpus_hash,
            row.expected_value,
            row.actual_surge,
        )
        prior = case_identity.setdefault(row.case_id, identity)
        if prior != identity:
            raise ValidationError(
                "capability fixture identity differs across variants"
            )


def _lifecycle_summary(
    protocol: EvolutionBenefitProtocol, item: EvolutionLifecycleEvidence
) -> dict[str, Any]:
    promoted = bool(
        item.promotion_evaluation_key
        and item.promoted_registry_hash == protocol.candidate_registry_hash
    )
    registry_loaded = item.downstream_registry_hash == protocol.candidate_registry_hash
    executed = registry_loaded and bool(item.executed_case_ids)
    cited = executed and bool(item.cited_case_ids)
    return {
        "candidate_ref": item.candidate_ref,
        "candidate_hash": item.candidate_hash,
        "promoted": promoted,
        "promotion_evaluation_key": item.promotion_evaluation_key,
        "promoted_registry_hash": item.promoted_registry_hash,
        "candidate_registry_loaded_downstream": registry_loaded,
        "executed_downstream": executed,
        "cited_downstream": cited,
        "executed_case_ids": list(item.executed_case_ids),
        "cited_case_ids": list(item.cited_case_ids),
    }


def _validate_response_reuse(rows: Iterable[SystemCaseResult]) -> None:
    within_replicate: dict[tuple[str, str], str] = {}
    response_replicate: dict[str, str] = {}
    response_input: dict[str, str] = {}
    response_outcome: dict[str, tuple[bool | None, bool, bool]] = {}
    for row in rows:
        if row.input_hash is None or row.response_id is None:
            continue
        same_input = (row.replicate_id, row.input_hash)
        prior_response = within_replicate.setdefault(same_input, row.response_id)
        if prior_response != row.response_id:
            raise ValidationError(
                "identical paired model inputs did not reuse one response invocation"
            )
        prior_input = response_input.setdefault(row.response_id, row.input_hash)
        if prior_input != row.input_hash:
            raise ValidationError("one response invocation has multiple model inputs")
        outcome = (
            row.predicted_surge,
            row.contract_valid,
            row.execution_failed,
        )
        prior_outcome = response_outcome.setdefault(row.response_id, outcome)
        if prior_outcome != outcome:
            raise ValidationError("one response invocation has conflicting outputs")
        prior_replicate = response_replicate.setdefault(
            row.response_id, row.replicate_id
        )
        if prior_replicate != row.replicate_id:
            raise ValidationError(
                "independent replicates reused one response invocation"
            )


def _cost_increase_ratio(baseline: float, candidate: float) -> float | None:
    if baseline == 0:
        return 0.0 if candidate == 0 else None
    return (candidate - baseline) / baseline


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = round((len(values) - 1) * quantile)
    return values[index]


def _ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _result_key_text(key: tuple[BenefitArm, str, str]) -> str:
    arm, case_id, replicate_id = key
    return f"{arm.value}:{case_id}:{replicate_id}"


def _require_id(value: str, name: str) -> None:
    if not _SAFE_ID.fullmatch(value):
        raise ValidationError(f"{name} must be a safe non-empty id")


def _require_unique_ids(
    values: tuple[str, ...], name: str, *, allow_empty: bool = False
) -> None:
    if (not values and not allow_empty) or len(set(values)) != len(values):
        raise ValidationError(f"{name} must contain unique ids")
    for value in values:
        _require_id(value, name)


def _require_hash(value: str, name: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValidationError(f"{name} must be a SHA-256 hash")


def _require_finite_range(value: float, name: str, low: float, high: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not low <= float(value) <= high
    ):
        raise ValidationError(f"{name} must be finite and in [{low}, {high}]")
