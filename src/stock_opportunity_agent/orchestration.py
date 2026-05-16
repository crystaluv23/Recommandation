"""Pipeline orchestration entry points."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

from stock_opportunity_agent.cases import (
    ColdStartLearningResult,
    ControlMatchCriteria,
    HistoricalCase,
    apply_matched_groups,
    learn_pre_surge_signal_logic,
    match_controls,
)
from stock_opportunity_agent.config import AgentConfig
from stock_opportunity_agent.memory.playbooks import FilePlaybookLibrary
from stock_opportunity_agent.memory.signals import FileSignalLibrary
from stock_opportunity_agent.memory.themes import FileThemeLibrary
from stock_opportunity_agent.models import VersionStamp
from stock_opportunity_agent.research.cold_start import (
    BlindCaseAnalysis,
    BlindCaseResearcher,
    HeuristicBlindCaseResearcher,
)
from stock_opportunity_agent.research.inflection_discovery import (
    HeuristicInflectionResearcher,
    InflectionResearchResult,
    InflectionResearcher,
)
from stock_opportunity_agent.research.playbooks import (
    HeuristicSurgePlaybookSynthesizer,
    SurgePlaybookSynthesis,
    SurgePlaybookSynthesizer,
)
from stock_opportunity_agent.themes import ThemeMapBuildResult, build_cold_start_theme_maps


ProgressReporter = Callable[[str], None]
TAnalysis = TypeVar("TAnalysis")


@dataclass(frozen=True)
class ColdStartRunOutput:
    """Files written by a cold-start case-learning run."""

    run_id: str
    output_dir: Path
    manifest_path: Path
    signal_logic_path: Path
    signal_definitions_path: Path
    observations_path: Path
    theme_maps_path: Path
    playbooks_path: Path
    inflection_analysis_path: Path
    blind_analysis_path: Path
    signal_library_dir: Path | None
    theme_library_dir: Path | None
    playbook_library_dir: Path | None
    result: ColdStartLearningResult
    theme_maps: ThemeMapBuildResult
    playbook_synthesis: SurgePlaybookSynthesis
    inflection_analyses: tuple[InflectionResearchResult, ...]
    blind_analyses: tuple[BlindCaseAnalysis, ...]


def run_cold_start_case_learning(
    cases: Iterable[HistoricalCase],
    *,
    config: AgentConfig | None = None,
    output_dir: str | Path | None = None,
    run_id: str | None = None,
    created_at: datetime | None = None,
    signal_version: str | None = None,
    blind_researcher: BlindCaseResearcher | None = None,
    inflection_researcher: InflectionResearcher | None = None,
    signal_library: FileSignalLibrary | None = None,
    theme_library: FileThemeLibrary | None = None,
    playbook_library: FilePlaybookLibrary | None = None,
    playbook_synthesizer: SurgePlaybookSynthesizer | None = None,
    control_match_criteria: ControlMatchCriteria | None = None,
    research_max_workers: int = 1,
    progress: ProgressReporter | None = None,
) -> ColdStartRunOutput:
    """Run cold-start case learning and persist auditable artifacts."""

    if research_max_workers < 1:
        raise ValueError("research_max_workers must be at least 1")
    active_config = config or AgentConfig()
    created = created_at or datetime.now(timezone.utc)
    active_run_id = run_id or "cold-start-" + created.strftime("%Y%m%dT%H%M%SZ")
    _report(progress, f"[cold-start] run_id={active_run_id}")
    version = _version_from_config(active_config)
    active_signal_version = signal_version or version.signal_version
    base_dir = Path(output_dir) if output_dir is not None else Path(active_config.storage.reports_dir) / "cold_start" / active_run_id
    base_dir.mkdir(parents=True, exist_ok=True)
    signal_logic_path = base_dir / "pre_surge_signal_logic.json"
    signal_definitions_path = base_dir / "signal_definitions.json"
    observations_path = base_dir / "case_signal_observations.json"
    theme_maps_path = base_dir / "theme_maps.json"
    playbooks_path = base_dir / "surge_research_playbooks.json"
    inflection_analysis_path = base_dir / "inflection_analyses.json"
    blind_analysis_path = base_dir / "blind_case_analyses.json"
    manifest_path = base_dir / "manifest.json"
    _report(progress, f"[cold-start] artifact dir: {base_dir}")
    input_cases = list(cases)
    _report(progress, f"[cold-start] loaded {len(input_cases)} case(s)")
    matched_sets = match_controls(input_cases, control_match_criteria) if control_match_criteria is not None else ()
    case_list = list(apply_matched_groups(input_cases, matched_sets)) if matched_sets else input_cases
    if matched_sets:
        for match in matched_sets:
            controls = ", ".join(match.control_case_ids) if match.control_case_ids else "none"
            warning = f" warnings={'; '.join(match.warnings)}" if match.warnings else ""
            _report(progress, f"[cold-start] matched {match.winner_case_id} -> {controls}{warning}")
    else:
        _report(progress, "[cold-start] control matching skipped")
    active_inflection_researcher = inflection_researcher or HeuristicInflectionResearcher()
    _report(progress, f"[cold-start] discovering inflections with {active_inflection_researcher.__class__.__name__}")
    inflection_analyses = _run_case_research(
        case_list,
        active_inflection_researcher.discover,
        label="inflection",
        max_workers=research_max_workers,
        checkpoint_path=inflection_analysis_path,
        run_id=active_run_id,
        result_key="inflection_analyses",
        progress=progress,
    )
    for analysis in inflection_analyses:
        top = analysis.candidates[0] if analysis.candidates else None
        if top is not None:
            _report(
                progress,
                (
                    f"[cold-start] inflection {analysis.case_id}: {top.inflection_date.isoformat()} "
                    f"{top.method} score={top.score:.2f}"
                ),
            )
    researcher = blind_researcher or HeuristicBlindCaseResearcher()
    _report(progress, f"[cold-start] running blind analysis with {researcher.__class__.__name__}")
    blind_analyses = _run_case_research(
        case_list,
        researcher.analyze,
        label="blind",
        max_workers=research_max_workers,
        checkpoint_path=blind_analysis_path,
        run_id=active_run_id,
        result_key="blind_case_analyses",
        progress=progress,
    )
    for analysis in blind_analyses:
        first_signal = analysis.pre_surge_signals[0] if analysis.pre_surge_signals else "no signal"
        _report(progress, f"[cold-start] blind {analysis.case_id}: confidence={analysis.confidence:.2f}; {first_signal}")
    _report(progress, "[cold-start] measuring deterministic packet signals")
    result = learn_pre_surge_signal_logic(case_list, signal_version=active_signal_version)
    promoted = ", ".join(definition.signal_id for definition in result.signal_definitions) or "none"
    _report(progress, f"[cold-start] promoted {len(result.signal_definitions)} signal(s): {promoted}")
    _report(progress, "[cold-start] building theme maps")
    theme_maps = build_cold_start_theme_maps(case_list, result)
    theme_summary = ", ".join(theme.theme_id for theme in theme_maps.theme_maps) or "none"
    _report(progress, f"[cold-start] theme maps {len(theme_maps.theme_maps)}: {theme_summary}")
    active_playbook_synthesizer = playbook_synthesizer or HeuristicSurgePlaybookSynthesizer()
    _report(
        progress,
        f"[cold-start] synthesizing research playbooks with {active_playbook_synthesizer.__class__.__name__}",
    )
    playbook_synthesis = active_playbook_synthesizer.synthesize(
        case_list,
        blind_analyses,
        result,
        theme_maps,
    )
    playbook_summary = ", ".join(playbook.playbook_id for playbook in playbook_synthesis.playbooks)
    _report(progress, f"[cold-start] research playbooks {len(playbook_synthesis.playbooks)}: {playbook_summary}")

    _report(progress, f"[cold-start] writing artifacts to {base_dir}")

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
    _write_json(
        theme_maps_path,
        {
            "run_id": active_run_id,
            **theme_maps.to_dict(),
        },
    )
    _write_json(
        playbooks_path,
        {
            "run_id": active_run_id,
            "created_at": created.isoformat(),
            "source_artifacts": {
                "blind_case_analyses": str(blind_analysis_path),
                "case_signal_observations": str(observations_path),
                "pre_surge_signal_logic": str(signal_logic_path),
                "signal_definitions": str(signal_definitions_path),
                "theme_maps": str(theme_maps_path),
            },
            **playbook_synthesis.to_dict(),
        },
    )
    _write_json(
        inflection_analysis_path,
        {
            "run_id": active_run_id,
            "inflection_analyses": [analysis.to_dict() for analysis in inflection_analyses],
        },
    )
    _write_json(
        blind_analysis_path,
        {
            "run_id": active_run_id,
            "blind_case_analyses": [analysis.to_dict() for analysis in blind_analyses],
        },
    )
    if signal_library is not None:
        signal_library.write_cold_start(
            run_id=active_run_id,
            definitions=result.signal_definitions,
            logic=result.signal_logic,
            created_at=created,
        )
        _report(progress, f"[cold-start] signal library updated at {signal_library.root_dir}")
    if theme_library is not None:
        theme_library.write_cold_start(
            run_id=active_run_id,
            theme_maps=theme_maps.theme_maps,
            created_at=created,
        )
        _report(progress, f"[cold-start] theme library updated at {theme_library.root_dir}")
    if playbook_library is not None:
        playbook_library.write_cold_start(
            run_id=active_run_id,
            synthesis=playbook_synthesis,
            created_at=created,
        )
        _report(progress, f"[cold-start] playbook library updated at {playbook_library.root_dir}")
    manifest = _manifest(
        run_id=active_run_id,
        created_at=created,
        config=active_config,
        version=version,
        cases=case_list,
        matched_sets=matched_sets,
        result=result,
        output_paths={
            "pre_surge_signal_logic": signal_logic_path,
            "signal_definitions": signal_definitions_path,
            "case_signal_observations": observations_path,
            "theme_maps": theme_maps_path,
            "surge_research_playbooks": playbooks_path,
            "inflection_analyses": inflection_analysis_path,
            "blind_case_analyses": blind_analysis_path,
        },
        theme_maps=theme_maps,
        playbook_synthesis=playbook_synthesis,
        signal_library=signal_library,
        theme_library=theme_library,
        playbook_library=playbook_library,
    )
    _write_json(manifest_path, manifest)
    _report(progress, f"[cold-start] manifest: {manifest_path}")
    _report(progress, f"[cold-start] complete: {signal_logic_path}")

    return ColdStartRunOutput(
        run_id=active_run_id,
        output_dir=base_dir,
        manifest_path=manifest_path,
        signal_logic_path=signal_logic_path,
        signal_definitions_path=signal_definitions_path,
        observations_path=observations_path,
        theme_maps_path=theme_maps_path,
        playbooks_path=playbooks_path,
        inflection_analysis_path=inflection_analysis_path,
        blind_analysis_path=blind_analysis_path,
        signal_library_dir=signal_library.root_dir if signal_library is not None else None,
        theme_library_dir=theme_library.root_dir if theme_library is not None else None,
        playbook_library_dir=playbook_library.root_dir if playbook_library is not None else None,
        result=result,
        theme_maps=theme_maps,
        playbook_synthesis=playbook_synthesis,
        inflection_analyses=inflection_analyses,
        blind_analyses=blind_analyses,
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


def _run_case_research(
    cases: list[HistoricalCase],
    research: Callable[[HistoricalCase], TAnalysis],
    *,
    label: str,
    max_workers: int,
    checkpoint_path: Path,
    run_id: str,
    result_key: str,
    progress: ProgressReporter | None,
) -> tuple[TAnalysis, ...]:
    completed_by_case = _load_research_checkpoint(checkpoint_path, result_key)
    if completed_by_case:
        _report(progress, f"[cold-start] {label} resume {len(completed_by_case)}/{len(cases)} from {checkpoint_path}")
    if max_workers == 1 or len(cases) <= 1:
        analyses_by_case = dict(completed_by_case)
        for index, case in enumerate(cases, start=1):
            if case.case_id in analyses_by_case:
                continue
            analyses_by_case[case.case_id] = research(case)
            _report(progress, f"[cold-start] {label} progress {index}/{len(cases)}: {case.case_id}")
            _write_research_checkpoint(
                checkpoint_path,
                run_id,
                result_key,
                [analyses_by_case[item.case_id] for item in cases if item.case_id in analyses_by_case],
            )
        return tuple(analyses_by_case[case.case_id] for case in cases if case.case_id in analyses_by_case)

    results: list[TAnalysis | None] = [None] * len(cases)
    for index, case in enumerate(cases):
        if case.case_id in completed_by_case:
            results[index] = completed_by_case[case.case_id]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(research, case): (index, case)
            for index, case in enumerate(cases)
            if case.case_id not in completed_by_case
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            index, case = futures[future]
            results[index] = future.result()
            _report(progress, f"[cold-start] {label} progress {completed}/{len(cases)}: {case.case_id}")
            _write_research_checkpoint(
                checkpoint_path,
                run_id,
                result_key,
                [result for result in results if result is not None],
            )
    return tuple(result for result in results if result is not None)


def _load_research_checkpoint(path: Path, result_key: str) -> dict[str, Any]:
    if result_key != "blind_case_analyses" or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw_items = data.get(result_key)
    if not isinstance(raw_items, list):
        return {}
    loaded: dict[str, BlindCaseAnalysis] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            analysis = BlindCaseAnalysis(
                case_id=str(item["case_id"]),
                packet_id=str(item["packet_id"]),
                as_of_date=str(item["as_of_date"]),
                surge_candidate=str(item["surge_candidate"]),
                surge_candidate_reason=str(item["surge_candidate_reason"]),
                expectation_gap=str(item["expectation_gap"]),
                pre_surge_signals=tuple(str(value) for value in item["pre_surge_signals"]),
                contrary_evidence=tuple(str(value) for value in item["contrary_evidence"]),
                catalyst_watch=tuple(str(value) for value in item["catalyst_watch"]),
                confidence=float(item["confidence"]),
                raw_text=str(item["raw_text"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        loaded[analysis.case_id] = analysis
    return loaded


def _write_research_checkpoint(
    path: Path,
    run_id: str,
    result_key: str,
    analyses: Iterable[Any],
) -> None:
    analysis_list = list(analyses)
    _write_json(
        path,
        {
            "run_id": run_id,
            "checkpoint": True,
            "completed_count": len(analysis_list),
            result_key: [analysis.to_dict() for analysis in analysis_list],
        },
    )


def _manifest(
    *,
    run_id: str,
    created_at: datetime,
    config: AgentConfig,
    version: VersionStamp,
    cases: list[HistoricalCase],
    matched_sets: tuple[Any, ...],
    result: ColdStartLearningResult,
    output_paths: dict[str, Path],
    theme_maps: ThemeMapBuildResult,
    playbook_synthesis: SurgePlaybookSynthesis,
    signal_library: FileSignalLibrary | None,
    theme_library: FileThemeLibrary | None,
    playbook_library: FilePlaybookLibrary | None,
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
            "matched_control_sets": [
                {
                    "winner_case_id": match.winner_case_id,
                    "control_case_ids": list(match.control_case_ids),
                    "criteria_id": match.criteria_id,
                    "warnings": list(match.warnings),
                }
                for match in matched_sets
            ],
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
            "theme_map_count": len(theme_maps.theme_maps),
            "theme_ids": [theme.theme_id for theme in theme_maps.theme_maps],
            "playbook_count": len(playbook_synthesis.playbooks),
            "playbook_ids": [playbook.playbook_id for playbook in playbook_synthesis.playbooks],
            "inflection_analysis_count": len(cases),
            "blind_analysis_count": len(cases),
            "signal_library_dir": str(signal_library.root_dir) if signal_library is not None else None,
            "theme_library_dir": str(theme_library.root_dir) if theme_library is not None else None,
            "playbook_library_dir": str(playbook_library.root_dir) if playbook_library is not None else None,
        },
        "warnings": list(result.warnings) + list(theme_maps.warnings) + list(playbook_synthesis.warnings),
        "assumptions": [
            "Winner, control, and failure labels were produced before signal learning.",
            "Retrospective inflection discovery may use future outcomes and web search, but its output is not added to blind packets.",
            "Blind analysis uses only point-in-time ResearchPacket features and known catalysts.",
            "Research playbook synthesis is retrospective; it may compare labels but must not treat labels as as-of evidence.",
            "Cold-start theme maps initialize industry-chain hypotheses from supplied cases; they are not full live theme discovery.",
        ],
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _report(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)
