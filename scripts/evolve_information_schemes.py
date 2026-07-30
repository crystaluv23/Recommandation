"""Run bounded, proposal-only information-scheme evolution."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from stock_opportunity_agent.cases import CaseOutcomeLabel, learn_pre_surge_signal_logic
from stock_opportunity_agent.llm.openai import UrllibTransport
from stock_opportunity_agent.llm.openrouter import OpenRouterChatClient
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research import (
    HeuristicBlindCaseResearcher,
    HeuristicSurgePlaybookSynthesizer,
    synthesize_information_scheme,
)
from stock_opportunity_agent.research.scheme_evolution import (
    CandidateRejection,
    CandidateValidator,
    DataSplitSpec,
    EvaluationSpec,
    EvolutionStateStore,
    FileSchemeProposer,
    FixedEvolutionSpec,
    LabelSpec,
    LabeledSample,
    MockSchemeFoldEvaluator,
    QualityDiversityArchive,
    SchemeEvolutionEngine,
    SchemeGenome,
    build_walk_forward_folds,
    merge_meta_lessons,
)
from stock_opportunity_agent.research.scheme_evolution_ralph import (
    HeuristicGenomeBlindAnalyzer,
    OpenAIGenomeBlindAnalyzer,
    RalphInformationPlanFoldEvaluator,
)
from stock_opportunity_agent.research.ralph_artifacts import (
    load_documents_by_symbol,
    load_historical_cases,
)
from stock_opportunity_agent.themes import build_cold_start_theme_maps


DEFAULT_INITIAL_GENOME = Path("configs/evolution/initial_genome.json")
DEFAULT_CANDIDATES = Path("configs/evolution/codex_candidates_v1.json")
DEFAULT_FORMAL_RUN_DIR = Path(
    "runs/cold_start/formal/cold-start-formal-openrouter-2026-05-13-clean-universe"
)


def main() -> None:
    """Run a dry validation or the network-free vertical slice."""

    args = _parse_args()
    if args.max_concurrency != 1:
        raise ValidationError("v0.1 supports max_concurrency=1; provider concurrency remains external")
    initial = SchemeGenome.from_dict(
        json.loads(Path(args.initial_genome).read_text(encoding="utf-8"))
    )
    proposer = FileSchemeProposer(args.candidate_json)
    output_dir = Path(args.output_dir)
    if args.dry_run:
        _run_dry_validation(initial, proposer, output_dir, count=args.children_per_generation)
        return
    execution_mode = "synthetic_mock_vertical_slice" if args.mock_llm else args.mode
    fixed_spec = _fixed_spec(args, synthetic=args.mock_llm)
    if args.mock_llm:
        folds = build_walk_forward_folds(
            _synthetic_samples(),
            _synthetic_admission_starts(),
            fixed_spec=fixed_spec,
            admission_window_days=35,
        )
        evaluator = MockSchemeFoldEvaluator()
    else:
        folds, evaluator = _real_evaluation_context(args, fixed_spec)
    folds = _select_folds(folds, args.selected_folds)
    if not folds:
        raise ValidationError("no selected walk-forward folds are available")
    archive = QualityDiversityArchive()
    incumbent = initial
    all_experiments = []
    all_rejections: list[CandidateRejection] = []
    meta_memory = []
    mutation_requests = []
    last_paths: dict[str, Path] = {}
    completed_generations = 0
    for generation in range(1, args.generations + 1):
        state_store = EvolutionStateStore(output_dir / f"generation-{generation:02d}")
        engine = SchemeEvolutionEngine(
            proposer=proposer,
            evaluator=evaluator,
            fixed_spec=fixed_spec,
            state_store=state_store,
            archive=archive,
            max_candidates=args.max_candidates,
            max_api_cost_usd=args.max_api_cost,
        )
        result = engine.run(
            incumbent,
            folds,
            meta_memory=meta_memory,
            mutation_requests=mutation_requests,
            candidate_count=args.children_per_generation,
            resume=args.resume,
        )
        incumbent = result.incumbent
        archive = result.archive
        all_experiments.extend(result.experiments)
        all_rejections.extend(result.rejections)
        meta_memory = merge_meta_lessons([*meta_memory, *result.meta_lessons])
        mutation_requests = result.mutation_requests
        last_paths = result.artifact_paths
        completed_generations = generation
        if not result.experiments:
            break
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = (
        Path(args.archive_export)
        if args.archive_export
        else output_dir / "quality_diversity_archive.json"
    )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        json.dumps(archive.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path = output_dir / "evolution_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": "scheme-evolution-v0.1",
                "incumbent_genome_id": incumbent.genome_id,
                "generation_count": completed_generations,
                "selected_fold_ids": [fold.fold_id for fold in folds],
                "experiment_count": len(all_experiments),
                "rejection_count": len(all_rejections),
                "meta_lesson_count": len(meta_memory),
                "next_mutation_request_count": len(mutation_requests),
                "archive_entry_count": len(archive.entries),
                "archive_path": str(archive_path),
                "last_generation_artifacts": {
                    name: str(path) for name, path in sorted(last_paths.items())
                },
                "execution_mode": execution_mode,
                "effectiveness_claim_allowed": False,
                "sealed_test_included": False,
                "provider_execution_enabled": execution_mode == "llm",
                "external_provider_call_count": int(
                    getattr(getattr(evaluator, "analyzer", None), "external_call_count", 0)
                ),
                "blind_cache_hit_count": int(
                    getattr(getattr(evaluator, "analyzer", None), "cache_hit_count", 0)
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[scheme-evolution] incumbent={incumbent.genome_id}")
    print(f"[scheme-evolution] experiments={len(all_experiments)}")
    print(f"[scheme-evolution] archive_entries={len(archive.entries)}")
    print(f"[scheme-evolution] summary={summary_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-genome", default=str(DEFAULT_INITIAL_GENOME))
    parser.add_argument("--candidate-json", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--output-dir", default="runs/cold_start/evolution/codex-v1")
    parser.add_argument(
        "--cases-path",
        default=str(DEFAULT_FORMAL_RUN_DIR / "05_packets/historical_cases.json"),
    )
    parser.add_argument(
        "--documents-path",
        default=str(DEFAULT_FORMAL_RUN_DIR / "04_documents/documents_and_catalysts.json"),
    )
    parser.add_argument("--mode", choices=("heuristic", "llm"), default="heuristic")
    parser.add_argument("--openrouter-model", default="openai/gpt-5.5")
    parser.add_argument(
        "--openrouter-provider",
        default="",
        help="Exact OpenRouter provider slug; required in llm mode.",
    )
    parser.add_argument("--openrouter-temperature", type=float, default=0.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument(
        "--input-cost-per-million-tokens",
        type=float,
        default=0.0,
        help="Current input-token price estimate used by the fixed run cost gate.",
    )
    parser.add_argument(
        "--output-cost-per-million-tokens",
        type=float,
        default=0.0,
        help="Current output-token price estimate used by the fixed run cost gate.",
    )
    parser.add_argument(
        "--blind-cache-dir",
        help="Shared exact packet/prompt/model response cache for real Ralph folds.",
    )
    parser.add_argument(
        "--admission-starts",
        default="2025-01-01,2025-04-01,2025-07-01,2025-10-01",
        help="Comma-separated UTC dates defining walk-forward admission windows.",
    )
    parser.add_argument("--admission-window-days", type=int, default=15)
    parser.add_argument("--label-horizon-days", type=int, default=180)
    parser.add_argument("--purge-days", type=int, default=15)
    parser.add_argument("--embargo-days", type=int, default=15)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--children-per-generation", type=int, default=2)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--max-api-cost", type=float, default=20.0)
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument(
        "--selected-folds",
        default="",
        help="Comma-separated fold ids or one-based fold indexes; default uses all.",
    )
    parser.add_argument("--archive-export")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use the synthetic network-free vertical slice instead of real Ralph artifacts.",
    )
    args = parser.parse_args()
    if args.generations < 1:
        parser.error("--generations must be positive")
    if args.children_per_generation < 1:
        parser.error("--children-per-generation must be positive")
    if args.admission_window_days < 1 or args.label_horizon_days < 1:
        parser.error("admission window and label horizon must be positive")
    return args


def _run_dry_validation(
    initial: SchemeGenome,
    proposer: FileSchemeProposer,
    output_dir: Path,
    *,
    count: int,
) -> None:
    candidates = proposer.propose([initial], [], [], count)
    validator = CandidateValidator()
    accepted: list[SchemeGenome] = []
    rejections: list[CandidateRejection] = []
    for candidate in candidates:
        reasons = validator.validate(candidate, parents=[initial], accepted=accepted)
        if reasons:
            rejections.append(CandidateRejection(candidate.genome_id, reasons))
        else:
            accepted.append(candidate)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "dry_run_validation.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "scheme-evolution-v0.1",
                "initial_genome_id": initial.genome_id,
                "accepted_candidate_ids": [candidate.genome_id for candidate in accepted],
                "rejections": [rejection.to_dict() for rejection in rejections],
                "provider_call_performed": False,
                "sealed_test_included": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[scheme-evolution] dry_run={path}")
    print(f"[scheme-evolution] accepted={len(accepted)} rejected={len(rejections)}")


def _fixed_spec(args: argparse.Namespace, *, synthetic: bool) -> FixedEvolutionSpec:
    return FixedEvolutionSpec(
        label_spec=LabelSpec(
            version=(
                "synthetic-surge-label-v1"
                if synthetic
                else f"historical-outcome-label-{args.label_horizon_days}d-v1"
            ),
            horizon_days=90 if synthetic else args.label_horizon_days,
        ),
        split_spec=DataSplitSpec(
            version=(
                "synthetic-expanding-walk-forward-v1"
                if synthetic
                else "ralph-expanding-company-disjoint-walk-forward-v1"
            ),
            purge_days=15 if synthetic else args.purge_days,
            embargo_days=15 if synthetic else args.embargo_days,
        ),
        evaluation_spec=EvaluationSpec(
            version=(
                "synthetic-paired-admission-v1"
                if synthetic
                else "ralph-paired-admission-v1"
            ),
            top_k=4,
            bootstrap_replicates=200,
            minimum_paired_blocks=4,
            maximum_cost_usd=args.max_api_cost,
        ),
    )


def _real_evaluation_context(
    args: argparse.Namespace,
    fixed_spec: FixedEvolutionSpec,
):
    cases = load_historical_cases(Path(args.cases_path))
    documents = load_documents_by_symbol(Path(args.documents_path))
    samples = [
        _real_sample(case, documents)
        for case in cases
        if case.label in {CaseOutcomeLabel.WINNER, CaseOutcomeLabel.CONTROL}
    ]
    admission_starts = [
        datetime.fromisoformat(value.strip()).replace(tzinfo=timezone.utc)
        for value in args.admission_starts.split(",")
        if value.strip()
    ]
    folds = build_walk_forward_folds(
        samples,
        admission_starts,
        fixed_spec=fixed_spec,
        admission_window_days=args.admission_window_days,
    )
    if not folds:
        raise ValidationError(
            "real artifacts produced no eligible walk-forward folds after purge/embargo"
        )
    discovery_cases = [
        case
        for sample in folds[0].discovery_samples
        for case in (next(item for item in cases if item.case_id == sample.sample_id),)
    ]
    learning = learn_pre_surge_signal_logic(discovery_cases)
    themes = build_cold_start_theme_maps(discovery_cases, learning)
    baseline = tuple(
        HeuristicBlindCaseResearcher().analyze(case)
        for case in discovery_cases
    )
    playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(
        discovery_cases,
        baseline,
        learning,
        themes,
    )
    base_scheme, _diagnostic = synthesize_information_scheme(
        discovery_cases,
        learning_result=learning,
        theme_maps=themes,
        playbook_synthesis=playbooks,
    )
    if args.mode == "heuristic":
        analyzer = HeuristicGenomeBlindAnalyzer()
    else:
        if (
            args.input_cost_per_million_tokens <= 0
            or args.output_cost_per_million_tokens <= 0
        ):
            raise ValidationError(
                "llm mode requires positive input/output token price estimates "
                "so --max-api-cost can fail closed"
            )
        if not args.openrouter_provider.strip():
            raise ValidationError(
                "llm mode requires --openrouter-provider so provider routing is fixed"
            )
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValidationError("OPENROUTER_API_KEY is not set")
        cache_dir = (
            Path(args.blind_cache_dir)
            if args.blind_cache_dir
            else Path(args.output_dir) / "blind_analysis_cache"
        )
        client = OpenRouterChatClient(
            args.openrouter_model,
            api_key,
            temperature=args.openrouter_temperature,
            provider_only=(args.openrouter_provider,),
            provider_require_parameters=True,
            provider_allow_fallbacks=False,
            transport=UrllibTransport(
                timeout_seconds=args.timeout_seconds,
                max_attempts=4,
            ),
        )
        analyzer = OpenAIGenomeBlindAnalyzer(
            client,
            cache_dir,
            provider=f"openrouter:{args.openrouter_provider}",
            model=args.openrouter_model,
            temperature=args.openrouter_temperature,
            input_cost_per_million_tokens=args.input_cost_per_million_tokens,
            output_cost_per_million_tokens=args.output_cost_per_million_tokens,
            max_cost_usd=args.max_api_cost,
        )
    evaluator = RalphInformationPlanFoldEvaluator(
        cases=cases,
        documents_by_symbol=documents,
        base_scheme=base_scheme,
        analyzer=analyzer,
        artifact_dir=Path(args.output_dir) / "packet_preflight",
    )
    return folds, evaluator


def _real_sample(case, documents_by_symbol) -> LabeledSample:
    packet = case.packet
    symbol = packet.company.ticker.symbol.upper()
    market_cap = packet.company.market_cap_usd
    market_cap_bucket = (
        "unknown"
        if market_cap is None
        else "small"
        if market_cap < 2_000_000_000
        else "mid"
        if market_cap < 10_000_000_000
        else "large"
    )
    prediction_time = datetime.combine(
        packet.as_of.as_of_date,
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    available_dates = [
        document.available_date
        for document in documents_by_symbol.get(symbol, ())
        if document.available_date is not None
        and document.available_date <= packet.as_of.as_of_date
    ]
    return LabeledSample(
        sample_id=case.case_id,
        company_key=symbol,
        prediction_time=prediction_time,
        label=1 if case.label is CaseOutcomeLabel.WINNER else 0,
        sector=packet.company.sector,
        market_cap_bucket=market_cap_bucket,
        period=f"{packet.as_of.as_of_date.year}-Q{(packet.as_of.as_of_date.month - 1) // 3 + 1}",
        features={},
        evidence_source_ids=[],
        document_available_dates=available_dates,
    )


def _synthetic_samples() -> list[LabeledSample]:
    samples: list[LabeledSample] = []
    discovery_start = datetime(2023, 1, 10, tzinfo=timezone.utc)
    for index in range(8):
        prediction_time = discovery_start + timedelta(days=index * 24)
        label = index % 2
        samples.append(
            _synthetic_sample(
                sample_id=f"discovery-{index + 1:02d}",
                company_key=f"discovery-company-{index + 1:02d}",
                prediction_time=prediction_time,
                label=label,
                strength=0.7 if label else 0.25,
                period="2023-H1" if index < 4 else "2023-H2",
            )
        )
    for fold_index, start in enumerate(_synthetic_admission_starts(), start=1):
        for offset, (label, strength) in enumerate(
            ((1, 0.72), (0, 0.24), (1, 0.68), (0, 0.28)),
            start=1,
        ):
            samples.append(
                _synthetic_sample(
                    sample_id=f"admission-{fold_index:02d}-{offset:02d}",
                    company_key=f"admission-company-{fold_index:02d}-{offset:02d}",
                    prediction_time=start + timedelta(days=offset),
                    label=label,
                    strength=strength,
                    period=start.strftime("%Y-%m"),
                )
            )
    return samples


def _synthetic_admission_starts() -> list[datetime]:
    return [
        datetime(2024, 6, 1, tzinfo=timezone.utc),
        datetime(2024, 10, 1, tzinfo=timezone.utc),
        datetime(2025, 2, 1, tzinfo=timezone.utc),
        datetime(2025, 6, 1, tzinfo=timezone.utc),
    ]


def _synthetic_sample(
    *,
    sample_id: str,
    company_key: str,
    prediction_time: datetime,
    label: int,
    strength: float,
    period: str,
) -> LabeledSample:
    return LabeledSample(
        sample_id=sample_id,
        company_key=company_key,
        prediction_time=prediction_time,
        label=label,
        sector="synthetic-sector-a" if label else "synthetic-sector-b",
        market_cap_bucket="small" if label else "mid",
        period=period,
        features={"signal_strength": strength},
        evidence_source_ids=[f"source:{sample_id}"],
        document_available_dates=[prediction_time.date() - timedelta(days=1)],
    )


def _select_folds(folds, raw_selection: str):
    if not raw_selection.strip():
        return folds
    requested = {item.strip() for item in raw_selection.split(",") if item.strip()}
    selected = [
        fold
        for index, fold in enumerate(folds, start=1)
        if fold.fold_id in requested or str(index) in requested
    ]
    missing = requested - {
        value
        for index, fold in enumerate(folds, start=1)
        for value in (fold.fold_id, str(index))
    }
    if missing:
        raise ValidationError(f"unknown selected folds: {sorted(missing)}")
    return selected


if __name__ == "__main__":
    main()
