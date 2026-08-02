"""Bounded, proposal-only, resumable information-scheme evolution.

This controller reuses the repository's data, packet, and provider boundaries.
It owns only candidate validation, per-sample checkpoints, fixed evaluation,
Top-K selection, and structured experiment memory.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from stock_opportunity_agent.models import SerializableRecord, ValidationError
from stock_opportunity_agent.research.scheme_evolution_evaluation import (
    _genome_complexity,
    build_labeled_sample,
    build_walk_forward_folds,
    evaluate_predictions,
    prediction_agreement,
    realized_max_multiple,
    validate_folds,
)
from stock_opportunity_agent.research.scheme_evolution_records import (
    SCHEME_EVOLUTION_SCHEMA_VERSION,
    _BLIND_FORBIDDEN_VARIABLES,
    AdmissionDecision,
    BlindSample,
    DataSourceSpec,
    DataSplitSpec,
    EvaluationContract,
    EvaluationSpec,
    EvolutionFold,
    FixedEvolutionSpec,
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
    """Deterministic candidate provider for tests and offline vertical slices."""

    def __init__(self, candidates: Iterable[SchemeGenome]) -> None:
        self.candidates = list(candidates)

    def propose(
        self,
        parents: list[SchemeGenome],
        meta_memory: list[MetaLesson],
        mutation_requests: list[MutationRequest],
        count: int,
    ) -> list[SchemeGenome]:
        """Return configured candidates without reading validation labels."""

        del parents, meta_memory, mutation_requests
        return self.candidates[:count]


class FileSchemeProposer:
    """Load Codex- or human-authored candidates from reviewed JSON."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def propose(
        self,
        parents: list[SchemeGenome],
        meta_memory: list[MetaLesson],
        mutation_requests: list[MutationRequest],
        count: int,
    ) -> list[SchemeGenome]:
        """Return candidates related to the active parents, capped by ``count``."""

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
        return [
            candidate
            for candidate in candidates
            if not candidate.parent_ids or parent_ids.intersection(candidate.parent_ids)
        ][:count]


@dataclass(frozen=True)
class CandidateRejection(SerializableRecord):
    """Auditable rejection produced before expensive evaluation."""

    genome_id: str
    reasons: list[str]


class CandidateValidator:
    """Static schema, leakage, budget, fixed-output, and duplicate validation."""

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
    """Network-free A/B/C evaluator used only to prove orchestration."""

    def __init__(self, *, interrupt_after: int | None = None) -> None:
        self.observed_blind_inputs: list[dict[str, Any]] = []
        self.interrupt_after = interrupt_after
        self.predict_call_count = 0

    @property
    def evaluator_fingerprint(self) -> str:
        return "mock-abc-scheme-evaluator-v0.2"

    def materialize(self, genome: SchemeGenome, fold: EvolutionFold) -> MaterializedScheme:
        """Freeze seed signals and hash continuous discovery labels."""

        materialization_input = {
            "genome": genome_recipe_hash(genome),
            "fold_id": fold.fold_id,
            "discovery": [
                {
                    "sample_id": sample.sample_id,
                    "realized_max_multiple": sample.realized_max_multiple,
                    "true_class": sample.true_class,
                    "is_surge": sample.is_surge,
                }
                for sample in fold.discovery_samples
            ],
        }
        input_hash = _hash_json(materialization_input)
        output_hash = _hash_json(
            {
                "retained_signal_ids": [
                    signal.signal_id for signal in genome.seed_signal_specs
                ],
                "input_hash": input_hash,
            }
        )
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

    def restore(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        fold: EvolutionFold,
    ) -> None:
        """Mock materialization has no transient state to restore."""

        del genome, materialized, fold

    def extract(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        sample: BlindSample,
    ) -> dict[str, Any]:
        """Return deterministic label-free mock signal observations."""

        del genome
        return {
            "sample_id": sample.sample_id,
            "materialized_scheme_id": materialized.materialized_scheme_id,
            "signal_observations": [
                {
                    "signal_id": signal.signal_id,
                    "observed_strength": float(sample.features.get("signal_strength", 0.0)),
                    "evidence_source_ids": list(sample.evidence_source_ids),
                }
                for signal in materialized.retained_signals
            ],
        }

    def predict(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        sample: BlindSample,
    ) -> PredictionRecord:
        """Classify deterministic label-free signal strength into A/B/C."""

        self.predict_call_count += 1
        if self.interrupt_after is not None and self.predict_call_count > self.interrupt_after:
            raise KeyboardInterrupt
        blind_payload = sample.to_dict()
        if set(blind_payload) & _BLIND_FORBIDDEN_VARIABLES:
            raise ValidationError("blind sample unexpectedly contains label fields")
        self.observed_blind_inputs.append(blind_payload)
        strength = float(sample.features.get("signal_strength", 0.0))
        ordinal_shift = int(genome.metadata.get("ordinal_shift", 0))
        shift_min_strength = float(genome.metadata.get("ordinal_shift_min_strength", 0.5))
        class_index = 2 if strength >= 0.8 else 1 if strength >= 0.5 else 0
        class_index = min(
            2,
            max(0, class_index + (ordinal_shift if strength >= shift_min_strength else 0)),
        )
        predicted_class = ("A", "B", "C")[class_index]
        confidence = "high" if strength >= 0.85 or strength <= 0.15 else "medium"
        difficulty = "high" if 0.4 <= strength <= 0.6 else "low"
        return PredictionRecord(
            genome_id=genome.genome_id,
            materialized_scheme_id=materialized.materialized_scheme_id,
            fold_id=materialized.fold_id,
            sample_id=sample.sample_id,
            prediction_time=sample.prediction_time,
            predicted_class=predicted_class,
            is_surge=predicted_class in {"B", "C"},
            confidence_level=confidence,
            difficulty_level=difficulty,
            difficulty_reasons=["near_class_boundary"] if difficulty == "high" else [],
            decisive_signals=[
                signal.signal_id for signal in materialized.retained_signals
            ],
            conflicting_signals=[],
            missing_information=[] if difficulty == "low" else ["event_materiality"],
            flip_conditions=["materially different event evidence"],
            evidence_source_ids=list(sample.evidence_source_ids),
            model_metadata={
                "provider": "local_mock",
                "model": "deterministic_abc",
                "temperature": 0.0,
                "token_cost_usd": 0.0,
                "data_cost_usd": sum(
                    source.estimated_cost_usd for source in genome.data_source_specs
                ),
                "latency_ms": 0.0,
            },
            input_hash="pending-engine-hash",
            raw_response_location=None,
        )


@dataclass(frozen=True)
class ArchiveEntry(SerializableRecord):
    """One evaluated scheme retained by fixed binary-F1 Top-K selection."""

    genome: SchemeGenome
    evaluation: SchemeEvaluationResult
    binary_predictions_by_sample: dict[str, bool]


