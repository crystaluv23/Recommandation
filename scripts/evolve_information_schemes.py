"""Run bounded, proposal-only information-scheme evolution."""

from __future__ import annotations

import argparse
import calendar
import json
import os
from collections import Counter
from dataclasses import replace
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
    EvaluationContract,
    EvaluationSpec,
    EvolutionStateStore,
    FileSchemeProposer,
    FixedEvolutionSpec,
    LabeledSample,
    MockSchemeFoldEvaluator,
    MockSchemeProposer,
    MutationOperator,
    TopKArchive,
    SchemeEvolutionEngine,
    SchemeGenome,
    build_walk_forward_folds,
    evaluate_predictions,
    merge_meta_lessons,
    realized_max_multiple,
    validate_folds,
)
from stock_opportunity_agent.research.scheme_evolution_ralph import (
    HeuristicGenomeBlindAnalyzer,
    OpenAIGenomeBlindAnalyzer,
    OpenRouterFusionSchemeProposer,
    RalphInformationPlanFoldEvaluator,
)
from stock_opportunity_agent.research.scheme_evolution_dashboard import (
    write_evolution_dashboard,
    write_evolution_dashboard_index,
)
from stock_opportunity_agent.research.ralph_artifacts import (
    load_documents_by_symbol,
    load_historical_cases,
)
from stock_opportunity_agent.themes import build_cold_start_theme_maps


DEFAULT_INITIAL_GENOME = Path("configs/evolution/initial_genome.json")
DEFAULT_CANDIDATES = Path("configs/evolution/codex_candidates_v1.json")
DEFAULT_EVOLUTION_ROOT = Path("runs/cold_start/evolution")
DEFAULT_FORMAL_RUN_DIR = Path(
    "runs/cold_start/formal/cold-start-formal-openrouter-2026-05-13-clean-universe"
)


