"""Dual-loop evolution of adaptive Information Plans and versioned Signals."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Generic, Iterable, Mapping, Protocol, TypeVar

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.llm.agent import (
    AgentUsage,
    DomainTool,
    GenericAgent,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    LLMSignalRunner,
    SignalBatchResult,
    SignalExecutionType,
    SignalExecutor,
    SignalRegistry,
    SignalResult,
    SignalSpec,
    SignalValue,
    default_deterministic_signal_functions,
)


T = TypeVar("T")
ProgressCallback = Callable[[Mapping[str, Any]], None]
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]*$")
_FORBIDDEN_BASIC_INFO_FIELDS = frozenset(
    {
        "ground_truth",
        "outcome",
        "outcome_label",
        "label",
        "is_surge",
        "magnitude_class",
        "realized_return",
        "realized_max_multiple",
        "future_price",
        "future_return",
        "post_outcome",
    }
)


class ResearchDecision(str, Enum):
    """Research Controller decision after initial reasoning or batch reflection."""

    CONTINUE = "continue"
    FINALIZE = "finalize"


class MagnitudeClass(str, Enum):
    """Stage-2 class for a predicted or realized surge."""

    TWO_TO_THREE = "2-3x"
    THREE_TO_TEN = "3-10x"
    TEN_PLUS = "10x+"


class ConfidenceLevel(str, Enum):
    """Qualitative prediction confidence."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RuntimeStopReason(str, Enum):
    """Why adaptive research stopped selecting more Signals."""

    FINALIZED = "finalized"
    NO_SIGNAL_MATCH = "no_signal_match"
    MAX_SIGNAL_ROUNDS = "max_signal_rounds"
    MAX_SIGNAL_CALLS = "max_signal_calls"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True)
class AgentStep(Generic[T]):
    """One structured role result plus reported model usage."""

    value: T
    usage: AgentUsage = field(default_factory=AgentUsage)