class TopKArchive:
    """Keep behaviorally distinct schemes ordered by the fixed v1 tie-breaks."""

    def __init__(self, entries: Iterable[ArchiveEntry] = ()) -> None:
        self._entries = list(entries)

    @property
    def entries(self) -> list[ArchiveEntry]:
        """Return the current selected schemes in ranking order."""

        return list(self._entries)

    def select(
        self,
        candidates: Iterable[ArchiveEntry],
        *,
        top_k: int,
        similarity_threshold: float,
        maximum_cost_usd: float,
    ) -> list[ArchiveEntry]:
        """Merge, rank, and behaviorally deduplicate evaluated schemes."""

        by_id = {entry.genome.genome_id: entry for entry in [*self._entries, *candidates]}
        ranked = sorted(by_id.values(), key=_archive_sort_key)
        selected: list[ArchiveEntry] = []
        for entry in ranked:
            total_cost = entry.evaluation.data_cost_usd + entry.evaluation.token_cost_usd
            if total_cost > maximum_cost_usd:
                continue
            duplicate = False
            for retained in selected:
                agreement = prediction_agreement(
                    entry.binary_predictions_by_sample,
                    retained.binary_predictions_by_sample,
                )
                if agreement is not None and agreement >= similarity_threshold:
                    duplicate = True
                    break
            if duplicate:
                continue
            selected.append(entry)
            if len(selected) >= top_k:
                break
        self._entries = selected
        return self.entries

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON artifact for the current Top-K."""

        return {
            "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
            "selection_metric": "binary_f1",
            "entries": [entry.to_dict() for entry in self._entries],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TopKArchive":
        """Restore an archive written by :meth:`to_dict`."""

        rows = data.get("entries", [])
        if not isinstance(rows, list):
            raise ValidationError("archive entries must be a list")
        return cls(ArchiveEntry.from_dict(row) for row in rows)


# Compatibility import for callers of the v0.1 name; active semantics are Top-K.
QualityDiversityArchive = TopKArchive


class EvolutionStateStore:
    """Atomic run store with append-only events and per-sample checkpoints."""

    _DIRECTORIES = (
        "schemes",
        "frozen_signals",
        "signal_extractions",
        "predictions",
        "evaluations",
        "prompts",
        "cache",
        "experiments",
        "rounds",
    )

    def __init__(self, root: str | Path, *, run_id: str | None = None) -> None:
        self.root = Path(root)
        self.run_id = run_id or self.root.name

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    def initialize(
        self,
        fixed_spec: FixedEvolutionSpec,
        *,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        """Create or verify a run and freeze its evaluation contract."""

        self.root.mkdir(parents=True, exist_ok=True)
        for name in self._DIRECTORIES:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        contract_path = self.root / "evaluation_contract.json"
        if contract_path.exists():
            existing = EvaluationContract.from_dict(_read_json(contract_path))
            if existing.content_hash != fixed_spec.evaluation_contract.content_hash:
                raise ValidationError("frozen evaluation contract does not match resume request")
        else:
            _write_json(contract_path, fixed_spec.evaluation_contract.to_dict())
        config_path = self.root / "config.json"
        if config_path.exists():
            existing_config = _read_json(config_path)
            for key in (
                "evolution_model",
                "judge_model",
                "evolution_model_registration",
                "judge_model_registration",
            ):
                requested = (config or {}).get(key)
                if (
                    requested is not None
                    and key in existing_config
                    and existing_config.get(key) != requested
                ):
                    raise ValidationError(
                        f"frozen run model configuration changed on resume: {key}"
                    )
            missing_config = {
                key: value
                for key, value in dict(config or {}).items()
                if key not in existing_config
                and key
                in {
                    "evolution_model",
                    "judge_model",
                    "evolution_model_registration",
                    "judge_model_registration",
                }
            }
            if missing_config:
                _write_json(config_path, {**existing_config, **missing_config})
        else:
            _write_json(
                config_path,
                {
                    "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                    "run_id": self.run_id,
                    "fixed_spec_hash": fixed_spec.content_hash,
                    "random_seed": (config or {}).get("random_seed", 42),
                    **dict(config or {}),
                },
            )
        if not (self.root / "memory.json").exists():
            _write_json(self.root / "memory.json", {"lessons": []})
        if not (self.root / "events.jsonl").exists():
            (self.root / "events.jsonl").touch()
        if not self.state_path.exists():
            self._write_state(
                {
                    "run_id": self.run_id,
                    "current_iteration": 0,
                    "last_completed_iteration": 0,
                    "status": "initialized",
                    "top_k_scheme_ids": [],
                    "current_tasks": [],
                    "last_checkpoint_at": _now(),
                    "fixed_spec_hash": fixed_spec.content_hash,
                    "proposal_status": "proposal_only_pending_human_review",
                    "final_test_accessed": False,
                }
            )
            self.append_event("run_initialized", {"fixed_spec_hash": fixed_spec.content_hash})
        else:
            state = self.load_state()
            if state.get("fixed_spec_hash") != fixed_spec.content_hash:
                raise ValidationError("fixed evolution spec changed since run initialization")

    def load_state(self) -> dict[str, Any]:
        """Read current atomic state."""

        if not self.state_path.exists():
            raise ValidationError("run is not initialized")
        return _read_json(self.state_path)

    def begin_iteration(self, iteration: int, *, resume: bool) -> None:
        """Start an iteration and recover interrupted running tasks as pending."""

        state = self.load_state()
        tasks = list(state.get("current_tasks", [])) if resume else []
        if resume:
            tasks = [
                {**task, "status": "pending" if task.get("status") == "running" else task.get("status")}
                for task in tasks
            ]
        state.update(
            {
                "current_iteration": iteration,
                "status": "running",
                "current_tasks": tasks,
                "last_checkpoint_at": _now(),
            }
        )
        self._write_state(state)
        self.append_event("iteration_started", {"iteration": iteration, "resume": resume})

    def checkpoint_task(
        self,
        task_id: str,
        *,
        status: str,
        context_hash: str,
        error: str | None = None,
    ) -> None:
        """Atomically record one prediction task transition."""

        if status not in {"pending", "running", "completed", "failed"}:
            raise ValidationError("invalid task status")
        state = self.load_state()
        by_id = {task["task_id"]: task for task in state.get("current_tasks", [])}
        by_id[task_id] = {
            "task_id": task_id,
            "context_hash": context_hash,
            "status": status,
            "error": error,
            "updated_at": _now(),
        }
        state["current_tasks"] = [by_id[key] for key in sorted(by_id)]
        state["last_checkpoint_at"] = _now()
        self._write_state(state)
        self.append_event(
            "task_status_changed",
            {"task_id": task_id, "context_hash": context_hash, "status": status, "error": error},
        )

    def pause(self, reason: str) -> None:
        """Persist a resumable pause, including KeyboardInterrupt."""

        state = self.load_state()
        state["status"] = "paused_by_operator"
        state["last_checkpoint_at"] = _now()
        self._write_state(state)
        self.append_event("run_paused", {"reason": reason})

    def fail(self, error: str) -> None:
        """Persist a failed but resumable state."""

        state = self.load_state()
        state["status"] = "failed"
        state["last_checkpoint_at"] = _now()
        self._write_state(state)
        self.append_event("run_failed", {"error": error})

    def complete(self, top_k_scheme_ids: Iterable[str]) -> None:
        """Mark the current bounded run complete."""

        state = self.load_state()
        state.update(
            {
                "status": "completed",
                "last_completed_iteration": int(state.get("current_iteration", 0)),
                "top_k_scheme_ids": list(top_k_scheme_ids),
                "last_checkpoint_at": _now(),
            }
        )
        self._write_state(state)
        self.append_event("iteration_completed", {"top_k_scheme_ids": state["top_k_scheme_ids"]})

    def append_event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        """Append one JSON event without rewriting prior history."""

        event = {"timestamp": _now(), "event_type": event_type, **dict(payload)}
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()

    def write_scheme(self, genome: SchemeGenome) -> None:
        """Persist a candidate and all prompt contracts separately."""

        name = _safe_name(genome.genome_id)
        _write_json(self.root / "schemes" / f"{name}.json", genome.to_dict())
        prompt_dir = self.root / "prompts" / name
        _write_json(prompt_dir / "signal_discovery.json", genome.contrastive_discovery_prompt.to_dict())
        _write_json(prompt_dir / "signal_merge.json", genome.signal_merge_prompt.to_dict())
        _write_json(prompt_dir / "analysis_system.json", genome.blind_analysis_prompt.to_dict())

    def write_objective_prompt(self, text: str) -> None:
        """Freeze the static candidate-generation objective in the run directory."""

        if not text.strip():
            raise ValidationError("evolution objective prompt must be non-empty")
        path = self.root / "prompts" / "evolution_objective.md"
        temporary = path.with_suffix(".md.tmp")
        temporary.write_text(text.rstrip() + "\n", encoding="utf-8")
        temporary.replace(path)

    def fold_dir(self, context_hash: str) -> Path:
        return self.root / "experiments" / context_hash

    def load_materialized(self, context_hash: str) -> MaterializedScheme | None:
        path = self.fold_dir(context_hash) / "materialized_scheme.json"
        return MaterializedScheme.from_dict(_read_json(path)) if path.exists() else None

    def write_materialized(self, context_hash: str, materialized: MaterializedScheme) -> None:
        """Persist frozen signals before any validation prediction."""

        payload = materialized.to_dict()
        _write_json(self.fold_dir(context_hash) / "materialized_scheme.json", payload)
        _write_json(
            self.root
            / "frozen_signals"
            / _safe_name(materialized.genome_id)
            / f"{_safe_name(materialized.fold_id)}.json",
            payload,
        )

    def load_prediction(
        self,
        context_hash: str,
        sample_id: str,
        *,
        input_hash: str,
    ) -> PredictionRecord | None:
        path = self._prediction_path(context_hash, sample_id)
        if not path.exists():
            return None
        prediction = PredictionRecord.from_dict(_read_json(path))
        if prediction.input_hash != input_hash:
            return None
        return prediction

    def write_prediction(self, context_hash: str, prediction: PredictionRecord) -> Path:
        """Atomically persist one stock prediction immediately after completion."""

        path = self._prediction_path(context_hash, prediction.sample_id)
        payload = prediction.to_dict()
        _write_json(path, payload)
        _write_json(
            self.root
            / "predictions"
            / _safe_name(prediction.genome_id)
            / _safe_name(prediction.fold_id)
            / f"{_safe_name(prediction.sample_id)}.json",
            payload,
        )
        return path

    def load_signal_extraction(
        self,
        context_hash: str,
        sample_id: str,
        *,
        input_hash: str,
    ) -> dict[str, Any] | None:
        """Reuse one extraction only when its exact label-free input matches."""

        path = self._extraction_path(context_hash, sample_id)
        if not path.exists():
            return None
        payload = _read_json(path)
        return payload if payload.get("input_hash") == input_hash else None

    def write_signal_extraction(
        self,
        context_hash: str,
        sample_id: str,
        payload: Mapping[str, Any],
    ) -> Path:
        """Atomically persist one frozen-signal extraction before analysis."""

        path = self._extraction_path(context_hash, sample_id)
        _write_json(path, dict(payload))
        _write_json(
            self.root
            / "signal_extractions"
            / context_hash
            / f"{_safe_name(sample_id)}.json",
            dict(payload),
        )
        return path

    def write_evaluation(
        self,
        context_hash: str,
        evaluation: SchemeEvaluationResult,
        *,
        context: Mapping[str, Any],
    ) -> None:
        """Write label-aware evaluation only after prediction files exist."""

        prediction_dir = self.fold_dir(context_hash) / "predictions"
        if not prediction_dir.exists() or not any(prediction_dir.glob("*.json")):
            raise ValidationError("predictions must be persisted before evaluation")
        _write_json(self.fold_dir(context_hash) / "evaluation.json", evaluation.to_dict())
        _write_json(
            self.fold_dir(context_hash) / "context.json",
            {**dict(context), "context_hash": context_hash},
        )
        _write_json(
            self.root
            / "evaluations"
            / f"{_safe_name(evaluation.genome_id)}-{context_hash[:12]}.json",
            evaluation.to_dict(),
        )

    def write_run_artifacts(
        self,
        result: "EvolutionRunResult",
        *,
        fixed_spec: FixedEvolutionSpec,
        rejections: Iterable[CandidateRejection],
    ) -> dict[str, Path]:
        """Write Top-K, experiments, meta-memory, and compact report."""

        rejection_rows = list(rejections)
        paths = {
            "state": self.state_path,
            "top_k": self.root / "top_k.json",
            "experiments": self.root / "scheme_experiments.json",
            "meta_lessons": self.root / "memory.json",
            "report": self.root / "experiment_report.json",
            "history": self.root / "evolution_history.json",
        }
        _write_json(paths["top_k"], result.archive.to_dict())
        _write_json(
            paths["experiments"],
            {
                "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                "experiments": [item.to_dict() for item in result.experiments],
                "candidate_rejections": [item.to_dict() for item in rejection_rows],
            },
        )
        _write_json(
            paths["meta_lessons"],
            {
                "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                "lessons": [item.to_dict() for item in result.meta_lessons],
                "next_mutation_requests": [item.to_dict() for item in result.mutation_requests],
                "contains_validation_diagnostics": True,
                "contains_final_test_labels": False,
            },
        )
        _write_json(
            paths["report"],
            {
                "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                "fixed_spec_hash": fixed_spec.content_hash,
                "evaluation_contract_hash": fixed_spec.evaluation_contract.content_hash,
                "incumbent_genome_id": result.incumbent.genome_id,
                "top_k_scheme_ids": [entry.genome.genome_id for entry in result.top_k],
                "evaluated_candidate_count": len(result.experiments),
                "selection_metric": "binary_f1",
                "synthetic_or_mock_result_is_effectiveness_evidence": False,
                "final_test_accessed": False,
                "proposal_status": "proposal_only_pending_human_review",
            },
        )
        self._write_evolution_round(
            paths["history"],
            result,
            rejection_count=len(rejection_rows),
        )
        paths["round_checkpoint"] = self.write_round_checkpoint(
            result,
            fixed_spec=fixed_spec,
        )
        return paths

    def write_round_checkpoint(
        self,
        result: "EvolutionRunResult",
        *,
        fixed_spec: FixedEvolutionSpec,
    ) -> Path:
        """Write one immutable, branchable checkpoint for the active round."""

        state = self.load_state()
        iteration = int(state.get("current_iteration", 0))
        if iteration < 1:
            raise ValidationError("cannot checkpoint an evolution round before it starts")
        path = self.round_checkpoint_path(iteration)
        payload = {
            "schema_version": "scheme-evolution-round-checkpoint-v1",
            "run_id": self.run_id,
            "iteration": iteration,
            "created_at": _now(),
            "fixed_spec_hash": fixed_spec.content_hash,
            "incumbent": result.incumbent.to_dict(),
            "archive": result.archive.to_dict(),
            "meta_lessons": [item.to_dict() for item in result.meta_lessons],
            "mutation_requests": [item.to_dict() for item in result.mutation_requests],
            "contains_final_test_metrics": False,
        }
        if path.exists():
            existing = _read_json(path)
            comparable_existing = dict(existing)
            comparable_payload = dict(payload)
            comparable_existing.pop("created_at", None)
            comparable_payload.pop("created_at", None)
            if comparable_existing != comparable_payload:
                raise ValidationError("completed round checkpoint is immutable")
            return path
        _write_json(path, payload)
        return path

    def round_checkpoint_path(self, iteration: int) -> Path:
        """Return the canonical checkpoint path for one positive round number."""

        if iteration < 1:
            raise ValidationError("round checkpoint iteration must be positive")
        return self.root / "rounds" / f"round-{iteration:04d}" / "checkpoint.json"

    def seed_branch(
        self,
        checkpoint: Mapping[str, Any],
        *,
        parent_run_dir: str | Path,
        parent_history: Mapping[str, Any],
    ) -> Path:
        """Seed a new trajectory from one completed parent round without mutation."""

        state = self.load_state()
        if int(state.get("current_iteration", 0)) != 0:
            raise ValidationError("branch target trajectory has already started")
        iteration = _validated_checkpoint_iteration(checkpoint)
        if checkpoint.get("fixed_spec_hash") != state.get("fixed_spec_hash"):
            raise ValidationError("branch checkpoint fixed spec does not match child trajectory")
        archive = TopKArchive.from_dict(_mapping(checkpoint.get("archive"), "archive"))
        incumbent = SchemeGenome.from_dict(
            _mapping(checkpoint.get("incumbent"), "incumbent")
        )
        if not archive.entries or archive.entries[0].genome.genome_id != incumbent.genome_id:
            raise ValidationError("branch checkpoint incumbent does not match archive best")
        parent_root = Path(parent_run_dir)
        inherited_context_count = self._inherit_branch_contexts(
            parent_root,
            genome_ids={entry.genome.genome_id for entry in archive.entries},
        )
        lineage = {
            "schema_version": "scheme-evolution-trajectory-lineage-v1",
            "trajectory_id": self.run_id,
            "parent_trajectory_id": str(checkpoint.get("run_id") or parent_root.name),
            "parent_run_directory": str(parent_root),
            "parent_round": iteration,
            "inherited_evaluation_context_count": inherited_context_count,
            "parent_checkpoint": str(
                parent_root / "rounds" / f"round-{iteration:04d}" / "checkpoint.json"
            ),
            "created_at": _now(),
        }
        lineage_path = self.root / "trajectory_lineage.json"
        _write_json(lineage_path, lineage)
        _write_json(self.root / "top_k.json", archive.to_dict())
        _write_json(
            self.root / "memory.json",
            {
                "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                "lessons": list(checkpoint.get("meta_lessons", [])),
                "next_mutation_requests": list(checkpoint.get("mutation_requests", [])),
                "contains_validation_diagnostics": True,
                "contains_final_test_labels": False,
            },
        )
        for entry in archive.entries:
            self.write_scheme(entry.genome)
        inherited_rounds = []
        raw_rounds = parent_history.get("rounds", [])
        if not isinstance(raw_rounds, list):
            raise ValidationError("parent evolution history rounds must be a list")
        for row in raw_rounds:
            if not isinstance(row, Mapping):
                raise ValidationError("parent evolution history round must be an object")
            row_iteration = int(row.get("iteration", 0))
            if row_iteration <= iteration:
                inherited_rounds.append(
                    {
                        **dict(row),
                        "source": "inherited_round",
                        "inherited_from_trajectory": lineage["parent_trajectory_id"],
                    }
                )
        _write_json(
            self.root / "evolution_history.json",
            {
                "schema_version": "scheme-evolution-history-v1",
                "run_id": self.run_id,
                "primary_metric": "binary_f1",
                "contains_final_test_metrics": False,
                "lineage": lineage,
                "rounds": inherited_rounds,
            },
        )
        inherited_checkpoint = {
            **dict(checkpoint),
            "run_id": self.run_id,
            "inherited_from_trajectory": lineage["parent_trajectory_id"],
            "inherited_from_round": iteration,
        }
        _write_json(self.round_checkpoint_path(iteration), inherited_checkpoint)
        state.update(
            {
                "current_iteration": iteration,
                "last_completed_iteration": iteration,
                "status": "initialized_from_branch",
                "top_k_scheme_ids": [
                    entry.genome.genome_id for entry in archive.entries
                ],
                "current_tasks": [],
                "last_checkpoint_at": _now(),
                "parent_trajectory_id": lineage["parent_trajectory_id"],
                "parent_round": iteration,
            }
        )
        self._write_state(state)
        self.append_event(
            "trajectory_branched",
            {
                "parent_trajectory_id": lineage["parent_trajectory_id"],
                "parent_round": iteration,
            },
        )
        return lineage_path

    def _inherit_branch_contexts(
        self,
        parent_root: Path,
        *,
        genome_ids: set[str],
    ) -> int:
        """Copy exact parent contexts that match genomes in the branch archive."""

        inherited = 0
        for source in sorted((parent_root / "experiments").glob("*")):
            materialized_path = source / "materialized_scheme.json"
            if (
                source.is_symlink()
                or not source.is_dir()
                or not materialized_path.exists()
            ):
                continue
            materialized = _read_json(materialized_path)
            if str(materialized.get("genome_id") or "") not in genome_ids:
                continue
            shutil.copytree(
                source,
                self.root / "experiments" / source.name,
                dirs_exist_ok=True,
            )
            inherited += 1
        return inherited

    def _write_evolution_round(
        self,
        path: Path,
        result: "EvolutionRunResult",
        *,
        rejection_count: int,
    ) -> None:
        """Atomically upsert one development-only metric snapshot by iteration."""

        state = self.load_state()
        iteration = int(state.get("current_iteration", 0))
        if iteration < 1:
            raise ValidationError("cannot record evolution metrics before an iteration starts")
        if path.exists():
            history = _read_json(path)
        else:
            history = {
                "schema_version": "scheme-evolution-history-v1",
                "run_id": self.run_id,
                "primary_metric": "binary_f1",
                "contains_final_test_metrics": False,
                "rounds": [],
            }
        if history.get("schema_version") != "scheme-evolution-history-v1":
            raise ValidationError("unsupported evolution history schema")
        if history.get("primary_metric") != "binary_f1":
            raise ValidationError("evolution history primary metric must remain binary_f1")
        if history.get("contains_final_test_metrics") is not False:
            raise ValidationError("evolution history must exclude final-test metrics")
        existing_rounds = history.get("rounds", [])
        if not isinstance(existing_rounds, list):
            raise ValidationError("evolution history rounds must be a list")
        if not result.top_k:
            raise ValidationError("evolution history requires a retained archive entry")
        archive_best = result.top_k[0]
        completed_times = [item.completed_at.isoformat() for item in result.experiments]
        snapshot = {
            "iteration": iteration,
            "completed_at": max(completed_times) if completed_times else _now(),
            "source": "native_round",
            "incumbent_genome_id": result.incumbent.genome_id,
            "archive_best_genome_id": archive_best.genome.genome_id,
            "archive_best_metrics": _dashboard_metrics(archive_best.evaluation),
            "candidate_count": len(result.experiments),
            "rejection_count": rejection_count,
            "candidates": [
                {
                    "genome_id": item.candidate_genome_id,
                    "parent_genome_ids": list(item.parent_genome_ids),
                    "admitted": item.admission_decision.admitted,
                    "admission_status": item.admission_decision.status,
                    "metrics": _dashboard_metrics(item.evaluation_result),
                }
                for item in result.experiments
            ],
        }
        rounds_by_iteration: dict[int, Mapping[str, Any]] = {}
        for row in existing_rounds:
            if not isinstance(row, Mapping):
                raise ValidationError("evolution history round must be an object")
            try:
                existing_iteration = int(row.get("iteration", 0))
            except (TypeError, ValueError) as exc:
                raise ValidationError("evolution history iteration must be an integer") from exc
            if existing_iteration < 1:
                raise ValidationError("evolution history iteration must be positive")
            if existing_iteration in rounds_by_iteration:
                raise ValidationError("evolution history iteration must be unique")
            rounds_by_iteration[existing_iteration] = row
        rounds_by_iteration[iteration] = snapshot
        history.update(
            {
                "schema_version": "scheme-evolution-history-v1",
                "run_id": self.run_id,
                "primary_metric": "binary_f1",
                "contains_final_test_metrics": False,
                "rounds": [rounds_by_iteration[key] for key in sorted(rounds_by_iteration)],
            }
        )
        _write_json(path, history)

    def write_final_test_artifacts(
        self,
        evaluation: SchemeEvaluationResult,
        predictions: Iterable[PredictionRecord],
        extractions: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Path]:
        """Persist an explicitly invoked one-shot final-test result separately."""

        base = self.root / "final_test"
        prediction_rows = list(predictions)
        for prediction in prediction_rows:
            _write_json(
                base / "predictions" / f"{_safe_name(prediction.sample_id)}.json",
                prediction.to_dict(),
            )
        for sample_id, extraction in extractions.items():
            _write_json(
                base / "signal_extractions" / f"{_safe_name(sample_id)}.json",
                dict(extraction),
            )
        paths = {
            "evaluation": base / "evaluation.json",
            "manifest": base / "manifest.json",
        }
        _write_json(paths["evaluation"], evaluation.to_dict())
        _write_json(
            paths["manifest"],
            {
                "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                "explicit_final_test_command": True,
                "genome_id": evaluation.genome_id,
                "sample_count": evaluation.sample_count,
                "prediction_count": len(prediction_rows),
            },
        )
        state = self.load_state()
        state["final_test_accessed"] = True
        state["last_checkpoint_at"] = _now()
        self._write_state(state)
        self.append_event(
            "final_test_completed",
            {"genome_id": evaluation.genome_id, "sample_count": evaluation.sample_count},
        )
        return paths

    def _prediction_path(self, context_hash: str, sample_id: str) -> Path:
        return self.fold_dir(context_hash) / "predictions" / f"{_safe_name(sample_id)}.json"

    def _extraction_path(self, context_hash: str, sample_id: str) -> Path:
        return self.fold_dir(context_hash) / "signal_extractions" / f"{_safe_name(sample_id)}.json"

    def _write_state(self, state: Mapping[str, Any]) -> None:
        _write_json(self.state_path, dict(state))


@dataclass(frozen=True)
class EvolutionRunResult:
    """Result of one bounded generation."""

    incumbent: SchemeGenome
    top_k: list[ArchiveEntry]
    experiments: list[SchemeExperimentRecord]
    archive: TopKArchive
    rejections: list[CandidateRejection]
    meta_lessons: list[MetaLesson]
    mutation_requests: list[MutationRequest]
    artifact_paths: dict[str, Path]


class SchemeEvolutionEngine:
    """Evaluate one candidate batch under a frozen A/B/C contract."""

    def __init__(
        self,
        *,
        proposer: SchemeProposer,
        evaluator: SchemeFoldEvaluator,
        fixed_spec: FixedEvolutionSpec,
        state_store: EvolutionStateStore,
        archive: TopKArchive | None = None,
        validator: CandidateValidator | None = None,
        max_candidates: int = 8,
        max_api_cost_usd: float = 20.0,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        if max_candidates < 1:
            raise ValidationError("max_candidates must be positive")
        if max_api_cost_usd < 0:
            raise ValidationError("max_api_cost_usd cannot be negative")
        self.proposer = proposer
        self.evaluator = evaluator
        self.fixed_spec = fixed_spec
        self.state_store = state_store
        self.archive = archive or TopKArchive()
        self.validator = validator or CandidateValidator()
        self.max_candidates = max_candidates
        self.max_api_cost_usd = max_api_cost_usd
        self.progress = progress

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
        """Run one bounded generation and return proposal-only Top-K schemes."""

        fold_list = list(folds)
        meta_memory_list = list(meta_memory)
        mutation_request_list = list(mutation_requests)
        if not fold_list:
            raise ValidationError("scheme evolution requires at least one fold")
        validate_folds(fold_list, self.fixed_spec)
        self.state_store.initialize(self.fixed_spec)
        state = self.state_store.load_state()
        current_iteration = int(state.get("current_iteration", 0))
        last_completed_iteration = _last_completed_iteration(state)
        resume_current_round = (
            resume
            and current_iteration > last_completed_iteration
            and state.get("status") in {
                "running",
                "failed",
                "paused",
                "paused_by_operator",
            }
        )
        iteration = (
            current_iteration
            if resume_current_round
            else max(incumbent.generation + 1, last_completed_iteration + 1)
        )
        self.state_store.begin_iteration(iteration, resume=resume_current_round)
        self._report(
            f"[scheme-evolution] round={iteration} status=started "
            f"resume_partial={str(resume_current_round).lower()} "
            "scope=development proposal_only=true final_test=false"
        )
        try:
            parents = [entry.genome for entry in self.archive.entries] or [incumbent]
            requested = min(candidate_count, self.max_candidates)
            proposed = self.proposer.propose(
                parents,
                meta_memory_list,
                mutation_request_list,
                requested,
            )
            self._report(
                f"[scheme-evolution] round={iteration} proposed={len(proposed)} "
                f"parents={','.join(parent.genome_id for parent in parents)}"
            )
            for candidate in proposed:
                self._report(
                    f"[scheme-evolution] candidate={candidate.genome_id} "
                    f"parents={','.join(candidate.parent_ids) or 'none'} "
                    f"mutation={candidate.mutation_operator.value} "
                    f"target={candidate.target_failure_type} "
                    f"changed={','.join(candidate.changed_fields) or 'none'}"
                )
                self._report(
                    f"[scheme-evolution] candidate-summary={candidate.genome_id} "
                    f"expected={_compact_progress_text(candidate.expected_benefit)} "
                    f"falsification={_compact_progress_text(candidate.falsification_test)}"
                )
            accepted: list[SchemeGenome] = []
            rejections: list[CandidateRejection] = []
            for candidate in proposed:
                reasons = self.validator.validate(
                    candidate,
                    parents=parents,
                    accepted=accepted,
                )
                if reasons:
                    rejections.append(CandidateRejection(candidate.genome_id, reasons))
                    self._report(
                        f"[scheme-evolution] candidate-rejected={candidate.genome_id} "
                        f"reasons={_compact_progress_text('; '.join(reasons))}"
                    )
                else:
                    accepted.append(candidate)
                    self.state_store.write_scheme(candidate)
                    self._report(
                        f"[scheme-evolution] candidate-accepted={candidate.genome_id}"
                    )
            for parent in parents:
                self.state_store.write_scheme(parent)
            evaluated: dict[str, tuple[SchemeGenome, list[PredictionRecord], SchemeEvaluationResult]] = {}
            for genome in [*parents, *accepted]:
                if genome.genome_id in evaluated:
                    continue
                self._report(
                    f"[scheme-evolution] evaluating={genome.genome_id} "
                    f"folds={len(fold_list)} resume={str(resume).lower()}"
                )
                predictions, evaluation = self._evaluate_genome(
                    genome,
                    fold_list,
                    resume=resume,
                )
                evaluated[genome.genome_id] = (genome, predictions, evaluation)
                self._report(
                    _evaluation_progress_line(
                        "evaluated",
                        evaluation,
                        prefix=f"round={iteration} ",
                    )
                )
            new_entries = [
                ArchiveEntry(
                    genome=genome,
                    evaluation=evaluation,
                    binary_predictions_by_sample=evaluation.binary_predictions_by_sample,
                )
                for genome, _predictions, evaluation in evaluated.values()
            ]
            top_k = self.archive.select(
                new_entries,
                top_k=self.fixed_spec.evaluation_spec.top_k,
                similarity_threshold=self.fixed_spec.evaluation_spec.prediction_similarity_threshold,
                maximum_cost_usd=min(
                    self.fixed_spec.evaluation_spec.maximum_cost_usd,
                    self.max_api_cost_usd,
                ),
            )
            if not top_k:
                raise ValidationError("no scheme remained after fixed cost and Top-K gates")
            for rank, entry in enumerate(top_k, start=1):
                self._report(
                    _evaluation_progress_line(
                        "top-k",
                        entry.evaluation,
                        prefix=f"round={iteration} rank={rank} ",
                    )
                )
            retained_ids = {entry.genome.genome_id for entry in top_k}
            parent_evaluations = {
                parent.genome_id: evaluated[parent.genome_id][2]
                for parent in parents
            }
            experiments = [
                self._experiment_record(
                    candidate,
                    evaluated[candidate.genome_id][2],
                    parent_evaluations,
                    retained=candidate.genome_id in retained_ids,
                    git_commit=git_commit,
                )
                for candidate in accepted
            ]
            for experiment in experiments:
                decision = experiment.admission_decision
                self._report(
                    f"[scheme-evolution] decision={experiment.candidate_genome_id} "
                    f"status={decision.status} retained={str(decision.admitted).lower()} "
                    f"binary_f1_delta={decision.primary_metric_delta:.4f} "
                    f"reasons={_compact_progress_text('; '.join(decision.reasons) or 'none')}"
                )
            lessons, requests = derive_meta_lessons(experiments)
            cumulative_lessons = merge_meta_lessons([*meta_memory_list, *lessons])
            provisional = EvolutionRunResult(
                incumbent=top_k[0].genome,
                top_k=top_k,
                experiments=experiments,
                archive=self.archive,
                rejections=rejections,
                meta_lessons=cumulative_lessons,
                mutation_requests=requests,
                artifact_paths={},
            )
            paths = self.state_store.write_run_artifacts(
                provisional,
                fixed_spec=self.fixed_spec,
                rejections=rejections,
            )
            self.state_store.complete(entry.genome.genome_id for entry in top_k)
            self._report(
                f"[scheme-evolution] round={iteration} status=completed "
                f"incumbent={top_k[0].genome.genome_id} top_k={len(top_k)}"
            )
            return replace(provisional, artifact_paths=paths)
        except KeyboardInterrupt:
            self.state_store.pause("keyboard_interrupt")
            raise
        except Exception as exc:
            self.state_store.fail(f"{type(exc).__name__}: {exc}")
            raise

    def _report(self, message: str) -> None:
        """Emit best-effort observational progress without changing the run."""

        if self.progress is None:
            return
        try:
            self.progress(message)
        except Exception:
            return

    def _evaluate_genome(
        self,
        genome: SchemeGenome,
        folds: list[EvolutionFold],
        *,
        resume: bool,
    ) -> tuple[list[PredictionRecord], SchemeEvaluationResult]:
        all_predictions: list[PredictionRecord] = []
        labels: dict[str, LabeledSample] = {}
        for fold in folds:
            context = {
                "fixed_spec_hash": self.fixed_spec.content_hash,
                "evaluation_contract_hash": self.fixed_spec.evaluation_contract.content_hash,
                "genome_recipe_hash": genome_recipe_hash(genome),
                "fold_id": fold.fold_id,
                "fold_fingerprint": _hash_json(fold.to_dict()),
                "evaluator_fingerprint": self.evaluator.evaluator_fingerprint,
            }
            context_hash = _hash_json(context)
            materialized = self.state_store.load_materialized(context_hash) if resume else None
            if materialized is None:
                materialized = self.evaluator.materialize(genome, fold)
                self.state_store.write_materialized(context_hash, materialized)
            else:
                self.evaluator.restore(genome, materialized, fold)
            fold_predictions: list[PredictionRecord] = []
            sample_total = len(fold.admission_samples)
            for sample_index, sample in enumerate(fold.admission_samples, start=1):
                blind = sample.blind_view()
                extraction_input_hash = _hash_json(
                    {
                        "genome_recipe_hash": genome_recipe_hash(genome),
                        "materialized_output_hash": materialized.output_hash,
                        "blind_sample": blind.to_dict(),
                    }
                )
                extraction = (
                    self.state_store.load_signal_extraction(
                        context_hash,
                        sample.sample_id,
                        input_hash=extraction_input_hash,
                    )
                    if resume
                    else None
                )
                if extraction is None:
                    extraction = {
                        "schema_version": SCHEME_EVOLUTION_SCHEMA_VERSION,
                        "input_hash": extraction_input_hash,
                        "extraction": self.evaluator.extract(
                            genome,
                            materialized,
                            blind,
                        ),
                    }
                    self.state_store.write_signal_extraction(
                        context_hash,
                        sample.sample_id,
                        extraction,
                    )
                input_hash = _hash_json(
                    {
                        "genome_recipe_hash": genome_recipe_hash(genome),
                        "materialized_output_hash": materialized.output_hash,
                        "blind_sample": blind.to_dict(),
                        "signal_extraction_hash": _hash_json(extraction),
                        "evaluator_fingerprint": self.evaluator.evaluator_fingerprint,
                    }
                )
                task_id = f"{genome.genome_id}:{fold.fold_id}:{sample.sample_id}"
                cached = (
                    self.state_store.load_prediction(
                        context_hash,
                        sample.sample_id,
                        input_hash=input_hash,
                    )
                    if resume
                    else None
                )
                if cached is not None:
                    prediction = cached
                    cache_status = "reused"
                    self.state_store.checkpoint_task(
                        task_id,
                        status="completed",
                        context_hash=context_hash,
                    )
                else:
                    cache_status = "new"
                    self.state_store.checkpoint_task(
                        task_id,
                        status="running",
                        context_hash=context_hash,
                    )
                    try:
                        prediction = self.evaluator.predict(genome, materialized, blind)
                    except KeyboardInterrupt:
                        self.state_store.checkpoint_task(
                            task_id,
                            status="pending",
                            context_hash=context_hash,
                            error="keyboard_interrupt",
                        )
                        raise
                    except Exception as exc:
                        self.state_store.checkpoint_task(
                            task_id,
                            status="failed",
                            context_hash=context_hash,
                            error=f"{type(exc).__name__}: {exc}",
                        )
                        raise
                    prediction = replace(prediction, input_hash=input_hash)
                    self.state_store.write_prediction(context_hash, prediction)
                    self.state_store.checkpoint_task(
                        task_id,
                        status="completed",
                        context_hash=context_hash,
                    )
                self._report(
                    f"[scheme-evolution] prediction-persisted genome={genome.genome_id} "
                    f"fold={fold.fold_id} sample={sample_index}/{sample_total} "
                    f"cache={cache_status} class={prediction.predicted_class} "
                    f"confidence={prediction.confidence_level} labels_revealed=false"
                )
                fold_predictions.append(prediction)
                if sample.sample_id in labels:
                    raise ValidationError("validation sample appears in more than one selected fold")
                labels[sample.sample_id] = sample
            fold_evaluation = evaluate_predictions(
                genome,
                fold_predictions,
                {sample.sample_id: sample for sample in fold.admission_samples},
            )
            self.state_store.write_evaluation(
                context_hash,
                fold_evaluation,
                context=context,
            )
            all_predictions.extend(fold_predictions)
        return all_predictions, evaluate_predictions(genome, all_predictions, labels)

    def _experiment_record(
        self,
        candidate: SchemeGenome,
        evaluation: SchemeEvaluationResult,
        parent_evaluations: Mapping[str, SchemeEvaluationResult],
        *,
        retained: bool,
        git_commit: str | None,
    ) -> SchemeExperimentRecord:
        parent_rows = [
            parent_evaluations[parent_id]
            for parent_id in candidate.parent_ids
            if parent_id in parent_evaluations
        ]
        baseline = max(parent_rows, key=lambda row: row.binary_f1) if parent_rows else next(
            iter(parent_evaluations.values())
        )
        deltas = {
            "binary_f1": evaluation.binary_f1 - baseline.binary_f1,
            "binary_precision": evaluation.binary_precision - baseline.binary_precision,
            "binary_recall": evaluation.binary_recall - baseline.binary_recall,
            "multiclass_macro_f1": evaluation.multiclass_macro_f1 - baseline.multiclass_macro_f1,
            "class_c_recall": evaluation.class_c_recall - baseline.class_c_recall,
            "ordinal_distance": evaluation.ordinal_distance - baseline.ordinal_distance,
        }
        total_cost = evaluation.data_cost_usd + evaluation.token_cost_usd
        cost_limit = min(
            self.fixed_spec.evaluation_spec.maximum_cost_usd,
            self.max_api_cost_usd,
        )
        reasons: list[str] = []
        if total_cost > cost_limit:
            reasons.append("candidate exceeded the fixed cost ceiling")
        if not retained:
            reasons.append("candidate was not retained by binary-F1 Top-K behavior deduplication")
        admission = AdmissionDecision(
            status="top_k_retained" if retained and not reasons else "not_retained",
            admitted=retained and not reasons,
            primary_metric_delta=round(deltas["binary_f1"], 8),
            diagnostic_metric_deltas={key: round(value, 8) for key, value in deltas.items()},
            reasons=reasons,
        )
        now = datetime.now(timezone.utc)
        experiment_id = _hash_json(
            {
                "fixed_spec": self.fixed_spec.content_hash,
                "candidate": genome_recipe_hash(candidate),
                "parents": sorted(candidate.parent_ids),
                "evaluator": self.evaluator.evaluator_fingerprint,
            }
        )
        return SchemeExperimentRecord(
            experiment_id=experiment_id,
            parent_genome_ids=list(candidate.parent_ids),
            candidate_genome_id=candidate.genome_id,
            mutation_operator=candidate.mutation_operator,
            data_split_version=self.fixed_spec.split_spec.version,
            evaluation_contract_hash=self.fixed_spec.evaluation_contract.content_hash,
            configuration_hashes={
                "fixed_spec": self.fixed_spec.content_hash,
                "candidate_recipe": genome_recipe_hash(candidate),
                "evaluator": self.evaluator.evaluator_fingerprint,
            },
            evaluation_result=evaluation,
            admission_decision=admission,
            failure_reason=None if admission.admitted else "; ".join(admission.reasons),
            started_at=now,
            completed_at=now,
            git_commit=git_commit,
        )


def _evaluation_progress_line(
    event: str,
    evaluation: SchemeEvaluationResult,
    *,
    prefix: str = "",
) -> str:
    """Render one fixed-metric development evaluation summary."""

    confusion = evaluation.confusion_matrix
    total_cost = evaluation.data_cost_usd + evaluation.token_cost_usd
    return (
        f"[scheme-evolution] {event} {prefix}genome={evaluation.genome_id} "
        f"tp={confusion.get('tp', 0)} fp={confusion.get('fp', 0)} "
        f"tn={confusion.get('tn', 0)} fn={confusion.get('fn', 0)} "
        f"binary_f1={evaluation.binary_f1:.4f} "
        f"class_c_recall={evaluation.class_c_recall:.4f} "
        f"ordinal_distance={evaluation.ordinal_distance:.4f} "
        f"cost_usd={total_cost:.4f} scope=development proposal_only=true"
    )


def _compact_progress_text(value: str, *, maximum_length: int = 240) -> str:
    """Keep free-text progress fields readable on one bounded terminal line."""

    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= maximum_length:
        return compact
    return compact[: maximum_length - 3].rstrip() + "..."


def genome_recipe_hash(genome: SchemeGenome) -> str:
    """Hash evolvable recipe content while ignoring identity and lineage."""

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
        "target_failure_type",
    ):
        data.pop(key, None)
    return _hash_json(data)


def merge_meta_lessons(lessons: Iterable[MetaLesson]) -> list[MetaLesson]:
    """Merge exact diagnosed issues without accumulating free-form reflections."""

    grouped: dict[tuple[str, str], list[MetaLesson]] = {}
    for lesson in lessons:
        key = (_normalize_text(lesson.diagnosed_issue), lesson.status)
        grouped.setdefault(key, []).append(lesson)
    merged: list[MetaLesson] = []
    for rows in grouped.values():
        latest = max(rows, key=lambda item: item.created_at)
        merged.append(
            replace(
                latest,
                supporting_experiment_ids=sorted(
                    {
                        experiment_id
                        for row in rows
                        for experiment_id in row.supporting_experiment_ids
                    }
                ),
                confidence=round(sum(row.confidence for row in rows) / len(rows), 8),
            )
        )
    return sorted(merged, key=lambda item: (-item.confidence, item.status, item.observation))


def derive_meta_lessons(
    experiments: Iterable[SchemeExperimentRecord],
) -> tuple[list[MetaLesson], list[MutationRequest]]:
    """Turn measured errors and child deltas into testable structured memory."""

    lessons: list[MetaLesson] = []
    requests: list[MutationRequest] = []
    for experiment in experiments:
        evaluation = experiment.evaluation_result
        decision = experiment.admission_decision
        failure_counts = evaluation.reflection_summary.get("failure_type_counts", {})
        dominant_failure = max(failure_counts, key=failure_counts.get) if failure_counts else "general"
        affected = [
            row["sample_id"]
            for row in evaluation.error_cases
            if row["failure_type"] == dominant_failure
        ]
        status = (
            "validated"
            if decision.admitted and decision.primary_metric_delta > 0
            else "rejected"
            if decision.primary_metric_delta <= 0
            else "hypothesis"
        )
        observation = (
            f"{dominant_failure} affected {len(affected)} validation cases"
            if affected
            else "No repeated validation error type dominated this candidate"
        )
        operator = (
            MutationOperator.SOURCE_EXPAND
            if dominant_failure in {"false_negative", "class_c_miss"}
            else MutationOperator.COUNTEREXAMPLE_REPAIR
            if dominant_failure == "false_positive"
            else MutationOperator.LOCAL_REFINE
        )
        lesson = MetaLesson(
            observation=observation,
            evidence={
                "affected_cases": len(affected),
                "mostly_affects": dominant_failure,
                "examples": affected[:10],
                "severe_ordinal_errors": sum(
                    row["ordinal_error"] == 2 for row in evaluation.error_cases
                ),
            },
            diagnosed_issue=f"Candidate remains sensitive to {dominant_failure} errors.",
            tested_change=experiment.mutation_operator.value,
            metric_delta=dict(decision.diagnostic_metric_deltas),
            status=status,
            confidence=min(0.95, evaluation.sample_count / (evaluation.sample_count + 10)),
            supporting_experiment_ids=[experiment.experiment_id],
            suggested_mutation_operators=[operator],
            created_at=experiment.completed_at,
        )
        lessons.append(lesson)
        if status != "validated":
            requests.append(
                MutationRequest(
                    operator=operator,
                    target_fields=(
                        ["data_source_specs", "seed_signal_specs"]
                        if operator is MutationOperator.SOURCE_EXPAND
                        else ["seed_signal_specs", "blind_analysis_prompt"]
                    ),
                    reason=observation,
                )
            )
    unique_requests = {
        (item.operator.value, tuple(item.target_fields), item.reason): item
        for item in requests
    }
    return merge_meta_lessons(lessons), [unique_requests[key] for key in sorted(unique_requests)]


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
        "predicted_class",
        "confidence_level",
        "difficulty_level",
        "difficulty_reasons",
        "decisive_signals",
        "conflicting_signals",
        "missing_information",
        "flip_conditions",
        "evidence_source_ids",
    }
    actual_output_fields = set(genome.blind_analysis_prompt.output_json_schema)
    if actual_output_fields != expected_output_fields:
        reasons.append("blind_analysis_prompt must preserve the fixed A/B/C prediction fields")
    forbidden_probability_fields = {
        field
        for field in actual_output_fields
        if "probability" in field or "logprob" in field
    }
    if forbidden_probability_fields:
        reasons.append("blind_analysis_prompt must not request probabilities or logprobs")
    if genome.blind_analysis_prompt.model_constraints.get("identity_masked") is not True:
        reasons.append("blind_analysis_prompt must require masked identity")
    return reasons


def _archive_sort_key(entry: ArchiveEntry) -> tuple[Any, ...]:
    evaluation = entry.evaluation
    total_cost = evaluation.data_cost_usd + evaluation.token_cost_usd
    return (
        -evaluation.binary_f1,
        -evaluation.class_c_recall,
        evaluation.ordinal_distance,
        total_cost,
        entry.genome.genome_id,
    )


def _dashboard_metrics(evaluation: SchemeEvaluationResult) -> dict[str, float | int]:
    """Return the bounded metric subset allowed in development drift history."""

    return {
        "sample_count": evaluation.sample_count,
        "binary_f1": evaluation.binary_f1,
        "binary_precision": evaluation.binary_precision,
        "binary_recall": evaluation.binary_recall,
        "multiclass_macro_f1": evaluation.multiclass_macro_f1,
        "class_c_recall": evaluation.class_c_recall,
        "ordinal_distance": evaluation.ordinal_distance,
        "data_cost_usd": evaluation.data_cost_usd,
        "token_cost_usd": evaluation.token_cost_usd,
        "latency_ms": evaluation.latency_ms,
    }


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
        "target_failure_type",
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


def _safe_name(value: str) -> str:
    prefix = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")[:80] or "artifact"
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:10]}"


def load_round_checkpoint(
    run_dir: str | Path,
    iteration: int,
) -> dict[str, Any]:
    """Load an exact branch checkpoint, with latest-round legacy reconstruction."""

    root = Path(run_dir)
    if iteration < 1:
        raise ValidationError("round checkpoint iteration must be positive")
    state = _read_json(root / "state.json")
    last_completed = _last_completed_iteration(state)
    if iteration > last_completed:
        raise ValidationError(
            "requested round is not committed; "
            f"last completed round is {last_completed}"
        )
    path = root / "rounds" / f"round-{iteration:04d}" / "checkpoint.json"
    if path.exists():
        payload = _read_json(path)
        _validate_round_checkpoint(payload, expected_iteration=iteration)
        return payload
    if iteration != last_completed:
        available = sorted(
            int(item.parent.name.removeprefix("round-"))
            for item in (root / "rounds").glob("round-*/checkpoint.json")
            if item.parent.name.removeprefix("round-").isdigit()
        )
        if last_completed:
            available = sorted(set([*available, last_completed]))
        raise ValidationError(
            "requested round has no exact branch checkpoint; "
            f"branchable rounds: {available}"
        )
    top_k_path = root / "top_k.json"
    if not top_k_path.exists():
        raise ValidationError("latest legacy round has no reconstructable Top-K archive")
    archive_payload = _read_json(top_k_path)
    archive = TopKArchive.from_dict(archive_payload)
    if not archive.entries:
        raise ValidationError("latest legacy Top-K archive is empty")
    memory = _read_json(root / "memory.json") if (root / "memory.json").exists() else {}
    config = _read_json(root / "config.json") if (root / "config.json").exists() else {}
    payload = {
        "schema_version": "scheme-evolution-round-checkpoint-v1",
        "run_id": str(state.get("run_id") or root.name),
        "iteration": iteration,
        "created_at": str(state.get("last_checkpoint_at") or ""),
        "fixed_spec_hash": str(
            state.get("fixed_spec_hash") or config.get("fixed_spec_hash") or ""
        ),
        "incumbent": archive.entries[0].genome.to_dict(),
        "archive": archive_payload,
        "meta_lessons": list(memory.get("lessons", [])),
        "mutation_requests": list(memory.get("next_mutation_requests", [])),
        "contains_final_test_metrics": False,
        "reconstructed_from_latest_legacy_artifacts": True,
    }
    _validate_round_checkpoint(payload, expected_iteration=iteration)
    return payload


def restore_round_context(
    checkpoint: Mapping[str, Any],
) -> tuple[SchemeGenome, TopKArchive, list[MetaLesson], list[MutationRequest]]:
    """Restore controller objects from a validated round checkpoint."""

    _validate_round_checkpoint(checkpoint)
    incumbent = SchemeGenome.from_dict(
        _mapping(checkpoint.get("incumbent"), "incumbent")
    )
    archive = TopKArchive.from_dict(_mapping(checkpoint.get("archive"), "archive"))
    lessons = [MetaLesson.from_dict(row) for row in checkpoint.get("meta_lessons", [])]
    requests = [
        MutationRequest.from_dict(row)
        for row in checkpoint.get("mutation_requests", [])
    ]
    return incumbent, archive, lessons, requests


def _validate_round_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    expected_iteration: int | None = None,
) -> None:
    if checkpoint.get("schema_version") != "scheme-evolution-round-checkpoint-v1":
        raise ValidationError("unsupported evolution round checkpoint schema")
    iteration = _validated_checkpoint_iteration(checkpoint)
    if expected_iteration is not None and iteration != expected_iteration:
        raise ValidationError("evolution round checkpoint iteration mismatch")
    if checkpoint.get("contains_final_test_metrics") is not False:
        raise ValidationError("round checkpoint must exclude final-test metrics")
    if not str(checkpoint.get("fixed_spec_hash") or "").strip():
        raise ValidationError("round checkpoint fixed-spec hash is missing")
    _mapping(checkpoint.get("incumbent"), "incumbent")
    _mapping(checkpoint.get("archive"), "archive")
    if not isinstance(checkpoint.get("meta_lessons", []), list):
        raise ValidationError("round checkpoint meta_lessons must be a list")
    if not isinstance(checkpoint.get("mutation_requests", []), list):
        raise ValidationError("round checkpoint mutation_requests must be a list")


def _validated_checkpoint_iteration(checkpoint: Mapping[str, Any]) -> int:
    try:
        iteration = int(checkpoint.get("iteration", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationError("round checkpoint iteration must be an integer") from exc
    if iteration < 1:
        raise ValidationError("round checkpoint iteration must be positive")
    return iteration


def _last_completed_iteration(state: Mapping[str, Any]) -> int:
    """Read new state directly and conservatively infer pre-field legacy state."""

    value = state.get("last_completed_iteration")
    if value is None:
        current = int(state.get("current_iteration", 0))
        return current if state.get("status") == "completed" else max(0, current - 1)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("last_completed_iteration must be an integer") from exc
    if parsed < 0:
        raise ValidationError("last_completed_iteration cannot be negative")
    return parsed


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"round checkpoint {name} must be an object")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON artifact {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValidationError(f"JSON artifact must contain an object: {path}")
    return raw


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
