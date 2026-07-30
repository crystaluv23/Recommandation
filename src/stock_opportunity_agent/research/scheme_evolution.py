"""Bounded, proposal-only evolution of Ralph information-scheme genomes.

The engine owns search state and admission control. Existing data archives,
packet renderers, blind researchers, and provider clients remain outside this
module and can be connected through :class:`SchemeFoldEvaluator`.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.models import SerializableRecord, ValidationError
from stock_opportunity_agent.research.scheme_evolution_evaluation import (
    _genome_complexity,
    _validate_folds,
    build_walk_forward_folds,
    evaluate_predictions,
    paired_admission_decision,
)
from stock_opportunity_agent.research.scheme_evolution_records import (
    SCHEME_EVOLUTION_SCHEMA_VERSION,
    _BLIND_FORBIDDEN_VARIABLES,
    AdmissionDecision,
    BlindSample,
    DataSourceSpec,
    DataSplitSpec,
    EvaluationSpec,
    EvolutionFold,
    FixedEvolutionSpec,
    LabelSpec,
    LabeledSample,
    MaterializedScheme,
    MetaLesson,
    MutationOperator,
    MutationRequest,
    PredictionRecord,
    PromptSpec,
    SchemeEvaluationResult,
    SchemeExperimentRecord,
    SchemeFoldEvaluator,
    SchemeGenome,
    SchemeProposer,
    SignalSpec,
)


class MockSchemeProposer:
    """Deterministic proposer for tests and offline vertical slices."""

    def __init__(self, candidates: Iterable[SchemeGenome]) -> None:
        self.candidates = list(candidates)

    def propose(
        self,
        parents: list[SchemeGenome],
        meta_memory: list[MetaLesson],
        mutation_requests: list[MutationRequest],
        count: int,
    ) -> list[SchemeGenome]:
        """Return the configured candidates without reading labels or sealed data."""

        del parents, meta_memory, mutation_requests
        return self.candidates[:count]


class FileSchemeProposer:
    """Load Codex- or human-authored candidates from a reviewed JSON file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def propose(
        self,
        parents: list[SchemeGenome],
        meta_memory: list[MetaLesson],
        mutation_requests: list[MutationRequest],
        count: int,
    ) -> list[SchemeGenome]:
        """Return candidates related to the supplied parents, capped by ``count``."""

        del meta_memory, mutation_requests
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"cannot load scheme candidate file: {exc}") from exc
        rows = raw.get("candidates") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            raise ValidationError("candidate file must be a list or contain a candidates list")
        try:
            candidates = [SchemeGenome.from_dict(row) for row in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"invalid scheme candidate: {exc}") from exc
        parent_ids = {parent.genome_id for parent in parents}
        related = [
            candidate
            for candidate in candidates
            if not candidate.parent_ids or parent_ids.intersection(candidate.parent_ids)
        ]
        return related[:count]


@dataclass(frozen=True)
class CandidateRejection(SerializableRecord):
    """Auditable rejection produced before any expensive evaluation."""

    genome_id: str
    reasons: list[str]


