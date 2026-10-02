"""Crash-safe workspace state and Fast Plan evolution."""

from __future__ import annotations

import concurrent.futures
import fcntl
import json
import os
import random
import threading
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping
from stock_opportunity_agent.artifacts import (
    atomic_write_json as _atomic_write_json,
    canonical_json_hash as _canonical_hash,
)
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.resolution import (
    aggregate_capability_gaps,
    EvidenceResolver,
    extract_unresolved_signal_needs,
    RawInfoRequest,
    RawInfoResolution,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    LLMSignalRunner,
    SignalExecutor,
    SignalRegistry,
    SignalResult,
)

from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.signal_tracking import record_committed_signal_use
from stock_opportunity_agent.research.evolution_core import (
    BlindPrediction,
    BlindPredictor,
    CandidateExecutionRejected,
    CandidateProposalRejected,
    DEFAULT_EVOLUTION_PRIORS,
    EvaluationCaseReadiness,
    EvaluationDatasetManager,
    EvolutionCase,
    EvolutionPriors,
    ExecutionTrajectory,
    FitnessEligibility,
    GroundTruth,
    HashingPlanEmbedder,
    InformationPlan,
    InformationPlanProposer,
    ParentPlanReflectionEvidence,
    PlanArchive,
    PlanCritic,
    PlanEmbedder,
    PlanEvaluationConfig,
    PlanEvaluationSummary,
    PlanEvaluator,
    PlanMetaMemory,
    PlanMetaReflection,
    PlanMetrics,
    PlanRecord,
    ProgressCallback,
    ResearchController,
    RoundMetaEntry,
    RoundPaused,
    RoundReflector,
    RuntimeLimits,
    SharedEvaluationDataUnavailable,
    SignalRetrievalAgent,
    _case_identity_alias_inventory,
    _emit_progress,
    _last_event_sequence,
    _read_json,
    _same_artifact_path,
    _shared_missing_source_case_ids,
    _signal_learning_events_from_record,
    _trajectory_is_fitness_finalized,
    _write_or_verify_json,
    assess_fitness_eligibility,
    is_technical_exclusion_trajectory,
    build_parent_plan_comparison,
    collect_signal_usage,
    cosine_similarity,
    execute_information_plan,
    score_predictions,
    summarize_information_plan,
    CandidateJudgment,
    ConfidenceLevel,
    PredictionSelfReflection,
    RuntimeStopReason,
    RuntimeUsage,
    ResearchDecision,
    ResearchState,
)