@dataclass(frozen=True)
class BasicInfoPolicy:
    """Small bootstrap field set that cannot preload the Raw Info Store."""

    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.fields or any(not field_name.strip() for field_name in self.fields):
            raise ValidationError("basic info policy requires non-empty fields")
        if len(set(self.fields)) != len(self.fields):
            raise ValidationError("basic info policy fields must be unique")
        forbidden = sorted(
            field_name
            for field_name in self.fields
            if _is_forbidden_basic_info_field(field_name)
        )
        if forbidden:
            raise ValidationError(
                "basic info policy cannot request outcome fields: "
                + ", ".join(forbidden)
            )
        object.__setattr__(self, "fields", tuple(self.fields))

    def to_dict(self) -> dict[str, Any]:
        return {"fields": list(self.fields)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BasicInfoPolicy":
        return cls(fields=tuple(str(item) for item in data.get("fields", ())))


@dataclass(frozen=True)
class InformationPlan:
    """The four-part evolvable research strategy S=(B,H_init,H_reflect,H_analyse)."""

    plan_id: str
    parent_ids: tuple[str, ...]
    basic_info_policy: BasicInfoPolicy
    initial_research_skill: str
    reflection_skill: str
    analysis_prompt: str

    def __post_init__(self) -> None:
        _validate_id(self.plan_id, "plan_id")
        for parent_id in self.parent_ids:
            _validate_id(parent_id, "parent_id")
        if self.plan_id in self.parent_ids:
            raise ValidationError("information plan cannot be its own parent")
        for name in (
            "initial_research_skill",
            "reflection_skill",
            "analysis_prompt",
        ):
            if not str(getattr(self, name)).strip():
                raise ValidationError(f"information plan {name} must not be empty")
        object.__setattr__(self, "parent_ids", tuple(self.parent_ids))

    def canonical_dict(self) -> dict[str, Any]:
        """Return stable content for embedding and identity checks."""

        return {
            "basic_info": list(self.basic_info_policy.fields),
            "initial_research": " ".join(self.initial_research_skill.split()),
            "reflection": " ".join(self.reflection_skill.split()),
            "analysis": " ".join(self.analysis_prompt.split()),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "parent_ids": list(self.parent_ids),
            "basic_info_policy": self.basic_info_policy.to_dict(),
            "initial_research_skill": self.initial_research_skill,
            "reflection_skill": self.reflection_skill,
            "analysis_prompt": self.analysis_prompt,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InformationPlan":
        return cls(
            plan_id=str(data["plan_id"]),
            parent_ids=tuple(str(item) for item in data.get("parent_ids", ())),
            basic_info_policy=BasicInfoPolicy.from_dict(
                dict(data["basic_info_policy"])
            ),
            initial_research_skill=str(data["initial_research_skill"]),
            reflection_skill=str(data["reflection_skill"]),
            analysis_prompt=str(data["analysis_prompt"]),
        )


@dataclass(frozen=True)
class ResearchState:
    """Complete Controller state after initial reasoning or batch reflection."""

    hypotheses: tuple[str, ...] = ()
    current_beliefs: tuple[str, ...] = ()
    supporting_evidence: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    resolved_questions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    next_information_needs: tuple[str, ...] = ()
    decision: ResearchDecision = ResearchDecision.CONTINUE

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ResearchDecision):
            object.__setattr__(self, "decision", ResearchDecision(self.decision))
        for name in (
            "hypotheses",
            "current_beliefs",
            "supporting_evidence",
            "contradictions",
            "resolved_questions",
            "open_questions",
            "next_information_needs",
        ):
            values = tuple(str(item) for item in getattr(self, name))
            if any(not item.strip() for item in values):
                raise ValidationError(f"research state {name} cannot contain blanks")
            object.__setattr__(self, name, values)
        if self.decision is ResearchDecision.CONTINUE and not self.next_information_needs:
            raise ValidationError("continuing research requires next information needs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypotheses": list(self.hypotheses),
            "current_beliefs": list(self.current_beliefs),
            "supporting_evidence": list(self.supporting_evidence),
            "contradictions": list(self.contradictions),
            "resolved_questions": list(self.resolved_questions),
            "open_questions": list(self.open_questions),
            "next_information_needs": list(self.next_information_needs),
            "decision": self.decision.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResearchState":
        return cls(
            hypotheses=tuple(str(item) for item in data.get("hypotheses", ())),
            current_beliefs=tuple(
                str(item) for item in data.get("current_beliefs", ())
            ),
            supporting_evidence=tuple(
                str(item) for item in data.get("supporting_evidence", ())
            ),
            contradictions=tuple(
                str(item) for item in data.get("contradictions", ())
            ),
            resolved_questions=tuple(
                str(item) for item in data.get("resolved_questions", ())
            ),
            open_questions=tuple(
                str(item) for item in data.get("open_questions", ())
            ),
            next_information_needs=tuple(
                str(item) for item in data.get("next_information_needs", ())
            ),
            decision=ResearchDecision(str(data.get("decision", "continue"))),
        )


class ResearchController(Protocol):
    """Decides what information is needed before and after each Signal batch."""

    def initialize(
        self,
        plan: InformationPlan,
        basic_info: Mapping[str, Any],
    ) -> AgentStep[ResearchState]:
        """Run H_init over Basic Info."""

    def reflect(
        self,
        plan: InformationPlan,
        state: ResearchState,
        batch: SignalBatchResult,
    ) -> AgentStep[ResearchState]:
        """Run H_reflect once over the complete Signal batch."""


class SignalRetrievalAgent(Protocol):
    """Maps natural-language needs to existing frozen Signal refs."""

    def select(
        self,
        information_needs: tuple[str, ...],
        signal_registry: FrozenSignalRegistry,
    ) -> AgentStep[tuple[str, ...]]:
        """Return a unique Signal batch after progressive disclosure."""


@dataclass(frozen=True)
class BlindPrediction:
    """Saved label-free two-stage Predictor output."""

    is_surge: bool
    magnitude: MagnitudeClass | None
    confidence: ConfidenceLevel
    key_reasons: tuple[str, ...]
    uncertainties: tuple[str, ...]
    session_id: str

    def __post_init__(self) -> None:
        if self.is_surge and self.magnitude is None:
            raise ValidationError("surge prediction requires magnitude class")
        if not self.is_surge and self.magnitude is not None:
            raise ValidationError("non-surge prediction cannot include magnitude")
        if self.magnitude is not None and not isinstance(self.magnitude, MagnitudeClass):
            object.__setattr__(self, "magnitude", MagnitudeClass(self.magnitude))
        if not isinstance(self.confidence, ConfidenceLevel):
            object.__setattr__(self, "confidence", ConfidenceLevel(self.confidence))
        if not self.session_id.strip():
            raise ValidationError("blind prediction requires session_id")
        if not self.key_reasons:
            raise ValidationError("blind prediction requires key reasons")
        object.__setattr__(self, "key_reasons", tuple(self.key_reasons))
        object.__setattr__(self, "uncertainties", tuple(self.uncertainties))

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_surge": self.is_surge,
            "magnitude": self.magnitude.value if self.magnitude else None,
            "confidence": {"level": self.confidence.value},
            "key_reasons": list(self.key_reasons),
            "uncertainties": list(self.uncertainties),
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BlindPrediction":
        confidence = data.get("confidence", {})
        confidence_value = (
            confidence.get("level") if isinstance(confidence, Mapping) else confidence
        )
        magnitude = data.get("magnitude")
        return cls(
            is_surge=bool(data["is_surge"]),
            magnitude=MagnitudeClass(str(magnitude)) if magnitude else None,
            confidence=ConfidenceLevel(str(confidence_value)),
            key_reasons=tuple(str(item) for item in data.get("key_reasons", ())),
            uncertainties=tuple(
                str(item) for item in data.get("uncertainties", ())
            ),
            session_id=str(data["session_id"]),
        )


@dataclass(frozen=True)
class GroundTruth:
    """Continuous realized multiple plus deterministic two-stage labels."""

    realized_max_multiple: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.realized_max_multiple) or self.realized_max_multiple < 0:
            raise ValidationError("realized_max_multiple must be finite and non-negative")

    @property
    def is_surge(self) -> bool:
        return self.realized_max_multiple >= 2.0

    @property
    def magnitude(self) -> MagnitudeClass | None:
        if not self.is_surge:
            return None
        if self.realized_max_multiple < 3.0:
            return MagnitudeClass.TWO_TO_THREE
        if self.realized_max_multiple < 10.0:
            return MagnitudeClass.THREE_TO_TEN
        return MagnitudeClass.TEN_PLUS

    def to_dict(self) -> dict[str, Any]:
        return {
            "realized_max_multiple": self.realized_max_multiple,
            "is_surge": self.is_surge,
            "magnitude": self.magnitude.value if self.magnitude else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GroundTruth":
        return cls(realized_max_multiple=float(data["realized_max_multiple"]))


@dataclass(frozen=True)
class PredictionSelfReflection:
    """Post-hoc usability feedback produced only after label reveal."""

    correct: bool
    why_prediction_failed: tuple[str, ...] = ()
    misleading_signals: tuple[str, ...] = ()
    ignored_evidence: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    plan_issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "why_prediction_failed",
            "misleading_signals",
            "ignored_evidence",
            "missing_information",
            "plan_issues",
        ):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_outcome": {"correct": self.correct},
            "why_prediction_failed": list(self.why_prediction_failed),
            "misleading_signals": list(self.misleading_signals),
            "ignored_evidence": list(self.ignored_evidence),
            "missing_information": list(self.missing_information),
            "plan_issues": list(self.plan_issues),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PredictionSelfReflection":
        outcome = dict(data.get("prediction_outcome", {}))
        return cls(
            correct=bool(outcome.get("correct", False)),
            why_prediction_failed=tuple(
                str(item) for item in data.get("why_prediction_failed", ())
            ),
            misleading_signals=tuple(
                str(item) for item in data.get("misleading_signals", ())
            ),
            ignored_evidence=tuple(
                str(item) for item in data.get("ignored_evidence", ())
            ),
            missing_information=tuple(
                str(item) for item in data.get("missing_information", ())
            ),
            plan_issues=tuple(str(item) for item in data.get("plan_issues", ())),
        )


class BlindPredictor(Protocol):
    """Same adapter performs label-free prediction and label-revealed reflection."""

    def predict(self, final_context: Mapping[str, Any]) -> AgentStep[BlindPrediction]:
        """Predict without label, identity leakage, or web tools."""

    def reflect(
        self,
        original_context: Mapping[str, Any],
        original_prediction: BlindPrediction,
        ground_truth: GroundTruth,
    ) -> AgentStep[PredictionSelfReflection]:
        """Reflect in the saved prediction session after truth is revealed."""


@dataclass(frozen=True)
class SignalRound:
    """One need-selection-execution batch in a research trajectory."""

    information_needs: tuple[str, ...]
    selected_signals: tuple[str, ...]
    batch: SignalBatchResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "information_needs": list(self.information_needs),
            "selected_signals": list(self.selected_signals),
            "batch": {
                "results": [result.to_dict() for result in self.batch.results],
                "signal_calls": self.batch.signal_calls,
                "usage": _usage_to_dict(self.batch.usage),
            },
        }

    def to_model_context_dict(self) -> dict[str, Any]:
        """Return semantic Signal evidence without cache-variant usage metadata."""

        return {
            "information_needs": list(self.information_needs),
            "selected_signals": list(self.selected_signals),
            "batch": {
                "results": [result.to_dict() for result in self.batch.results],
                "signal_calls": self.batch.signal_calls,
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalRound":
        batch = dict(data["batch"])
        return cls(
            information_needs=tuple(
                str(item) for item in data.get("information_needs", ())
            ),
            selected_signals=tuple(
                str(item) for item in data.get("selected_signals", ())
            ),
            batch=SignalBatchResult(
                results=tuple(
                    SignalResult.from_dict(item) for item in batch.get("results", ())
                ),
                signal_calls=int(batch.get("signal_calls", 0)),
                usage=_usage_from_dict(dict(batch.get("usage", {}))),
            ),
        )


@dataclass(frozen=True)
class RuntimeLimits:
    """Fixed engineering guards, not evolvable research logic."""

    max_signal_rounds: int = 8
    max_signal_calls: int = 20
    max_llm_calls: int = 30
    max_tokens: int = 100_000
    max_cost: float = 20.0

    def __post_init__(self) -> None:
        if min(
            self.max_signal_rounds,
            self.max_signal_calls,
            self.max_llm_calls,
            self.max_tokens,
        ) < 1:
            raise ValidationError("runtime count and token limits must be positive")
        if self.max_llm_calls < 3:
            raise ValidationError("runtime requires at least three LLM calls")
        if self.max_cost <= 0:
            raise ValidationError("runtime max_cost must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_signal_rounds": self.max_signal_rounds,
            "max_signal_calls": self.max_signal_calls,
            "max_llm_calls": self.max_llm_calls,
            "max_tokens": self.max_tokens,
            "max_cost": self.max_cost,
        }


@dataclass(frozen=True)
class RuntimeUsage:
    """Complete usage accumulated by one Information Plan execution."""

    signal_rounds: int
    signal_calls: int
    model: AgentUsage

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_rounds": self.signal_rounds,
            "signal_calls": self.signal_calls,
            "model": _usage_to_dict(self.model),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuntimeUsage":
        return cls(
            signal_rounds=int(data["signal_rounds"]),
            signal_calls=int(data["signal_calls"]),
            model=_usage_from_dict(dict(data["model"])),
        )


@dataclass(frozen=True)
class ExecutionTrajectory:
    """Complete auditable Plan execution for one company."""

    company_id: str
    prediction_time: datetime
    basic_info: Mapping[str, Any]
    initial_state: ResearchState
    signal_rounds: tuple[SignalRound, ...]
    final_state: ResearchState
    final_context: Mapping[str, Any]
    prediction: BlindPrediction
    prediction_ref: str
    ground_truth: GroundTruth
    self_reflection: PredictionSelfReflection
    stop_reason: RuntimeStopReason
    usage: RuntimeUsage
    case_id: str = ""

    def __post_init__(self) -> None:
        _validate_id(self.company_id, "company_id")
        resolved_case_id = self.case_id or _default_case_id(
            self.company_id, self.prediction_time
        )
        _validate_id(resolved_case_id, "case_id")
        object.__setattr__(self, "case_id", resolved_case_id)
        if not self.prediction_ref.strip():
            raise ValidationError("execution trajectory requires persisted prediction ref")
        object.__setattr__(self, "basic_info", dict(self.basic_info))
        object.__setattr__(self, "signal_rounds", tuple(self.signal_rounds))
        object.__setattr__(self, "final_context", dict(self.final_context))
        if not isinstance(self.stop_reason, RuntimeStopReason):
            object.__setattr__(self, "stop_reason", RuntimeStopReason(self.stop_reason))

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "company_id": self.company_id,
            "prediction_time": self.prediction_time.isoformat(),
            "basic_info": dict(self.basic_info),
            "initial_state": self.initial_state.to_dict(),
            "signal_rounds": [item.to_dict() for item in self.signal_rounds],
            "final_state": self.final_state.to_dict(),
            "final_context": dict(self.final_context),
            "prediction": self.prediction.to_dict(),
            "prediction_ref": self.prediction_ref,
            "ground_truth": self.ground_truth.to_dict(),
            "self_reflection": self.self_reflection.to_dict(),
            "stop_reason": self.stop_reason.value,
            "usage": self.usage.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionTrajectory":
        return cls(
            case_id=str(data.get("case_id", "")),
            company_id=str(data["company_id"]),
            prediction_time=datetime.fromisoformat(str(data["prediction_time"])),
            basic_info=dict(data.get("basic_info", {})),
            initial_state=ResearchState.from_dict(dict(data["initial_state"])),
            signal_rounds=tuple(
                SignalRound.from_dict(item) for item in data.get("signal_rounds", ())
            ),
            final_state=ResearchState.from_dict(dict(data["final_state"])),
            final_context=dict(data.get("final_context", {})),
            prediction=BlindPrediction.from_dict(dict(data["prediction"])),
            prediction_ref=str(data["prediction_ref"]),
            ground_truth=GroundTruth.from_dict(dict(data["ground_truth"])),
            self_reflection=PredictionSelfReflection.from_dict(
                dict(data["self_reflection"])
            ),
            stop_reason=RuntimeStopReason(str(data["stop_reason"])),
            usage=RuntimeUsage.from_dict(dict(data["usage"])),
        )


class RuntimeBudgetExceeded(ValidationError):
    """Raised when a completed model step crosses a hard token or cost limit."""


def execute_information_plan(
    *,
    plan: InformationPlan,
    company_id: str,
    case_id: str | None = None,
    company_basic_source: Mapping[str, Any],
    prediction_time: datetime,
    signal_registry: FrozenSignalRegistry,
    signal_executor: SignalExecutor,
    controller: ResearchController,
    signal_agent: SignalRetrievalAgent,
    predictor: BlindPredictor,
    prediction_sink: Callable[
        [str, datetime, Mapping[str, Any], BlindPrediction], str
    ],
    ground_truth_provider: Callable[[str], GroundTruth],
    limits: RuntimeLimits = RuntimeLimits(),
) -> ExecutionTrajectory:
    """Execute one adaptive Plan and persist its prediction before label reveal."""

    _validate_id(company_id, "company_id")
    _require_aware_datetime(prediction_time, "prediction_time")
    resolved_case_id = case_id or _default_case_id(company_id, prediction_time)
    _validate_id(resolved_case_id, "case_id")
    basic_info = {
        field_name: company_basic_source.get(field_name)
        for field_name in plan.basic_info_policy.fields
    }
    source_aliases = company_basic_source.get("identity_aliases", ())
    if isinstance(source_aliases, str):
        source_aliases = (source_aliases,)
    model_usage = AgentUsage()
    initial_step = controller.initialize(plan, basic_info)
    model_usage = _consume_model_step(model_usage, initial_step.usage, limits)
    initial_state = initial_step.value
    state = initial_state
    rounds: list[SignalRound] = []
    signal_calls = 0
    stop_reason = RuntimeStopReason.FINALIZED

    while state.decision is ResearchDecision.CONTINUE:
        if len(rounds) >= limits.max_signal_rounds:
            stop_reason = RuntimeStopReason.MAX_SIGNAL_ROUNDS
            break
        if signal_calls >= limits.max_signal_calls:
            stop_reason = RuntimeStopReason.MAX_SIGNAL_CALLS
            break
        if model_usage.llm_calls + 4 > limits.max_llm_calls:
            stop_reason = RuntimeStopReason.BUDGET_EXHAUSTED
            break

        selection_step = signal_agent.select(
            state.next_information_needs,
            signal_registry,
        )
        model_usage = _consume_model_step(model_usage, selection_step.usage, limits)
        selected = tuple(selection_step.value)
        if len(set(selected)) != len(selected):
            raise ValidationError("Signal Retrieval Agent returned duplicate refs")
        if not selected:
            stop_reason = RuntimeStopReason.NO_SIGNAL_MATCH
            break
        remaining_calls = limits.max_signal_calls - signal_calls
        selected = selected[:remaining_calls]
        batch = signal_executor.execute_batch(
            selected,
            company_id=company_id,
            as_of=prediction_time,
        )
        model_usage = _consume_usage(model_usage, batch.usage, limits)
        signal_calls += batch.signal_calls
        rounds.append(
            SignalRound(
                information_needs=state.next_information_needs,
                selected_signals=selected,
                batch=batch,
            )
        )
        reflection_step = controller.reflect(plan, state, batch)
        model_usage = _consume_model_step(model_usage, reflection_step.usage, limits)
        state = reflection_step.value
        if state.decision is ResearchDecision.FINALIZE:
            stop_reason = RuntimeStopReason.FINALIZED

    final_context = _assemble_final_context(
        plan=plan,
        company_id=company_id,
        additional_identity_aliases=tuple(str(item) for item in source_aliases),
        basic_info=basic_info,
        state=state,
        rounds=rounds,
        stop_reason=stop_reason,
    )
    prediction_step = predictor.predict(final_context)
    model_usage = _consume_model_step(model_usage, prediction_step.usage, limits)
    prediction = prediction_step.value
    prediction_ref = prediction_sink(
        company_id,
        prediction_time,
        final_context,
        prediction,
    )
    if not prediction_ref.strip():
        raise ValidationError("prediction sink must return a durable reference")

    ground_truth = ground_truth_provider(company_id)
    reflection_step = predictor.reflect(final_context, prediction, ground_truth)
    model_usage = _consume_model_step(model_usage, reflection_step.usage, limits)

    return ExecutionTrajectory(
        case_id=resolved_case_id,
        company_id=company_id,
        prediction_time=prediction_time,
        basic_info=basic_info,
        initial_state=initial_state,
        signal_rounds=tuple(rounds),
        final_state=state,
        final_context=final_context,
        prediction=prediction,
        prediction_ref=prediction_ref,
        ground_truth=ground_truth,
        self_reflection=reflection_step.value,
        stop_reason=stop_reason,
        usage=RuntimeUsage(
            signal_rounds=len(rounds),
            signal_calls=signal_calls,
            model=model_usage,
        ),
    )


def _assemble_final_context(
    *,
    plan: InformationPlan,
    company_id: str,
    additional_identity_aliases: tuple[str, ...],
    basic_info: Mapping[str, Any],
    state: ResearchState,
    rounds: Iterable[SignalRound],
    stop_reason: RuntimeStopReason,
) -> dict[str, Any]:
    identity_keys = {"company_id", "company_name", "ticker", "symbol"}
    identity_aliases = [
        company_id,
        *additional_identity_aliases,
        *(
            str(value)
            for key, value in basic_info.items()
            if key in identity_keys and value is not None
        ),
    ]
    context = {
        "basic_info": {
            key: value for key, value in basic_info.items() if key not in identity_keys
        },
        "signal_rounds": [item.to_model_context_dict() for item in rounds],
        "final_research_state": state.to_dict(),
        "analysis_prompt": plan.analysis_prompt,
        "runtime_stop_reason": stop_reason.value,
    }
    return _mask_identity_values(context, identity_aliases)


def _consume_model_step(
    current: AgentUsage,
    reported: AgentUsage,
    limits: RuntimeLimits,
) -> AgentUsage:
    if reported.llm_calls == 0:
        reported = AgentUsage(llm_calls=1, tokens=reported.tokens, cost=reported.cost)
    return _consume_usage(current, reported, limits)


def _consume_usage(
    current: AgentUsage,
    additional: AgentUsage,
    limits: RuntimeLimits,
) -> AgentUsage:
    result = current + additional
    if result.llm_calls > limits.max_llm_calls:
        raise RuntimeBudgetExceeded("runtime exceeded max_llm_calls")
    if result.tokens > limits.max_tokens:
        raise RuntimeBudgetExceeded("runtime exceeded max_tokens")
    if result.cost > limits.max_cost:
        raise RuntimeBudgetExceeded("runtime exceeded max_cost")
    return result


@dataclass(frozen=True)
class PlanMetrics:
    """Binary fitness plus Stage-2 diagnostics."""

    binary_precision: float
    binary_recall: float
    binary_f1: float
    magnitude_accuracy: float
    magnitude_macro_f1: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "binary_precision": self.binary_precision,
            "binary_recall": self.binary_recall,
            "binary_f1": self.binary_f1,
            "magnitude_accuracy": self.magnitude_accuracy,
            "magnitude_macro_f1": self.magnitude_macro_f1,
            "confusion": {
                "true_positive": self.true_positive,
                "false_positive": self.false_positive,
                "true_negative": self.true_negative,
                "false_negative": self.false_negative,
            },
            "sample_count": self.sample_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanMetrics":
        confusion = dict(data.get("confusion", {}))
        return cls(
            binary_precision=float(data["binary_precision"]),
            binary_recall=float(data["binary_recall"]),
            binary_f1=float(data["binary_f1"]),
            magnitude_accuracy=float(data["magnitude_accuracy"]),
            magnitude_macro_f1=float(data["magnitude_macro_f1"]),
            true_positive=int(confusion.get("true_positive", 0)),
            false_positive=int(confusion.get("false_positive", 0)),
            true_negative=int(confusion.get("true_negative", 0)),
            false_negative=int(confusion.get("false_negative", 0)),
            sample_count=int(data["sample_count"]),
        )


def score_predictions(trajectories: Iterable[ExecutionTrajectory]) -> PlanMetrics:
    """Compute binary metrics and three-class magnitude diagnostics."""

    rows = tuple(trajectories)
    if not rows:
        raise ValidationError("cannot score an empty trajectory set")
    true_positive = sum(
        row.prediction.is_surge and row.ground_truth.is_surge for row in rows
    )
    false_positive = sum(
        row.prediction.is_surge and not row.ground_truth.is_surge for row in rows
    )
    true_negative = sum(
        not row.prediction.is_surge and not row.ground_truth.is_surge for row in rows
    )
    false_negative = sum(
        not row.prediction.is_surge and row.ground_truth.is_surge for row in rows
    )
    precision = _safe_ratio(true_positive, true_positive + false_positive)
    recall = _safe_ratio(true_positive, true_positive + false_negative)
    binary_f1 = _safe_ratio(2 * precision * recall, precision + recall)

    surge_rows = tuple(row for row in rows if row.ground_truth.is_surge)
    magnitude_correct = sum(
        row.prediction.magnitude == row.ground_truth.magnitude for row in surge_rows
    )
    magnitude_accuracy = _safe_ratio(magnitude_correct, len(surge_rows))
    per_class_f1: list[float] = []
    for magnitude in MagnitudeClass:
        class_tp = sum(
            row.ground_truth.magnitude is magnitude
            and row.prediction.magnitude is magnitude
            for row in surge_rows
        )
        class_fp = sum(
            row.ground_truth.magnitude is not magnitude
            and row.prediction.magnitude is magnitude
            for row in surge_rows
        )
        class_fn = sum(
            row.ground_truth.magnitude is magnitude
            and row.prediction.magnitude is not magnitude
            for row in surge_rows
        )
        class_precision = _safe_ratio(class_tp, class_tp + class_fp)
        class_recall = _safe_ratio(class_tp, class_tp + class_fn)
        per_class_f1.append(
            _safe_ratio(
                2 * class_precision * class_recall,
                class_precision + class_recall,
            )
        )
    return PlanMetrics(
        binary_precision=precision,
        binary_recall=recall,
        binary_f1=binary_f1,
        magnitude_accuracy=magnitude_accuracy,
        magnitude_macro_f1=sum(per_class_f1) / len(per_class_f1),
        true_positive=true_positive,
        false_positive=false_positive,
        true_negative=true_negative,
        false_negative=false_negative,
        sample_count=len(rows),
    )


def _safe_ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


@dataclass(frozen=True)
class EvolutionCase:
    """One dataset case whose label owner is outside Plan execution."""

    company_id: str
    prediction_time: datetime
    basic_info: Mapping[str, Any]
    ground_truth: GroundTruth
    case_id: str = ""

    def __post_init__(self) -> None:
        _validate_id(self.company_id, "company_id")
        _require_aware_datetime(self.prediction_time, "prediction_time")
        resolved_case_id = self.case_id or _default_case_id(
            self.company_id, self.prediction_time
        )
        _validate_id(resolved_case_id, "case_id")
        object.__setattr__(self, "case_id", resolved_case_id)
        object.__setattr__(self, "basic_info", dict(self.basic_info))

    def to_discovery_dict(self) -> dict[str, Any]:
        """Return label-visible data only for the Discovery workspace."""

        return {
            "case_id": self.case_id,
            "company_id": self.company_id,
            "prediction_time": self.prediction_time.isoformat(),
            "basic_info": dict(self.basic_info),
            "ground_truth": self.ground_truth.to_dict(),
        }


@dataclass(frozen=True)
class EvolutionDataset:
    """Issuer-disjoint Discovery, Evolution Validation, and Locked Test sets."""

    discovery: tuple[EvolutionCase, ...]
    evolution_validation: tuple[EvolutionCase, ...]
    locked_test: tuple[EvolutionCase, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "discovery", tuple(self.discovery))
        object.__setattr__(
            self, "evolution_validation", tuple(self.evolution_validation)
        )
        object.__setattr__(self, "locked_test", tuple(self.locked_test))
        owners: dict[str, str] = {}
        seen_case_ids: set[str] = set()
        for split_name, cases in (
            ("discovery", self.discovery),
            ("evolution_validation", self.evolution_validation),
            ("locked_test", self.locked_test),
        ):
            if not cases:
                raise ValidationError(f"dataset split {split_name} must not be empty")
            for case in cases:
                if case.case_id in seen_case_ids:
                    raise ValidationError(f"duplicate evolution case_id: {case.case_id}")
                seen_case_ids.add(case.case_id)
                prior = owners.setdefault(case.company_id, split_name)
                if prior != split_name:
                    raise ValidationError(
                        f"company {case.company_id} crosses dataset ownership boundaries"
                    )


@dataclass(frozen=True)
class PlanReflection:
    """Plan-level Critic output over all trajectories and metrics."""

    successful_patterns: tuple[str, ...] = ()
    failed_patterns: tuple[str, ...] = ()
    repeated_failure_modes: tuple[str, ...] = ()
    misleading_signals: tuple[str, ...] = ()
    missing_information_needs: tuple[str, ...] = ()
    next_explorations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "successful_patterns",
            "failed_patterns",
            "repeated_failure_modes",
            "misleading_signals",
            "missing_information_needs",
            "next_explorations",
        ):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "successful_patterns": list(self.successful_patterns),
            "failed_patterns": list(self.failed_patterns),
            "repeated_failure_modes": list(self.repeated_failure_modes),
            "misleading_signals": list(self.misleading_signals),
            "missing_information_needs": list(self.missing_information_needs),
            "next_explorations": list(self.next_explorations),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanReflection":
        return cls(
            successful_patterns=tuple(
                str(item) for item in data.get("successful_patterns", ())
            ),
            failed_patterns=tuple(
                str(item) for item in data.get("failed_patterns", ())
            ),
            repeated_failure_modes=tuple(
                str(item) for item in data.get("repeated_failure_modes", ())
            ),
            misleading_signals=tuple(
                str(item) for item in data.get("misleading_signals", ())
            ),
            missing_information_needs=tuple(
                str(item) for item in data.get("missing_information_needs", ())
            ),
            next_explorations=tuple(
                str(item) for item in data.get("next_explorations", ())
            ),
        )


@dataclass(frozen=True)
class PlanRecord:
    """Durable Plan Archive record P=(S,E,J,R,U,T)."""

    plan: InformationPlan
    round_id: int
    embedding: tuple[float, ...]
    metrics: PlanMetrics
    reflection: PlanReflection
    signal_usage: Mapping[str, Mapping[str, int]]
    trajectories: tuple[ExecutionTrajectory, ...]

    def __post_init__(self) -> None:
        if self.round_id < 1:
            raise ValidationError("plan record round_id must be positive")
        if not self.embedding or not all(math.isfinite(item) for item in self.embedding):
            raise ValidationError("plan embedding must contain finite values")
        if not self.trajectories:
            raise ValidationError("plan record requires complete trajectories")
        object.__setattr__(self, "embedding", tuple(float(item) for item in self.embedding))
        object.__setattr__(
            self,
            "signal_usage",
            {
                ref: {str(key): int(value) for key, value in counts.items()}
                for ref, counts in self.signal_usage.items()
            },
        )
        object.__setattr__(self, "trajectories", tuple(self.trajectories))

    @property
    def plan_id(self) -> str:
        return self.plan.plan_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "parent_ids": list(self.plan.parent_ids),
            "round_id": self.round_id,
            "plan": self.plan.to_dict(),
            "embedding": list(self.embedding),
            "metrics": self.metrics.to_dict(),
            "reflection": self.reflection.to_dict(),
            "signal_usage": {
                ref: dict(counts) for ref, counts in self.signal_usage.items()
            },
            "trajectories": [item.to_dict() for item in self.trajectories],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanRecord":
        return cls(
            plan=InformationPlan.from_dict(dict(data["plan"])),
            round_id=int(data["round_id"]),
            embedding=tuple(float(item) for item in data.get("embedding", ())),
            metrics=PlanMetrics.from_dict(dict(data["metrics"])),
            reflection=PlanReflection.from_dict(dict(data["reflection"])),
            signal_usage={
                str(ref): {str(key): int(value) for key, value in dict(counts).items()}
                for ref, counts in dict(data.get("signal_usage", {})).items()
            },
            trajectories=tuple(
                ExecutionTrajectory.from_dict(item)
                for item in data.get("trajectories", ())
            ),
        )


class PlanEmbedder(Protocol):
    """Embeds a canonicalized Plan for diversity selection."""

    def embed(self, plan: InformationPlan) -> tuple[float, ...]:
        """Return a finite fixed-length vector."""


class HashingPlanEmbedder:
    """Dependency-free deterministic bag-of-token Plan embedder."""

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions < 8:
            raise ValidationError("plan embedding dimensions must be at least 8")
        self.dimensions = dimensions

    def embed(self, plan: InformationPlan) -> tuple[float, ...]:
        canonical = json.dumps(plan.canonical_dict(), sort_keys=True)
        vector = [0.0] * self.dimensions
        normalized = " ".join(canonical.casefold().split())
        tokens = re.findall(r"\w+", normalized, flags=re.UNICODE)
        compact = "".join(character for character in normalized if not character.isspace())
        tokens.extend(
            f"char3:{compact[index:index + 3]}"
            for index in range(max(0, len(compact) - 2))
        )
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(item * item for item in vector))
        if norm == 0:
            raise ValidationError("canonicalized plan produced empty embedding")
        return tuple(item / norm for item in vector)