class CandidateValidator:
    """Static schema, leakage, budget, and duplicate validation."""

    def __init__(self, *, near_duplicate_threshold: float = 0.97) -> None:
        if not 0.8 <= near_duplicate_threshold <= 1:
            raise ValidationError("near_duplicate_threshold must be between 0.8 and 1")
        self.near_duplicate_threshold = near_duplicate_threshold

    def validate(
        self,
        candidate: SchemeGenome,
        *,
        parents: Iterable[SchemeGenome],
        accepted: Iterable[SchemeGenome],
    ) -> list[str]:
        """Return rejection reasons; an empty list means the candidate is valid."""

        parent_list = list(parents)
        reasons: list[str] = []
        parent_ids = {parent.genome_id for parent in parent_list}
        if candidate.generation > 0 and not candidate.parent_ids:
            reasons.append("non-root candidate requires parent_ids")
        if candidate.parent_ids and not set(candidate.parent_ids).issubset(parent_ids):
            reasons.append("candidate references a parent outside the active parent set")
        if parent_list and candidate.generation <= max(parent.generation for parent in parent_list):
            reasons.append("candidate generation must be greater than its active parents")
        reasons.extend(_blind_prompt_leakage_reasons(candidate))
        source_count = len(candidate.data_source_specs)
        signal_count = len(candidate.seed_signal_specs)
        estimated_cost = sum(item.estimated_cost_usd for item in candidate.data_source_specs)
        if source_count > int(candidate.complexity_budget["max_sources"]):
            reasons.append("source count exceeds complexity budget")
        if signal_count > int(candidate.complexity_budget["max_signals"]):
            reasons.append("signal count exceeds complexity budget")
        if estimated_cost > float(candidate.complexity_budget["max_estimated_cost_usd"]):
            reasons.append("estimated data cost exceeds complexity budget")
        references = parent_list + list(accepted)
        candidate_fingerprint = genome_recipe_hash(candidate)
        candidate_tokens = _genome_tokens(candidate)
        for reference in references:
            if candidate.genome_id == reference.genome_id:
                reasons.append("genome_id duplicates an existing genome")
                continue
            if candidate_fingerprint == genome_recipe_hash(reference):
                reasons.append(f"exact recipe duplicate of {reference.genome_id}")
                continue
            similarity = _jaccard(candidate_tokens, _genome_tokens(reference))
            if similarity >= self.near_duplicate_threshold:
                reasons.append(
                    f"near-duplicate of {reference.genome_id} at similarity {similarity:.3f}"
                )
        return list(dict.fromkeys(reasons))


class MockSchemeFoldEvaluator:
    """Network-free evaluator used only to prove the evolution mechanics."""

    def __init__(self) -> None:
        self.observed_blind_inputs: list[dict[str, Any]] = []

    @property
    def evaluator_fingerprint(self) -> str:
        return "mock-scheme-evaluator-v0.1"

    def materialize(self, genome: SchemeGenome, fold: EvolutionFold) -> MaterializedScheme:
        """Retain seed signals and hash only discovery ids plus labels."""

        materialization_input = {
            "genome": genome_recipe_hash(genome),
            "fold_id": fold.fold_id,
            "discovery": [
                {"sample_id": sample.sample_id, "label": sample.label}
                for sample in fold.discovery_samples
            ],
        }
        input_hash = _hash_json(materialization_input)
        output = {
            "retained_signal_ids": [signal.signal_id for signal in genome.seed_signal_specs],
            "input_hash": input_hash,
        }
        output_hash = _hash_json(output)
        return MaterializedScheme(
            materialized_scheme_id=f"{genome.genome_id}:{fold.fold_id}:{output_hash[:12]}",
            genome_id=genome.genome_id,
            fold_id=fold.fold_id,
            discovered_signals=[],
            retained_signals=list(genome.seed_signal_specs),
            rejected_signals=[],
            materialization_inputs_hash=input_hash,
            output_hash=output_hash,
        )

    def predict(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        sample: BlindSample,
    ) -> PredictionRecord:
        """Produce a deterministic probability from label-free synthetic features."""

        blind_payload = sample.to_dict()
        if set(blind_payload) & _BLIND_FORBIDDEN_VARIABLES:
            raise ValidationError("blind sample unexpectedly contains label fields")
        self.observed_blind_inputs.append(blind_payload)
        strength = float(sample.features.get("signal_strength", 0.0))
        shift = float(genome.metadata.get("probability_shift", 0.0))
        weight = float(genome.metadata.get("feature_weight", 0.55))
        probability = min(0.99, max(0.01, 0.22 + weight * strength + shift))
        abstain_band = float(genome.metadata.get("abstain_band", 0.0))
        if abs(probability - 0.5) < abstain_band:
            decision = "abstain"
        else:
            decision = "positive" if probability >= 0.5 else "negative"
        confidence = "high" if abs(probability - 0.5) >= 0.3 else "medium"
        if abs(probability - 0.5) < 0.12:
            confidence = "low"
        return PredictionRecord(
            genome_id=genome.genome_id,
            materialized_scheme_id=materialized.materialized_scheme_id,
            fold_id=materialized.fold_id,
            sample_id=sample.sample_id,
            prediction_time=sample.prediction_time,
            probability_of_surge=round(probability, 6),
            binary_decision=decision,
            confidence=confidence,
            supporting_signals=(
                [signal.signal_id for signal in materialized.retained_signals]
                if probability >= 0.5
                else []
            ),
            contradicting_signals=[] if probability >= 0.5 else ["weak_signal_strength"],
            missing_information=[],
            difficulty_codes=["near_threshold"] if confidence == "low" else [],
            evidence_source_ids=list(sample.evidence_source_ids),
            model_metadata={
                "provider": "local_mock",
                "model": "deterministic",
                "temperature": 0.0,
                "token_cost_usd": 0.0,
                "data_cost_usd": sum(
                    source.estimated_cost_usd for source in genome.data_source_specs
                ),
                "latency_ms": 0.0,
            },
            raw_response_location=None,
        )