class RuntimePlanEvaluator:
    """Concrete Plan evaluator using the adaptive runtime and a durable sink."""

    def __init__(
        self,
        *,
        raw_info_store: RawInfoStore,
        evidence_resolver: EvidenceResolver | None = None,
        controller: ResearchController,
        signal_agent: SignalRetrievalAgent,
        predictor: BlindPredictor,
        prediction_root: str | Path,
        trajectory_root: str | Path | None = None,
        limits: RuntimeLimits = RuntimeLimits(),
        deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None,
        llm_signal_runner: LLMSignalRunner | None = None,
        signal_readiness_snapshot: FrozenSignalRegistry | None = None,
        minimum_signal_readiness: float = 0.8,
        on_progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        if not 0 < minimum_signal_readiness <= 1:
            raise ValidationError("minimum Signal readiness must be in (0, 1]")
        self.raw_info_store = raw_info_store
        self.evidence_resolver = evidence_resolver or EvidenceResolver(raw_info_store)
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
        self.signal_readiness_snapshot = signal_readiness_snapshot
        self.minimum_signal_readiness = minimum_signal_readiness
        self.on_progress = on_progress
        self.cancel_event = cancel_event

    def check_case_readiness(
        self, case: EvolutionCase
    ) -> EvaluationCaseReadiness:
        """Materialize the fixed label-free market backbone before Plan work."""

        resolution = self.evidence_resolver.resolve(
            RawInfoRequest(
                request_id="fixed_evaluation_market_backbone",
                description=(
                    "Read the point-in-time daily market backbone required by "
                    "the fixed evaluation evidence gate."
                ),
                source_types=("market_data",),
                lookback_days=60,
                max_documents=1,
            ),
            company_id=case.company_id,
            identity=case.basic_info,
            as_of=case.prediction_time,
        )
        if resolution.status == "resolved":
            signal_resolutions: tuple[RawInfoResolution, ...] = ()
            if self.signal_readiness_snapshot is not None:
                executor = SignalExecutor(
                    self.signal_readiness_snapshot,
                    self.raw_info_store,
                    resolver=self.evidence_resolver,
                    deterministic_functions=self.deterministic_functions,
                    llm_runner=self.llm_signal_runner,
                )
                signal_resolutions = executor.prepare_inputs(
                    (
                        spec.ref
                        for spec in self.signal_readiness_snapshot.specs
                    ),
                    company_id=case.company_id,
                    as_of=case.prediction_time,
                    identity=case.basic_info,
                )
                ready_count = sum(
                    item.status == "resolved" for item in signal_resolutions
                )
                total_count = len(signal_resolutions)
                ready_fraction = (
                    ready_count / total_count if total_count else 1.0
                )
                if ready_fraction < self.minimum_signal_readiness:
                    failed = tuple(
                        item for item in signal_resolutions
                        if item.status != "resolved"
                    )
                    failed_reasons = {
                        str(event.details.get("reason", ""))
                        for item in failed
                        for event in item.events
                        if event.kind == "acquisition_failed"
                    }
                    result = EvaluationCaseReadiness(
                        case.case_id,
                        False,
                        (
                            "signal_data_readiness_below_threshold:"
                            f"{ready_count}/{total_count}"
                        ),
                        retryable="provider_error" in failed_reasons,
                    )
                    _emit_progress(
                        self.on_progress,
                        "evaluation_case_signal_data_unavailable",
                        **result.to_dict(),
                        minimum_signal_readiness=self.minimum_signal_readiness,
                        ready_signal_count=ready_count,
                        total_signal_count=total_count,
                        unready_signals={
                            item.request.request_id.removeprefix("signal:"): (
                                item.gap.reason.value
                                if item.gap is not None
                                else "no_matching_documents"
                            )
                            for item in failed
                        },
                    )
                    return result
            result = EvaluationCaseReadiness(case.case_id, True)
            _emit_progress(
                self.on_progress,
                "evaluation_case_data_ready",
                case_id=case.case_id,
                document_count=len(resolution.documents),
                appended_document_count=len(resolution.appended_documents),
                ready_signal_count=sum(
                    item.status == "resolved" for item in signal_resolutions
                ),
                total_signal_count=len(signal_resolutions),
            )
            return result
        failed_reasons = {
            str(event.details.get("reason", ""))
            for event in resolution.events
            if event.kind == "acquisition_failed"
        }
        reason = (
            resolution.gap.reason.value
            if resolution.gap is not None
            else "no_matching_documents"
        )
        result = EvaluationCaseReadiness(
            case.case_id,
            False,
            reason,
            retryable="provider_error" in failed_reasons,
        )
        _emit_progress(
            self.on_progress,
            "evaluation_case_data_unavailable",
            **result.to_dict(),
            provider=(resolution.gap.provider if resolution.gap else None),
            attempted_providers=[
                str(event.details.get("provider", ""))
                for event in resolution.events
                if event.kind == "acquisition_started"
            ],
        )
        return result

    def evaluate(
        self,
        plan: InformationPlan,
        cases: tuple[EvolutionCase, ...],
        signal_registry: FrozenSignalRegistry,
    ) -> PlanEvaluationAttempt:
        if not cases:
            raise ValidationError("evolution validation cases must not be empty")
        expected_case_ids = tuple(item.case_id for item in cases)
        executor = SignalExecutor(
            signal_registry,
            self.raw_info_store,
            resolver=self.evidence_resolver,
            deterministic_functions=self.deterministic_functions,
            llm_runner=self.llm_signal_runner,
        )
        trajectories: list[ExecutionTrajectory] = []
        failures: list[CaseEvaluationFailure] = []

        def stop_after_unfinalized(
            trajectory: ExecutionTrajectory,
        ) -> PlanEvaluationAttempt | None:
            if _trajectory_is_fitness_finalized(trajectory):
                return None
            _emit_progress(
                self.on_progress,
                "candidate_evaluation_stopped",
                plan_id=plan.plan_id,
                case_id=trajectory.case_id,
                reason="unfinalized_case",
                stop_reason=trajectory.stop_reason.value,
                completed_case_count=len(trajectories),
                expected_case_count=len(cases),
            )
            return PlanEvaluationAttempt(
                plan=plan,
                expected_case_ids=expected_case_ids,
                trajectories=tuple(trajectories),
                failures=tuple(failures),
            )

        for case_index, case in enumerate(cases, start=1):
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise EvaluationCancelled(
                    0,
                    "stop requested before starting the next evaluation case",
                )
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
                    "signal_learning_hash": signal_registry.learning_hash,
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
                if is_technical_exclusion_trajectory(trajectory):
                    failure_path = trajectory_path.with_suffix(".failure.json")
                    if not failure_path.exists():
                        raise ValidationError("technical trajectory missing failure checkpoint")
                    failure_record = _read_json(failure_path)
                    if (failure_record.get("schema_version") != "case-evaluation-failure-v1"
                            or failure_record.get("input_hash") != input_hash
                            or failure_record.get("case_id") != case.case_id):
                        raise ValidationError("conflicting technical failure checkpoint")
                    fields = ("stage", "error_type", "message", "artifact_ref")
                    if any(not isinstance(failure_record.get(key), str)
                           or not failure_record[key].strip() for key in fields):
                        raise ValidationError("technical failure checkpoint lacks diagnosis")
                    failures.append(CaseEvaluationFailure(
                        case_id=case.case_id,
                        **{key: failure_record[key] for key in fields},
                    ))
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
                stopped_attempt = stop_after_unfinalized(trajectory)
                if stopped_attempt is not None:
                    return stopped_attempt
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

            try:
                with ExitStack() as boundaries:
                    callers: set[int] = set()
                    for role in (self.controller, self.signal_agent, self.predictor,
                                 self.llm_signal_runner):
                        caller = getattr(role, "caller", None)
                        scope = getattr(caller, "anonymous_case", None)
                        if callable(scope) and id(caller) not in callers:
                            callers.add(id(caller))
                            boundaries.enter_context(scope(
                                aliases=_case_identity_alias_inventory((case,)),
                                company_id=case.company_id,
                                ticker=str(case.basic_info.get("ticker") or
                                           case.basic_info.get("symbol") or ""),
                            ))
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
            except ValidationError as exc:
                stage = (
                    exc.stage
                    if isinstance(exc, CandidateExecutionRejected)
                    else "case_execution"
                )
                failure_path = (
                    self.trajectory_root
                    / plan.plan_id
                    / f"{case.case_id}.failure.json"
                )
                failure = CaseEvaluationFailure(
                    case_id=case.case_id,
                    stage=stage,
                    error_type=type(exc).__name__,
                    message=str(exc),
                    artifact_ref=str(failure_path),
                )
                _write_or_verify_json(
                    failure_path,
                    {
                        "schema_version": "case-evaluation-failure-v1",
                        "input_hash": input_hash,
                        **failure.to_dict(),
                    },
                )
                _emit_progress(
                    self.on_progress,
                    "case_evaluation_failed",
                    plan_id=plan.plan_id,
                    case_id=case.case_id,
                    stage=stage,
                    error_type=type(exc).__name__,
                    failure_path=str(failure_path),
                )
                failures.append(failure)
                prior_abstains = sum(
                    1
                    for row in trajectories
                    if str(row.prediction.session_id).startswith("exclusion_")
                )
                if (
                    isinstance(exc, CandidateExecutionRejected)
                    # Every earlier failure this attempt already has its
                    # abstain row in trajectories, so the cumulative total is
                    # prior abstains plus this one candidate exclusion.
                    and prior_abstains < MAX_TECHNICAL_CASE_EXCLUSIONS
                ):
                    # User-approved carry-over (2026-09-21): a model-side
                    # correction exhaustion on one case records the failure,
                    # abstains that case (insufficient_information = a real
                    # finalized negative prediction, so the label-blind
                    # confusion matrix still counts it), and continues the
                    # remaining cases. Above the cap the attempt stays a
                    # rejection exactly as before; control-plane errors
                    # (budget, shared-data) still abort the attempt.
                    abstain = BlindPrediction(
                        is_surge=False,
                        candidate_judgment=CandidateJudgment.INSUFFICIENT_INFORMATION,
                        magnitude=None,
                        confidence=ConfidenceLevel.LOW,
                        key_reasons=(
                            "Technical exclusion: bounded corrections exhausted "
                            "before a compliant research state; abstaining is "
                            "recorded as a negative prediction.",
                        ),
                        uncertainties=(),
                        session_id=f"exclusion_{case.case_id}",
                    )
                    trajectories.append(
                        ExecutionTrajectory(
                            case_id=case.case_id,
                            company_id=case.company_id,
                            prediction_time=case.prediction_time,
                            basic_info={"requests": []},
                            basic_info_projection={},
                            initial_state=ResearchState(
                                decision=ResearchDecision.FINALIZE
                            ),
                            signal_rounds=(),
                            final_state=ResearchState(
                                decision=ResearchDecision.FINALIZE
                            ),
                            final_context={},
                            prediction=abstain,
                            prediction_ref=str(
                                self.trajectory_root
                                / plan.plan_id
                                / f"{case.case_id}.abstain.json"
                            ),
                            ground_truth=case.ground_truth,
                            self_reflection=PredictionSelfReflection(
                                correct=not case.ground_truth.is_surge,
                                plan_issues=(
                                    "technical_case_exclusion: "
                                    + str(exc)[:180],
                                ),
                            ),
                            stop_reason=RuntimeStopReason.FINALIZED,
                            usage=RuntimeUsage(signal_rounds=0, signal_calls=0, model=AgentUsage()),
                        )
                    )
                    _write_or_verify_json(
                        self.trajectory_root
                        / plan.plan_id
                        / f"{case.case_id}.abstain.json",
                        {
                            "case_id": case.case_id,
                            "company_id": case.company_id,
                            "prediction_time": case.prediction_time.isoformat(),
                            "final_context": {},
                            "prediction": abstain.to_dict(),
                        },
                    )
                    abstain_row = trajectories[-1]
                    _write_or_verify_json(
                        self.trajectory_root
                        / plan.plan_id
                        / f"{case.case_id}.json",
                        {
                            "schema_version": (
                                "execution-trajectory-checkpoint-v1"
                            ),
                            "input_hash": input_hash,
                            "plan_id": plan.plan_id,
                            "case_id": case.case_id,
                            "trajectory": abstain_row.to_dict(),
                        },
                    )
                    _emit_progress(
                        self.on_progress,
                        "case_technical_exclusion",
                        plan_id=plan.plan_id,
                        case_id=case.case_id,
                        exclusion_count=len(failures),
                    )
                    continue
                return PlanEvaluationAttempt(
                    plan=plan,
                    expected_case_ids=expected_case_ids,
                    trajectories=tuple(trajectories),
                    failures=tuple(failures),
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
            stopped_attempt = stop_after_unfinalized(trajectory)
            if stopped_attempt is not None:
                return stopped_attempt
        return PlanEvaluationAttempt(
            plan=plan,
            expected_case_ids=expected_case_ids,
            trajectories=tuple(trajectories),
            failures=tuple(failures),
        )


class EvolutionWorkspace:
    """Atomic committed-round persistence and recovery boundary."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.plans_root = self.root / "plans"
        self.experiments_root = self.root / "experiments"
        self.meta_root = self.root / "meta"
        self.cache_root = self.root / "cache"
        self.evaluation_root = self.root / "evaluation"
        self.trajectory_root = self.experiments_root / "trajectories"
        for path in (
            self.plans_root,
            self.experiments_root,
            self.meta_root,
            self.cache_root,
            self.evaluation_root,
            self.trajectory_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            _atomic_write_json(self.state_path, {"last_completed_round": 0})
        self._event_sequence = _last_event_sequence(self.trajectory_events_path)
        self._fault_injector: Callable[[str], None] | None = None

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

    @contextmanager
    def execution_lock(self) -> Iterator[None]:
        """Prevent concurrent cycle executors from mutating one workspace."""

        with self.execution_lock_at(self.root):
            yield

    @staticmethod
    @contextmanager
    def execution_lock_at(root: str | Path) -> Iterator[None]:
        """Lock an existing workspace without materializing runtime directories."""

        lock_path = Path(root) / ".evolution-run.lock"
        with lock_path.open("a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValidationError(
                    "evolution workspace already has an active cycle executor"
                ) from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def staged_candidate_plan(
        self,
        *,
        round_id: int,
        candidate_index: int,
        candidate_count: int,
        selected_parent_ids: tuple[str, ...],
        run_contract_hash: str,
    ) -> tuple[InformationPlan, int] | None:
        """Load one exact accepted candidate checkpoint for restart recovery."""

        path = self._candidate_plan_path(round_id, candidate_index)
        if not path.exists():
            return None
        payload = _read_json(path)
        expected_identity = {
            "schema_version": "information-plan-candidate-checkpoint-v1",
            "round_id": round_id,
            "candidate_index": candidate_index,
            "candidate_count": candidate_count,
            "selected_parent_ids": list(selected_parent_ids),
            "run_contract_hash": run_contract_hash,
        }
        if any(payload.get(key) != value for key, value in expected_identity.items()):
            raise ValidationError("staged candidate Plan identity mismatch")
        raw_plan = payload.get("plan")
        proposal_attempt = payload.get("proposal_attempt")
        if not isinstance(raw_plan, Mapping) or (
            isinstance(proposal_attempt, bool)
            or not isinstance(proposal_attempt, int)
            or proposal_attempt < 1
        ):
            raise ValidationError("staged candidate Plan payload is invalid")
        plan = InformationPlan.from_dict(raw_plan)
        if tuple(plan.parent_ids) != selected_parent_ids:
            raise ValidationError("staged candidate Plan lineage mismatch")
        return plan, proposal_attempt

    def stage_candidate_plan(
        self,
        *,
        round_id: int,
        candidate_index: int,
        candidate_count: int,
        selected_parent_ids: tuple[str, ...],
        proposal_attempt: int,
        run_contract_hash: str,
        plan: InformationPlan,
    ) -> Path:
        """Persist one accepted candidate before its first evaluation case."""

        if round_id < 1 or candidate_index < 1 or candidate_index > candidate_count:
            raise ValidationError("candidate Plan checkpoint slot is invalid")
        if proposal_attempt < 1 or tuple(plan.parent_ids) != selected_parent_ids:
            raise ValidationError("candidate Plan checkpoint lineage is invalid")
        path = self._candidate_plan_path(round_id, candidate_index)
        _write_or_verify_json(
            path,
            {
                "schema_version": "information-plan-candidate-checkpoint-v1",
                "round_id": round_id,
                "candidate_index": candidate_index,
                "candidate_count": candidate_count,
                "selected_parent_ids": list(selected_parent_ids),
                "proposal_attempt": proposal_attempt,
                "run_contract_hash": run_contract_hash,
                "plan": plan.to_dict(),
            },
        )
        return path

    def _candidate_plan_path(self, round_id: int, candidate_index: int) -> Path:
        if round_id < 1 or candidate_index < 1:
            raise ValidationError("candidate Plan checkpoint identity is invalid")
        return (
            self.experiments_root
            / f"round-{round_id:04d}"
            / "candidates"
            / f"slot-{candidate_index:02d}.json"
        )

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
        cycle_mode: str = "fast_then_slow",
        initial_signal_registry_version: int,
        initial_signal_registry_hash: str,
        observed_signal_registry_version: int,
        observed_signal_registry_hash: str,
        max_slow_cycles: int | None = None,
    ) -> dict[str, Any]:
        """Freeze or recover one Fast/Slow cycle and its Registry boundary."""

        if cycle_mode not in {"fast_then_slow", "slow_bootstrap", "slow_only"}:
            raise ValidationError("cycle mode is invalid")
        if (
            not run_contract_hash
            or target_plan_rounds < 0
            or initial_signal_registry_version < 1
            or observed_signal_registry_version < 1
        ):
            raise ValidationError("cycle contract hash and round target are required")
        if (
            (cycle_mode == "fast_then_slow" and target_plan_rounds < 1)
            or (
                cycle_mode in {"slow_bootstrap", "slow_only"}
                and target_plan_rounds != 0
            )
        ):
            raise ValidationError("cycle mode and Fast-round target conflict")
        if cycle_mode == "slow_only" and (
            max_slow_cycles is None or max_slow_cycles < 1
        ):
            raise ValidationError("slow_only requires a positive cumulative limit")
        if self.cycle_state_path.exists():
            state = _read_json(self.cycle_state_path)
            if state.get("schema_version") != "dual-loop-cycle-state-v2":
                raise ValidationError("unsupported dual-loop cycle state schema")
            if state.get("run_contract_hash") != run_contract_hash:
                raise ValidationError("cycle state run contract mismatch")
            if (
                int(state.get("initial_signal_registry_version", 0))
                != initial_signal_registry_version
                or state.get("initial_signal_registry_hash")
                != initial_signal_registry_hash
            ):
                raise ValidationError("cycle state initial Signal Registry mismatch")
        else:
            state = {
                "schema_version": "dual-loop-cycle-state-v2",
                "run_contract_hash": run_contract_hash,
                "initial_signal_registry_version": initial_signal_registry_version,
                "initial_signal_registry_hash": initial_signal_registry_hash,
                "current_signal_registry_version": initial_signal_registry_version,
                "current_signal_registry_hash": initial_signal_registry_hash,
                "last_completed_cycle": 0,
                "active_cycle": None,
            }
        active = state.get("active_cycle")
        resumed = isinstance(active, Mapping)
        if not resumed:
            if (
                cycle_mode == "slow_bootstrap"
                and int(state.get("last_completed_cycle", 0)) != 0
            ):
                raise ValidationError("slow_bootstrap contract is single-cycle")
            if (
                cycle_mode == "slow_only"
                and int(state.get("last_completed_cycle", 0))
                >= int(max_slow_cycles or 0)
            ):
                raise ValidationError("slow_only cumulative cycle limit exhausted")
            if (
                int(state.get("current_signal_registry_version", 0))
                != observed_signal_registry_version
                or state.get("current_signal_registry_hash")
                != observed_signal_registry_hash
            ):
                raise ValidationError(
                    "stable Signal Registry differs from last committed cycle output"
                )
            active = {
                "cycle_id": int(state.get("last_completed_cycle", 0)) + 1,
                "start_round": self.last_completed_round,
                "target_plan_rounds": target_plan_rounds,
                "cycle_mode": cycle_mode,
                "completed_plan_rounds": 0,
                "phase": "fast_loop",
                "input_signal_registry_version": observed_signal_registry_version,
                "input_signal_registry_hash": observed_signal_registry_hash,
            }
        else:
            active = dict(active)
            if int(active.get("target_plan_rounds", 0)) != target_plan_rounds:
                raise ValidationError("active cycle round target mismatch")
            if active.get("cycle_mode", "fast_then_slow") != cycle_mode:
                raise ValidationError("active cycle mode mismatch")
            if (
                int(active.get("input_signal_registry_version", 0))
                != int(state.get("current_signal_registry_version", 0))
                or active.get("input_signal_registry_hash")
                != state.get("current_signal_registry_hash")
            ):
                raise ValidationError("active cycle Signal input is not committed state")
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
        if phase not in {"fast_loop", "slow_loop", "signal_transition"}:
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

    def stage_slow_input(
        self,
        *,
        cycle_id: int,
        slow_input: Mapping[str, Any],
    ) -> Path:
        """Freeze one cycle's committed feedback and neutral sample identity."""

        payload = self._validated_slow_artifact_identity(
            cycle_id=cycle_id,
            value=slow_input,
            schema_version="slow-input-v1",
        )
        path = self._slow_artifact_path(cycle_id, "slow_input.json")
        _write_or_verify_json(path, payload)
        return path

    def load_slow_input(self, cycle_id: int) -> dict[str, Any] | None:
        """Load and validate a frozen Slow input for an active/committed cycle."""

        return self._load_slow_artifact(
            cycle_id=cycle_id,
            filename="slow_input.json",
            schema_version="slow-input-v1",
        )

    def stage_slow_memory(
        self,
        *,
        cycle_id: int,
        slow_memory: Mapping[str, Any],
    ) -> Path:
        """Append one immutable memory delta linked to the frozen Slow input."""

        slow_input = self.load_slow_input(cycle_id)
        if slow_input is None:
            raise ValidationError("cannot stage Slow memory before Slow input")
        payload = self._validated_slow_artifact_identity(
            cycle_id=cycle_id,
            value=slow_memory,
            schema_version="slow-memory-v1",
        )
        if payload.get("input_hash") != _canonical_hash(slow_input):
            raise ValidationError("Slow memory input hash mismatch")
        path = self._slow_artifact_path(cycle_id, "slow_memory.json")
        _write_or_verify_json(path, payload)
        return path

    def load_slow_memory(self, cycle_id: int) -> dict[str, Any] | None:
        """Load and validate one immutable Slow memory delta."""

        value = self._load_slow_artifact(
            cycle_id=cycle_id,
            filename="slow_memory.json",
            schema_version="slow-memory-v1",
        )
        if value is None:
            return None
        slow_input = self.load_slow_input(cycle_id)
        if slow_input is None or value.get("input_hash") != _canonical_hash(slow_input):
            raise ValidationError("Slow memory input lineage mismatch")
        return value

    def stage_slow_experiments(
        self,
        *,
        cycle_id: int,
        slow_experiments: Mapping[str, Any],
    ) -> Path:
        """Seal the complete Slow attempt index before candidate validation."""

        slow_input = self.load_slow_input(cycle_id)
        slow_memory = self.load_slow_memory(cycle_id)
        if slow_input is None or slow_memory is None:
            raise ValidationError(
                "cannot stage Slow experiments before input and memory"
            )
        payload = self._validated_slow_artifact_identity(
            cycle_id=cycle_id,
            value=slow_experiments,
            schema_version="slow-experiments-v1",
        )
        if (
            payload.get("input_hash") != _canonical_hash(slow_input)
            or payload.get("memory_hash") != _canonical_hash(slow_memory)
        ):
            raise ValidationError("Slow experiments lineage mismatch")
        path = self._slow_artifact_path(cycle_id, "slow_experiments.json")
        _write_or_verify_json(path, payload)
        return path

    def load_slow_experiments(self, cycle_id: int) -> dict[str, Any] | None:
        """Load and validate the sealed Slow experiment index."""

        value = self._load_slow_artifact(
            cycle_id=cycle_id,
            filename="slow_experiments.json",
            schema_version="slow-experiments-v1",
        )
        if value is None:
            return None
        slow_input = self.load_slow_input(cycle_id)
        slow_memory = self.load_slow_memory(cycle_id)
        if (
            slow_input is None
            or slow_memory is None
            or value.get("input_hash") != _canonical_hash(slow_input)
            or value.get("memory_hash") != _canonical_hash(slow_memory)
        ):
            raise ValidationError("Slow experiments lineage mismatch")
        return value

    def committed_slow_artifacts(self) -> tuple[dict[str, Any], ...]:
        """Return only pointer-reachable Slow input/memory/experiment chains."""

        rows: list[dict[str, Any]] = []
        for cycle_id in range(1, self.last_completed_cycle + 1):
            slow_input = self.load_slow_input(cycle_id)
            slow_memory = self.load_slow_memory(cycle_id)
            slow_experiments = self.load_slow_experiments(cycle_id)
            if slow_input is None or slow_memory is None or slow_experiments is None:
                continue
            rows.append(
                {
                    "cycle_id": cycle_id,
                    "slow_input": slow_input,
                    "slow_memory": slow_memory,
                    "slow_experiments": slow_experiments,
                }
            )
        return tuple(rows)

    def _validated_slow_artifact_identity(
        self,
        *,
        cycle_id: int,
        value: Mapping[str, Any],
        schema_version: str,
    ) -> dict[str, Any]:
        if cycle_id < 1:
            raise ValidationError("cycle id must be positive")
        state = _read_json(self.cycle_state_path)
        active = state.get("active_cycle")
        if not isinstance(active, Mapping) or int(active.get("cycle_id", 0)) != cycle_id:
            raise ValidationError("Slow artifact requires the active cycle")
        payload = dict(value)
        if (
            payload.get("schema_version") != schema_version
            or int(payload.get("cycle_id", 0)) != cycle_id
            or payload.get("contract_hash") != state.get("run_contract_hash")
        ):
            raise ValidationError("Slow artifact identity mismatch")
        return payload

    def _load_slow_artifact(
        self,
        *,
        cycle_id: int,
        filename: str,
        schema_version: str,
    ) -> dict[str, Any] | None:
        path = self._slow_artifact_path(cycle_id, filename)
        if not path.exists():
            return None
        payload = _read_json(path)
        state = _read_json(self.cycle_state_path)
        active = state.get("active_cycle")
        is_active = (
            isinstance(active, Mapping)
            and int(active.get("cycle_id", 0)) == cycle_id
        )
        if cycle_id > int(state.get("last_completed_cycle", 0)) and not is_active:
            raise ValidationError("uncommitted Slow artifact is not active")
        if (
            payload.get("schema_version") != schema_version
            or int(payload.get("cycle_id", 0)) != cycle_id
            or payload.get("contract_hash") != state.get("run_contract_hash")
        ):
            raise ValidationError("Slow artifact identity mismatch")
        return payload

    def staged_slow_validation(self, cycle_id: int) -> dict[str, Any] | None:
        path = self._slow_validation_path(cycle_id)
        if not path.exists():
            return None
        payload = _read_json(path)
        cycle_state = _read_json(self.cycle_state_path)
        if (
            payload.get("schema_version") != "dual-loop-slow-validation-v1"
            or int(payload.get("cycle_id", 0)) != cycle_id
            or payload.get("run_contract_hash")
            != cycle_state.get("run_contract_hash")
        ):
            raise ValidationError("staged Slow-loop validation identity mismatch")
        active = cycle_state.get("active_cycle")
        validation = dict(payload.get("validation", {}))
        if not isinstance(active, Mapping) or (
            int(validation.get("input_registry_version", 0))
            != int(active.get("input_signal_registry_version", 0))
            or validation.get("input_registry_hash")
            != active.get("input_signal_registry_hash")
        ):
            raise ValidationError("staged Slow validation Registry input mismatch")
        self._verify_slow_validation_chain(cycle_id, validation)
        return validation

    def stage_slow_validation(
        self,
        *,
        cycle_id: int,
        validation: Mapping[str, Any],
    ) -> Path:
        path = self._slow_validation_path(cycle_id)
        cycle_state = _read_json(self.cycle_state_path)
        active = cycle_state.get("active_cycle")
        if not isinstance(active, Mapping) or int(active.get("cycle_id", 0)) != cycle_id:
            raise ValidationError("active dual-loop cycle identity mismatch")
        if self.last_completed_round != (
            int(active.get("start_round", -1))
            + int(active.get("target_plan_rounds", 0))
        ):
            raise ValidationError("cannot stage Slow validation before all Fast rounds")
        if (
            int(validation.get("input_registry_version", 0))
            != int(active.get("input_signal_registry_version", 0))
            or validation.get("input_registry_hash")
            != active.get("input_signal_registry_hash")
        ):
            raise ValidationError("Slow validation differs from cycle Registry input")
        slow_input = self.load_slow_input(cycle_id)
        slow_memory = self.load_slow_memory(cycle_id)
        slow_experiments = self.load_slow_experiments(cycle_id)
        if any(item is not None for item in (slow_input, slow_memory, slow_experiments)):
            if slow_input is None or slow_memory is None or slow_experiments is None:
                raise ValidationError("Slow validation requires the complete v8 chain")
            expected = {
                "slow_input_hash": _canonical_hash(slow_input),
                "slow_memory_hash": _canonical_hash(slow_memory),
                "slow_experiments_hash": _canonical_hash(slow_experiments),
            }
            if any(validation.get(key) != value for key, value in expected.items()):
                raise ValidationError("Slow validation artifact lineage mismatch")
        _write_or_verify_json(
            path,
            {
                "schema_version": "dual-loop-slow-validation-v1",
                "cycle_id": cycle_id,
                "run_contract_hash": cycle_state.get("run_contract_hash"),
                "validation": dict(validation),
            },
        )
        self.mark_cycle_phase("signal_transition")
        return path

    def staged_slow_result(self, cycle_id: int) -> dict[str, Any] | None:
        path = self._slow_result_path(cycle_id)
        if not path.exists():
            return None
        payload = _read_json(path)
        cycle_state = _read_json(self.cycle_state_path)
        if (
            payload.get("schema_version") != "dual-loop-slow-result-v2"
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
        active = cycle_state.get("active_cycle")
        if not isinstance(active, Mapping) or int(active.get("cycle_id", 0)) != cycle_id:
            raise ValidationError("active dual-loop cycle identity mismatch")
        if (
            int(result.get("input_registry_version", 0))
            != int(active.get("input_signal_registry_version", 0))
            or result.get("input_registry_hash")
            != active.get("input_signal_registry_hash")
        ):
            raise ValidationError("Slow result differs from cycle Registry input")
        validation = self.staged_slow_validation(cycle_id)
        has_v8_chain = any(
            self._slow_artifact_path(cycle_id, filename).exists()
            for filename in (
                "slow_input.json",
                "slow_memory.json",
                "slow_experiments.json",
            )
        )
        if validation is None and has_v8_chain:
            raise ValidationError("cannot stage Slow result without validation")
        if validation is not None:
            for key in (
                "slow_input_hash",
                "slow_memory_hash",
                "slow_experiments_hash",
                "sampling_manifest_hash",
            ):
                if validation.get(key) and result.get(key) != validation.get(key):
                    raise ValidationError("Slow result artifact lineage mismatch")
        _write_or_verify_json(
            path,
            {
                "schema_version": "dual-loop-slow-result-v2",
                "cycle_id": cycle_id,
                "run_contract_hash": cycle_state.get("run_contract_hash"),
                "result": dict(result),
            },
        )
        return path

    def complete_cycle(
        self,
        *,
        cycle_id: int,
        observed_signal_registry_version: int,
        observed_signal_registry_hash: str,
    ) -> None:
        """Advance the cycle pointer only after Fast rounds and Slow result exist."""

        state = _read_json(self.cycle_state_path)
        active = state.get("active_cycle")
        if not isinstance(active, Mapping):
            if (
                int(state.get("last_completed_cycle", 0)) == cycle_id
                and int(state.get("current_signal_registry_version", 0))
                == observed_signal_registry_version
                and state.get("current_signal_registry_hash")
                == observed_signal_registry_hash
                and state.get("last_cycle_ref") == str(self._slow_result_path(cycle_id))
            ):
                return
            raise ValidationError("active dual-loop cycle identity mismatch")
        if int(active.get("cycle_id", 0)) != cycle_id:
            raise ValidationError("active dual-loop cycle identity mismatch")
        target = int(active["target_plan_rounds"])
        expected_round = int(active["start_round"]) + target
        if self.last_completed_round != expected_round:
            raise ValidationError("cannot complete cycle before all Fast rounds")
        slow_path = self._slow_result_path(cycle_id)
        if not slow_path.exists():
            raise ValidationError("cannot complete cycle without staged Slow result")
        slow_result = self.staged_slow_result(cycle_id)
        if slow_result is None:
            raise ValidationError("cannot complete cycle without staged Slow result")
        if (
            int(slow_result.get("output_registry_version", 0))
            != observed_signal_registry_version
            or slow_result.get("output_registry_hash")
            != observed_signal_registry_hash
        ):
            raise ValidationError("stable Registry differs from staged Slow output")
        state.update(
            {
                "last_completed_cycle": cycle_id,
                "last_completed_round": self.last_completed_round,
                "last_cycle_ref": str(slow_path),
                "current_signal_registry_version": observed_signal_registry_version,
                "current_signal_registry_hash": observed_signal_registry_hash,
                "active_cycle": None,
            }
        )
        self._fault_checkpoint("before_cycle_pointer")
        _atomic_write_json(self.cycle_state_path, state)
        self._fault_checkpoint("after_cycle_pointer")

    def _fault_checkpoint(self, stage: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(stage)

    def _slow_validation_path(self, cycle_id: int) -> Path:
        if cycle_id < 1:
            raise ValidationError("cycle id must be positive")
        return (
            self.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_validation.json"
        )

    def _slow_result_path(self, cycle_id: int) -> Path:
        if cycle_id < 1:
            raise ValidationError("cycle id must be positive")
        return (
            self.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / "slow_loop_result.json"
        )

    def _slow_artifact_path(self, cycle_id: int, filename: str) -> Path:
        if cycle_id < 1 or filename not in {
            "slow_input.json",
            "slow_memory.json",
            "slow_experiments.json",
        }:
            raise ValidationError("Slow artifact path is invalid")
        return (
            self.experiments_root
            / "cycles"
            / f"cycle-{cycle_id:04d}"
            / filename
        )

    def _verify_slow_validation_chain(
        self, cycle_id: int, validation: Mapping[str, Any]
    ) -> None:
        """Verify the optional v8 artifact chain on every resume shortcut."""

        if not validation.get("slow_input_hash"):
            return
        slow_input = self.load_slow_input(cycle_id)
        slow_memory = self.load_slow_memory(cycle_id)
        slow_experiments = self.load_slow_experiments(cycle_id)
        if slow_input is None or slow_memory is None or slow_experiments is None:
            raise ValidationError("staged Slow validation lost its v8 artifact chain")
        expected = {
            "slow_input_hash": _canonical_hash(slow_input),
            "slow_memory_hash": _canonical_hash(slow_memory),
            "slow_experiments_hash": _canonical_hash(slow_experiments),
            "sampling_manifest_hash": _canonical_hash(
                dict(slow_input.get("sampling_manifest", {}))
            ),
        }
        if any(validation.get(key) != value for key, value in expected.items()):
            raise ValidationError("staged Slow validation artifact lineage mismatch")

    def commit_round(
        self,
        *,
        round_id: int,
        records: tuple[PlanRecord, ...],
        meta_entry: RoundMetaEntry,
        signal_registry_version: int,
        signal_registry_hash: str,
        signal_learning_hash: str = "",
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
        if signal_registry_version < 1:
            raise ValidationError("round Signal Registry version must be positive")
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
                "signal_registry_version": signal_registry_version,
                "signal_registry_hash": signal_registry_hash,
                "signal_learning_hash": signal_learning_hash,
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

    def stage_evaluation_attempt(
        self,
        *,
        round_id: int,
        attempt: PlanEvaluationAttempt,
        available_source_types: Iterable[str] = (),
    ) -> Path:
        """Persist one candidate attempt whether or not it is fitness-eligible."""

        if round_id < 1:
            raise ValidationError("evaluation attempt round must be positive")
        path = (
            self.experiments_root
            / f"round-{round_id:04d}"
            / "attempts"
            / f"{attempt.plan.plan_id}.json"
        )
        if path.exists():
            try:
                staged = _read_json(path)
            except (OSError, ValueError):
                staged = None
            # A diagnostic-only attempt (failures recorded, no metrics) may
            # be superseded by a later retry after restart: the per-case
            # failure artifacts and trajectory checkpoints retain the full
            # audit trail. An eligible attempt stays verify-only.
            supersede = isinstance(staged, Mapping) and (
                staged.get("metrics") is None or staged.get("failures")
            )
            if not supersede:
                _write_or_verify_json(path, attempt.to_dict())
            else:
                superseded_dir = path.parent / "superseded"
                superseded_dir.mkdir(parents=True, exist_ok=True)
                index = 1
                superseded_path = (
                    superseded_dir / f"{path.stem}-{index:03d}.json"
                )
                while superseded_path.exists():
                    index += 1
                    superseded_path = (
                        superseded_dir / f"{path.stem}-{index:03d}.json"
                    )
                path.replace(superseded_path)
                _write_or_verify_json(path, attempt.to_dict())
        else:
            _write_or_verify_json(path, attempt.to_dict())
        self.refresh_capability_backlog(
            available_source_types=available_source_types
        )
        return path

    def refresh_capability_backlog(
        self, *, available_source_types: Iterable[str] = ()
    ) -> Path:
        """Rebuild the derived backlog from committed checkpoint records."""

        archive = self.restore_archive()
        trajectories: list[Mapping[str, Any]] = []
        need_sources: list[Mapping[str, Any]] = []
        for record in archive.records:
            for trajectory in record.trajectories:
                serialized = trajectory.to_dict()
                trajectories.append(serialized)
                need_sources.append(
                    {
                        "source_ref": f"{record.plan_id}:{trajectory.case_id}",
                        "source_round": record.round_id,
                        "source_fingerprint": _canonical_hash(serialized),
                        "trajectory": serialized,
                    }
                )
        committed_signal_needs = extract_unresolved_signal_needs(need_sources)
        bootstrap_manifest_path = self.root / "slow_bootstrap" / "manifest.json"
        signal_need_items: Iterable[Mapping[str, Any]] = committed_signal_needs
        committed_fast_backlog: Mapping[str, Any] | None = None
        if bootstrap_manifest_path.exists():
            envelope = _read_json(bootstrap_manifest_path)
            manifest = envelope.get("manifest", {})
            if isinstance(manifest, Mapping):
                backlog_seed = manifest.get("capability_backlog_seed", {})
                if isinstance(backlog_seed, Mapping):
                    if manifest.get("source_kind") == "committed_fast":
                        committed_fast_backlog = dict(backlog_seed)
                    elif not committed_signal_needs:
                        raw_items = backlog_seed.get("signal_need_items", ())
                        if isinstance(raw_items, list):
                            signal_need_items = tuple(
                                item
                                for item in raw_items
                                if isinstance(item, Mapping)
                            )
        history_path = self.root / "slow_history" / "manifest.json"
        if history_path.exists() and not archive.records:
            envelope = _read_json(history_path)
            manifest = envelope.get("manifest", {})
            if not isinstance(manifest, Mapping):
                raise ValidationError("Slow history manifest is invalid")
            if manifest.get("schema_version") == "slow-history-manifest-v2":
                context = manifest.get("fast_context", {})
                if (
                    envelope.get("manifest_hash") != _canonical_hash(manifest)
                    or not isinstance(context, Mapping)
                    or not isinstance(context.get("capability_backlog_seed"), Mapping)
                ):
                    raise ValidationError("Slow history Fast backlog seed is invalid")
                committed_fast_backlog = dict(context["capability_backlog_seed"])
        report = (
            dict(committed_fast_backlog)
            if committed_fast_backlog is not None and not archive.records
            else aggregate_capability_gaps(
                trajectories,
                available_source_types=available_source_types,
                signal_need_items=signal_need_items,
            )
        )
        diagnostic_attempts = []
        for path in sorted(self.experiments_root.glob("round-*/attempts/*.json")):
            attempt = _read_json(path)
            failures = attempt.get("failures", ())
            if isinstance(failures, list) and failures:
                diagnostic_attempts.append(
                    {
                        "attempt_ref": str(path.relative_to(self.root)),
                        "failure_count": len(failures),
                        "failures": [
                            dict(item) for item in failures if isinstance(item, Mapping)
                        ],
                    }
                )
        report["diagnostic_attempts"] = diagnostic_attempts
        _atomic_write_json(
            self.experiments_root / "capability_gap_report.json",
            report,
        )
        path = self.root / "capability_backlog.json"
        _atomic_write_json(path, report)
        return path

    def reject_round(
        self,
        *,
        round_id: int,
        reason: str,
        attempts: Iterable[PlanEvaluationAttempt],
    ) -> Path:
        """Persist one immutable pause checkpoint without advancing state."""

        if round_id != self.last_completed_round + 1:
            raise ValidationError("round rejection does not follow committed state")
        path = self.experiments_root / f"round-{round_id:04d}" / "rejected.json"
        payload = {
            "schema_version": "plan-round-rejected-v1",
            "round_id": round_id,
            "reason": str(reason),
            "attempts": [attempt.to_dict() for attempt in attempts],
            "last_completed_round": self.last_completed_round,
        }
        _write_or_verify_json(path, payload)
        return path

    def stage_shared_data_pause(
        self,
        *,
        round_id: int,
        case_reasons: Mapping[str, str],
        retryable: bool,
    ) -> Path:
        """Persist a replaceable diagnostic without committing or rejecting."""

        if round_id != self.last_completed_round + 1:
            raise ValidationError("shared-data pause does not follow committed state")
        path = (
            self.experiments_root
            / f"round-{round_id:04d}"
            / "shared-data-pause.json"
        )
        _atomic_write_json(
            path,
            {
                "schema_version": "plan-round-shared-data-pause-v1",
                "round_id": round_id,
                "case_reasons": {
                    str(case_id): str(reason)
                    for case_id, reason in case_reasons.items()
                },
                "retryable": bool(retryable),
                "last_completed_round": self.last_completed_round,
            },
        )
        return path

    def load_round_rejection(self, round_id: int) -> dict[str, Any] | None:
        path = self.experiments_root / f"round-{round_id:04d}" / "rejected.json"
        return _read_json(path) if path.exists() else None

    def restore_archive(self, *, expected_run_contract_hash: str | None = None) -> PlanArchive:
        """Load only Plans reachable from authoritative completed checkpoints."""

        state = _read_json(self.state_path)
        last_completed_round = int(state.get("last_completed_round", 0))
        if last_completed_round < 0:
            raise ValidationError("completed round pointer cannot be negative")
        if last_completed_round:
            expected_last_checkpoint = (
                self.experiments_root
                / f"round-{last_completed_round:04d}"
                / "checkpoint.json"
            )
            if not _same_artifact_path(
                state.get("checkpoint_ref"), expected_last_checkpoint
            ):
                raise ValidationError(
                    "state pointer checkpoint_ref differs from its completed round"
                )
        records: list[PlanRecord] = []
        for round_id in range(1, last_completed_round + 1):
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
            plan_ids = checkpoint.get("plan_ids")
            if (
                not isinstance(plan_ids, list)
                or not plan_ids
                or any(not isinstance(item, str) or not item for item in plan_ids)
                or len(set(plan_ids)) != len(plan_ids)
            ):
                raise ValidationError("round checkpoint Plan ids are invalid")
            expected_meta_ref = self.meta_root / f"round-{round_id:04d}.json"
            if not _same_artifact_path(checkpoint.get("meta_ref"), expected_meta_ref):
                raise ValidationError("round checkpoint meta reference mismatch")
            for plan_id in plan_ids:
                record = PlanRecord.from_dict(
                    _read_json(self.plans_root / plan_id / "record.json")
                )
                if record.plan_id != plan_id or record.round_id != round_id:
                    raise ValidationError(
                        "round checkpoint cross-links a different Plan record"
                    )
                records.append(record)
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


@dataclass(frozen=True)
class CaseEvaluationFailure:
    """Durable reason one case could not cross the prediction boundary."""

    case_id: str
    stage: str
    error_type: str
    message: str
    artifact_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "stage": self.stage,
            "error_type": self.error_type,
            "message": self.message,
            "artifact_ref": self.artifact_ref,
        }


@dataclass(frozen=True)
class PlanEvaluationAttempt:
    """Complete or stopped candidate evaluation before archive admission."""

    plan: InformationPlan
    expected_case_ids: tuple[str, ...]
    trajectories: tuple[ExecutionTrajectory, ...]
    failures: tuple[CaseEvaluationFailure, ...] = ()

    @property
    def technical_exclusion_case_ids(self) -> tuple[str, ...]:
        """Failed cases carried over as recorded abstain predictions.

        Cumulative per candidate: replayed abstain rows (persisted across
        restarts) merge with this attempt's fresh failures, so the cap
        survives evaluation re-entry.
        """

        if len(self.trajectories) != len(self.expected_case_ids):
            return ()
        abstains = {
            row.case_id
            for row in self.trajectories
            if str(row.prediction.session_id).startswith("exclusion_")
        }
        fresh = {failure.case_id for failure in self.failures}
        total = abstains | fresh
        if not total or len(total) > MAX_TECHNICAL_CASE_EXCLUSIONS:
            return ()
        return tuple(sorted(total))

    @property
    def metrics(self) -> PlanMetrics | None:
        if len(self.trajectories) != len(self.expected_case_ids):
            return None
        total_exclusions = len(
            {
                row.case_id
                for row in self.trajectories
                if str(row.prediction.session_id).startswith("exclusion_")
            }
            | {failure.case_id for failure in self.failures}
        )
        if total_exclusions > MAX_TECHNICAL_CASE_EXCLUSIONS:
            return None
        if self.failures and not self.technical_exclusion_case_ids:
            return None
        return score_predictions(self.trajectories)

    @property
    def fitness(self) -> FitnessEligibility:
        return assess_fitness_eligibility(
            self.trajectories,
            expected_case_ids=self.expected_case_ids,
            technical_exclusion_case_ids=self.technical_exclusion_case_ids,
        )

    def to_dict(self) -> dict[str, Any]:
        metrics = self.metrics
        return {
            "schema_version": "plan-evaluation-attempt-v1",
            "plan_id": self.plan.plan_id,
            "expected_case_ids": list(self.expected_case_ids),
            "completed_case_ids": [item.case_id for item in self.trajectories],
            "trajectories": [item.to_dict() for item in self.trajectories],
            "failures": [item.to_dict() for item in self.failures],
            "technical_exclusion_case_ids": list(
                self.technical_exclusion_case_ids
            ),
            "metrics": metrics.to_dict() if metrics is not None else None,
            "fitness": self.fitness.to_dict(),
        }


@dataclass(frozen=True)
class PlanEvaluationResult:
    """In-round predictions and metrics before durable PlanRecord creation."""

    plan: InformationPlan
    trajectories: tuple[ExecutionTrajectory, ...]
    metrics: PlanMetrics
    metrics_by_cohort: Mapping[str, PlanMetrics]
    fitness: FitnessEligibility


MAX_TECHNICAL_CASE_EXCLUSIONS = 6


class EvaluationCancelled(ValidationError):
    """Coordinator-level stop of candidate admission and dispatch."""

    def __init__(self, round_id: int, message: str) -> None:
        super().__init__(f"evaluation cancelled at round {round_id}: {message}")
        self.round_id = round_id


def install_stop_handler(
    cancel_event: threading.Event,
) -> Callable[[], None]:
    """Handle SIGINT in the coordinator thread by marking stop intent.

    Defect #12 fix: the handler replaces the default KeyboardInterrupt with a
    cancel flag, so a stop during a blocking provider call is no longer
    swallowed-or-fatal; the engine finishes the in-flight unit, then stops
    admission at the next safe boundary. Only the coordinator main thread
    installs it; workers never install signal handlers.
    """

    import signal

    previous = signal.getsignal(signal.SIGINT)

    def _mark_stop(signum, frame):  # noqa: ARG001
        cancel_event.set()

    signal.signal(signal.SIGINT, _mark_stop)

    def restore() -> None:
        signal.signal(signal.SIGINT, previous)

    return restore


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
        warm_start_plans: tuple[InformationPlan, ...] = (),
        warm_start_parent_evidence: tuple[
            ParentPlanReflectionEvidence, ...
        ] = (),
        priors: EvolutionPriors = DEFAULT_EVOLUTION_PRIORS,
        embedder: PlanEmbedder | None = None,
        candidates_per_round: int = 3,
        top_k: int = 3,
        random_k: int = 2,
        similarity_threshold: float = 0.9,
        rng: random.Random | None = None,
        parent_selection_seed: int | None = None,
        capability_source_types: Iterable[str] = (),
        evaluation_config: PlanEvaluationConfig = PlanEvaluationConfig(),
        case_readiness: Callable[[EvolutionCase], EvaluationCaseReadiness]
        | None = None,
        run_contract_hash: str = "",
        on_progress: ProgressCallback | None = None,
        evaluator_factory: Callable[[], "PlanEvaluator"] | None = None,
        max_parallel_plans: int = 1,
        cancel_event: threading.Event | None = None,
        worker_wait_timeout_seconds: float = 3600.0,
    ) -> None:
        if candidates_per_round < 1:
            raise ValidationError("candidates_per_round must be positive")
        if not seed_plans:
            raise ValidationError("plan evolution requires at least one seed Plan")
        if max_parallel_plans < 1:
            raise ValidationError("max_parallel_plans must be positive")
        if max_parallel_plans > 1 and evaluator_factory is None:
            raise ValidationError(
                "parallel Plan evaluation requires an evaluator factory so "
                "each worker owns its own mutable role instances"
            )
        self.archive = archive
        self.meta_memory = meta_memory
        self.signal_registry = signal_registry
        self.evaluator = evaluator
        self.evaluator_factory = evaluator_factory
        self.max_parallel_plans = max_parallel_plans
        self.cancel_event = cancel_event
        self.worker_wait_timeout_seconds = float(worker_wait_timeout_seconds)
        self._progress_lock = threading.Lock()
        self.proposer = proposer
        self.critic = critic
        self.round_reflector = round_reflector
        self.workspace = workspace
        self.seed_plans = tuple(seed_plans)
        self.warm_start_plans = tuple(warm_start_plans)
        self.warm_start_parent_evidence = {
            item.plan.plan_id: item for item in warm_start_parent_evidence
        }
        parent_seed_ids = [
            plan.plan_id for plan in (*self.seed_plans, *self.warm_start_plans)
        ]
        if len(parent_seed_ids) != len(set(parent_seed_ids)):
            raise ValidationError("plan evolution seed ids must be unique")
        if len(self.warm_start_parent_evidence) != len(
            tuple(warm_start_parent_evidence)
        ) or set(self.warm_start_parent_evidence) - {
            plan.plan_id for plan in self.warm_start_plans
        }:
            raise ValidationError("warm-start reflection evidence is inconsistent")
        warm_plans_by_id = {
            plan.plan_id: plan for plan in self.warm_start_plans
        }
        if any(
            evidence.plan != warm_plans_by_id[plan_id]
            for plan_id, evidence in self.warm_start_parent_evidence.items()
        ):
            raise ValidationError("warm-start reflection Plan content differs")
        self.priors = priors
        self.embedder = embedder or HashingPlanEmbedder()
        self.candidates_per_round = candidates_per_round
        self.top_k = top_k
        self.random_k = random_k
        self.similarity_threshold = similarity_threshold
        self.rng = rng or random.Random()
        self.parent_selection_seed = parent_selection_seed
        self.capability_source_types = tuple(capability_source_types)
        self.evaluation_config = evaluation_config
        self.case_readiness = case_readiness
        self.run_contract_hash = run_contract_hash
        self.on_progress = on_progress
        for committed_record in self.archive.records:
            self._record_signal_statistics(committed_record)

    def run_round(
        self,
        *,
        round_id: int,
        validation_cases: tuple[EvolutionCase, ...],
        anchor_cases: tuple[EvolutionCase, ...],
        signal_snapshot: FrozenSignalRegistry,
    ) -> PlanRoundResult:
        """Sample N independent Plans, evaluate, critique, archive, and reflect."""

        if round_id != self.workspace.last_completed_round + 1:
            raise ValidationError("fast-loop round id does not follow committed state")
        rejected = self.workspace.load_round_rejection(round_id)
        if rejected is not None:
            checkpoint = (
                self.workspace.experiments_root
                / f"round-{round_id:04d}"
                / "rejected.json"
            )
            raise RoundPaused(round_id, str(rejected["reason"]), str(checkpoint))
        dataset_manager = EvaluationDatasetManager(
            self.workspace.evaluation_root,
            validation_cases,
            anchor_cases,
            self.evaluation_config,
            case_readiness=self.case_readiness,
        )
        try:
            round_snapshot = dataset_manager.get_or_create_round_dataset(round_id)
        except SharedEvaluationDataUnavailable as unavailable:
            checkpoint = self.workspace.stage_shared_data_pause(
                round_id=round_id,
                case_reasons=unavailable.case_reasons,
                retryable=unavailable.retryable,
            )
            _emit_progress(
                self.on_progress,
                "shared_evaluation_data_unavailable",
                round_id=round_id,
                case_reasons=dict(unavailable.case_reasons),
                retryable=unavailable.retryable,
                checkpoint_ref=str(checkpoint),
            )
            raise SharedEvaluationDataUnavailable(
                round_id,
                unavailable.case_reasons,
                retryable=unavailable.retryable,
                checkpoint_ref=str(checkpoint),
            ) from unavailable
        round_cases = dataset_manager.resolve_cases(round_snapshot.case_ids)
        round_aliases = _case_identity_alias_inventory(round_cases)
        for role in (self.proposer, self.critic, self.round_reflector):
            setter = getattr(role, "set_anonymous_aliases", None)
            if callable(setter):
                setter(round_aliases)
        _emit_progress(
            self.on_progress,
            "round_started",
            round_id=round_id,
            candidate_count=self.candidates_per_round,
            validation_case_count=len(validation_cases),
            evaluation_case_count=len(round_cases),
            evaluation_snapshot_id=round_snapshot.snapshot_id,
        )
        selection = self.archive.select_parents(
            top_k=self.top_k,
            random_k=self.random_k,
            similarity_threshold=self.similarity_threshold,
            rng=(
                random.Random(f"{self.parent_selection_seed}:{round_id}")
                if self.parent_selection_seed is not None
                else self.rng
            ),
        )
        quality_parents = [record.plan for record in selection.top]
        quality_embeddings = [record.embedding for record in selection.top]
        parent_evidence_by_id = {
            record.plan_id: ParentPlanReflectionEvidence(
                plan=record.plan,
                source_scope="current_archive",
                evaluation_snapshot_ids=record.evaluation.dataset_snapshot_ids,
                metrics_by_cohort=record.evaluation.metrics_by_cohort,
            )
            for record in selection.records
        }
        selected_warm_start_plans: list[InformationPlan] = []
        for plan in self.warm_start_plans:
            if len(quality_parents) >= self.top_k:
                break
            embedding = self.embedder.embed(plan)
            if all(
                cosine_similarity(embedding, kept) < self.similarity_threshold
                for kept in quality_embeddings
            ):
                quality_parents.append(plan)
                quality_embeddings.append(embedding)
                selected_warm_start_plans.append(plan)
                parent_evidence_by_id[plan.plan_id] = (
                    self.warm_start_parent_evidence.get(plan.plan_id)
                    or ParentPlanReflectionEvidence(
                        plan=plan,
                        source_scope="historical_seed",
                    )
                )
        if not quality_parents:
            quality_parents.extend(self.seed_plans)
            parent_evidence_by_id.update(
                {
                    plan.plan_id: ParentPlanReflectionEvidence(
                        plan=plan,
                        source_scope="manual_seed",
                    )
                    for plan in self.seed_plans
                }
            )
        parents = tuple(quality_parents) + tuple(
            record.plan for record in selection.random
        )
        selected_parent_ids = tuple(plan.plan_id for plan in parents)
        _emit_progress(
            self.on_progress,
            "parents_selected",
            round_id=round_id,
            top_parent_ids=[record.plan_id for record in selection.top],
            random_parent_ids=[record.plan_id for record in selection.random],
            seed_parent_ids=[plan.plan_id for plan in selected_warm_start_plans]
            or (
                [plan.plan_id for plan in self.seed_plans]
                if not selection.top
                else []
            ),
        )
        allowed_parent_ids = {plan.plan_id for plan in parents}
        candidate_plans: list[InformationPlan] = []
        forbidden_content_hashes = {
            _canonical_hash(record.plan.canonical_dict())
            for record in self.archive.records
        } | {_canonical_hash(plan.canonical_dict()) for plan in parents}
        for candidate_index in range(1, self.candidates_per_round + 1):
            accepted: InformationPlan | None = None
            accepted_proposal_attempt: int | None = None
            staged_candidate = self.workspace.staged_candidate_plan(
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=self.candidates_per_round,
                selected_parent_ids=selected_parent_ids,
                run_contract_hash=self.run_contract_hash,
            )
            if staged_candidate is not None:
                accepted, accepted_proposal_attempt = staged_candidate
                content_hash = _canonical_hash(accepted.canonical_dict())
                if content_hash in forbidden_content_hashes:
                    raise ValidationError(
                        "staged candidate Plan duplicates prior or sibling content"
                    )
                forbidden_content_hashes.add(content_hash)
                _emit_progress(
                    self.on_progress,
                    "candidate_proposal_reused",
                    round_id=round_id,
                    candidate_index=candidate_index,
                    candidate_count=self.candidates_per_round,
                    proposal_attempt=accepted_proposal_attempt,
                    plan_id=accepted.plan_id,
                )
            else:
                for proposal_attempt in range(
                    1, self.evaluation_config.max_proposal_attempts_per_slot + 1
                ):
                    meta_view = self.meta_memory.archive_view()
                    _emit_progress(
                        self.on_progress,
                        "candidate_proposal_started",
                        round_id=round_id,
                        candidate_index=candidate_index,
                        candidate_count=self.candidates_per_round,
                        proposal_attempt=proposal_attempt,
                        meta_context_hash=_canonical_hash(meta_view),
                        meta_round_ids=[
                            int(item["round_id"]) for item in meta_view
                        ],
                        meta_case_count=sum(
                            len(plan.original_case_reflections)
                            for entry in self.meta_memory.entries
                            for plan in entry.plan_reflections
                        ),
                    )
                    try:
                        candidate = self.proposer.propose(
                            round_id=round_id,
                            candidate_index=candidate_index,
                            candidate_count=self.candidates_per_round,
                            proposal_attempt=proposal_attempt,
                            forbidden_plan_ids=tuple(
                                sorted(
                                    {
                                        *(
                                            record.plan_id
                                            for record in self.archive.records
                                        ),
                                        *(plan.plan_id for plan in candidate_plans),
                                    }
                                )
                            ),
                            parents=parents,
                            meta_info=self.meta_memory.entries,
                            prior=self.priors.propose_plan,
                        )
                        if (
                            not candidate.parent_ids
                            or set(candidate.parent_ids) != allowed_parent_ids
                        ):
                            raise CandidateProposalRejected(
                                "runtime lineage differs from selected parents"
                            )
                        content_hash = _canonical_hash(candidate.canonical_dict())
                        if content_hash in forbidden_content_hashes:
                            raise CandidateProposalRejected(
                                "candidate Plan content duplicates an existing Plan"
                            )
                    except CandidateProposalRejected as exc:
                        _emit_progress(
                            self.on_progress,
                            "candidate_proposal_rejected",
                            round_id=round_id,
                            candidate_index=candidate_index,
                            candidate_count=self.candidates_per_round,
                            proposal_attempt=proposal_attempt,
                            reason=str(exc),
                        )
                        continue
                    accepted = candidate
                    accepted_proposal_attempt = proposal_attempt
                    forbidden_content_hashes.add(content_hash)
                    self.workspace.stage_candidate_plan(
                        round_id=round_id,
                        candidate_index=candidate_index,
                        candidate_count=self.candidates_per_round,
                        selected_parent_ids=selected_parent_ids,
                        proposal_attempt=proposal_attempt,
                        run_contract_hash=self.run_contract_hash,
                        plan=accepted,
                    )
                    break
            if accepted is None:
                continue
            candidate_plans.append(accepted)
            _emit_progress(
                self.on_progress,
                "candidate_proposed",
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=self.candidates_per_round,
                plan_id=accepted.plan_id,
                parent_ids=list(accepted.parent_ids),
                plan_summary=summarize_information_plan(accepted),
            )

        if not candidate_plans:
            checkpoint = self.workspace.reject_round(
                round_id=round_id,
                reason="all_candidate_proposals_rejected",
                attempts=(),
            )
            raise RoundPaused(
                round_id,
                "all_candidate_proposals_rejected",
                str(checkpoint),
            )

        attempts: list[PlanEvaluationAttempt] = []
        evaluation_results: list[PlanEvaluationResult] = []
        evaluated: (
            list[tuple[int, InformationPlan, PlanEvaluationAttempt, Path]] | None
        ) = None
        if self.evaluator_factory is not None:
            evaluated = self._evaluate_candidates_bounded(
                candidate_plans,
                round_id=round_id,
                round_cases=round_cases,
                round_snapshot=round_snapshot,
                signal_snapshot=signal_snapshot,
            )
        for candidate_index, plan in enumerate(candidate_plans, start=1):
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise EvaluationCancelled(
                    round_id,
                    "stop requested before candidate admission",
                )
            if evaluated is not None:
                _, plan, attempt, attempt_path = evaluated[candidate_index - 1]
            else:
                _emit_progress(
                    self.on_progress,
                    "candidate_evaluation_started",
                    round_id=round_id,
                    candidate_index=candidate_index,
                    candidate_count=len(candidate_plans),
                    plan_id=plan.plan_id,
                )
                raw_attempt = self.evaluator.evaluate(
                    plan,
                    round_cases,
                    signal_snapshot,
                )
                attempt = (
                    raw_attempt
                    if isinstance(raw_attempt, PlanEvaluationAttempt)
                    else PlanEvaluationAttempt(
                        plan=plan,
                        expected_case_ids=round_snapshot.case_ids,
                        trajectories=tuple(raw_attempt),
                    )
                )
                attempt_path = self.workspace.stage_evaluation_attempt(
                    round_id=round_id,
                    attempt=attempt,
                    available_source_types=self.capability_source_types,
                )
            attempts.append(attempt)
            metrics = attempt.metrics
            fitness = attempt.fitness
            if metrics is None:
                _emit_progress(
                    self.on_progress,
                    "candidate_evaluation_rejected",
                    round_id=round_id,
                    candidate_index=candidate_index,
                    plan_id=plan.plan_id,
                    reasons=list(fitness.reasons),
                    attempt_ref=str(attempt_path),
                )
                continue
            trajectories_by_id = {
                trajectory.case_id: trajectory for trajectory in attempt.trajectories
            }
            if set(trajectories_by_id) != set(round_snapshot.case_ids):
                _emit_progress(
                    self.on_progress,
                    "candidate_evaluation_rejected",
                    round_id=round_id,
                    candidate_index=candidate_index,
                    plan_id=plan.plan_id,
                    reasons=list(fitness.reasons),
                    attempt_ref=str(attempt_path),
                )
                continue
            anchor_trajectories = tuple(
                trajectories_by_id[case_id]
                for case_id in round_snapshot.anchor_case_ids
            )
            random_trajectories = tuple(
                trajectories_by_id[case_id]
                for case_id in round_snapshot.random_case_ids
            )
            metrics_by_cohort = {
                "anchor": score_predictions(anchor_trajectories),
                "random": score_predictions(random_trajectories),
                "combined": metrics,
            }
            _emit_progress(
                self.on_progress,
                "candidate_scored" if fitness.eligible else "candidate_diagnostic_only",
                round_id=round_id,
                candidate_index=candidate_index,
                candidate_count=len(candidate_plans),
                plan_id=plan.plan_id,
                metrics=metrics.to_dict(),
                metrics_by_cohort={
                    cohort: cohort_metrics.to_dict()
                    for cohort, cohort_metrics in metrics_by_cohort.items()
                },
                fitness=fitness.to_dict(),
                trajectory_count=len(attempt.trajectories),
                evaluation_stage="round",
                case_ids=list(round_snapshot.case_ids),
                attempt_ref=str(attempt_path),
            )
            evaluation_results.append(
                PlanEvaluationResult(
                    plan=plan,
                    trajectories=attempt.trajectories,
                    metrics=metrics,
                    metrics_by_cohort=metrics_by_cohort,
                    fitness=fitness,
                )
            )

        shared_missing_case_ids = _shared_missing_source_case_ids(attempts)
        if shared_missing_case_ids:
            case_reasons = {
                case_id: "missing_source_evidence_after_readiness"
                for case_id in shared_missing_case_ids
            }
            checkpoint = self.workspace.stage_shared_data_pause(
                round_id=round_id,
                case_reasons=case_reasons,
                retryable=False,
            )
            _emit_progress(
                self.on_progress,
                "shared_evaluation_data_unavailable",
                round_id=round_id,
                case_reasons=case_reasons,
                retryable=False,
                checkpoint_ref=str(checkpoint),
            )
            raise SharedEvaluationDataUnavailable(
                round_id,
                case_reasons,
                retryable=False,
                checkpoint_ref=str(checkpoint),
            )

        records: list[PlanRecord] = []
        parent_comparisons_by_plan_id: dict[
            str, tuple[Mapping[str, Any], ...]
        ] = {}
        for result in evaluation_results:
            trajectories = result.trajectories
            metrics = result.metrics
            try:
                comparisons = tuple(
                    build_parent_plan_comparison(
                        parent=parent_evidence_by_id[parent_id],
                        child_plan=result.plan,
                        child_metrics=metrics,
                        child_snapshot_id=round_snapshot.snapshot_id,
                    )
                    for parent_id in result.plan.parent_ids
                )
            except KeyError as exc:
                raise ValidationError(
                    "candidate parent reflection evidence is missing"
                ) from exc
            parent_comparisons_by_plan_id[result.plan.plan_id] = comparisons
            reflection = self.critic.critique(
                plan=result.plan,
                trajectories=trajectories,
                metrics=metrics,
                parent_comparisons=comparisons,
            )
            records.append(
                PlanRecord(
                    plan=result.plan,
                    round_id=round_id,
                    embedding=self.embedder.embed(result.plan),
                    metrics=metrics,
                    reflection=reflection,
                    signal_usage=collect_signal_usage(trajectories),
                    trajectories=trajectories,
                    evaluation=PlanEvaluationSummary(
                        evaluation_stage="round",
                        n_cases=len(trajectories),
                        case_ids=round_snapshot.case_ids,
                        dataset_snapshot_ids=(round_snapshot.snapshot_id,),
                        metrics_by_cohort=result.metrics_by_cohort,
                    ),
                    fitness=result.fitness,
                )
            )

        record_tuple = tuple(records)
        if not any(record.fitness.eligible for record in record_tuple):
            checkpoint = self.workspace.reject_round(
                round_id=round_id,
                reason="no_fitness_eligible_candidates",
                attempts=attempts,
            )
            _emit_progress(
                self.on_progress,
                "round_rejected",
                round_id=round_id,
                reason="no_fitness_eligible_candidates",
                checkpoint_ref=str(checkpoint),
            )
            raise RoundPaused(
                round_id,
                "no_fitness_eligible_candidates",
                str(checkpoint),
            )
        horizontal_meta_entry = self.round_reflector.reflect(
            round_id=round_id,
            records=record_tuple,
            prior=self.priors.reflect_round,
            parent_comparisons_by_plan_id=parent_comparisons_by_plan_id,
        )
        if horizontal_meta_entry.round_id != round_id:
            raise ValidationError("round reflector returned a different round id")
        meta_entry = horizontal_meta_entry.append_plan_reflections(
            PlanMetaReflection.from_record(
                record,
                parent_comparisons=parent_comparisons_by_plan_id[record.plan_id],
            )
            for record in record_tuple
        )
        expected_refs = {record.plan_id for record in record_tuple}
        if tuple(
            item.plan_id for item in meta_entry.plan_reflections
        ) != tuple(record.plan_id for record in record_tuple):
            raise ValidationError(
                "round meta entry must retain every new Plan reflection in order"
            )
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
            signal_registry_version=signal_snapshot.version,
            signal_registry_hash=signal_snapshot.registry_hash,
            signal_learning_hash=signal_snapshot.learning_hash,
            run_contract_hash=self.run_contract_hash,
        )
        for record in record_tuple:
            self.archive.add(record)
            self._record_signal_statistics(record)
        self.meta_memory.append(meta_entry)
        self.workspace.refresh_capability_backlog(
            available_source_types=self.capability_source_types
        )
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
                    "magnitude_macro_f1": record.metrics.magnitude_macro_f1,
                }
                for record in record_tuple
            ],
            top_k=[
                {
                    "plan_id": record.plan_id,
                    "binary_f1": record.metrics.binary_f1,
                    "magnitude_macro_f1": record.metrics.magnitude_macro_f1,
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

    def _evaluate_one_candidate(
        self,
        *,
        candidate_index: int,
        candidate_count: int,
        plan: InformationPlan,
        evaluator: "PlanEvaluator",
        round_id: int,
        round_cases: tuple[EvolutionCase, ...],
        round_snapshot: Any,
        signal_snapshot: Any,
    ) -> tuple[int, InformationPlan, PlanEvaluationAttempt, Path]:
        """Evaluate and stage one candidate on the caller's own evaluator."""

        raw_attempt = evaluator.evaluate(plan, round_cases, signal_snapshot)
        attempt = (
            raw_attempt
            if isinstance(raw_attempt, PlanEvaluationAttempt)
            else PlanEvaluationAttempt(
                plan=plan,
                expected_case_ids=round_snapshot.case_ids,
                trajectories=tuple(raw_attempt),
            )
        )
        attempt_path = self.workspace.stage_evaluation_attempt(
            round_id=round_id,
            attempt=attempt,
            available_source_types=self.capability_source_types,
        )
        return candidate_index, plan, attempt, attempt_path

    def _evaluate_candidates_bounded(
        self,
        candidate_plans: tuple[InformationPlan, ...],
        *,
        round_id: int,
        round_cases: tuple[EvolutionCase, ...],
        round_snapshot: Any,
        signal_snapshot: Any,
    ) -> list[tuple[int, InformationPlan, PlanEvaluationAttempt, Path]]:
        """Evaluate candidates with bounded workers in ascending slot order.

        The coordinator (this thread, holding the workspace execution lock)
        emits start events and dispatches tasks in candidate-slot order. Each
        worker owns one candidate at a time and a fresh evaluator from the
        factory, so no mutable role instance is shared. Workers keep case
        order inside a candidate; staging stays per-plan. Results are
        recombined in slot order, and commit-phase work remains on the
        coordinator thread.
        """

        results: dict[
            int, tuple[int, InformationPlan, PlanEvaluationAttempt, Path]
        ] = {}
        worker_count = max(1, min(self.max_parallel_plans, len(candidate_plans)))
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="plan-eval",
        ) as pool:
            futures: dict[concurrent.futures.Future, int] = {}
            for candidate_index, plan in enumerate(candidate_plans, start=1):
                if self.cancel_event is not None and self.cancel_event.is_set():
                    raise EvaluationCancelled(
                        round_id,
                        "stop requested before candidate admission",
                    )
                _emit_progress(
                    self.on_progress,
                    "candidate_evaluation_started",
                    round_id=round_id,
                    candidate_index=candidate_index,
                    candidate_count=len(candidate_plans),
                    plan_id=plan.plan_id,
                )
                future = pool.submit(
                    self._evaluate_one_candidate,
                    candidate_index=candidate_index,
                    candidate_count=len(candidate_plans),
                    plan=plan,
                    evaluator=self.evaluator_factory(),
                    round_id=round_id,
                    round_cases=round_cases,
                    round_snapshot=round_snapshot,
                    signal_snapshot=signal_snapshot,
                )
                futures[future] = candidate_index
            pending = set(futures)
            done, not_done = concurrent.futures.wait(
                pending,
                timeout=self.worker_wait_timeout_seconds,
            )
            if not_done:
                for future in not_done:
                    future.cancel()
                raise EvaluationCancelled(
                    round_id,
                    "bounded wait for evaluation workers exceeded "
                    f"{self.worker_wait_timeout_seconds}s with "
                    f"{len(not_done)} candidate(s) unfinished; staged attempts "
                    "are preserved for recovery",
                )
            for future, index in futures.items():
                entry = future.result()
                results[index] = entry
        return [results[index] for index in range(1, len(candidate_plans) + 1)]

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
        record_committed_signal_use(self.signal_registry, _signal_learning_events_from_record(record))