@dataclass(frozen=True)
class ParentSelection:
    """Quality-diverse Top-K records plus random exploration records."""

    top: tuple[PlanRecord, ...]
    random: tuple[PlanRecord, ...]

    @property
    def records(self) -> tuple[PlanRecord, ...]:
        return self.top + self.random

    @property
    def plans(self) -> tuple[InformationPlan, ...]:
        return tuple(record.plan for record in self.records)


class PlanArchive:
    """Committed in-memory Plan records with quality-diverse parent selection."""

    def __init__(self, records: Iterable[PlanRecord] = ()) -> None:
        self._records: dict[str, PlanRecord] = {}
        for record in records:
            self.add(record)

    @property
    def records(self) -> tuple[PlanRecord, ...]:
        return tuple(
            sorted(
                self._records.values(),
                key=lambda record: (record.round_id, record.plan_id),
            )
        )

    def add(self, record: PlanRecord) -> None:
        if record.plan_id in self._records:
            raise ValidationError(f"duplicate plan archive id: {record.plan_id}")
        self._records[record.plan_id] = record

    def select_parents(
        self,
        *,
        top_k: int,
        random_k: int = 2,
        similarity_threshold: float = 0.9,
        rng: random.Random | None = None,
    ) -> ParentSelection:
        """Select by binary F1, then remove embedding-near duplicates."""

        if top_k < 1 or random_k < 0:
            raise ValidationError("parent selection counts are invalid")
        if not -1 < similarity_threshold <= 1:
            raise ValidationError("similarity threshold must be in (-1, 1]")
        ranked = sorted(
            self._records.values(),
            key=lambda record: (-record.metrics.binary_f1, record.plan_id),
        )
        selected: list[PlanRecord] = []
        for record in ranked:
            if all(
                cosine_similarity(record.embedding, kept.embedding)
                < similarity_threshold
                for kept in selected
            ):
                selected.append(record)
            if len(selected) == top_k:
                break
        selected_ids = {record.plan_id for record in selected}
        exploration_pool = [
            record for record in ranked if record.plan_id not in selected_ids
        ]
        generator = rng or random.Random()
        random_records = tuple(
            generator.sample(exploration_pool, min(random_k, len(exploration_pool)))
        )
        return ParentSelection(top=tuple(selected), random=random_records)


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    """Return cosine similarity for equal finite vectors."""

    left_values = tuple(float(item) for item in left)
    right_values = tuple(float(item) for item in right)
    if not left_values or len(left_values) != len(right_values):
        raise ValidationError("cosine vectors must be non-empty and equal length")
    left_norm = math.sqrt(sum(item * item for item in left_values))
    right_norm = math.sqrt(sum(item * item for item in right_values))
    if left_norm == 0 or right_norm == 0:
        raise ValidationError("cosine vectors cannot have zero norm")
    return sum(a * b for a, b in zip(left_values, right_values)) / (
        left_norm * right_norm
    )


