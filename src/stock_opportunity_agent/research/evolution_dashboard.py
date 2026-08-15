"""Read-only local dashboard projection for committed evolution workspaces."""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.models import ValidationError


DASHBOARD_SCHEMA = "information-plan-evolution-dashboard-v2"
_PUBLIC_EVENT_KEYS = frozenset(
    {
        "sequence",
        "at",
        "event_type",
        "cycle_id",
        "round_id",
        "plan_id",
        "candidate_index",
        "candidate_count",
        "case_id",
        "case_index",
        "case_count",
        "stage",
        "model_alias",
        "status",
        "error_type",
        "completed_plan_rounds",
        "target_plan_rounds",
        "phase",
        "metrics",
        "top_k",
        "validated_candidates",
        "promoted",
        "input_registry_version",
        "output_registry_version",
        "validated_pending_approval",
        "last_completed_round",
        "last_completed_cycle",
    }
)


def build_evolution_dashboard_bundle(
    evolution_root: str | Path,
    *,
    recent_event_limit: int = 50,
) -> dict[str, Any]:
    """Project committed v1 workspaces and compatible legacy histories."""

    if recent_event_limit < 1:
        raise ValidationError("dashboard recent-event limit must be positive")
    root = Path(evolution_root)
    runs: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if root.exists():
        for child in sorted(path for path in root.iterdir() if path.is_dir()):
            try:
                if _is_v1_workspace(child):
                    runs.append(_project_v1_workspace(child, recent_event_limit))
                elif (child / "evolution_history.json").is_file():
                    runs.append(_project_legacy_history(child))
            except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
                skipped.append(
                    {
                        "run_id": child.name,
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )
    runs.sort(key=_run_sort_key, reverse=True)
    return {
        "schema_version": DASHBOARD_SCHEMA,
        "primary_metric": "binary_f1",
        "contains_final_test_metrics": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
        "skipped_runs": skipped,
    }


def write_evolution_dashboard_bundle(
    evolution_root: str | Path,
    *,
    recent_event_limit: int = 50,
) -> dict[str, Any]:
    """Atomically refresh the global JSON and file-compatible JS bundle."""

    root = Path(evolution_root)
    root.mkdir(parents=True, exist_ok=True)
    bundle = build_evolution_dashboard_bundle(
        root,
        recent_event_limit=recent_event_limit,
    )
    _atomic_write_text(
        root / "evolution_dashboard_index.json",
        json.dumps(bundle, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(
        root / "evolution_dashboard_data.js",
        "window.__SCHEME_EVOLUTION_DASHBOARD__ = "
        + json.dumps(bundle, sort_keys=True, separators=(",", ":"))
        + ";\n",
    )
    return bundle


def _is_v1_workspace(path: Path) -> bool:
    return (
        (path / "state.json").is_file()
        and (path / "plans").is_dir()
        and (path / "experiments").is_dir()
    )


def _project_v1_workspace(path: Path, recent_event_limit: int) -> dict[str, Any]:
    state = _read_object(path / "state.json")
    last_completed_round = int(state.get("last_completed_round", 0))
    if last_completed_round < 0:
        raise ValidationError("dashboard round pointer cannot be negative")
    contract = (
        _read_object(path / "run_contract.json")
        if (path / "run_contract.json").is_file()
        else {}
    )
    limits = dict(contract.get("limits", {}))
    top_k_count = int(limits.get("top_k", 3))
    similarity_threshold = float(limits.get("similarity_threshold", 0.9))
    if top_k_count < 1 or not -1 < similarity_threshold <= 1:
        raise ValidationError("dashboard selection limits are invalid")

    rounds: list[dict[str, Any]] = []
    committed_records: list[dict[str, Any]] = []
    latest_completed_at = ""
    for round_id in range(1, last_completed_round + 1):
        checkpoint_path = (
            path / "experiments" / f"round-{round_id:04d}" / "checkpoint.json"
        )
        checkpoint = _read_object(checkpoint_path)
        if int(checkpoint.get("round_id", 0)) != round_id:
            raise ValidationError("dashboard checkpoint round mismatch")
        plan_ids = checkpoint.get("plan_ids")
        if not isinstance(plan_ids, list) or not plan_ids:
            raise ValidationError("dashboard checkpoint has no Plan ids")
        round_records: list[dict[str, Any]] = []
        for plan_id in plan_ids:
            record = _read_object(path / "plans" / str(plan_id) / "record.json")
            if str(record.get("plan_id")) != str(plan_id):
                raise ValidationError("dashboard Plan record identity mismatch")
            if int(record.get("round_id", 0)) != round_id:
                raise ValidationError("dashboard Plan record round mismatch")
            normalized = _normalize_record(record)
            round_records.append(normalized)
            committed_records.append(normalized)
        selected = _select_quality_diverse(
            committed_records,
            top_k=top_k_count,
            similarity_threshold=similarity_threshold,
        )
        selected_ids = {record["plan_id"] for record in selected}
        candidates = [
            {
                "genome_id": record["plan_id"],
                "plan_id": record["plan_id"],
                "parent_genome_ids": record["parent_ids"],
                "parent_ids": record["parent_ids"],
                "metrics": record["metrics"],
                "metrics_by_cohort": record["metrics_by_cohort"],
                "plan_summary": record["plan_summary"],
                "trajectory_count": record["trajectory_count"],
                "stop_reason_counts": record["stop_reason_counts"],
                "usage": record["usage"],
                "admitted": record["plan_id"] in selected_ids,
                "admission_status": (
                    "quality_diverse_top_k"
                    if record["plan_id"] in selected_ids
                    else "committed_not_current_top_k"
                ),
            }
            for record in round_records
        ]
        archive_best = max(
            committed_records,
            key=lambda record: (
                float(record["metrics"].get("binary_f1", 0.0)),
                record["plan_id"],
            ),
        )
        completed_at = datetime.fromtimestamp(
            checkpoint_path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()
        latest_completed_at = completed_at
        rounds.append(
            {
                "iteration": round_id,
                "round_id": round_id,
                "source": "information_plan_signal_v1",
                "candidate_count": len(candidates),
                "candidates": candidates,
                "archive_best_genome_id": archive_best["plan_id"],
                "archive_best_metrics": archive_best["metrics"],
                "top_k": [
                    {
                        "plan_id": record["plan_id"],
                        "binary_f1": record["metrics"].get("binary_f1", 0.0),
                        "anchor_binary_f1": dict(
                            record["metrics_by_cohort"].get("anchor", {})
                        ).get("binary_f1"),
                        "random_binary_f1": dict(
                            record["metrics_by_cohort"].get("random", {})
                        ).get("binary_f1"),
                    }
                    for record in selected
                ],
                "trajectory_count": sum(
                    record["trajectory_count"] for record in round_records
                ),
                "completed_at": completed_at,
            }
        )

    cycle_state = (
        _read_object(path / "cycle_state.json")
        if (path / "cycle_state.json").is_file()
        else {
            "last_completed_cycle": 0,
            "active_cycle": None,
        }
    )
    all_events, corrupt_event_lines = _read_events(
        path / "experiments" / "trajectory.jsonl"
    )
    public_events = [_public_event(event) for event in all_events[-recent_event_limit:]]
    staged_trajectory_count = sum(
        1
        for candidate in (path / "experiments" / "trajectories").glob("*/*.json")
        if candidate.is_file()
    )
    committed_trajectory_count = sum(
        round_data["trajectory_count"] for round_data in rounds
    )
    current_top = rounds[-1]["top_k"] if rounds else []
    return {
        "schema_version": "information-plan-evolution-history-v1",
        "architecture": "information_plan_signal_v1",
        "run_id": str(contract.get("run_id") or path.name),
        "workspace_name": path.name,
        "primary_metric": "binary_f1",
        "contains_final_test_metrics": False,
        "last_completed_round": last_completed_round,
        "last_completed_cycle": int(cycle_state.get("last_completed_cycle", 0)),
        "active_cycle": cycle_state.get("active_cycle"),
        "current_top_k": current_top,
        "committed_trajectory_count": committed_trajectory_count,
        "staged_trajectory_file_count": staged_trajectory_count,
        "trajectory_event_count": len(all_events),
        "trajectory_event_corrupt_line_count": corrupt_event_lines,
        "interruption_count": sum(
            event.get("event_type") == "run_interrupted" for event in all_events
        ),
        "recent_events": public_events,
        "rounds": rounds,
        "updated_at": latest_completed_at or _path_updated_at(path / "state.json"),
    }


def _normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    plan = dict(record.get("plan", {}))
    metrics = dict(record.get("metrics", {}))
    embedding = record.get("embedding")
    trajectories = record.get("trajectories")
    if not isinstance(embedding, list) or not embedding:
        raise ValidationError("dashboard Plan embedding is missing")
    if not isinstance(trajectories, list):
        raise ValidationError("dashboard Plan trajectories are missing")
    stop_reasons: Counter[str] = Counter()
    llm_calls = 0
    tokens = 0
    cost = 0.0
    signal_calls = 0
    for trajectory in trajectories:
        if not isinstance(trajectory, Mapping):
            raise ValidationError("dashboard trajectory must be an object")
        stop_reasons[str(trajectory.get("stop_reason") or "unknown")] += 1
        usage = dict(trajectory.get("usage", {}))
        model = dict(usage.get("model", {}))
        signal_calls += int(usage.get("signal_calls", 0))
        llm_calls += int(model.get("llm_calls", 0))
        tokens += int(model.get("tokens", 0))
        cost += float(model.get("cost", 0.0))
    policy = dict(plan.get("basic_info_policy", {}))
    request_summaries = []
    for request in policy.get("requests", ()):
        if not isinstance(request, Mapping):
            continue
        request_summaries.append(
            {
                "request_id": str(request.get("request_id", "")),
                "source_types": [str(item) for item in request.get("source_types", ())],
                "lookback_days": request.get("lookback_days"),
                "max_documents": request.get("max_documents"),
            }
        )
    return {
        "plan_id": str(record["plan_id"]),
        "parent_ids": [str(item) for item in record.get("parent_ids", ())],
        "embedding": [float(item) for item in embedding],
        "metrics": metrics,
        "metrics_by_cohort": {
            str(cohort): dict(cohort_metrics)
            for cohort, cohort_metrics in dict(
                record.get("metrics_by_cohort", {})
            ).items()
            if isinstance(cohort_metrics, Mapping)
        },
        "plan_summary": {
            "basic_info_requests": request_summaries,
            "basic_info_fields": [str(item) for item in policy.get("fields", ())],
            "initial_research": _clip(plan.get("initial_research_skill")),
            "reflection": _clip(plan.get("reflection_skill")),
            "analysis": _clip(plan.get("analysis_prompt")),
        },
        "trajectory_count": len(trajectories),
        "stop_reason_counts": dict(sorted(stop_reasons.items())),
        "usage": {
            "signal_calls": signal_calls,
            "llm_calls": llm_calls,
            "tokens": tokens,
            "cost": cost,
        },
    }


def _select_quality_diverse(
    records: Iterable[Mapping[str, Any]],
    *,
    top_k: int,
    similarity_threshold: float,
) -> list[Mapping[str, Any]]:
    ranked = sorted(
        records,
        key=lambda record: (
            -float(dict(record["metrics"]).get("binary_f1", 0.0)),
            str(record["plan_id"]),
        ),
    )
    selected: list[Mapping[str, Any]] = []
    for record in ranked:
        if all(
            _cosine(record["embedding"], kept["embedding"])
            < similarity_threshold
            for kept in selected
        ):
            selected.append(record)
        if len(selected) == top_k:
            break
    return selected


def _cosine(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = tuple(float(value) for value in left)
    right_values = tuple(float(value) for value in right)
    if not left_values or len(left_values) != len(right_values):
        raise ValidationError("dashboard embeddings must be non-empty and equal")
    left_norm = math.sqrt(sum(value * value for value in left_values))
    right_norm = math.sqrt(sum(value * value for value in right_values))
    if left_norm == 0 or right_norm == 0:
        raise ValidationError("dashboard embeddings cannot have zero norm")
    return sum(a * b for a, b in zip(left_values, right_values)) / (
        left_norm * right_norm
    )


def _project_legacy_history(path: Path) -> dict[str, Any]:
    history = _read_object(path / "evolution_history.json")
    rounds = history.get("rounds")
    if not isinstance(rounds, list):
        raise ValidationError("legacy evolution history rounds must be a list")
    return {
        **history,
        "architecture": "legacy_scheme_genome",
        "workspace_name": path.name,
        "contains_final_test_metrics": False,
        "updated_at": (
            str(rounds[-1].get("completed_at") or "")
            if rounds and isinstance(rounds[-1], Mapping)
            else _path_updated_at(path / "evolution_history.json")
        ),
    }


def _public_event(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: event[key]
        for key in _PUBLIC_EVENT_KEYS
        if key in event
    }


def _read_events(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.is_file():
        return [], 0
    events: list[dict[str, Any]] = []
    corrupt_lines = 0
    for line in path.read_text(
        encoding="utf-8", errors="replace"
    ).splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            corrupt_lines += 1
            continue
        if not isinstance(event, dict):
            corrupt_lines += 1
            continue
        events.append(event)
    return events, corrupt_lines


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"dashboard artifact is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"dashboard artifact must be an object: {path}")
    return value


def _path_updated_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _run_sort_key(run: Mapping[str, Any]) -> tuple[str, str]:
    return str(run.get("updated_at") or ""), str(run.get("run_id") or "")


def _clip(value: Any, limit: int = 180) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
