"""Run an artifact-backed Ralph Loop refinement/holdout experiment."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from stock_opportunity_agent.cases import CaseOutcomeLabel, HistoricalCase, learn_pre_surge_signal_logic
from stock_opportunity_agent.llm.openai import UrllibTransport
from stock_opportunity_agent.llm.openrouter import OpenRouterChatClient
from stock_opportunity_agent.models import ResearchPacket, ValidationError
from stock_opportunity_agent.research import (
    BlindCaseAnalysis,
    HeuristicRalphBlindResearcher,
    HeuristicSurgePlaybookSynthesizer,
    OpenAIRalphBlindResearcher,
    run_ralph_experiment,
    write_ralph_experiment_artifacts,
)
from stock_opportunity_agent.themes import build_cold_start_theme_maps


DEFAULT_FORMAL_RUN_DIR = Path(
    "runs/cold_start/formal/cold-start-formal-openrouter-2026-05-13-clean-universe"
)


def main() -> None:
    """Run a bounded Ralph experiment from saved cold-start artifacts."""

    args = _parse_args()
    _load_local_env()
    created_at = datetime.now(timezone.utc)
    run_id = args.run_id or f"ralph-loop-experiment-{created_at.strftime('%Y%m%d-%H%M%S')}"
    output_dir = Path(args.output_dir) if args.output_dir else Path("runs/cold_start/ralph") / run_id
    cases = _load_cases(Path(args.cases_path))
    baseline = _load_blind_analyses(Path(args.baseline_blind_path))
    selected = _select_cases(
        cases,
        winner_symbol_count=args.winner_symbol_count,
        control_symbol_count=args.control_symbol_count,
        refinement_per_label=args.refinement_per_label,
    )
    refinement_cases = selected["refinement"]
    holdout_cases = selected["holdout"]
    baseline_refinement = tuple(
        baseline[case.case_id]
        for case in refinement_cases
        if case.case_id in baseline
    )
    if len(baseline_refinement) != len(refinement_cases):
        missing = sorted({case.case_id for case in refinement_cases} - set(baseline))
        raise ValidationError(f"missing baseline blind analyses for refinement cases: {missing}")

    learning = learn_pre_surge_signal_logic(refinement_cases)
    theme_maps = build_cold_start_theme_maps(refinement_cases, learning)
    playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(
        refinement_cases,
        baseline_refinement,
        learning,
        theme_maps,
    )
    researcher = _ralph_researcher(args)
    print(f"[ralph-experiment] run_id={run_id}")
    print(f"[ralph-experiment] output_dir={output_dir}")
    print("[ralph-experiment] selected symbols: " + ", ".join(_selection_symbols(selected)))
    print(
        "[ralph-experiment] refinement_cases="
        f"{len(refinement_cases)} holdout_cases={len(holdout_cases)} mode={args.mode}"
    )

    result = run_ralph_experiment(
        refinement_cases,
        holdout_cases,
        baseline_refinement_blind_analyses=baseline_refinement,
        learning_result=learning,
        theme_maps=theme_maps,
        playbook_synthesis=playbooks,
        run_id=run_id,
        blind_researcher=researcher,
        max_iterations=args.max_iterations,
    )
    selection_path = output_dir / "case_selection_label_aware.json"
    _write_json(
        selection_path,
        {
            "schema_version": "ralph-case-selection-v0.1",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "stage_boundary": "retrospective_label_aware",
            "selection_policy": {
                "winner_symbol_count": args.winner_symbol_count,
                "control_symbol_count": args.control_symbol_count,
                "refinement_per_label": args.refinement_per_label,
                "one_latest_case_per_symbol": True,
            },
            "refinement_cases": [_case_selection_record(case) for case in refinement_cases],
            "holdout_cases": [_case_selection_record(case) for case in holdout_cases],
        },
    )
    paths = write_ralph_experiment_artifacts(
        result,
        output_dir,
        created_at=created_at,
        proposal_memory_dir=Path(".agent_state/memory/ralph"),
        extra_output_paths={"case_selection_label_aware": selection_path},
    )

    _print_metric_summary(result)
    print(f"[ralph-experiment] manifest={paths['manifest']}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases-path",
        default=str(DEFAULT_FORMAL_RUN_DIR / "05_packets/historical_cases.json"),
    )
    parser.add_argument(
        "--baseline-blind-path",
        default=str(DEFAULT_FORMAL_RUN_DIR / "06_research/blind_case_analyses.json"),
    )
    parser.add_argument("--output-dir")
    parser.add_argument("--run-id")
    parser.add_argument("--mode", choices=("llm", "heuristic"), default="llm")
    parser.add_argument("--openrouter-model", default="openai/gpt-5.5")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--winner-symbol-count", type=int, default=4)
    parser.add_argument("--control-symbol-count", type=int, default=4)
    parser.add_argument("--refinement-per-label", type=int, default=2)
    parser.add_argument("--max-iterations", type=int, default=2)
    return parser.parse_args()


def _load_cases(path: Path) -> tuple[HistoricalCase, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("cases") or data.get("historical_cases")
    if not isinstance(records, list):
        raise ValidationError(f"{path} does not contain cases")
    return tuple(_case_from_record(record) for record in records)


def _case_from_record(record: dict[str, Any]) -> HistoricalCase:
    return HistoricalCase(
        case_id=_string(record, "case_id"),
        label=CaseOutcomeLabel(_string(record, "label")),
        packet=ResearchPacket.from_dict(_mapping(record, "packet")),
        outcome_start_date=date.fromisoformat(_string(record, "outcome_start_date")),
        outcome_end_date=date.fromisoformat(_string(record, "outcome_end_date")),
        outcome_return=_optional_float(record.get("outcome_return")),
        matched_group_id=_string(record, "matched_group_id"),
        hidden_outcome_summary=_string(record, "hidden_outcome_summary"),
        outcome_definition_id=record.get("outcome_definition_id"),
    )


def _load_blind_analyses(path: Path) -> dict[str, BlindCaseAnalysis]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("blind_case_analyses") or data.get("analyses")
    if not isinstance(records, list):
        raise ValidationError(f"{path} does not contain blind_case_analyses")
    analyses = tuple(_blind_from_record(record) for record in records)
    return {analysis.case_id: analysis for analysis in analyses}


def _blind_from_record(record: dict[str, Any]) -> BlindCaseAnalysis:
    return BlindCaseAnalysis(
        case_id=_string(record, "case_id"),
        packet_id=_string(record, "packet_id"),
        as_of_date=_string(record, "as_of_date"),
        surge_candidate=_string(record, "surge_candidate"),
        surge_candidate_reason=_string(record, "surge_candidate_reason"),
        expectation_gap=_string(record, "expectation_gap"),
        pre_surge_signals=tuple(_string_list(record, "pre_surge_signals")),
        contrary_evidence=tuple(_string_list(record, "contrary_evidence")),
        catalyst_watch=tuple(_string_list(record, "catalyst_watch")),
        confidence=_confidence(record.get("confidence")),
        raw_text=_string(record, "raw_text"),
    )


def _select_cases(
    cases: Iterable[HistoricalCase],
    *,
    winner_symbol_count: int,
    control_symbol_count: int,
    refinement_per_label: int,
) -> dict[str, tuple[HistoricalCase, ...]]:
    if winner_symbol_count < 2 or control_symbol_count < 2:
        raise ValidationError("select at least two winner and two control symbols")
    winners = _latest_case_per_symbol(cases, CaseOutcomeLabel.WINNER)
    controls = _latest_case_per_symbol(cases, CaseOutcomeLabel.CONTROL)
    if len(winners) < winner_symbol_count or len(controls) < control_symbol_count:
        raise ValidationError("not enough winner/control symbols for requested Ralph experiment")
    if refinement_per_label < 1:
        raise ValidationError("refinement_per_label must be positive")
    if refinement_per_label >= min(winner_symbol_count, control_symbol_count):
        raise ValidationError("refinement_per_label must leave at least one holdout per label")
    selected_winners = tuple(winners[:winner_symbol_count])
    selected_controls = tuple(controls[:control_symbol_count])
    refinement = selected_winners[:refinement_per_label] + selected_controls[:refinement_per_label]
    holdout = selected_winners[refinement_per_label:] + selected_controls[refinement_per_label:]
    return {
        "refinement": refinement,
        "holdout": holdout,
    }


def _latest_case_per_symbol(
    cases: Iterable[HistoricalCase],
    label: CaseOutcomeLabel,
) -> list[HistoricalCase]:
    latest: dict[str, HistoricalCase] = {}
    for case in cases:
        if case.label is not label:
            continue
        symbol = case.packet.company.ticker.symbol
        current = latest.get(symbol)
        if current is None or case.packet.as_of.as_of_date > current.packet.as_of.as_of_date:
            latest[symbol] = case
    return [latest[symbol] for symbol in sorted(latest)]


def _ralph_researcher(args: argparse.Namespace):
    if args.mode == "heuristic":
        return HeuristicRalphBlindResearcher()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    client = OpenRouterChatClient(
        args.openrouter_model,
        api_key,
        transport=UrllibTransport(timeout_seconds=args.timeout_seconds, max_attempts=2),
    )
    return OpenAIRalphBlindResearcher(client)


def _selection_symbols(selected: dict[str, tuple[HistoricalCase, ...]]) -> list[str]:
    return [
        f"{case.packet.company.ticker.symbol}:{case.label.value}:{bucket}"
        for bucket in ("refinement", "holdout")
        for case in selected[bucket]
    ]


def _case_selection_record(case: HistoricalCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "label": case.label.value,
        "symbol": case.packet.company.ticker.symbol,
        "company_name": case.packet.company.ticker.company_name,
        "as_of_date": case.packet.as_of.as_of_date.isoformat(),
        "outcome_return": case.outcome_return,
    }


def _print_metric_summary(result) -> None:
    refinement = result.refinement_loop.latest_evaluation
    holdout = result.holdout_evaluation
    print(
        "[ralph-experiment] refinement "
        f"scheme={refinement.scheme_version} gap={refinement.confidence_gap:.4f} "
        f"fp_rate={refinement.false_positive_rate:.4f} fn_rate={refinement.false_negative_rate:.4f} "
        f"passed={refinement.separation_passed}"
    )
    print(
        "[ralph-experiment] holdout "
        f"scheme={holdout.scheme_version} gap={holdout.confidence_gap:.4f} "
        f"fp_rate={holdout.false_positive_rate:.4f} fn_rate={holdout.false_negative_rate:.4f} "
        f"passed={holdout.separation_passed}"
    )
    print(f"[ralph-experiment] final_status={result.final_status}")
    if result.final_status != "holdout_separated":
        print(f"[ralph-experiment] error={result.holdout_error_analysis.recommendation}")


def _load_local_env(path: str = ".env.local") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"missing non-empty {key}")
    return value


def _mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValidationError(f"missing object {key}")
    return value


def _string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"{key} must be a non-empty string list")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise ValidationError("outcome_return must be numeric or null")


def _confidence(value: Any) -> float:
    if not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValidationError("confidence must be between 0 and 1")
    return float(value)


if __name__ == "__main__":
    main()