@dataclass(frozen=True)
class RoundMetaEntry:
    """One experiment-grounded compressed lesson for the FIFO window."""

    round_id: int
    successful_patterns: tuple[str, ...] = ()
    failed_patterns: tuple[str, ...] = ()
    false_positive_patterns: tuple[str, ...] = ()
    false_negative_patterns: tuple[str, ...] = ()
    useful_signals: tuple[str, ...] = ()
    suspicious_signals: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()
    search_implications: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.round_id < 1:
            raise ValidationError("meta entry round_id must be positive")
        for name in (
            "successful_patterns",
            "failed_patterns",
            "false_positive_patterns",
            "false_negative_patterns",
            "useful_signals",
            "suspicious_signals",
            "missing_capabilities",
            "search_implications",
            "evidence_refs",
        ):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))
        if not self.evidence_refs:
            raise ValidationError("round meta entry requires experiment evidence refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "plan_level": {
                "successful_patterns": list(self.successful_patterns),
                "failed_patterns": list(self.failed_patterns),
            },
            "prediction_errors": {
                "false_positive": list(self.false_positive_patterns),
                "false_negative": list(self.false_negative_patterns),
            },
            "signal_observations": {
                "useful": list(self.useful_signals),
                "suspicious": list(self.suspicious_signals),
                "missing_capabilities": list(self.missing_capabilities),
            },
            "search_implications": list(self.search_implications),
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RoundMetaEntry":
        plan_level = dict(data.get("plan_level", {}))
        prediction_errors = dict(data.get("prediction_errors", {}))
        observations = dict(data.get("signal_observations", {}))
        return cls(
            round_id=int(data["round_id"]),
            successful_patterns=tuple(
                str(item) for item in plan_level.get("successful_patterns", ())
            ),
            failed_patterns=tuple(
                str(item) for item in plan_level.get("failed_patterns", ())
            ),
            false_positive_patterns=tuple(
                str(item) for item in prediction_errors.get("false_positive", ())
            ),
            false_negative_patterns=tuple(
                str(item) for item in prediction_errors.get("false_negative", ())
            ),
            useful_signals=tuple(
                str(item) for item in observations.get("useful", ())
            ),
            suspicious_signals=tuple(
                str(item) for item in observations.get("suspicious", ())
            ),
            missing_capabilities=tuple(
                str(item) for item in observations.get("missing_capabilities", ())
            ),
            search_implications=tuple(
                str(item) for item in data.get("search_implications", ())
            ),
            evidence_refs=tuple(str(item) for item in data.get("evidence_refs", ())),
        )


class PlanMetaMemory:
    """One fixed-length FIFO of recent experiment-grounded round reflections."""

    def __init__(
        self,
        maxlen: int = 10,
        entries: Iterable[RoundMetaEntry] = (),
    ) -> None:
        if maxlen < 1:
            raise ValidationError("meta memory maxlen must be positive")
        self.maxlen = maxlen
        self._entries: list[RoundMetaEntry] = []
        for entry in entries:
            self.append(entry)

    @property
    def entries(self) -> tuple[RoundMetaEntry, ...]:
        return tuple(self._entries)

    def append(self, entry: RoundMetaEntry) -> None:
        if self._entries and entry.round_id <= self._entries[-1].round_id:
            raise ValidationError("round meta entries must advance monotonically")
        self._entries.append(entry)
        self._entries = self._entries[-self.maxlen :]


@dataclass(frozen=True)
class EvolutionPriors:
    """Fixed framework prompts H_R, H_P, H_E, and H_U."""

    reflect_round: str
    propose_plan: str
    mine_signal: str
    update_signal: str

    def __post_init__(self) -> None:
        for name in (
            "reflect_round",
            "propose_plan",
            "mine_signal",
            "update_signal",
        ):
            if not str(getattr(self, name)).strip():
                raise ValidationError(f"evolution prior {name} must not be empty")


DEFAULT_EVOLUTION_PRIORS = EvolutionPriors(
    reflect_round=(
        "Reflect only on the supplied completed Information Plan experiments. "
        "Compress repeated plan patterns, prediction errors, Signal observations, "
        "missing capabilities, and testable search implications with evidence refs."
    ),
    propose_plan=(
        "Propose one complete Information Plan S=(B,H_init,H_reflect,H_analyse). "
        "Use the quality-diverse parents and FIFO experiment lessons, make an "
        "attributable change, and never change labels, datasets, metrics, priors, "
        "runtime guards, or the stable Signal Registry."
    ),
    mine_signal=(
        "Use label-visible Discovery cases and point-in-time Raw Info to contrast "
        "positive cases with matched controls, identify a repeated missing capability, "
        "check the stable Registry, and stage an evidence-traceable candidate Signal."
    ),
    update_signal=(
        "Use committed experiments, actual trajectories, observed-policy statistics, "
        "and Raw Info to diagnose a stable Signal failure and stage an auditable "
        "vNext candidate without overwriting the stable version."
    ),
)


class InformationPlanProposer(Protocol):
    """Conditional candidate sampler called independently for every child."""

    def propose(
        self,
        *,
        round_id: int,
        candidate_index: int,
        candidate_count: int,
        forbidden_plan_ids: tuple[str, ...],
        parents: tuple[InformationPlan, ...],
        meta_info: tuple[RoundMetaEntry, ...],
        prior: str,
    ) -> InformationPlan:
        """Return one complete candidate Plan."""


class PlanCritic(Protocol):
    """Summarizes Plan behavior over its full validation batch."""

    def critique(
        self,
        *,
        plan: InformationPlan,
        trajectories: tuple[ExecutionTrajectory, ...],
        metrics: PlanMetrics,
    ) -> PlanReflection:
        """Return repeated strengths, failures, and next explorations."""


class RoundReflector(Protocol):
    """Applies fixed H_R to new round experiments, never to old meta alone."""

    def reflect(
        self,
        *,
        round_id: int,
        records: tuple[PlanRecord, ...],
        prior: str,
    ) -> RoundMetaEntry:
        """Return one grounded FIFO entry with record evidence refs."""


class PlanEvaluator(Protocol):
    """Evaluates one Plan on label-hidden evolution-validation cases."""

    def evaluate(
        self,
        plan: InformationPlan,
        cases: tuple[EvolutionCase, ...],
        signal_registry: FrozenSignalRegistry,
    ) -> tuple[ExecutionTrajectory, ...]:
        """Return complete trajectories after the persistence/reveal boundary."""