def main() -> None:
    """Run a dry validation or the network-free vertical slice."""

    _load_local_env()
    args = _parse_args()
    if args.max_concurrency != 1:
        raise ValidationError("v0.2 supports max_concurrency=1; provider concurrency remains external")
    initial = SchemeGenome.from_dict(
        json.loads(Path(args.initial_genome).read_text(encoding="utf-8"))
    )
    proposer = FileSchemeProposer(args.candidate_json)
    output_dir = Path(args.output_dir)
    state_store = EvolutionStateStore(output_dir, run_id=args.run_id or output_dir.name)
    if args.command == "status":
        state = state_store.load_state()
        _refresh_evolution_dashboards(output_dir)
        print(json.dumps(state, indent=2, sort_keys=True))
        return
    if args.command == "dashboard":
        state_store.load_state()
        paths = _refresh_evolution_dashboards(output_dir)
        print(f"[scheme-evolution] dashboard={paths['dashboard']}")
        print(f"[scheme-evolution] run_dashboard={paths['run_dashboard']}")
        return
    if args.command == "resume":
        args.resume = True
    if args.dry_run:
        _run_dry_validation(initial, proposer, output_dir, count=args.children_per_generation)
        return
    execution_mode = "synthetic_mock_vertical_slice" if args.mock_llm else args.mode
    fixed_spec = _fixed_spec(args, synthetic=args.mock_llm)
    state_store.initialize(
        fixed_spec,
        config={
            "random_seed": args.random_seed,
            "initial_genome": str(args.initial_genome),
            "candidate_json": str(args.candidate_json),
            "mode": execution_mode,
        },
    )
    state_store.write_objective_prompt(
        Path("prompts/evolution_objective.md").read_text(encoding="utf-8")
    )
    dashboard_paths = _refresh_evolution_dashboards(output_dir)
    if args.command == "init":
        print(f"[scheme-evolution] initialized={output_dir}")
        print(f"[scheme-evolution] dashboard={dashboard_paths['dashboard']}")
        return
    if args.command in {"fusion-preflight", "fusion-sample"}:
        fusion_proposer = _fusion_proposer(
            args,
            output_dir,
            preview_only=args.command == "fusion-preflight",
        )
        if args.command == "fusion-preflight":
            _run_fusion_proposal_preflight(
                initial,
                fusion_proposer,
                output_dir=output_dir,
            )
        else:
            if not args.external_transmission_authorized:
                raise ValidationError(
                    "fusion-sample requires --external-transmission-authorized"
                )
            _run_fusion_candidate_sample(
                initial,
                fusion_proposer,
                candidate_path=Path(args.candidate_json),
                output_dir=output_dir,
                state_store=state_store,
            )
        return
    if args.command == "final-test":
        if not args.mock_llm:
            raise ValidationError(
                "real final-test is fail-closed until a separately labeled A/B/C "
                "dataset and source archive are supplied; ordinary run/resume never "
                "loads final-test labels"
            )
        _run_mock_final_test(state_store, fixed_spec)
        return
    if (
        args.command in {"run", "resume"}
        and args.mode == "llm"
        and not args.external_transmission_authorized
    ):
        raise ValidationError(
            "real llm run/resume requires --external-transmission-authorized"
        )
    if args.mock_llm:
        folds = build_walk_forward_folds(
            _synthetic_samples(),
            _synthetic_admission_starts(),
            fixed_spec=fixed_spec,
            admission_window_days=35,
        )
        evaluator = MockSchemeFoldEvaluator()
    else:
        folds, evaluator = _real_evaluation_context(
            args,
            fixed_spec,
            preview_only=args.command == "external-preflight",
        )
    folds = _select_folds(folds, args.selected_folds)
    if not folds:
        raise ValidationError("no selected walk-forward folds are available")
    if args.command == "external-preflight":
        if args.mock_llm or args.mode != "llm":
            raise ValidationError("external-preflight requires real llm mode")
        _run_external_disclosure_preflight(
            initial,
            proposer,
            evaluator,
            folds,
            args=args,
            output_dir=output_dir,
        )
        return
    archive = TopKArchive()
    incumbent = initial
    all_experiments = []
    all_rejections: list[CandidateRejection] = []
    meta_memory = []
    mutation_requests = []
    last_paths: dict[str, Path] = {}
    completed_generations = 0
    for generation in range(1, args.generations + 1):
        generation_proposer = proposer
        if args.mock_llm and generation > 1:
            generation_proposer = MockSchemeProposer(
                [
                    replace(
                        incumbent,
                        genome_id=f"{incumbent.genome_id}-local-refine-g{generation}",
                        parent_ids=[incumbent.genome_id],
                        generation=incumbent.generation + 1,
                        mutation_operator=MutationOperator.LOCAL_REFINE,
                        hypothesis_of_change="Test a stricter threshold for extreme C-class evidence.",
                        changed_fields=["metadata.ordinal_shift_min_strength"],
                        expected_benefit="Reduce B-to-C ordinal overclassification without changing binary semantics.",
                        possible_side_effects=["May miss marginal C-class cases."],
                        falsification_test="Reject if class C recall falls or ordinal distance rises.",
                        target_failure_type="general",
                        metadata={
                            **incumbent.metadata,
                            "ordinal_shift_min_strength": 0.75,
                        },
                    )
                ]
            )
        engine = SchemeEvolutionEngine(
            proposer=generation_proposer,
            evaluator=evaluator,
            fixed_spec=fixed_spec,
            state_store=state_store,
            archive=archive,
            validator=(
                CandidateValidator(near_duplicate_threshold=1.0)
                if args.mock_llm and generation > 1
                else None
            ),
            max_candidates=args.max_candidates,
            max_api_cost_usd=args.max_api_cost,
            progress=print,
        )
        result = engine.run(
            incumbent,
            folds,
            meta_memory=meta_memory,
            mutation_requests=mutation_requests,
            candidate_count=args.children_per_generation,
            resume=args.resume or generation > 1,
        )
        incumbent = result.incumbent
        archive = result.archive
        all_experiments.extend(result.experiments)
        all_rejections.extend(result.rejections)
        meta_memory = merge_meta_lessons([*meta_memory, *result.meta_lessons])
        mutation_requests = result.mutation_requests
        last_paths = result.artifact_paths
        dashboard_paths = _refresh_evolution_dashboards(output_dir)
        last_paths = {**last_paths, **dashboard_paths}
        completed_generations = generation
        if not result.experiments:
            break
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = (
        Path(args.archive_export)
        if args.archive_export
        else output_dir / "top_k.json"
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
                "schema_version": "scheme-evolution-v0.2",
                "incumbent_genome_id": incumbent.genome_id,
                "generation_count": completed_generations,
                "selected_fold_ids": [fold.fold_id for fold in folds],
                "experiment_count": len(all_experiments),
                "rejection_count": len(all_rejections),
                "meta_lesson_count": len(meta_memory),
                "next_mutation_request_count": len(mutation_requests),
                "top_k_entry_count": len(archive.entries),
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
    print(f"[scheme-evolution] dashboard={dashboard_paths['dashboard']}")


def _refresh_evolution_dashboards(output_dir: Path) -> dict[str, Path]:
    """Refresh the portable run view and the one stable repository-level view."""

    run_paths = write_evolution_dashboard(output_dir)
    index_paths = write_evolution_dashboard_index(DEFAULT_EVOLUTION_ROOT)
    return {
        "run_history": run_paths["history"],
        "run_data": run_paths["data"],
        "run_dashboard": run_paths["dashboard"],
        "dashboard_index": index_paths["index"],
        "dashboard_data": index_paths["data"],
        "dashboard": index_paths["dashboard"],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=(
            "init",
            "run",
            "resume",
            "status",
            "dashboard",
            "external-preflight",
            "fusion-preflight",
            "fusion-sample",
            "final-test",
        ),
        default="run",
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--config", default="", help="Optional JSON experiment config.")
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
    parser.add_argument("--analysis-max-attempts", type=int, default=1)
    parser.add_argument("--provider-http-max-attempts", type=int, default=1)
    parser.add_argument("--blind-max-output-tokens", type=int, default=2200)
    parser.add_argument(
        "--blind-reasoning-effort",
        choices=("", "max", "xhigh", "high", "medium", "low"),
        default="",
    )
    parser.add_argument("--fusion-model", default="openrouter/fusion")
    parser.add_argument("--fusion-preset", default="general-high")
    parser.add_argument("--fusion-max-tool-calls", type=int, default=1)
    parser.add_argument("--fusion-inner-max-tokens", type=int, default=3000)
    parser.add_argument("--fusion-max-output-tokens", type=int, default=5000)
    parser.add_argument("--fusion-max-cost", type=float, default=2.0)
    parser.add_argument("--fusion-cache-dir", default="")
    parser.add_argument("--external-transmission-authorized", action="store_true")
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
    parser.add_argument("--purge-days", type=int, default=15)
    parser.add_argument("--embargo-days", type=int, default=15)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--children-per-generation", type=int, default=2)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--prediction-similarity-threshold", type=float, default=0.95)
    parser.add_argument("--max-api-cost", type=float, default=20.0)
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument(
        "--price-histories-path",
        default="",
        help="Required for real A/B/C evaluation; JSON with bars_by_symbol adjusted closes.",
    )
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
    if args.config:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        for key, value in config.get("cli", {}).items():
            attribute = key.replace("-", "_")
            if attribute == "external_transmission_authorized":
                parser.error("external transmission authorization must be CLI-only")
            if not hasattr(args, attribute):
                parser.error(f"unknown config.cli field: {key}")
            setattr(args, attribute, value)
        args.evaluation_contract_config = config.get("evaluation_contract")
    else:
        args.evaluation_contract_config = None
    if args.generations < 1:
        parser.error("--generations must be positive")
    if args.children_per_generation < 1:
        parser.error("--children-per-generation must be positive")
    if args.admission_window_days < 1:
        parser.error("admission window must be positive")
    if args.analysis_max_attempts < 1 or args.provider_http_max_attempts < 1:
        parser.error("LLM attempt bounds must be positive")
    if args.blind_max_output_tokens < 1:
        parser.error("--blind-max-output-tokens must be positive")
    if (
        args.fusion_max_tool_calls < 1
        or args.fusion_inner_max_tokens < 1
        or args.fusion_max_output_tokens < 1
        or args.fusion_max_cost <= 0
    ):
        parser.error("Fusion proposal bounds must be positive")
    return args


def _load_local_env(path: str = ".env.local") -> None:
    """Load uncommitted local credentials without overwriting process settings."""

    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


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
                "schema_version": "scheme-evolution-v0.2",
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


def _fusion_proposer(
    args: argparse.Namespace,
    output_dir: Path,
    *,
    preview_only: bool,
) -> OpenRouterFusionSchemeProposer:
    api_key = (
        "preview-only-no-network"
        if preview_only
        else os.environ.get("OPENROUTER_API_KEY")
    )
    if not api_key:
        raise ValidationError("OPENROUTER_API_KEY is not set")
    client = OpenRouterChatClient(
        args.fusion_model,
        api_key,
        temperature=0.0,
        transport=UrllibTransport(
            timeout_seconds=args.timeout_seconds,
            max_attempts=args.provider_http_max_attempts,
        ),
    )
    cache_dir = (
        Path(args.fusion_cache_dir)
        if args.fusion_cache_dir
        else output_dir / "fusion_proposal_cache"
    )
    return OpenRouterFusionSchemeProposer(
        client,
        cache_dir,
        objective_text=Path("prompts/evolution_objective.md").read_text(
            encoding="utf-8"
        ),
        preset=args.fusion_preset,
        max_tool_calls=args.fusion_max_tool_calls,
        inner_max_tokens=args.fusion_inner_max_tokens,
        outer_max_tokens=args.fusion_max_output_tokens,
        max_cost_usd=args.fusion_max_cost,
    )


def _run_fusion_proposal_preflight(
    initial: SchemeGenome,
    proposer: OpenRouterFusionSchemeProposer,
    *,
    output_dir: Path,
) -> None:
    preview = proposer.preview_request([initial], [], [], 1)
    estimated_cost = float(preview["maximum_estimated_cost_usd"])
    passed = estimated_cost <= proposer.max_cost_usd
    payload = {
        "schema_version": "scheme-evolution-fusion-proposal-preflight-v0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "proposal_generation_not_blind_validation",
        "authorization_status": "pending_updated_request_scope_approval",
        "proposal_only": True,
        "external_call_performed": False,
        "request_count": 1,
        "passed": passed,
        "configured_cost_cap_usd": proposer.max_cost_usd,
        "request": preview,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "fusion_proposal_preflight.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    print(
        f"[scheme-evolution] fusion-preflight={path} passed={str(passed).lower()} "
        f"requests=1 estimated_max_cost_usd={estimated_cost:.6f} external_calls=0"
    )
    if not passed:
        raise ValidationError("Fusion proposal preflight exceeds its cost cap")


def _run_fusion_candidate_sample(
    initial: SchemeGenome,
    proposer: OpenRouterFusionSchemeProposer,
    *,
    candidate_path: Path,
    output_dir: Path,
    state_store: EvolutionStateStore,
) -> None:
    preflight_path = output_dir / "fusion_proposal_preflight.json"
    if not preflight_path.exists():
        raise ValidationError("fusion-sample requires a passed Fusion preflight")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preview = proposer.preview_request([initial], [], [], 1)
    if not preflight.get("passed"):
        raise ValidationError("Fusion proposal preflight did not pass")
    if preflight.get("request", {}).get("request_hash") != preview["request_hash"]:
        raise ValidationError("Fusion proposal request differs from its reviewed preflight")
    candidates = proposer.propose([initial], [], [], 1)
    reasons = CandidateValidator().validate(
        candidates[0],
        parents=[initial],
        accepted=[],
    )
    payload = {
        "schema_version": "scheme-evolution-candidates-v0.2",
        "authored_by": "openrouter/fusion:general-high",
        "proposal_only": True,
        "external_call_count": proposer.external_call_count,
        "cache_hit_count": proposer.cache_hit_count,
        "reported_or_estimated_cost_usd": proposer.spent_cost_usd,
        "candidate_rejections": (
            [{"genome_id": candidates[0].genome_id, "reasons": reasons}]
            if reasons
            else []
        ),
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = candidate_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(candidate_path)
    state_store.append_event(
        "fusion_candidate_sampled",
        {
            "candidate_path": str(candidate_path),
            "candidate_id": candidates[0].genome_id,
            "rejection_reasons": reasons,
            "external_call_count": proposer.external_call_count,
        },
    )
    print(
        f"[scheme-evolution] fusion-candidate={candidates[0].genome_id} "
        f"accepted={str(not reasons).lower()} external_calls={proposer.external_call_count} "
        f"candidate_file={candidate_path}"
    )
    if reasons:
        raise ValidationError("Fusion candidate failed static validation")


def _run_external_disclosure_preflight(
    initial: SchemeGenome,
    proposer: FileSchemeProposer,
    evaluator: RalphInformationPlanFoldEvaluator,
    folds,
    *,
    args: argparse.Namespace,
    output_dir: Path,
) -> None:
    """Persist exact secret-free requests without contacting the provider."""

    if args.analysis_max_attempts != 1 or args.provider_http_max_attempts != 1:
        raise ValidationError(
            "the first external preflight requires one analyzer attempt and one HTTP attempt"
        )
    candidates = proposer.propose(
        [initial],
        [],
        [],
        min(args.children_per_generation, args.max_candidates),
    )
    validator = CandidateValidator()
    accepted: list[SchemeGenome] = []
    rejections: list[CandidateRejection] = []
    for candidate in candidates:
        reasons = validator.validate(candidate, parents=[initial], accepted=accepted)
        if reasons:
            rejections.append(CandidateRejection(candidate.genome_id, reasons))
        else:
            accepted.append(candidate)
    genomes = [initial, *accepted]
    forbidden_keys = {
        "company_key",
        "company_name",
        "forward_return",
        "future_price",
        "is_surge",
        "label",
        "outcome",
        "outcome_return",
        "realized_max_multiple",
        "source_case_id",
        "ticker",
        "true_class",
    }
    requests = []
    findings: list[dict[str, object]] = []
    maximum_cost_usd = 0.0
    for genome in genomes:
        print(
            f"[scheme-evolution] preflight-genome={genome.genome_id} "
            f"mutation={genome.mutation_operator.value} "
            f"changed={','.join(genome.changed_fields) or 'baseline'} "
            "scope=development proposal_only=true"
        )
        for fold in folds:
            materialized = evaluator.materialize(genome, fold)
            for sample in fold.admission_samples:
                preview = evaluator.preview_request(
                    genome,
                    materialized,
                    sample.blind_view(),
                )
                payload_keys = _nested_mapping_keys(preview["input_payload"])
                request_findings = sorted(payload_keys & forbidden_keys)
                serialized_input = json.dumps(
                    preview["input_payload"],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if sample.sample_id in serialized_input:
                    request_findings.append("source_sample_id_value")
                if request_findings:
                    findings.append(
                        {
                            "request_index": len(requests) + 1,
                            "finding_types": request_findings,
                        }
                    )
                request_cost = float(preview["maximum_request_cost_usd"])
                maximum_cost_usd += request_cost
                requests.append(
                    {
                        "request_index": len(requests) + 1,
                        "genome_id": genome.genome_id,
                        "fold_id": fold.fold_id,
                        "anonymous_case_id": preview["input_payload"]["packet"][
                            "anonymous_case_id"
                        ],
                        "input_hash": preview["input_hash"],
                        "cache_key": preview["cache_key"],
                        "finding_types": request_findings,
                        "request": preview,
                    }
                )
    packet_preflights = sorted(
        str(path)
        for path in (output_dir / "packet_preflight").glob(
            "*/materialization_preflight.json"
        )
    )
    passed = (
        bool(requests)
        and not findings
        and maximum_cost_usd <= args.max_api_cost
        and len(packet_preflights) == len(genomes) * len(folds)
    )
    payload = {
        "schema_version": "scheme-evolution-external-disclosure-preflight-v0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id or output_dir.name,
        "scope": "retrospective_development_proposal_only",
        "authorization_status": "pending_explicit_user_approval",
        "external_call_performed": False,
        "effectiveness_claim_allowed": False,
        "passed": passed,
        "finding_count": len(findings),
        "findings": findings,
        "destination": requests[0]["request"]["destination"] if requests else None,
        "provider": requests[0]["request"]["provider"] if requests else None,
        "model": args.openrouter_model,
        "temperature": args.openrouter_temperature,
        "provider_routing": (
            requests[0]["request"]["provider_routing"] if requests else None
        ),
        "analysis_max_attempts": args.analysis_max_attempts,
        "provider_http_max_attempts": args.provider_http_max_attempts,
        "request_count": len(requests),
        "hard_maximum_external_request_count": len(requests),
        "maximum_total_cost_usd": maximum_cost_usd,
        "configured_cost_cap_usd": args.max_api_cost,
        "accepted_genome_ids": [genome.genome_id for genome in genomes],
        "candidate_summaries": [
            {
                "genome_id": genome.genome_id,
                "parent_ids": genome.parent_ids,
                "mutation_operator": genome.mutation_operator.value,
                "changed_fields": genome.changed_fields,
                "expected_benefit": genome.expected_benefit,
                "falsification_test": genome.falsification_test,
            }
            for genome in accepted
        ],
        "candidate_rejections": [row.to_dict() for row in rejections],
        "packet_preflight_paths": packet_preflights,
        "requests": requests,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "external_disclosure_preflight.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    analyzer = evaluator.analyzer
    if int(getattr(analyzer, "external_call_count", -1)) != 0:
        raise ValidationError("external disclosure preflight unexpectedly called the provider")
    print(
        f"[scheme-evolution] external-preflight={path} passed={str(passed).lower()} "
        f"requests={len(requests)} findings={len(findings)} "
        f"max_cost_usd={maximum_cost_usd:.6f} external_calls=0"
    )
    if not passed:
        raise ValidationError("external disclosure preflight failed; inspect its findings")


def _nested_mapping_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key))
            keys.update(_nested_mapping_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            keys.update(_nested_mapping_keys(nested))
    return keys


def _fixed_spec(args: argparse.Namespace, *, synthetic: bool) -> FixedEvolutionSpec:
    return FixedEvolutionSpec(
        evaluation_contract=(
            EvaluationContract.from_dict(args.evaluation_contract_config)
            if args.evaluation_contract_config
            else EvaluationContract()
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
                "synthetic-binary-f1-top-k-v2"
                if synthetic
                else "ralph-binary-f1-top-k-v2"
            ),
            top_k=args.top_k,
            prediction_similarity_threshold=args.prediction_similarity_threshold,
            maximum_cost_usd=args.max_api_cost,
        ),
    )


def _real_evaluation_context(
    args: argparse.Namespace,
    fixed_spec: FixedEvolutionSpec,
    *,
    preview_only: bool = False,
):
    cases = load_historical_cases(Path(args.cases_path))
    documents = load_documents_by_symbol(Path(args.documents_path))
    if not args.price_histories_path:
        raise ValidationError(
            "real A/B/C evaluation requires --price-histories-path; legacy terminal-return "
            "labels cannot be presented as the frozen five-day-smoothed maximum multiple"
        )
    price_payload = json.loads(Path(args.price_histories_path).read_text(encoding="utf-8"))
    bars_by_symbol = price_payload.get("bars_by_symbol")
    if not isinstance(bars_by_symbol, dict):
        raise ValidationError("price histories must contain bars_by_symbol")
    considered_cases = [
        case
        for case in cases
        if case.label in {CaseOutcomeLabel.WINNER, CaseOutcomeLabel.CONTROL}
    ]
    samples: list[LabeledSample] = []
    exclusions: list[dict[str, str]] = []
    for case in considered_cases:
        try:
            samples.append(
                _real_sample(
                    case,
                    documents,
                    bars_by_symbol,
                    fixed_spec.evaluation_contract,
                )
            )
        except ValidationError as exc:
            reason_code = _price_sample_exclusion_reason(exc)
            if reason_code is None:
                raise
            exclusions.append(
                {
                    "case_id": case.case_id,
                    "reason": reason_code,
                    "detail": str(exc),
                }
            )
    admission_starts = [
        datetime.fromisoformat(value.strip()).replace(tzinfo=timezone.utc)
        for value in args.admission_starts.split(",")
        if value.strip()
    ]
    folds = _select_folds(
        build_walk_forward_folds(
            samples,
            admission_starts,
            fixed_spec=fixed_spec,
            admission_window_days=args.admission_window_days,
        ),
        args.selected_folds,
    )
    class_support_issues = _fold_class_support_issues(folds)
    preflight_path = _write_real_dataset_preflight(
        Path(args.output_dir),
        args=args,
        fixed_spec=fixed_spec,
        considered_cases=considered_cases,
        samples=samples,
        exclusions=exclusions,
        folds=folds,
        price_payload=price_payload,
        class_support_issues=class_support_issues,
    )
    print(
        f"[scheme-evolution] dataset-preflight={preflight_path} "
        f"eligible={len(samples)} excluded={len(exclusions)} folds={len(folds)}"
    )
    for fold in folds:
        discovery_counts = Counter(sample.true_class for sample in fold.discovery_samples)
        admission_counts = Counter(sample.true_class for sample in fold.admission_samples)
        print(
            f"[scheme-evolution] fold={fold.fold_id} "
            f"signal_train={len(fold.discovery_samples)} "
            f"signal_train_classes={dict(sorted(discovery_counts.items()))} "
            f"development={len(fold.admission_samples)} "
            f"development_classes={dict(sorted(admission_counts.items()))}"
        )
    if class_support_issues:
        raise ValidationError("; ".join(class_support_issues))
    validate_folds(folds, fixed_spec)
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
        api_key = (
            "preview-only-no-network"
            if preview_only
            else os.environ.get("OPENROUTER_API_KEY")
        )
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
                max_attempts=args.provider_http_max_attempts,
            ),
        )
        analyzer = OpenAIGenomeBlindAnalyzer(
            client,
            cache_dir,
            provider=f"openrouter:{args.openrouter_provider}",
            model=args.openrouter_model,
            temperature=args.openrouter_temperature,
            max_attempts=args.analysis_max_attempts,
            max_output_tokens=args.blind_max_output_tokens,
            reasoning_effort=args.blind_reasoning_effort or None,
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


def _price_sample_exclusion_reason(error: ValidationError) -> str | None:
    message = str(error)
    if "has no adjusted close at prediction time" in message:
        return "missing_prediction_adjusted_close"
    if message == "future price history is shorter than the smoothing window":
        return "insufficient_future_smoothing_window"
    return None


def _fold_class_support_issues(folds) -> list[str]:
    if not folds:
        return ["real artifacts produced no eligible walk-forward folds after purge/embargo"]
    issues: list[str] = []
    for fold in folds:
        for partition_name, samples in (
            ("signal-train", fold.discovery_samples),
            ("development validation", fold.admission_samples),
        ):
            binary_classes = {sample.is_surge for sample in samples}
            if binary_classes != {False, True}:
                issues.append(
                    f"fold {fold.fold_id} {partition_name} requires both A and B/C classes"
                )
    return issues


def _write_real_dataset_preflight(
    output_dir: Path,
    *,
    args: argparse.Namespace,
    fixed_spec: FixedEvolutionSpec,
    considered_cases,
    samples: list[LabeledSample],
    exclusions: list[dict[str, str]],
    folds,
    price_payload: dict,
    class_support_issues: list[str],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "dataset_preflight_label_aware.json"
    payload = {
        "schema_version": "scheme-evolution-dataset-preflight-v1",
        "scope": "retrospective_label_aware_development",
        "proposal_status": "proposal_only_pending_human_review",
        "external_call_performed_during_dataset_preflight": False,
        "effectiveness_claim_allowed": False,
        "evaluation_contract_hash": fixed_spec.evaluation_contract.content_hash,
        "cases_path": args.cases_path,
        "documents_path": args.documents_path,
        "price_histories_path": args.price_histories_path,
        "considered_case_count": len(considered_cases),
        "eligible_case_count": len(samples),
        "excluded_case_count": len(exclusions),
        "eligible_class_counts": dict(sorted(Counter(sample.true_class for sample in samples).items())),
        "exclusion_reason_counts": dict(
            sorted(Counter(row["reason"] for row in exclusions).items())
        ),
        "excluded_cases": exclusions,
        "price_requested_symbol_count": price_payload.get("requested_symbol_count"),
        "price_priced_symbol_count": price_payload.get("priced_symbol_count"),
        "price_failed_symbols": price_payload.get("failed_symbols", {}),
        "admission_starts": [value.strip() for value in args.admission_starts.split(",") if value.strip()],
        "admission_window_days": args.admission_window_days,
        "selected_fold_ids": [fold.fold_id for fold in folds],
        "folds": [
            {
                "fold_id": fold.fold_id,
                "signal_train_count": len(fold.discovery_samples),
                "signal_train_class_counts": dict(
                    sorted(Counter(sample.true_class for sample in fold.discovery_samples).items())
                ),
                "development_validation_count": len(fold.admission_samples),
                "development_validation_class_counts": dict(
                    sorted(Counter(sample.true_class for sample in fold.admission_samples).items())
                ),
            }
            for fold in folds
        ],
        "class_support_passed": not class_support_issues,
        "class_support_issues": class_support_issues,
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _real_sample(case, documents_by_symbol, bars_by_symbol, contract) -> LabeledSample:
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
    bars = sorted(
        bars_by_symbol.get(symbol, ()),
        key=lambda row: row["as_of_date"],
    )
    prediction_rows = [
        row for row in bars if row["as_of_date"] <= packet.as_of.as_of_date.isoformat()
    ]
    if not prediction_rows:
        raise ValidationError(f"{case.case_id} has no adjusted close at prediction time")
    prediction_close = float(prediction_rows[-1]["adjusted_close"])
    cutoff_date = _add_months(packet.as_of.as_of_date, contract.horizon_months)
    future_closes = [
        float(row["adjusted_close"])
        for row in bars
        if packet.as_of.as_of_date.isoformat() < row["as_of_date"] <= cutoff_date.isoformat()
    ]
    multiple = realized_max_multiple(
        prediction_close,
        future_closes,
        smoothing_window_days=contract.smoothing_window_days,
    )
    true_class = contract.classify(multiple)
    return LabeledSample(
        sample_id=case.case_id,
        company_key=symbol,
        prediction_time=prediction_time,
        realized_max_multiple=multiple,
        true_class=true_class,
        is_surge=contract.is_positive(true_class),
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
    realized = 3.4 if label and strength >= 0.7 else 2.4 if label else 1.35
    true_class = "C" if realized >= 3 else "B" if label else "A"
    return LabeledSample(
        sample_id=sample_id,
        company_key=company_key,
        prediction_time=prediction_time,
        realized_max_multiple=realized,
        true_class=true_class,
        is_surge=bool(label),
        sector="synthetic-sector-a" if label else "synthetic-sector-b",
        market_cap_bucket="small" if label else "mid",
        period=period,
        features={"signal_strength": strength},
        evidence_source_ids=[f"source:{sample_id}"],
        document_available_dates=[prediction_time.date() - timedelta(days=1)],
    )


def _add_months(value, months: int):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


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


def _run_mock_final_test(
    state_store: EvolutionStateStore,
    fixed_spec: FixedEvolutionSpec,
) -> None:
    """Run the selected proposal once on a separate synthetic sealed set."""

    top_k_path = state_store.root / "top_k.json"
    if not top_k_path.exists():
        raise ValidationError("final-test requires a completed run with top_k.json")
    archive = TopKArchive.from_dict(json.loads(top_k_path.read_text(encoding="utf-8")))
    if not archive.entries:
        raise ValidationError("final-test requires at least one selected scheme")
    genome = archive.entries[0].genome
    final_start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    final_samples = [
        _synthetic_sample(
            sample_id=f"final-test-{index}",
            company_key=f"sealed-final-company-{index}",
            prediction_time=final_start + timedelta(days=index),
            label=1 if outcome_class in {"B", "C"} else 0,
            strength={"A": 0.2, "B": 0.65, "C": 0.78}[outcome_class],
            period="2026-06-final-test",
        )
        for index, outcome_class in enumerate(("A", "B", "C"), start=1)
    ]
    # Keep the explicit requested class when the binary fixture helper would
    # otherwise derive B/C from strength alone.
    final_samples[2] = replace(
        final_samples[2],
        realized_max_multiple=3.4,
        true_class="C",
        is_surge=True,
    )
    fold = build_walk_forward_folds(
        [*_synthetic_samples(), *final_samples],
        [final_start],
        fixed_spec=fixed_spec,
        admission_window_days=10,
    )
    if len(fold) != 1:
        raise ValidationError("mock final-test split could not be constructed")
    evaluator = MockSchemeFoldEvaluator()
    materialized = evaluator.materialize(genome, fold[0])
    predictions = []
    extractions = {}
    for sample in fold[0].admission_samples:
        blind = sample.blind_view()
        extractions[sample.sample_id] = evaluator.extract(genome, materialized, blind)
        prediction = evaluator.predict(genome, materialized, blind)
        predictions.append(
            replace(
                prediction,
                input_hash=f"mock-final-test:{materialized.output_hash}:{sample.sample_id}",
            )
        )
    evaluation = evaluate_predictions(
        genome,
        predictions,
        {sample.sample_id: sample for sample in fold[0].admission_samples},
    )
    paths = state_store.write_final_test_artifacts(evaluation, predictions, extractions)
    print(f"[scheme-evolution] final_test_genome={genome.genome_id}")
    print(f"[scheme-evolution] final_test_binary_f1={evaluation.binary_f1}")
    print(f"[scheme-evolution] final_test_evaluation={paths['evaluation']}")


if __name__ == "__main__":
    main()
