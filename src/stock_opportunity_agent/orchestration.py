"""Pipeline orchestration entry points."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from stock_opportunity_agent.cases import ColdStartLearningResult, HistoricalCase, learn_pre_surge_signal_logic
from stock_opportunity_agent.config import AgentConfig
from stock_opportunity_agent.models import VersionStamp


@dataclass(frozen=True)
class ColdStartRunOutput:
    """Files written by a cold-start case-learning run."""

    run_id: str
    output_dir: Path
    manifest_path: Path
    signal_logic_path: Path
    signal_definitions_path: Path
    observations_path: Path
    result: ColdStartLearningResult


def run_cold_start_case_learning(
    cases: Iterable[HistoricalCase],
    *,
    config: AgentConfig | None = None,
    output_dir: str | Path | None = None,
    run_id: str | None = None,
    created_at: datetime | None = None,
    signal_version: str | None = None,
) -> ColdStartRunOutput:
    """Run cold-start case learning and persist auditable artifacts."""

    active_config = config or AgentConfig()
    created = created_at or datetime.now(timezone.utc)
    active_run_id = run_id or "cold-start-" + created.strftime("%Y%m%dT%H%M%SZ")
    version = _version_from_config(active_config)
    active_signal_version = signal_version or version.signal_version
    case_list = list(cases)
    result = learn_pre_surge_signal_logic(case_list, signal_version=active_signal_version)

    base_dir = Path(output_dir) if output_dir is not None else Path(active_config.storage.reports_dir) / "cold_start" / active_run_id
    base_dir.mkdir(parents=True, exist_ok=True)
    signal_logic_path = base_dir / "pre_surge_signal_logic.json"
    signal_definitions_path = base_dir / "signal_definitions.json"
    observations_path = base_dir / "case_signal_observations.json"
    manifest_path = base_dir / "manifest.json"

    _write_json(
        signal_logic_path,
        {
            "run_id": active_run_id,
            "created_at": created.isoformat(),
            "signal_version": active_signal_version,
            "assumption": (
                "Initial cold start consumes versioned outcome labels and supplied matched groups; "
                "automatic matched-control construction is deferred."
            ),
            "signals": [signal.to_dict() for signal in result.signal_logic],
        },
    )
    _write_json(
        signal_definitions_path,
        {
            "run_id": active_run_id,
            "signal_definitions": [definition.to_dict() for definition in result.signal_definitions],
        },
    )
    _write_json(
        observations_path,
        {
            "run_id": active_run_id,
            "observations_by_case": result.observations_to_dict(),
        },
    )
    manifest = _manifest(
        run_id=active_run_id,
        created_at=created,
        config=active_config,
        version=version,
        cases=case_list,
        result=result,
        output_paths={
            "pre_surge_signal_logic": signal_logic_path,
            "signal_definitions": signal_definitions_path,
            "case_signal_observations": observations_path,
        },
    )
    _write_json(manifest_path, manifest)

    return ColdStartRunOutput(
        run_id=active_run_id,
        output_dir=base_dir,
        manifest_path=manifest_path,
        signal_logic_path=signal_logic_path,
        signal_definitions_path=signal_definitions_path,
        observations_path=observations_path,
        result=result,
    )


def _version_from_config(config: AgentConfig) -> VersionStamp:
    return VersionStamp(
        prompt_version=config.prompts.prompt_version,
        scoring_version=config.scoring.scoring_version,
        signal_version=config.meta_learning.signal_version,
        model_version=config.prompts.model_version,
        data_pipeline_version=config.pipeline.data_pipeline_version,
        config_version=config.config_version,
    )


def _manifest(
    *,
    run_id: str,
    created_at: datetime,
    config: AgentConfig,
    version: VersionStamp,
    cases: list[HistoricalCase],
    result: ColdStartLearningResult,
    output_paths: dict[str, Path],
) -> dict[str, Any]:
    labels: dict[str, int] = {}
    for case in cases:
        labels[case.label.value] = labels.get(case.label.value, 0) + 1
    return {
        "pipeline": "cold_start_case_learning",
        "run_id": run_id,
        "created_at": created_at.isoformat(),
        "versions": version.to_dict(),
        "config": config.public_dict(),
        "inputs": {
            "case_count": len(cases),
            "labels": labels,
            "matched_group_count": len({case.matched_group_id for case in cases}),
            "outcome_definition_ids": sorted(
                {
                    case.outcome_definition_id
                    for case in cases
                    if case.outcome_definition_id is not None
                }
            ),
            "packet_ids": [case.packet.packet_id for case in cases],
        },
        "outputs": {name: str(path) for name, path in output_paths.items()},
        "result_summary": {
            "measured_signal_count": len(result.signal_logic),
            "promoted_signal_count": len(result.signal_definitions),
            "promoted_signal_ids": [definition.signal_id for definition in result.signal_definitions],
        },
        "warnings": list(result.warnings),
        "assumptions": [
            "Winner, control, and failure labels were produced before signal learning.",
            "Matched control construction is not automated in this MVP.",
            "Only point-in-time ResearchPacket features and known catalysts are measured.",
        ],
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