class RuntimePlanEvaluator:
    """Concrete Plan evaluator using the adaptive runtime and a durable sink."""

    def __init__(
        self,
        *,
        raw_info_store: RawInfoStore,
        controller: ResearchController,
        signal_agent: SignalRetrievalAgent,
        predictor: BlindPredictor,
        prediction_root: str | Path,
        trajectory_root: str | Path | None = None,
        limits: RuntimeLimits = RuntimeLimits(),
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
        llm_signal_runner: LLMSignalRunner | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.raw_info_store = raw_info_store
        self.controller = controller
        self.signal_agent = signal_agent
        self.predictor = predictor
        self.prediction_root = Path(prediction_root)
        self.prediction_root.mkdir(parents=True, exist_ok=True)
        self.trajectory_root = (
            Path(trajectory_root)
            if trajectory_root is not None
            else self.prediction_root.parent / "trajectories"
        )
        self.trajectory_root.mkdir(parents=True, exist_ok=True)
        self.limits = limits
        self.deterministic_functions = deterministic_functions
        self.llm_signal_runner = llm_signal_runner
        self.on_progress = on_progress

    def evaluate(
        self,
        plan: InformationPlan,
        cases: tuple[EvolutionCase, ...],
        signal_registry: FrozenSignalRegistry,
    ) -> tuple[ExecutionTrajectory, ...]:
        if not cases:
            raise ValidationError("evolution validation cases must not be empty")
        executor = SignalExecutor(
            signal_registry,
            self.raw_info_store,
            deterministic_functions=self.deterministic_functions,
            llm_runner=self.llm_signal_runner,
        )
        trajectories: list[ExecutionTrajectory] = []
        for case_index, case in enumerate(cases, start=1):
            case_path = self.prediction_root / plan.plan_id / f"{case.case_id}.json"
            trajectory_path = (
                self.trajectory_root / plan.plan_id / f"{case.case_id}.json"
            )
            input_hash = _canonical_hash(
                {
                    "schema_version": "execution-trajectory-input-v1",
                    "plan": plan.to_dict(),
                    "case": {
                        "case_id": case.case_id,
                        "company_id": case.company_id,
                        "prediction_time": case.prediction_time.isoformat(),
                        "basic_info": dict(case.basic_info),
                        "ground_truth": case.ground_truth.to_dict(),
                    },
                    "signal_registry_hash": signal_registry.registry_hash,
                    "runtime_limits": self.limits.to_dict(),
                }
            )
            if trajectory_path.exists():
                staged = _read_json(trajectory_path)
                if (
                    staged.get("schema_version")
                    != "execution-trajectory-checkpoint-v1"
                    or staged.get("input_hash") != input_hash
                ):
                    raise ValidationError(
                        f"conflicting staged execution trajectory: {trajectory_path}"
                    )
                trajectory = ExecutionTrajectory.from_dict(
                    dict(staged.get("trajectory", {}))
                )
                if trajectory.case_id != case.case_id:
                    raise ValidationError("staged execution trajectory case mismatch")
                trajectories.append(trajectory)
                _emit_progress(
                    self.on_progress,
                    "case_trajectory_reused",
                    plan_id=plan.plan_id,
                    case_id=case.case_id,
                    case_index=case_index,
                    case_count=len(cases),
                    trajectory_path=str(trajectory_path),
                )
                continue

            _emit_progress(
                self.on_progress,
                "case_started",
                plan_id=plan.plan_id,
                case_id=case.case_id,
                case_index=case_index,
                case_count=len(cases),
            )

            def sink(
                company_id: str,
                prediction_time: datetime,
                final_context: Mapping[str, Any],
                prediction: BlindPrediction,
                *,
                path: Path = case_path,
                expected_case_id: str = case.case_id,
            ) -> str:
                _write_or_verify_json(
                    path,
                    {
                        "case_id": expected_case_id,
                        "company_id": company_id,
                        "prediction_time": prediction_time.isoformat(),
                        "final_context": dict(final_context),
                        "prediction": prediction.to_dict(),
                    },
                )
                return str(path)

            def truth_provider(
                company_id: str,
                *,
                path: Path = case_path,
                expected_company_id: str = case.company_id,
                truth: GroundTruth = case.ground_truth,
            ) -> GroundTruth:
                if not path.exists():
                    raise ValidationError("ground truth requested before prediction persistence")
                if company_id != expected_company_id:
                    raise ValidationError("ground truth requested for the wrong case")
                return truth

            trajectory = execute_information_plan(
                plan=plan,
                company_id=case.company_id,
                case_id=case.case_id,
                company_basic_source=case.basic_info,
                prediction_time=case.prediction_time,
                signal_registry=signal_registry,
                signal_executor=executor,
                controller=self.controller,
                signal_agent=self.signal_agent,
                predictor=self.predictor,
                prediction_sink=sink,
                ground_truth_provider=truth_provider,
                limits=self.limits,
            )
            _write_or_verify_json(
                trajectory_path,
                {
                    "schema_version": "execution-trajectory-checkpoint-v1",
                    "input_hash": input_hash,
                    "plan_id": plan.plan_id,
                    "case_id": case.case_id,
                    "trajectory": trajectory.to_dict(),
                },
            )
            trajectories.append(trajectory)
            _emit_progress(
                self.on_progress,
                "case_completed",
                plan_id=plan.plan_id,
                case_id=case.case_id,
                case_index=case_index,
                case_count=len(cases),
                stop_reason=trajectory.stop_reason.value,
                signal_rounds=trajectory.usage.signal_rounds,
                signal_calls=trajectory.usage.signal_calls,
                llm_calls=trajectory.usage.model.llm_calls,
                tokens=trajectory.usage.model.tokens,
                cost=trajectory.usage.model.cost,
                trajectory_path=str(trajectory_path),
            )
        return tuple(trajectories)


class EvolutionWorkspace:
    """Atomic committed-round persistence and recovery boundary."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.plans_root = self.root / "plans"
        self.experiments_root = self.root / "experiments"
        self.meta_root = self.root / "meta"
        self.cache_root = self.root / "cache"
        self.trajectory_root = self.experiments_root / "trajectories"
        for path in (
            self.plans_root,
            self.experiments_root,
            self.meta_root,
            self.cache_root,
            self.trajectory_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            _atomic_write_json(self.state_path, {"last_completed_round": 0})
        self._event_sequence = _last_event_sequence(self.trajectory_events_path)

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @property
    def cycle_state_path(self) -> Path:
        return self.root / "cycle_state.json"

    @property
    def trajectory_events_path(self) -> Path:
        return self.experiments_root / "trajectory.jsonl"

    @property
    def last_completed_round(self) -> int:
        return int(_read_json(self.state_path).get("last_completed_round", 0))

    @property
    def last_completed_cycle(self) -> int:
        if not self.cycle_state_path.exists():
            return 0
        return int(_read_json(self.cycle_state_path).get("last_completed_cycle", 0))

    def append_event(
        self,
        event_type: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one diagnostic event; never use it as completion authority."""

        normalized_type = str(event_type).strip()
        if not normalized_type:
            raise ValidationError("evolution event type must not be empty")
        self._event_sequence += 1
        event = {
            **dict(details or {}),
            "schema_version": "evolution-trajectory-event-v1",
            "sequence": self._event_sequence,
            "at": datetime.now(timezone.utc).isoformat(),
            "event_type": normalized_type,
        }
        self.trajectory_events_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        with self.trajectory_events_path.open("a+b") as handle:
            if handle.tell() > 0:
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) != b"\n":
                    handle.write(b"\n")
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        return event

    def load_events(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Load valid append-only debug events, optionally retaining the tail."""

        if limit is not None and limit < 1:
            raise ValidationError("evolution event limit must be positive")
        if not self.trajectory_events_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.trajectory_events_path.read_text(
            encoding="utf-8"
        ).splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(value, dict):
                continue
            events.append(value)
        return events[-limit:] if limit is not None else events

    def start_or_resume_cycle(
        self,
        *,
        run_contract_hash: str,
        target_plan_rounds: int,
    ) -> dict[str, Any]:
        """Freeze or recover one Fast/Slow cycle under the exact run contract."""

        if not run_contract_hash or target_plan_rounds < 1:
            raise ValidationError("cycle contract hash and round target are required")
        if self.cycle_state_path.exists():
            state = _read_json(self.cycle_state_path)
            if state.get("schema_version") != "dual-loop-cycle-state-v1":
                raise ValidationError("unsupported dual-loop cycle state schema")
            if state.get("run_contract_hash") != run_contract_hash:
                raise ValidationError("cycle state run contract mismatch")
        else:
            state = {
                "schema_version": "dual-loop-cycle-state-v1",
                "run_contract_hash": run_contract_hash,
                "last_completed_cycle": 0,
                "active_cycle": None,
            }
        active = state.get("active_cycle")
        resumed = isinstance(active, Mapping)
        if not resumed:
            active = {
                "cycle_id": int(state.get("last_completed_cycle", 0)) + 1,
                "start_round": self.last_completed_round,
                "target_plan_rounds": target_plan_rounds,
                "completed_plan_rounds": 0,
                "phase": "fast_loop",
            }
        else:
            active = dict(active)
            if int(active.get("target_plan_rounds", 0)) != target_plan_rounds:
                raise ValidationError("active cycle round target mismatch")
        start_round = int(active.get("start_round", -1))
        completed = self.last_completed_round - start_round
        if completed < 0 or completed > target_plan_rounds:
            raise ValidationError("committed round pointer conflicts with active cycle")
        active["completed_plan_rounds"] = completed
        active["phase"] = (
            "slow_loop" if completed == target_plan_rounds else "fast_loop"
        )
        state["active_cycle"] = active
        _atomic_write_json(self.cycle_state_path, state)
        return {**active, "resumed": resumed}

    def mark_cycle_phase(self, phase: str) -> None:
        if phase not in {"fast_loop", "slow_loop"}:
            raise ValidationError("invalid dual-loop cycle phase")
        state = _read_json(self.cycle_state_path)
        active = state.get("active_cycle")
        if not isinstance(active, Mapping):
            raise ValidationError("no active dual-loop cycle")
        active = dict(active)
        active["completed_plan_rounds"] = (
            self.last_completed_round - int(active["start_round"])
        )
        active["phase"] = phase
        state["active_cycle"] = active
        _atomic_write_json(self.cycle_state_path, state)

    def staged_slow_result(self, cycle_id: int) -> dict[str, Any] | None:
        path = self._slow_result_path(cycle_id)
        if not path.exists():
            return None
        payload = _read_json(path)
        cycle_state = _read_json(self.cycle_state_path)
        if (
            payload.get("schema_version") != "dual-loop-slow-result-v1"
            or int(payload.get("cycle_id", 0)) != cycle_id
            or payload.get("run_contract_hash")
            != cycle_state.get("run_contract_hash")
        ):
            raise ValidationError("staged Slow-loop result identity mismatch")
        return dict(payload.get("result", {}))

    def stage_slow_result(
        self,
        *,
        cycle_id: int,
        result: Mapping[str, Any],
    ) -> Path:
        path = self._slow_result_path(cycle_id)
        cycle_state = _read_json(self.cycle_state_path)
        _write_or_verify_json(
            path,
            {
                "schema_version": "dual-loop-slow-result-v1",
                "cycle_id": cycle_id,
                "run_contract_hash": cycle_state.get("run_contract_hash"),
                "result": dict(result),
            },
        )
        return path

    def complete_cycle(self, *, cycle_id: int) -> None:
        """Advance the cycle pointer only after Fast rounds and Slow result exist."""

        state = _read_json(self.cycle_state_path)
        active = state.get("active_cycle")
        if not isinstance(active, Mapping) or int(active.get("cycle_id", 0)) != cycle_id:
            raise ValidationError("active dual-loop cycle identity mismatch")
        target = int(active["target_plan_rounds"])
        expected_round = int(active["start_round"]) + target
        if self.last_completed_round != expected_round:
            raise ValidationError("cannot complete cycle before all Fast rounds")
        slow_path = self._slow_result_path(cycle_id)
        if not slow_path.exists():
            raise ValidationError("cannot complete cycle without staged Slow result")
        self.staged_slow_result(cycle_id)
        state.update(
            {
                "last_completed_cycle": cycle_id,
                "last_completed_round": self.last_completed_round,
                "last_cycle_ref": str(slow_path),
                "active_cycle": None,
            }
        )
        _atomic_write_json(self.cycle_state_path, state)

    def _slow_result_path(self, cycle_id: int) -> Path:
        if cycle_id < 1:
            raise ValidationError("cycle id must be positive")
        return (
            self.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_result.json"
        )

    def commit_round(
        self,
        *,
        round_id: int,
        records: tuple[PlanRecord, ...],
        meta_entry: RoundMetaEntry,
        signal_registry_hash: str,
        run_contract_hash: str = "",
    ) -> None:
        """Write or verify exact staged artifacts, then advance one pointer last."""

        expected = self.last_completed_round + 1
        if round_id != expected:
            raise ValidationError(
                f"round commit must advance from {expected - 1} to {expected}"
            )
        if not records or any(record.round_id != round_id for record in records):
            raise ValidationError("round commit requires records from the same round")
        if meta_entry.round_id != round_id:
            raise ValidationError("round meta entry does not match committed round")
        plan_ids = [record.plan_id for record in records]
        if len(set(plan_ids)) != len(plan_ids):
            raise ValidationError("round cannot commit duplicate plan ids")

        for record in records:
            path = self.plans_root / record.plan_id / "record.json"
            _write_or_verify_json(path, record.to_dict())
        _write_or_verify_json(
            self.meta_root / f"round-{round_id:04d}.json",
            meta_entry.to_dict(),
        )
        checkpoint_path = (
            self.experiments_root / f"round-{round_id:04d}" / "checkpoint.json"
        )
        _write_or_verify_json(
            checkpoint_path,
            {
                "round_id": round_id,
                "plan_ids": plan_ids,
                "meta_ref": str(
                    self.meta_root / f"round-{round_id:04d}.json"
                ),
                "signal_registry_hash": signal_registry_hash,
                "run_contract_hash": run_contract_hash,
            },
        )
        _atomic_write_json(
            self.state_path,
            {
                "last_completed_round": round_id,
                "checkpoint_ref": str(checkpoint_path),
            },
        )

    def restore_archive(self, *, expected_run_contract_hash: str | None = None) -> PlanArchive:
        """Load only Plans reachable from authoritative completed checkpoints."""

        records: list[PlanRecord] = []
        for round_id in range(1, self.last_completed_round + 1):
            checkpoint = _read_json(
                self.experiments_root
                / f"round-{round_id:04d}"
                / "checkpoint.json"
            )
            if int(checkpoint["round_id"]) != round_id:
                raise ValidationError("round checkpoint identity mismatch")
            if (
                expected_run_contract_hash is not None
                and checkpoint.get("run_contract_hash") != expected_run_contract_hash
            ):
                raise ValidationError("round checkpoint run contract mismatch")
            for plan_id in checkpoint.get("plan_ids", ()):
                records.append(
                    PlanRecord.from_dict(
                        _read_json(self.plans_root / str(plan_id) / "record.json")
                    )
                )
        return PlanArchive(records)

    def restore_meta(self, *, maxlen: int = 10) -> PlanMetaMemory:
        entries = [
            RoundMetaEntry.from_dict(
                _read_json(self.meta_root / f"round-{round_id:04d}.json")
            )
            for round_id in range(1, self.last_completed_round + 1)
        ]
        return PlanMetaMemory(maxlen=maxlen, entries=entries)

    def load_experiment_records(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return committed summaries for the Signal Update Agent."""

        if limit < 1:
            raise ValidationError("experiment record limit must be positive")
        records = self.restore_archive().records[-limit:]
        return [
            {
                "plan_id": record.plan_id,
                "round_id": record.round_id,
                "metrics": record.metrics.to_dict(),
                "reflection": record.reflection.to_dict(),
                "signal_usage": {
                    ref: dict(counts) for ref, counts in record.signal_usage.items()
                },
            }
            for record in records
        ]


@dataclass(frozen=True)
class PlanRoundResult:
    """One fully committed fast-loop round."""

    round_id: int
    parents: tuple[InformationPlan, ...]
    records: tuple[PlanRecord, ...]
    meta_entry: RoundMetaEntry


class PlanEvolutionEngine:
    """Bounded Information Plan Fast Loop under a frozen Signal Registry."""

    def __init__(
        self,
        *,
        archive: PlanArchive,
        meta_memory: PlanMetaMemory,
        signal_registry: SignalRegistry,
        evaluator: PlanEvaluator,
        proposer: InformationPlanProposer,
        critic: PlanCritic,
        round_reflector: RoundReflector,
        workspace: EvolutionWorkspace,
        seed_plans: tuple[InformationPlan, ...],
        priors: EvolutionPriors = DEFAULT_EVOLUTION_PRIORS,
        embedder: PlanEmbedder | None = None,
        candidates_per_round: int = 3,
        top_k: int = 3,
        random_k: int = 2,
        similarity_threshold: float = 0.9,
        rng: random.Random | None = None,
        run_contract_hash: str = "",
        on_progress: ProgressCallback | None = None,
    ) -> None:
        if candidates_per_round < 1:
            raise ValidationError("candidates_per_round must be positive")
        if not seed_plans:
            raise ValidationError("plan evolution requires at least one seed Plan")
        self.archive = archive
        self.meta_memory = meta_memory
        self.signal_registry = signal_registry
        self.evaluator = evaluator
        self.proposer = proposer
        self.critic = critic
        self.round_reflector = round_reflector
        self.workspace = workspace
        self.seed_plans = tuple(seed_plans)
        self.priors = priors
        self.embedder = embedder or HashingPlanEmbedder()
        self.candidates_per_round = candidates_per_round
        self.top_k = top_k
        self.random_k = random_k
        self.similarity_threshold = similarity_threshold
        self.rng = rng or random.Random()
        self.run_contract_hash = run_contract_hash
        self.on_progress = on_progress
        for committed_record in self.archive.records:
            self._record_signal_statistics(committed_record)

    def run_round(
        self,
        *,
        round_id: int,
        validation_cases: tuple[EvolutionCase, ...],
        signal_snapshot: FrozenSignalRegistry,
    ) -> PlanRoundResult:
        """Sample N independent Plans, evaluate, critique, archive, and reflect."""

        if round_id != self.workspace.last_completed_round + 1:
            raise ValidationError("fast-loop round id does not follow committed state")
        _emit_progress(
            self.on_progress,
            "round_started",
            round_id=round_id,
            candidate_count=self.candidates_per_round,
            validation_case_count=len(validation_cases),
        )
        selection = self.archive.select_parents(
            top_k=self.top_k,
            random_k=self.random_k,
            similarity_threshold=self.similarity_threshold,
            rng=self.rng,
        )
        parents = selection.plans or self.seed_plans
        _emit_progress(
            self.on_progress,
            "parents_selected",
            round_id=round_id,
            top_parent_ids=[record.plan_id for record in selection.top],
            random_parent_ids=[record.plan_id for record in selection.random],
            seed_parent_ids=(
                [plan.plan_id for plan in self.seed_plans]
                if not selection.plans
                else []
            ),
        )
        allowed_parent_ids = {plan.plan_id for plan in parents}
        candidate_plans: list[InformationPlan] = []
        for candidate_index in range(1, self.candidates_per_round + 1):
            _emit_progress(
                self.on_progress,
                "candidate_proposal_started",
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=self.candidates_per_round,
            )
            candidate = self.proposer.propose(
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=self.candidates_per_round,
                forbidden_plan_ids=tuple(
                    sorted(
                        {
                            *(record.plan_id for record in self.archive.records),
                            *(plan.plan_id for plan in candidate_plans),
                        }
                    )
                ),
                parents=parents,
                meta_info=self.meta_memory.entries,
                prior=self.priors.propose_plan,
            )
            if candidate.plan_id in {plan.plan_id for plan in candidate_plans}:
                raise ValidationError("proposer returned duplicate Plan ids in one round")
            if candidate.plan_id in {record.plan_id for record in self.archive.records}:
                raise ValidationError("proposer reused an archived Plan id")
            if not candidate.parent_ids or not set(candidate.parent_ids).issubset(
                allowed_parent_ids
            ):
                raise ValidationError(
                    "candidate parent_ids must cite only selected parent Plans"
                )
            candidate_plans.append(candidate)
            _emit_progress(
                self.on_progress,
                "candidate_proposed",
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=self.candidates_per_round,
                plan_id=candidate.plan_id,
                parent_ids=list(candidate.parent_ids),
                plan_summary=summarize_information_plan(candidate),
            )

        records: list[PlanRecord] = []
        for candidate_index, plan in enumerate(candidate_plans, start=1):
            _emit_progress(
                self.on_progress,
                "candidate_evaluation_started",
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=len(candidate_plans),
                plan_id=plan.plan_id,
            )
            trajectories = self.evaluator.evaluate(
                plan,
                validation_cases,
                signal_snapshot,
            )
            metrics = score_predictions(trajectories)
            _emit_progress(
                self.on_progress,
                "candidate_scored",
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=len(candidate_plans),
                plan_id=plan.plan_id,
                metrics=metrics.to_dict(),
                trajectory_count=len(trajectories),
            )
            reflection = self.critic.critique(
                plan=plan,
                trajectories=trajectories,
                metrics=metrics,
            )
            records.append(
                PlanRecord(
                    plan=plan,
                    round_id=round_id,
                    embedding=self.embedder.embed(plan),
                    metrics=metrics,
                    reflection=reflection,
                    signal_usage=collect_signal_usage(trajectories),
                    trajectories=trajectories,
                )
            )

        record_tuple = tuple(records)
        meta_entry = self.round_reflector.reflect(
            round_id=round_id,
            records=record_tuple,
            prior=self.priors.reflect_round,
        )
        expected_refs = {record.plan_id for record in record_tuple}
        if not set(meta_entry.evidence_refs).issubset(expected_refs):
            raise ValidationError("round meta entry cites evidence outside new experiments")
        _emit_progress(
            self.on_progress,
            "round_commit_started",
            round_id=round_id,
            plan_ids=[record.plan_id for record in record_tuple],
        )
        self.workspace.commit_round(
            round_id=round_id,
            records=record_tuple,
            meta_entry=meta_entry,
            signal_registry_hash=signal_snapshot.registry_hash,
            run_contract_hash=self.run_contract_hash,
        )
        for record in record_tuple:
            self.archive.add(record)
            self._record_signal_statistics(record)
        self.meta_memory.append(meta_entry)
        current_top = self.archive.select_parents(
            top_k=self.top_k,
            random_k=0,
            similarity_threshold=self.similarity_threshold,
            rng=self.rng,
        ).top
        _emit_progress(
            self.on_progress,
            "round_committed",
            round_id=round_id,
            plan_ids=[record.plan_id for record in record_tuple],
            candidate_scores=[
                {
                    "plan_id": record.plan_id,
                    "binary_f1": record.metrics.binary_f1,
                    "binary_precision": record.metrics.binary_precision,
                    "binary_recall": record.metrics.binary_recall,
                }
                for record in record_tuple
            ],
            top_k=[
                {
                    "plan_id": record.plan_id,
                    "binary_f1": record.metrics.binary_f1,
                }
                for record in current_top
            ],
            checkpoint_ref=str(
                self.workspace.experiments_root
                / f"round-{round_id:04d}"
                / "checkpoint.json"
            ),
        )
        return PlanRoundResult(
            round_id=round_id,
            parents=parents,
            records=record_tuple,
            meta_entry=meta_entry,
        )

    def _record_signal_statistics(self, record: PlanRecord) -> None:
        for trajectory in record.trajectories:
            for round_index, signal_round in enumerate(trajectory.signal_rounds):
                for result_index, result in enumerate(signal_round.batch.results):
                    observation_id = ":".join(
                        (
                            record.plan_id,
                            trajectory.case_id,
                            str(round_index),
                            str(result_index),
                            result.ref,
                        )
                    )
                    self.signal_registry.record_observation(
                        observation_id,
                        result,
                        is_surge=trajectory.ground_truth.is_surge,
                    )


def collect_signal_usage(
    trajectories: Iterable[ExecutionTrajectory],
) -> dict[str, dict[str, int]]:
    """Count actual selected canonical states, not mere Plan membership."""

    usage: dict[str, dict[str, int]] = {}
    for trajectory in trajectories:
        for signal_round in trajectory.signal_rounds:
            for result in signal_round.batch.results:
                counts = usage.setdefault(
                    result.ref,
                    {value.value: 0 for value in SignalValue},
                )
                counts[result.value.value] += 1
    return usage


@dataclass(frozen=True)
class SignalCandidateValidation:
    """Fail-closed validation result before stable Signal promotion."""

    signal_ref: str
    accepted: bool
    reasons: tuple[str, ...]
    candidate_hash: str = ""
    executed_tests: int = 0


class SignalCandidateValidator:
    """Validate schema, executability, leakage, evidence, and uniqueness."""

    def __init__(
        self,
        registry: SignalRegistry,
        *,
        llm_runner: LLMSignalRunner | None,
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
        forbidden_identity_terms: Iterable[str] = (),
    ) -> None:
        self.registry = registry
        self.llm_runner = llm_runner
        self.deterministic_functions = {
            **default_deterministic_signal_functions(),
            **dict(deterministic_functions or {}),
        }
        self.forbidden_identity_terms = tuple(
            sorted(
                {
                    str(item).strip()
                    for item in forbidden_identity_terms
                    if len(str(item).strip()) >= 3
                },
                key=len,
                reverse=True,
            )
        )

    def validate(
        self,
        spec: SignalSpec,
        *,
        skill: str | None,
        tests: Iterable[Mapping[str, Any]],
    ) -> SignalCandidateValidation:
        reasons: list[str] = []
        materialized_tests = tuple(dict(item) for item in tests)
        try:
            current = self.registry.latest_spec(spec.signal_id)
        except ValidationError:
            current = None
        if current is None and spec.version != 1:
            reasons.append("new signal must start at version 1")
        if current is not None and spec.version != current.version + 1:
            reasons.append("update must use exactly the next stable version")
        if spec.execution_type is SignalExecutionType.DETERMINISTIC:
            if spec.function not in self.deterministic_functions:
                reasons.append("deterministic function is not registered")
        elif self.llm_runner is None or not (skill or "").strip():
            reasons.append("LLM executor or skill is unavailable")
        if not all(
            (
                spec.evidence_policy.require_source,
                spec.evidence_policy.require_timestamp,
                spec.evidence_policy.require_exact_span,
            )
        ):
            reasons.append("candidate weakens required evidence traceability")
        serialized = json.dumps(spec.to_dict(), sort_keys=True).casefold()
        serialized += " " + (skill or "").casefold()
        serialized += " " + json.dumps(materialized_tests, sort_keys=True).casefold()
        for phrase in (
            "ground truth",
            "outcome label",
            "realized return",
            "future price",
            "post-outcome",
        ):
            if phrase in serialized:
                reasons.append(f"obvious leakage phrase: {phrase}")
        for identity in self.forbidden_identity_terms:
            if re.search(
                rf"(?<![a-z0-9]){re.escape(identity.casefold())}(?![a-z0-9])",
                serialized,
            ):
                reasons.append(f"discovery identity leaked into candidate: {identity}")
        normalized = _normalize_semantics(spec.description)
        for card in self.registry.list_signal_cards():
            if card.signal_id == spec.signal_id:
                continue
            if _normalize_semantics(card.description) == normalized:
                reasons.append(f"semantic duplicate of stable signal {card.signal_id}")
                break
        executed_tests = 0
        if not materialized_tests:
            reasons.append("candidate requires non-empty executable fixtures")
        elif not reasons:
            for index, fixture in enumerate(materialized_tests):
                try:
                    self._execute_fixture(spec, skill, fixture, index=index)
                    executed_tests += 1
                except (ValidationError, KeyError, TypeError, ValueError) as exc:
                    reasons.append(f"fixture {index + 1} failed: {exc}")
        return SignalCandidateValidation(
            signal_ref=spec.ref,
            accepted=not reasons,
            reasons=tuple(reasons),
            executed_tests=executed_tests,
        )

    def _execute_fixture(
        self,
        spec: SignalSpec,
        skill: str | None,
        fixture: Mapping[str, Any],
        *,
        index: int,
    ) -> None:
        name = str(fixture.get("name", "")).strip()
        if not name:
            raise ValidationError("fixture name is required")
        expected = SignalValue(str(fixture["expected"]))
        as_of = datetime.fromisoformat(
            str(fixture.get("as_of", "2025-01-01T00:00:00+00:00"))
        )
        _require_aware_datetime(as_of, "candidate fixture as_of")
        company_id = str(fixture.get("company_id", f"candidate_fixture_{index + 1}"))
        _validate_id(company_id, "candidate fixture company_id")
        documents_data = fixture.get("documents")
        if not isinstance(documents_data, list) or not documents_data:
            raise ValidationError("fixture requires point-in-time documents")
        documents: list[RawInfoDocument] = []
        for document_index, raw_document in enumerate(documents_data):
            if not isinstance(raw_document, Mapping):
                raise ValidationError("fixture document must be an object")
            published_at = datetime.fromisoformat(
                str(raw_document.get("published_at", as_of.isoformat()))
            )
            available_at = datetime.fromisoformat(
                str(raw_document.get("available_at", published_at.isoformat()))
            )
            source_type = str(raw_document["source_type"])
            if source_type not in spec.source_types:
                raise ValidationError("fixture source_type is outside candidate retrieval")
            documents.append(
                RawInfoDocument.create(
                    document_id=str(
                        raw_document.get(
                            "document_id",
                            f"candidate_fixture_{index + 1}_{document_index + 1}",
                        )
                    ),
                    company_id=company_id,
                    source_type=source_type,
                    published_at=published_at,
                    available_at=available_at,
                    content=str(raw_document["content"]),
                    metadata=dict(raw_document.get("metadata", {})),
                )
            )
        snapshot_payload = {
            "spec": spec.to_dict(),
            "skill": (skill or "").rstrip(),
        }
        snapshot_hash = hashlib.sha256(
            json.dumps(snapshot_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        executor = SignalExecutor(
            FrozenSignalRegistry(
                version=0,
                registry_hash=snapshot_hash,
                specs=(spec,),
                skills=({spec.ref: skill} if skill is not None else {}),
            ),
            RawInfoStore(documents=documents),
            deterministic_functions=self.deterministic_functions,
            llm_runner=self.llm_runner,
        )
        result = executor.execute_batch(
            (spec.ref,), company_id=company_id, as_of=as_of
        ).results[0]
        if result.value is not expected:
            raise ValidationError(
                f"expected {expected.value}, received {result.value.value}"
            )


@dataclass(frozen=True)
class SlowLoopResult:
    """Staged, validated, and promoted Signal slow-loop outcome."""

    mined_candidates: tuple[str, ...]
    updated_candidates: tuple[str, ...]
    promoted: tuple[str, ...]
    validated_pending_approval: Mapping[str, str]
    rejected: Mapping[str, tuple[str, ...]]
    registry_version: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "mined_candidates": list(self.mined_candidates),
            "updated_candidates": list(self.updated_candidates),
            "promoted": list(self.promoted),
            "validated_pending_approval": dict(
                self.validated_pending_approval
            ),
            "rejected": {
                ref: list(reasons) for ref, reasons in self.rejected.items()
            },
            "registry_version": self.registry_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SlowLoopResult":
        return cls(
            mined_candidates=tuple(
                str(item) for item in data.get("mined_candidates", ())
            ),
            updated_candidates=tuple(
                str(item) for item in data.get("updated_candidates", ())
            ),
            promoted=tuple(str(item) for item in data.get("promoted", ())),
            validated_pending_approval={
                str(ref): str(candidate_hash)
                for ref, candidate_hash in dict(
                    data.get("validated_pending_approval", {})
                ).items()
            },
            rejected={
                str(ref): tuple(str(reason) for reason in reasons)
                for ref, reasons in dict(data.get("rejected", {})).items()
            },
            registry_version=int(data.get("registry_version", 0)),
        )


class SignalEvolutionEngine:
    """Generic-Agent Signal Mining and Signal Update Slow Loop."""

    def __init__(
        self,
        *,
        registry: SignalRegistry,
        raw_info_store: RawInfoStore,
        discovery_cases: tuple[EvolutionCase, ...],
        meta_memory: PlanMetaMemory,
        workspace: EvolutionWorkspace,
        mining_agent: GenericAgent,
        update_agent: GenericAgent,
        llm_signal_runner: LLMSignalRunner | None,
        priors: EvolutionPriors = DEFAULT_EVOLUTION_PRIORS,
        max_agent_steps: int = 20,
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
    ) -> None:
        if not discovery_cases:
            raise ValidationError("Signal evolution requires label-visible Discovery cases")
        self.registry = registry
        self.raw_info_store = raw_info_store
        self.discovery_cases = discovery_cases
        self.meta_memory = meta_memory
        self.workspace = workspace
        self.mining_agent = mining_agent
        self.update_agent = update_agent
        self.llm_signal_runner = llm_signal_runner
        self.priors = priors
        self.max_agent_steps = max_agent_steps
        self.validator = SignalCandidateValidator(
            registry,
            llm_runner=llm_signal_runner,
            deterministic_functions=deterministic_functions,
            forbidden_identity_terms=_discovery_identity_terms(discovery_cases),
        )

    def run_cycle(self) -> SlowLoopResult:
        """Stage all candidates, validate as a batch, then version-promote."""

        mined: list[str] = []
        updated: list[str] = []
        mining_tools = self._mining_tools(mined)
        update_tools = self._update_tools(updated)
        mining_result = self.mining_agent.run(
            prompt=self.priors.mine_signal,
            tools=mining_tools,
            workspace=self._agent_workspace(),
            output_schema=_candidate_refs_schema,
            max_steps=self.max_agent_steps,
        )
        update_result = self.update_agent.run(
            prompt=self.priors.update_signal,
            tools=update_tools,
            workspace=self._agent_workspace(),
            output_schema=_candidate_refs_schema,
            max_steps=self.max_agent_steps,
        )
        mined = _ordered_unique([*mined, *mining_result.value])
        updated = _ordered_unique([*updated, *update_result.value])
        all_refs = _ordered_unique([*mined, *updated])

        validations: dict[str, SignalCandidateValidation] = {}
        accepted_hashes: dict[str, str] = {}
        semantic_seen: dict[str, str] = {}
        for signal_ref in all_refs:
            spec, skill = self.registry.load_candidate(signal_ref)
            tests = self.registry.load_candidate_tests(signal_ref)
            candidate_hash = self.registry.candidate_hash(signal_ref)
            validation = self.validator.validate(spec, skill=skill, tests=tests)
            validation = SignalCandidateValidation(
                signal_ref=validation.signal_ref,
                accepted=validation.accepted,
                reasons=validation.reasons,
                candidate_hash=candidate_hash,
                executed_tests=validation.executed_tests,
            )
            semantic = _normalize_semantics(spec.description)
            prior_ref = semantic_seen.get(semantic)
            if validation.accepted and prior_ref is not None:
                validation = SignalCandidateValidation(
                    signal_ref=signal_ref,
                    accepted=False,
                    reasons=(f"semantic duplicate of candidate {prior_ref}",),
                    candidate_hash=candidate_hash,
                    executed_tests=validation.executed_tests,
                )
            if validation.accepted:
                semantic_seen[semantic] = signal_ref
                accepted_hashes[signal_ref] = candidate_hash
            validations[signal_ref] = validation
            self.registry.record_candidate_validation(
                signal_ref,
                candidate_hash=candidate_hash,
                accepted=validation.accepted,
                reasons=validation.reasons,
            )
        return SlowLoopResult(
            mined_candidates=tuple(mined),
            updated_candidates=tuple(updated),
            promoted=(),
            validated_pending_approval=accepted_hashes,
            rejected={
                signal_ref: validation.reasons
                for signal_ref, validation in validations.items()
                if not validation.accepted
            },
            registry_version=self.registry.version,
        )

    def promote_approved(
        self,
        pending: SlowLoopResult,
        *,
        approvals: Mapping[str, str],
        approved_by: str,
    ) -> SlowLoopResult:
        """Promote only caller-selected refs whose reviewed hashes are exact."""

        if not approvals:
            raise ValidationError("promotion requires at least one explicit approval")
        unknown = set(approvals) - set(pending.validated_pending_approval)
        if unknown:
            raise ValidationError(
                "approval contains non-validated candidate refs: "
                + ", ".join(sorted(unknown))
            )
        promoted: list[str] = []
        for signal_ref, expected_hash in approvals.items():
            if pending.validated_pending_approval[signal_ref] != expected_hash:
                raise ValidationError("approval hash differs from validation result")
            self.registry.approve_candidate(
                signal_ref,
                expected_candidate_hash=expected_hash,
                approved_by=approved_by,
            )
            self.registry.promote_candidate(signal_ref)
            promoted.append(signal_ref)
        if promoted:
            self.registry.bump_version()
        return SlowLoopResult(
            mined_candidates=pending.mined_candidates,
            updated_candidates=pending.updated_candidates,
            promoted=tuple(promoted),
            validated_pending_approval={
                ref: value
                for ref, value in pending.validated_pending_approval.items()
                if ref not in approvals
            },
            rejected=pending.rejected,
            registry_version=self.registry.version,
        )

    def _agent_workspace(self) -> dict[str, Any]:
        return {
            "meta_info": [entry.to_dict() for entry in self.meta_memory.entries],
            "signal_registry_version": self.registry.version,
            "last_completed_plan_round": self.workspace.last_completed_round,
            "dataset_role": "discovery",
            "locked_test_available": False,
        }

    def _mining_tools(self, collected: list[str]) -> list[DomainTool]:
        return [
            DomainTool(
                "list_signal_categories",
                "List stable Signal categories without loading full specs.",
                lambda: list(self.registry.list_categories()),
            ),
            DomainTool(
                "list_signal_cards",
                "List compact Signal cards for one category.",
                lambda category: [
                    card.to_dict()
                    for card in self.registry.list_signal_cards(str(category))
                ],
            ),
            DomainTool(
                "search_signal_cards",
                "Search compact Signal cards by a natural-language query.",
                lambda query: [
                    card.to_dict()
                    for card in self.registry.search_signal_cards(str(query))
                ],
            ),
            DomainTool(
                "load_signal_spec",
                "Load one exact stable SignalSpec after card-level inspection.",
                lambda signal_ref: self.registry.load_spec(str(signal_ref)).to_dict(),
            ),
            DomainTool(
                "sample_discovery_cases",
                "Read label-visible Discovery cases for contrastive analysis.",
                lambda limit=10: [
                    case.to_discovery_dict()
                    for case in self.discovery_cases[: int(limit)]
                ],
            ),
            DomainTool(
                "search_raw_info",
                "Search point-in-time Raw Info for one exact Discovery case.",
                self._search_raw_info_tool,
            ),
            DomainTool(
                "load_raw_document",
                "Load one document under one exact Discovery case cutoff.",
                self._load_discovery_raw_document,
            ),
            DomainTool(
                "create_candidate_signal",
                "Stage one complete candidate SignalSpec outside the stable Registry.",
                lambda spec, skill=None, tests=(): self._stage_from_tool(
                    spec=spec,
                    skill=skill,
                    tests=tests,
                    origin="mining",
                    collected=collected,
                ),
            ),
        ]

    def _update_tools(self, collected: list[str]) -> list[DomainTool]:
        return [
            DomainTool(
                "list_signal_categories",
                "List stable Signal categories without loading full specs.",
                lambda: list(self.registry.list_categories()),
            ),
            DomainTool(
                "list_signal_cards",
                "List compact stable Signal cards and observed-policy credit.",
                lambda category: [
                    card.to_dict()
                    for card in self.registry.list_signal_cards(str(category))
                ],
            ),
            DomainTool(
                "load_signal_spec",
                "Load one exact stable SignalSpec for failure diagnosis.",
                lambda signal_ref: self.registry.load_spec(str(signal_ref)).to_dict(),
            ),
            DomainTool(
                "load_experiment_records",
                "Load committed Plan experiment summaries only.",
                lambda limit=100: self.workspace.load_experiment_records(
                    limit=int(limit)
                ),
            ),
            DomainTool(
                "query_signal_usage",
                "Load observed-policy counts for one stable Signal.",
                lambda signal_id: self.registry.load_stats(str(signal_id)).to_dict(),
            ),
            DomainTool(
                "query_signal_failure_cases",
                "Find committed Predictor reflections that name a misleading Signal.",
                self._query_signal_failure_cases,
            ),
            DomainTool(
                "search_raw_info",
                "Search point-in-time Raw Info for one exact Discovery case.",
                self._search_raw_info_tool,
            ),
            DomainTool(
                "clone_signal_version",
                "Stage one complete vNext SignalSpec without overwriting stable files.",
                lambda signal_ref, spec, skill=None, tests=(): self._clone_from_tool(
                    signal_ref=signal_ref,
                    spec=spec,
                    skill=skill,
                    tests=tests,
                    collected=collected,
                ),
            ),
            DomainTool(
                "run_signal_tests",
                "Run local candidate contract checks before final selection.",
                self._run_signal_tests_tool,
            ),
        ]

    def _search_raw_info_tool(
        self,
        case_id: str,
        as_of: str,
        source_types: list[str] | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        cases_by_id = {case.case_id: case for case in self.discovery_cases}
        if case_id not in cases_by_id:
            raise ValidationError("Signal Agent may search only exact Discovery cases")
        case = cases_by_id[case_id]
        requested_as_of = datetime.fromisoformat(as_of)
        _require_aware_datetime(requested_as_of, "raw info tool as_of")
        if requested_as_of > case.prediction_time:
            raise ValidationError(
                "Signal Agent cannot search after the Discovery prediction time"
            )
        return [
            document.to_dict()
            for document in self.raw_info_store.search(
                case.company_id,
                as_of=requested_as_of,
                source_types=source_types,
                query=query,
            )
        ]

    def _load_discovery_raw_document(
        self, case_id: str, document_id: str
    ) -> dict[str, Any]:
        document = self.raw_info_store.load(str(document_id))
        cases_by_id = {case.case_id: case for case in self.discovery_cases}
        try:
            case = cases_by_id[str(case_id)]
        except KeyError as exc:
            raise ValidationError(
                "Signal Agent may load documents only for exact Discovery cases"
            ) from exc
        if document.company_id != case.company_id:
            raise ValidationError("raw document belongs to a different Discovery case")
        return self.raw_info_store.load(
            document.document_id,
            as_of=case.prediction_time,
        ).to_dict()

    def _stage_from_tool(
        self,
        *,
        spec: Mapping[str, Any],
        skill: str | None,
        tests: Iterable[Mapping[str, Any]],
        origin: str,
        collected: list[str],
    ) -> str:
        candidate = SignalSpec.from_dict(dict(spec))
        signal_ref = self.registry.stage_candidate(
            candidate,
            skill=skill,
            tests=tests,
            origin=origin,
        )
        collected.append(signal_ref)
        return signal_ref

    def _clone_from_tool(
        self,
        *,
        signal_ref: str,
        spec: Mapping[str, Any],
        skill: str | None,
        tests: Iterable[Mapping[str, Any]],
        collected: list[str],
    ) -> str:
        stable = self.registry.load_spec(str(signal_ref))
        candidate = SignalSpec.from_dict(dict(spec))
        if candidate.signal_id != stable.signal_id:
            raise ValidationError("cloned Signal must preserve signal_id")
        if candidate.version != stable.version + 1:
            raise ValidationError("cloned Signal must use vNext")
        if skill is None and candidate.execution_type is SignalExecutionType.LLM:
            skill = self.registry.load_skill(stable.ref)
        return self._stage_from_tool(
            spec=candidate.to_dict(),
            skill=skill,
            tests=tests,
            origin=f"update:{stable.ref}",
            collected=collected,
        )

    def _run_signal_tests_tool(self, signal_ref: str) -> dict[str, Any]:
        spec, skill = self.registry.load_candidate(str(signal_ref))
        validation = self.validator.validate(
            spec,
            skill=skill,
            tests=self.registry.load_candidate_tests(str(signal_ref)),
        )
        return {
            "signal_ref": signal_ref,
            "accepted": validation.accepted,
            "reasons": list(validation.reasons),
        }

    def _query_signal_failure_cases(self, signal_id: str) -> list[dict[str, Any]]:
        failures: list[dict[str, Any]] = []
        for record in self.workspace.restore_archive().records:
            for trajectory in record.trajectories:
                if signal_id in trajectory.self_reflection.misleading_signals:
                    failures.append(
                        {
                            "plan_id": record.plan_id,
                            "company_id": trajectory.company_id,
                            "prediction": trajectory.prediction.to_dict(),
                            "ground_truth": trajectory.ground_truth.to_dict(),
                            "self_reflection": trajectory.self_reflection.to_dict(),
                        }
                    )
        return failures


@dataclass(frozen=True)
class DualLoopResult:
    """One finite fast-loop group followed by one Signal slow loop."""

    plan_rounds: tuple[PlanRoundResult, ...]
    signal_evolution: SlowLoopResult


class DualLoopEvolutionEngine:
    """Run a finite Plan group, then allow one validated Signal version change."""

    def __init__(
        self,
        *,
        plan_engine: PlanEvolutionEngine,
        signal_engine: SignalEvolutionEngine,
        signal_registry: SignalRegistry,
        dataset: EvolutionDataset,
        plan_rounds_per_signal_cycle: int = 5,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        if plan_rounds_per_signal_cycle < 1:
            raise ValidationError("plan rounds per Signal cycle must be positive")
        self.plan_engine = plan_engine
        self.signal_engine = signal_engine
        self.signal_registry = signal_registry
        self.dataset = dataset
        self.plan_rounds_per_signal_cycle = plan_rounds_per_signal_cycle
        self.on_progress = on_progress

    def run_cycle(self, *, completed_plan_rounds: int = 0) -> DualLoopResult:
        """Resume remaining Fast rounds, then run one validation-only Slow loop."""

        if not 0 <= completed_plan_rounds <= self.plan_rounds_per_signal_cycle:
            raise ValidationError("completed Fast-round count is outside cycle target")

        snapshot = self.signal_registry.freeze()
        rounds: list[PlanRoundResult] = []
        _emit_progress(
            self.on_progress,
            "fast_loop_started",
            completed_plan_rounds=completed_plan_rounds,
            target_plan_rounds=self.plan_rounds_per_signal_cycle,
            signal_registry_hash=snapshot.registry_hash,
        )
        for _ in range(
            completed_plan_rounds,
            self.plan_rounds_per_signal_cycle,
        ):
            round_id = self.plan_engine.workspace.last_completed_round + 1
            rounds.append(
                self.plan_engine.run_round(
                    round_id=round_id,
                    validation_cases=self.dataset.evolution_validation,
                    signal_snapshot=snapshot,
                )
            )
        if self.signal_registry.version != snapshot.version:
            raise ValidationError("stable Signal definitions changed during fast loop")
        _emit_progress(
            self.on_progress,
            "slow_loop_started",
            completed_plan_rounds=self.plan_rounds_per_signal_cycle,
            target_plan_rounds=self.plan_rounds_per_signal_cycle,
        )
        signal_result = self.signal_engine.run_cycle()
        _emit_progress(
            self.on_progress,
            "slow_loop_completed",
            mined_candidates=list(signal_result.mined_candidates),
            updated_candidates=list(signal_result.updated_candidates),
            validated_pending_approval=dict(
                signal_result.validated_pending_approval
            ),
            rejected={
                ref: list(reasons)
                for ref, reasons in signal_result.rejected.items()
            },
            registry_version=signal_result.registry_version,
        )
        return DualLoopResult(
            plan_rounds=tuple(rounds),
            signal_evolution=signal_result,
        )


def default_information_plan() -> InformationPlan:
    """Return the first manual Plan used to bring up the adaptive runtime."""

    return InformationPlan(
        plan_id="plan_manual_v1",
        parent_ids=(),
        basic_info_policy=BasicInfoPolicy(
            fields=(
                "company_name",
                "ticker",
                "market_cap",
                "industry",
                "business_description",
                "revenue_segments",
                "development_stage",
            )
        ),
        initial_research_skill=(
            "Form an initial commercialization and expectation-gap hypothesis from "
            "Basic Info only, then state the most decision-relevant information needs."
        ),
        reflection_skill=(
            "Reflect over the entire Signal batch. Track support, contradiction, "
            "resolved questions, concentration risk, and the next smallest set of "
            "information needs; finalize only when the surge thesis is decidable."
        ),
        analysis_prompt=(
            "Weigh source-backed supporting and counter evidence, distinguish real "
            "commercial adoption from narrative, and make the two-stage blind forecast."
        ),
    )


def _candidate_refs_schema(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        raise ValidationError("Signal Agent final output must be an object")
    refs = value.get("candidate_refs", ())
    if not isinstance(refs, list):
        raise ValidationError("Signal Agent candidate_refs must be a list")
    parsed = tuple(str(item) for item in refs)
    if len(set(parsed)) != len(parsed):
        raise ValidationError("Signal Agent final candidate refs must be unique")
    return parsed


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _normalize_semantics(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _is_forbidden_basic_info_field(value: str) -> bool:
    normalized = _normalize_field_name(value)
    return normalized in _FORBIDDEN_BASIC_INFO_FIELDS or any(
        normalized.startswith(f"{field}_") or normalized.endswith(f"_{field}")
        for field in _FORBIDDEN_BASIC_INFO_FIELDS
    )


def _discovery_identity_terms(cases: Iterable[EvolutionCase]) -> tuple[str, ...]:
    identity_keys = {
        "company_id",
        "company_name",
        "ticker",
        "symbol",
        "identity_aliases",
    }
    terms: set[str] = set()
    for case in cases:
        terms.add(case.company_id)
        for key, value in case.basic_info.items():
            if key not in identity_keys:
                continue
            if isinstance(value, str):
                terms.add(value)
            elif isinstance(value, Iterable) and not isinstance(value, Mapping):
                terms.update(str(item) for item in value)
    return tuple(sorted((item for item in terms if item.strip()), key=len, reverse=True))


def _default_case_id(company_id: str, prediction_time: datetime) -> str:
    _require_aware_datetime(prediction_time, "prediction_time")
    timestamp = prediction_time.astimezone(timezone.utc).strftime("%Y%m%dt%H%M%sz")
    return f"{company_id}:{timestamp}"


def _mask_identity_values(value: Any, aliases: Iterable[str]) -> Any:
    normalized_aliases = sorted(
        {alias.strip() for alias in aliases if alias and alias.strip()},
        key=len,
        reverse=True,
    )

    def mask(item: Any) -> Any:
        if isinstance(item, str):
            result = item
            for alias in normalized_aliases:
                escaped = re.escape(alias)
                if alias[0].isalnum() and alias[-1].isalnum():
                    pattern = rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
                else:
                    pattern = escaped
                result = re.sub(
                    pattern,
                    "[MASKED_COMPANY]",
                    result,
                    flags=re.IGNORECASE,
                )
            return result
        if isinstance(item, list):
            return [mask(child) for child in item]
        if isinstance(item, tuple):
            return tuple(mask(child) for child in item)
        if isinstance(item, Mapping):
            return {key: mask(child) for key, child in item.items()}
        return item

    return mask(value)


def _validate_id(value: str, name: str) -> None:
    if not _SAFE_ID.fullmatch(value):
        raise ValidationError(f"{name} must use lowercase safe identifier characters")


def _require_aware_datetime(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{name} must be timezone-aware")


def _usage_to_dict(usage: AgentUsage) -> dict[str, Any]:
    return {
        "llm_calls": usage.llm_calls,
        "tokens": usage.tokens,
        "cost": usage.cost,
    }


def _usage_from_dict(data: Mapping[str, Any]) -> AgentUsage:
    return AgentUsage(
        llm_calls=int(data.get("llm_calls", 0)),
        tokens=int(data.get("tokens", 0)),
        cost=float(data.get("cost", 0.0)),
    )


def summarize_information_plan(
    plan: InformationPlan,
    *,
    max_text_chars: int = 180,
) -> dict[str, Any]:
    """Return a concise, terminal/dashboard-safe summary of one sampled Plan."""

    if max_text_chars < 20:
        raise ValidationError("Plan summary text limit is too small")

    def clip(value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) <= max_text_chars:
            return normalized
        return normalized[: max_text_chars - 1].rstrip() + "…"

    return {
        "plan_id": plan.plan_id,
        "parent_ids": list(plan.parent_ids),
        "basic_info_fields": list(plan.basic_info_policy.fields),
        "initial_research": clip(plan.initial_research_skill),
        "reflection": clip(plan.reflection_skill),
        "analysis": clip(plan.analysis_prompt),
    }


def _emit_progress(
    callback: ProgressCallback | None,
    event_type: str,
    **details: Any,
) -> None:
    if callback is not None:
        callback({"event_type": event_type, **details})


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _last_event_sequence(path: Path) -> int:
    if not path.exists():
        return 0
    latest = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            latest = max(latest, int(value.get("sequence", 0)))
    return latest


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"required evolution artifact is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"evolution artifact must be an object: {path}")
    return value


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_or_verify_json(path: Path, value: Mapping[str, Any]) -> None:
    """Reuse a crash-staged JSON object only when its canonical value is exact."""

    expected = json.loads(json.dumps(dict(value), sort_keys=True))
    if path.exists():
        actual = _read_json(path)
        if actual != expected:
            raise ValidationError(f"conflicting staged evolution artifact: {path}")
        return
    _atomic_write_json(path, expected)