@dataclass(frozen=True)
class ArchiveEntry(SerializableRecord):
    """One non-dominated candidate retained in a quality-diversity niche."""

    niche: str
    genome: SchemeGenome
    evaluation: SchemeEvaluationResult
    admitted: bool
    complexity: float


class QualityDiversityArchive:
    """Keep Pareto candidates by source, signal, cost, complexity, and orientation."""

    def __init__(self, entries: Iterable[ArchiveEntry] = ()) -> None:
        self._entries: dict[str, list[ArchiveEntry]] = {}
        for entry in entries:
            self._entries.setdefault(entry.niche, []).append(entry)

    @property
    def entries(self) -> list[ArchiveEntry]:
        """Return entries in deterministic niche/genome order."""

        return sorted(
            (entry for rows in self._entries.values() for entry in rows),
            key=lambda item: (item.niche, item.genome.genome_id),
        )

    def update(
        self,
        genome: SchemeGenome,
        evaluation: SchemeEvaluationResult,
        *,
        admitted: bool,
    ) -> bool:
        """Insert a candidate unless an incumbent in its niche dominates it."""

        niche = _niche_for_genome(genome)
        entry = ArchiveEntry(
            niche=niche,
            genome=genome,
            evaluation=evaluation,
            admitted=admitted,
            complexity=_genome_complexity(genome),
        )
        current = self._entries.setdefault(niche, [])
        if any(_dominates(existing, entry) for existing in current):
            return False
        self._entries[niche] = [
            existing for existing in current if not _dominates(entry, existing)
        ] + [entry]
        return True

    def to_dict(self) -> dict[str, Any]:
        """Return an exportable archive artifact."""

        return {
            "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "QualityDiversityArchive":
        """Restore an archive written by :meth:`to_dict`."""

        rows = data.get("entries", [])
        if not isinstance(rows, list):
            raise ValidationError("archive entries must be a list")
        return cls(ArchiveEntry.from_dict(row) for row in rows)


class EvolutionStateStore:
    """File-backed, hash-checked state for resumable candidate evaluation."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def fold_dir(self, context_hash: str) -> Path:
        return self.root / "experiments" / context_hash

    def load_fold(
        self,
        context_hash: str,
    ) -> tuple[MaterializedScheme, list[PredictionRecord], SchemeEvaluationResult] | None:
        """Load a completed fold only when every required artifact exists."""

        base = self.fold_dir(context_hash)
        required = (
            base / "materialized_scheme.json",
            base / "predictions.json",
            base / "evaluation.json",
            base / "context.json",
        )
        if not all(path.exists() for path in required):
            return None
        context = json.loads((base / "context.json").read_text(encoding="utf-8"))
        if context.get("context_hash") != context_hash:
            raise ValidationError("resume context hash mismatch")
        materialized = MaterializedScheme.from_dict(
            json.loads((base / "materialized_scheme.json").read_text(encoding="utf-8"))
        )
        predictions_raw = json.loads((base / "predictions.json").read_text(encoding="utf-8"))
        predictions = [PredictionRecord.from_dict(row) for row in predictions_raw["predictions"]]
        evaluation = SchemeEvaluationResult.from_dict(
            json.loads((base / "evaluation.json").read_text(encoding="utf-8"))
        )
        return materialized, predictions, evaluation

    def write_materialized(self, context_hash: str, materialized: MaterializedScheme) -> None:
        """Persist materialization before any blind prediction."""

        _write_json(self.fold_dir(context_hash) / "materialized_scheme.json", materialized.to_dict())

    def write_predictions(
        self,
        context_hash: str,
        predictions: Iterable[PredictionRecord],
    ) -> None:
        """Durably write all predictions before labels are scored."""

        _write_json(
            self.fold_dir(context_hash) / "predictions.json",
            {
                "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                "predictions_persisted_before_evaluation": True,
                "predictions": [prediction.to_dict() for prediction in predictions],
            },
        )

    def write_evaluation(
        self,
        context_hash: str,
        evaluation: SchemeEvaluationResult,
        *,
        context: Mapping[str, Any],
    ) -> None:
        """Write label-aware evaluation after the prediction artifact exists."""

        prediction_path = self.fold_dir(context_hash) / "predictions.json"
        if not prediction_path.exists():
            raise ValidationError("predictions must be persisted before evaluation")
        _write_json(self.fold_dir(context_hash) / "evaluation.json", evaluation.to_dict())
        _write_json(
            self.fold_dir(context_hash) / "context.json",
            {**dict(context), "context_hash": context_hash},
        )

    def write_run_artifacts(
        self,
        result: "EvolutionRunResult",
        *,
        fixed_spec: FixedEvolutionSpec,
        rejections: Iterable[CandidateRejection],
    ) -> dict[str, Path]:
        """Write final state, archive, experiments, and a compact report."""

        self.root.mkdir(parents=True, exist_ok=True)
        paths = {
            "state": self.root / "evolution_state.json",
            "archive": self.root / "quality_diversity_archive.json",
            "experiments": self.root / "scheme_experiments.json",
            "meta_lessons": self.root / "meta_lessons.json",
            "report": self.root / "experiment_report.json",
        }
        _write_json(
            paths["state"],
            {
                "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                "fixed_spec_hash": fixed_spec.content_hash,
                "incumbent": result.incumbent.to_dict(),
                "completed_experiment_ids": [
                    experiment.experiment_id for experiment in result.experiments
                ],
                "candidate_rejections": [item.to_dict() for item in rejections],
                "next_mutation_requests": [
                    item.to_dict() for item in result.mutation_requests
                ],
                "proposal_status": "proposal_only_pending_human_review",
                "sealed_test_included": False,
            },
        )
        _write_json(paths["archive"], result.archive.to_dict())
        _write_json(
            paths["experiments"],
            {
                "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                "experiments": [item.to_dict() for item in result.experiments],
            },
        )
        _write_json(
            paths["meta_lessons"],
            {
                "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                "lessons": [item.to_dict() for item in result.meta_lessons],
                "next_mutation_requests": [
                    item.to_dict() for item in result.mutation_requests
                ],
                "contains_per_sample_labels": False,
            },
        )
        _write_json(
            paths["report"],
            {
                "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                "incumbent_genome_id": result.incumbent.genome_id,
                "evaluated_candidate_count": len(result.experiments),
                "archive_niche_count": len({entry.niche for entry in result.archive.entries}),
                "archive_entry_count": len(result.archive.entries),
                "admitted_candidate_ids": [
                    item.candidate_genome_id
                    for item in result.experiments
                    if item.admission_decision.admitted
                ],
                "meta_lesson_count": len(result.meta_lessons),
                "next_mutation_request_count": len(result.mutation_requests),
                "synthetic_or_mock_result_is_effectiveness_evidence": False,
                "sealed_test_included": False,
            },
        )
        return paths


@dataclass(frozen=True)
class EvolutionRunResult:
    """Result of one bounded candidate batch."""

    incumbent: SchemeGenome
    experiments: list[SchemeExperimentRecord]
    archive: QualityDiversityArchive
    rejections: list[CandidateRejection]
    meta_lessons: list[MetaLesson]
    mutation_requests: list[MutationRequest]
    artifact_paths: dict[str, Path]


class SchemeEvolutionEngine:
    """Evaluate a bounded proposal batch under fixed, non-evolvable rules."""

    def __init__(
        self,
        *,
        proposer: SchemeProposer,
        evaluator: SchemeFoldEvaluator,
        fixed_spec: FixedEvolutionSpec,
        state_store: EvolutionStateStore,
        archive: QualityDiversityArchive | None = None,
        validator: CandidateValidator | None = None,
        max_candidates: int = 8,
        max_api_cost_usd: float = 20.0,
    ) -> None:
        if max_candidates < 1:
            raise ValidationError("max_candidates must be positive")
        if max_api_cost_usd < 0:
            raise ValidationError("max_api_cost_usd cannot be negative")
        self.proposer = proposer
        self.evaluator = evaluator
        self.fixed_spec = fixed_spec
        self.state_store = state_store
        self.archive = archive or QualityDiversityArchive()
        self.validator = validator or CandidateValidator()
        self.max_candidates = max_candidates
        self.max_api_cost_usd = max_api_cost_usd

    def run(
        self,
        incumbent: SchemeGenome,
        folds: Iterable[EvolutionFold],
        *,
        meta_memory: Iterable[MetaLesson] = (),
        mutation_requests: Iterable[MutationRequest] = (),
        candidate_count: int = 8,
        resume: bool = False,
        git_commit: str | None = None,
    ) -> EvolutionRunResult:
        """Run one bounded generation and return a proposal-only incumbent."""

        fold_list = list(folds)
        if not fold_list:
            raise ValidationError("scheme evolution requires at least one fold")
        _validate_folds(fold_list, self.fixed_spec)
        requested = min(candidate_count, self.max_candidates)
        proposed = self.proposer.propose(
            [incumbent],
            list(meta_memory),
            list(mutation_requests),
            requested,
        )
        accepted: list[SchemeGenome] = []
        rejections: list[CandidateRejection] = []
        for candidate in proposed:
            reasons = self.validator.validate(
                candidate,
                parents=[incumbent],
                accepted=accepted,
            )
            if reasons:
                rejections.append(CandidateRejection(candidate.genome_id, reasons))
            else:
                accepted.append(candidate)
        incumbent_predictions, incumbent_evaluation = self._evaluate_genome(
            incumbent,
            fold_list,
            resume=resume,
        )
        self.archive.update(incumbent, incumbent_evaluation, admitted=True)
        experiments: list[SchemeExperimentRecord] = []
        best = incumbent
        best_lower_bound = 0.0
        for candidate in accepted:
            started_at = datetime.now(timezone.utc)
            predictions, evaluation = self._evaluate_genome(
                candidate,
                fold_list,
                resume=resume,
            )
            total_cost = evaluation.data_cost_usd + evaluation.token_cost_usd
            if total_cost > self.max_api_cost_usd:
                admission = AdmissionDecision(
                    status="cost_budget_exceeded",
                    admitted=False,
                    utility_difference=evaluation.primary_utility
                    - incumbent_evaluation.primary_utility,
                    confidence_interval=[],
                    paired_block_count=0,
                    reasons=["candidate exceeded run-level API/data cost budget"],
                )
            else:
                admission = paired_admission_decision(
                    incumbent_predictions,
                    predictions,
                    fold_list,
                    incumbent=incumbent_evaluation,
                    candidate=evaluation,
                    spec=self.fixed_spec.evaluation_spec,
                    candidate_complexity=_genome_complexity(candidate),
                    incumbent_complexity=_genome_complexity(incumbent),
                )
            completed_at = datetime.now(timezone.utc)
            experiment_id = _hash_json(
                {
                    "fixed_spec": self.fixed_spec.content_hash,
                    "candidate": genome_recipe_hash(candidate),
                    "incumbent": genome_recipe_hash(incumbent),
                    "folds": [fold.fold_id for fold in fold_list],
                    "evaluator": self.evaluator.evaluator_fingerprint,
                }
            )
            record = SchemeExperimentRecord(
                experiment_id=experiment_id,
                parent_genome_ids=list(candidate.parent_ids),
                candidate_genome_id=candidate.genome_id,
                mutation_operator=candidate.mutation_operator,
                data_split_version=self.fixed_spec.split_spec.version,
                label_spec_version=self.fixed_spec.label_spec.version,
                configuration_hashes={
                    "fixed_spec": self.fixed_spec.content_hash,
                    "candidate_recipe": genome_recipe_hash(candidate),
                    "evaluator": self.evaluator.evaluator_fingerprint,
                },
                evaluation_result=evaluation,
                admission_decision=admission,
                failure_reason=None if admission.admitted else "; ".join(admission.reasons),
                started_at=started_at,
                completed_at=completed_at,
                git_commit=git_commit,
            )
            experiments.append(record)
            self.archive.update(candidate, evaluation, admitted=admission.admitted)
            lower_bound = admission.confidence_interval[0] if admission.confidence_interval else math.nan
            if admission.admitted and not math.isnan(lower_bound) and lower_bound > best_lower_bound:
                best = candidate
                best_lower_bound = lower_bound
        generated_lessons, next_mutations = derive_meta_lessons(
            experiments,
            spec=self.fixed_spec.evaluation_spec,
        )
        provisional = EvolutionRunResult(
            incumbent=best,
            experiments=experiments,
            archive=self.archive,
            rejections=rejections,
            meta_lessons=generated_lessons,
            mutation_requests=next_mutations,
            artifact_paths={},
        )
        paths = self.state_store.write_run_artifacts(
            provisional,
            fixed_spec=self.fixed_spec,
            rejections=rejections,
        )
        return EvolutionRunResult(
            incumbent=best,
            experiments=experiments,
            archive=self.archive,
            rejections=rejections,
            meta_lessons=generated_lessons,
            mutation_requests=next_mutations,
            artifact_paths=paths,
        )

    def _evaluate_genome(
        self,
        genome: SchemeGenome,
        folds: list[EvolutionFold],
        *,
        resume: bool,
    ) -> tuple[list[PredictionRecord], SchemeEvaluationResult]:
        all_predictions: list[PredictionRecord] = []
        labels: dict[str, int] = {}
        metadata: dict[str, LabeledSample] = {}
        for fold in folds:
            context = {
                "fixed_spec_hash": self.fixed_spec.content_hash,
                "genome_recipe_hash": genome_recipe_hash(genome),
                "fold_id": fold.fold_id,
                "fold_fingerprint": _hash_json(fold.to_dict()),
                "evaluator_fingerprint": self.evaluator.evaluator_fingerprint,
            }
            context_hash = _hash_json(context)
            cached = self.state_store.load_fold(context_hash) if resume else None
            if cached is not None:
                _materialized, predictions, _evaluation = cached
            else:
                materialized = self.evaluator.materialize(genome, fold)
                self.state_store.write_materialized(context_hash, materialized)
                predictions = [
                    self.evaluator.predict(genome, materialized, sample.blind_view())
                    for sample in fold.admission_samples
                ]
                self.state_store.write_predictions(context_hash, predictions)
                fold_labels = {sample.sample_id: sample.label for sample in fold.admission_samples}
                fold_metadata = {sample.sample_id: sample for sample in fold.admission_samples}
                fold_evaluation = evaluate_predictions(
                    genome,
                    predictions,
                    fold_labels,
                    fold_metadata,
                    spec=self.fixed_spec.evaluation_spec,
                )
                self.state_store.write_evaluation(
                    context_hash,
                    fold_evaluation,
                    context=context,
                )
            all_predictions.extend(predictions)
            for sample in fold.admission_samples:
                if sample.sample_id in labels:
                    raise ValidationError("admission sample appears in more than one selected fold")
                labels[sample.sample_id] = sample.label
                metadata[sample.sample_id] = sample
        return all_predictions, evaluate_predictions(
            genome,
            all_predictions,
            labels,
            metadata,
            spec=self.fixed_spec.evaluation_spec,
        )


def genome_recipe_hash(genome: SchemeGenome) -> str:
    """Hash evolvable recipe content while ignoring identity and lineage metadata."""

    data = genome.to_dict()
    for key in (
        "genome_id",
        "parent_ids",
        "generation",
        "mutation_operator",
        "hypothesis_of_change",
        "changed_fields",
        "expected_benefit",
        "possible_side_effects",
        "falsification_test",
    ):
        data.pop(key, None)
    return _hash_json(data)


def merge_meta_lessons(lessons: Iterable[MetaLesson]) -> list[MetaLesson]:
    """Merge equivalent scoped lessons without unbounded free-text accumulation."""

    grouped: dict[tuple[str, str], list[MetaLesson]] = {}
    for lesson in lessons:
        key = (_normalize_text(lesson.scope), _normalize_text(lesson.lesson))
        grouped.setdefault(key, []).append(lesson)
    merged: list[MetaLesson] = []
    for rows in grouped.values():
        latest = max(rows, key=lambda item: item.created_at)
        positive = sum(item.positive_cases_count for item in rows)
        counter = sum(item.counterexamples_count for item in rows)
        weight = max(1, positive + counter)
        effect = sum(
            item.estimated_effect
            * max(1, item.positive_cases_count + item.counterexamples_count)
            for item in rows
        ) / sum(
            max(1, item.positive_cases_count + item.counterexamples_count)
            for item in rows
        )
        merged.append(
            MetaLesson(
                lesson=latest.lesson,
                scope=latest.scope,
                supporting_experiment_ids=sorted(
                    {
                        experiment_id
                        for item in rows
                        for experiment_id in item.supporting_experiment_ids
                    }
                ),
                positive_cases_count=positive,
                counterexamples_count=counter,
                estimated_effect=round(effect, 8),
                confidence=round(min(1.0, max(item.confidence for item in rows) * weight / (weight + 2)), 8),
                suggested_mutation_operators=sorted(
                    {
                        operator
                        for item in rows
                        for operator in item.suggested_mutation_operators
                    },
                    key=lambda item: item.value,
                ),
                created_at=latest.created_at,
                superseded_by=latest.superseded_by,
            )
        )
    return sorted(merged, key=lambda item: (-item.confidence, item.scope, item.lesson))


def derive_meta_lessons(
    experiments: Iterable[SchemeExperimentRecord],
    *,
    spec: EvaluationSpec,
) -> tuple[list[MetaLesson], list[MutationRequest]]:
    """Aggregate candidate-level outcomes without exposing per-sample labels."""

    lessons: list[MetaLesson] = []
    requests: list[MutationRequest] = []
    for experiment in experiments:
        evaluation = experiment.evaluation_result
        decision = experiment.admission_decision
        confusion = evaluation.confusion_matrix
        common = {
            "supporting_experiment_ids": [experiment.experiment_id],
            "positive_cases_count": int(confusion.get("tp", 0)),
            "counterexamples_count": int(confusion.get("fp", 0))
            + int(confusion.get("fn", 0)),
            "estimated_effect": decision.utility_difference,
            "confidence": min(
                0.95,
                decision.paired_block_count / max(1, spec.minimum_paired_blocks),
            ),
            "created_at": experiment.completed_at,
        }
        if decision.admitted:
            lessons.append(
                MetaLesson(
                    lesson="Paired admission gates supported this recipe change.",
                    scope="admitted_recipe",
                    suggested_mutation_operators=[MutationOperator.LOCAL_REFINE],
                    **common,
                )
            )
            requests.append(
                MutationRequest(
                    operator=MutationOperator.LOCAL_REFINE,
                    target_fields=["changed_fields"],
                    reason="Explore one bounded refinement while preserving admitted behavior.",
                )
            )
        if evaluation.coverage_rate < spec.minimum_coverage:
            lessons.append(
                MetaLesson(
                    lesson="Candidate coverage remained below the fixed admission floor.",
                    scope="coverage",
                    suggested_mutation_operators=[
                        MutationOperator.SOURCE_EXPAND,
                        MutationOperator.SOURCE_REPLACE,
                    ],
                    **common,
                )
            )
            requests.append(
                MutationRequest(
                    operator=MutationOperator.SOURCE_EXPAND,
                    target_fields=["data_source_specs", "seed_signal_specs"],
                    reason="Raise aggregate blind coverage without reading admission labels.",
                )
            )
        if not decision.confidence_interval or decision.confidence_interval[0] <= 0:
            lessons.append(
                MetaLesson(
                    lesson="Candidate utility did not have a positive paired lower bound.",
                    scope="paired_admission",
                    suggested_mutation_operators=[
                        MutationOperator.COUNTEREXAMPLE_REPAIR,
                        MutationOperator.ORTHOGONAL_REDESIGN,
                    ],
                    **common,
                )
            )
            requests.append(
                MutationRequest(
                    operator=MutationOperator.COUNTEREXAMPLE_REPAIR,
                    target_fields=["seed_signal_specs", "blind_analysis_prompt"],
                    reason="Address aggregate false-positive/false-negative tradeoffs.",
                )
            )
        if evaluation.data_cost_usd + evaluation.token_cost_usd > spec.maximum_cost_usd:
            lessons.append(
                MetaLesson(
                    lesson="Candidate exceeded the fixed evaluation cost ceiling.",
                    scope="cost",
                    suggested_mutation_operators=[MutationOperator.COST_COMPRESS],
                    **common,
                )
            )
            requests.append(
                MutationRequest(
                    operator=MutationOperator.COST_COMPRESS,
                    target_fields=["data_source_specs", "complexity_budget"],
                    reason="Reduce aggregate source and token cost.",
                )
            )
    merged = merge_meta_lessons(lessons)
    unique_requests = {
        (request.operator.value, tuple(request.target_fields), request.reason): request
        for request in requests
    }
    return merged, [
        unique_requests[key]
        for key in sorted(unique_requests)
    ]


def _blind_prompt_leakage_reasons(genome: SchemeGenome) -> list[str]:
    reasons: list[str] = []
    for prompt_name, prompt in (
        ("signal_merge_prompt", genome.signal_merge_prompt),
        ("blind_analysis_prompt", genome.blind_analysis_prompt),
    ):
        forbidden = sorted(
            variable
            for variable in prompt.variables
            if _normalize_text(variable) in _BLIND_FORBIDDEN_VARIABLES
        )
        if forbidden:
            reasons.append(f"{prompt_name} exposes forbidden variables: {forbidden}")
        placeholders = {
            _normalize_text(match)
            for match in re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", prompt.template)
        }
        leaked = sorted(placeholders & _BLIND_FORBIDDEN_VARIABLES)
        if leaked:
            reasons.append(f"{prompt_name} contains forbidden placeholders: {leaked}")
        if prompt.model_constraints.get("web_tools_allowed") is not False:
            reasons.append(f"{prompt_name} must keep web tools disabled")
    expected_output_fields = {
        "probability_of_surge",
        "decision",
        "confidence",
        "supporting_signals",
        "contradicting_signals",
        "missing_critical_information",
        "difficulty_codes",
        "evidence_source_ids",
    }
    actual_output_fields = set(genome.blind_analysis_prompt.output_json_schema)
    if actual_output_fields != expected_output_fields:
        reasons.append("blind_analysis_prompt must preserve the fixed prediction fields")
    if genome.blind_analysis_prompt.model_constraints.get("identity_masked") is not True:
        reasons.append("blind_analysis_prompt must require masked identity")
    return reasons


def _niche_for_genome(genome: SchemeGenome) -> str:
    source_family = str(
        genome.metadata.get(
            "dominant_source_family",
            genome.data_source_specs[0].source_family,
        )
    )
    signal_family = str(
        genome.metadata.get(
            "dominant_signal_family",
            genome.seed_signal_specs[0].signal_id if genome.seed_signal_specs else "none",
        )
    )
    context = float(genome.complexity_budget["max_context_tokens"])
    complexity_bucket = "small" if context <= 2500 else "medium" if context <= 5000 else "large"
    cost = sum(source.estimated_cost_usd for source in genome.data_source_specs)
    cost_bucket = "free" if cost == 0 else "low" if cost <= 1 else "high"
    orientation = str(genome.metadata.get("orientation", "balanced"))
    sector = str(genome.metadata.get("specialist_sector", "universal"))
    return "|".join(
        (source_family, signal_family, complexity_bucket, cost_bucket, orientation, sector)
    )


def _dominates(left: ArchiveEntry, right: ArchiveEntry) -> bool:
    left_values = (
        left.evaluation.pr_auc,
        left.evaluation.precision_at_k,
        left.evaluation.recall_at_k,
        -left.evaluation.brier_score,
        -left.evaluation.data_cost_usd - left.evaluation.token_cost_usd,
        -left.complexity,
    )
    right_values = (
        right.evaluation.pr_auc,
        right.evaluation.precision_at_k,
        right.evaluation.recall_at_k,
        -right.evaluation.brier_score,
        -right.evaluation.data_cost_usd - right.evaluation.token_cost_usd,
        -right.complexity,
    )
    return all(left_value >= right_value for left_value, right_value in zip(left_values, right_values)) and any(
        left_value > right_value for left_value, right_value in zip(left_values, right_values)
    )


def _genome_tokens(genome: SchemeGenome) -> set[str]:
    data = genome.to_dict()
    for key in (
        "genome_id",
        "parent_ids",
        "generation",
        "mutation_operator",
        "hypothesis_of_change",
        "changed_fields",
        "expected_benefit",
        "possible_side_effects",
        "falsification_test",
    ):
        data.pop(key, None)
    return set(re.findall(r"[a-z0-9_]+", json.dumps(data, sort_keys=True).lower()))


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def _hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
