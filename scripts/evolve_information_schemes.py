"""Run bounded, proposal-only information-scheme evolution."""

from __future__ import annotations

import argparse
import calendar
import fcntl
import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from stock_opportunity_agent.cases import CaseOutcomeLabel, learn_pre_surge_signal_logic
from stock_opportunity_agent.llm import (
    ModelClientSettings,
    RegisteredModel,
    get_model,
    model_catalog,
)
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
    load_round_checkpoint,
    merge_meta_lessons,
    realized_max_multiple,
    restore_round_context,
    validate_folds,
)
from stock_opportunity_agent.research.scheme_evolution_ralph import (
    ContinuousExternalSessionLedger,
    HeuristicGenomeBlindAnalyzer,
    OpenAIGenomeBlindAnalyzer,
    OpenRouterFusionSchemeProposer,
    RegisteredLLMSchemeProposer,
    RalphInformationPlanFoldEvaluator,
    blind_request_contract_findings,
)
from stock_opportunity_agent.research.scheme_evolution_dashboard import (
    list_evolution_trajectories,
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


def _print_model_catalog() -> None:
    """Print the auto-discovered, role-aware model list."""

    print("ALIAS\tROLES\tPROVIDER\tMODEL\tWEB\tDESCRIPTION")
    for item in model_catalog():
        print(
            f"{item.alias}\t{','.join(item.roles)}\t{item.provider_identity}\t"
            f"{item.model}\t{str(item.web_tools_allowed).lower()}\t{item.description}"
        )


def _print_trajectory_catalog(root: Path) -> None:
    """Print local trajectories and their exactly branchable rounds."""

    rows = list_evolution_trajectories(root)
    if not rows:
        print(f"[scheme-evolution] no trajectories under {root}")
        return
    print("TRAJECTORY\tSTATUS\tCURRENT\tCOMPLETED\tBRANCHABLE\tMODELS\tPARENT")
    for row in rows:
        if not row.get("valid"):
            print(
                f"{row['trajectory_id']}\tinvalid\t-\t-\t-\t-\t"
                f"{row.get('error', '')}"
            )
            continue
        models = row.get("models", {})
        lineage = row.get("lineage", {})
        parent = (
            f"{lineage.get('parent_trajectory_id')}:round-{lineage.get('parent_round')}"
            if lineage.get("parent_trajectory_id")
            else "-"
        )
        print(
            f"{row['trajectory_id']}\t{row['status']}\t{row['current_round']}\t"
            f"{row['last_completed_round']}\t"
            f"{','.join(str(value) for value in row['branchable_rounds']) or '-'}\t"
            f"{models.get('evolution_model', 'unknown')}→"
            f"{models.get('judge_model', 'unknown')}\t{parent}"
        )


def _resolve_launch_selection(args: argparse.Namespace) -> None:
    """Resolve interactive or explicit new/resume/branch launch parameters."""

    root = Path(args.evolution_root)
    rows = [row for row in list_evolution_trajectories(root) if row.get("valid")]
    by_id = {str(row["trajectory_id"]): row for row in rows}
    action = args.trajectory_action
    requested_model_aliases = {
        "evolution_model": args.evolution_model,
        "judge_model": args.judge_model,
    }
    if not action:
        if not sys.stdin.isatty():
            raise ValidationError(
                "non-interactive launch requires --trajectory-action new, resume, or branch"
            )
        _print_trajectory_catalog(root)
        choice = input("选择 new / resume / branch: ").strip().lower()
        if choice not in {"new", "resume", "branch"}:
            raise ValidationError("trajectory action must be new, resume, or branch")
        action = choice
    args.trajectory_action = action
    session_overrides = {
        "evolution_root": args.evolution_root,
        "max_rounds": args.max_rounds,
        "continuous_external_session_authorized": (
            args.continuous_external_session_authorized
        ),
        "session_max_cost_usd": args.session_max_cost_usd,
    }
    if action == "new":
        trajectory_id = args.trajectory_id or _default_trajectory_id()
        _validate_trajectory_id(trajectory_id)
        output_dir = root / trajectory_id
        if (output_dir / "state.json").exists():
            raise ValidationError(
                f"trajectory already exists; use resume or choose another id: {trajectory_id}"
            )
        args.run_id = trajectory_id
        args.output_dir = str(output_dir)
        args.command = "run"
        args.resume = False
    elif action == "resume":
        source_id = args.from_trajectory or args.trajectory_id
        if not source_id:
            if not sys.stdin.isatty():
                raise ValidationError("resume requires --from-trajectory")
            source_id = input("输入要继续的 trajectory id: ").strip()
        if source_id not in by_id:
            raise ValidationError(f"unknown local trajectory: {source_id}")
        source_dir = Path(str(by_id[source_id]["run_directory"]))
        _apply_saved_run_arguments(args, source_dir)
        _reject_changed_saved_models(args, requested_model_aliases)
        args.run_id = source_id
        args.output_dir = str(source_dir)
        args.command = "resume"
        args.resume = True
    else:
        source_id = args.from_trajectory
        if not source_id:
            if not sys.stdin.isatty():
                raise ValidationError("branch requires --from-trajectory")
            source_id = input("输入父 trajectory id: ").strip()
        if source_id not in by_id:
            raise ValidationError(f"unknown local parent trajectory: {source_id}")
        source_row = by_id[source_id]
        source_round = args.from_round
        if source_round == 0:
            if not sys.stdin.isatty():
                raise ValidationError("branch requires --from-round")
            source_round = int(input("输入父 round: ").strip())
        if source_round not in source_row["branchable_rounds"]:
            raise ValidationError(
                f"round {source_round} is not branchable; available: "
                f"{source_row['branchable_rounds']}"
            )
        trajectory_id = args.trajectory_id or _default_trajectory_id(prefix=f"{source_id}-r{source_round}")
        _validate_trajectory_id(trajectory_id)
        output_dir = root / trajectory_id
        if (output_dir / "state.json").exists():
            raise ValidationError(f"branch target already exists: {trajectory_id}")
        source_dir = Path(str(source_row["run_directory"]))
        _apply_saved_run_arguments(args, source_dir)
        _reject_changed_saved_models(args, requested_model_aliases)
        args.from_round = source_round
        args.branch_source_dir = str(source_dir)
        args.run_id = trajectory_id
        args.output_dir = str(output_dir)
        args.command = "run"
        args.resume = False
    for key, value in session_overrides.items():
        setattr(args, key, value)
    args.continuous = True


def _reject_changed_saved_models(
    args: argparse.Namespace,
    requested: dict[str, str],
) -> None:
    """Fail clearly when resume/branch tries to change a frozen model alias."""

    for field, requested_alias in requested.items():
        saved_alias = str(getattr(args, field, ""))
        if requested_alias and requested_alias != saved_alias:
            raise ValidationError(
                f"{field} is frozen as {saved_alias!r} for this trajectory; "
                "start a fresh trajectory to use another alias"
            )


def _resolve_registered_models(
    args: argparse.Namespace,
) -> tuple[RegisteredModel, RegisteredModel]:
    """Resolve aliases and project their immutable defaults onto legacy CLI fields."""

    evolution_alias = args.evolution_model or (
        "openrouter-fusion"
        if args.command in {"fusion-preflight", "fusion-sample"}
        else "codex-reviewed-file"
    )
    judge_alias = args.judge_model
    if not judge_alias:
        if args.mock_llm or args.mode == "heuristic":
            judge_alias = "local-heuristic"
        else:
            matches = [
                item
                for item in model_catalog(role="judge")
                if item.provider == "openrouter"
                and item.model == args.openrouter_model
                and (item.provider_route or "") == (args.openrouter_provider or "")
            ]
            if len(matches) != 1:
                available = ", ".join(item.alias for item in model_catalog(role="judge"))
                raise ValidationError(
                    "legacy judge provider/model does not map to one registered alias; "
                    f"choose --judge-model from: {available}"
                )
            judge_alias = matches[0].alias
    evolution_model = get_model(evolution_alias, role="evolution")
    judge_model = get_model(judge_alias, role="judge")
    args.evolution_model = evolution_model.alias
    args.judge_model = judge_model.alias
    if evolution_model.provider != "local":
        args.fusion_model = evolution_model.model
    if judge_model.provider == "local":
        args.mode = "heuristic"
    else:
        args.mode = "llm"
        args.openrouter_model = judge_model.model
        args.openrouter_provider = judge_model.provider_route or ""
        if (
            args.blind_max_output_tokens == 2200
            and judge_model.default_max_output_tokens != 2200
        ):
            args.blind_max_output_tokens = judge_model.default_max_output_tokens
        if not args.blind_reasoning_effort and judge_model.default_reasoning_effort:
            args.blind_reasoning_effort = judge_model.default_reasoning_effort
        if args.input_cost_per_million_tokens == 0:
            args.input_cost_per_million_tokens = (
                judge_model.default_input_cost_per_million_tokens
            )
        if args.output_cost_per_million_tokens == 0:
            args.output_cost_per_million_tokens = (
                judge_model.default_output_cost_per_million_tokens
            )
    return evolution_model, judge_model


def _apply_saved_run_arguments(args: argparse.Namespace, run_dir: Path) -> None:
    """Restore fixed local paths/settings before resuming without a config flag."""

    path = run_dir / "config.json"
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    saved = payload.get("run_arguments", {})
    if not isinstance(saved, dict):
        raise ValidationError("saved run_arguments must be an object")
    for key, value in saved.items():
        if hasattr(args, key):
            setattr(args, key, value)
    args.evolution_model = str(payload.get("evolution_model") or args.evolution_model)
    args.judge_model = str(payload.get("judge_model") or args.judge_model)


def _restore_pending_branch_intent(
    args: argparse.Namespace,
    state_store: EvolutionStateStore,
) -> None:
    """Recover branch initialization metadata after an early Ctrl+C."""

    if getattr(args, "branch_source_dir", None):
        return
    state = state_store.load_state()
    if int(state.get("current_iteration", 0)) != 0:
        return
    config = json.loads(
        (state_store.root / "config.json").read_text(encoding="utf-8")
    )
    branch = config.get("branch_source")
    if branch is None:
        return
    if not isinstance(branch, dict):
        raise ValidationError("saved branch_source must be an object")
    trajectory_id = str(branch.get("trajectory_id") or "")
    try:
        source_round = int(branch.get("round", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationError("saved branch round must be an integer") from exc
    source_dir = Path(str(branch.get("run_directory") or ""))
    relocated_source = Path(args.evolution_root) / trajectory_id
    if not (source_dir / "state.json").exists() and trajectory_id:
        source_dir = relocated_source
    if not trajectory_id or source_round < 1 or not (source_dir / "state.json").exists():
        raise ValidationError("saved branch source is incomplete or unavailable")
    args.branch_source_dir = str(source_dir)
    args.from_trajectory = trajectory_id
    args.from_round = source_round


def _safe_run_arguments(args: argparse.Namespace) -> dict[str, object]:
    """Persist replay settings while excluding CLI-only authority and session state."""

    excluded = {
        "command",
        "config",
        "external_transmission_authorized",
        "continuous_external_session_authorized",
        "session_max_cost_usd",
        "authorized_extra_http_attempts",
        "trajectory_action",
        "trajectory_id",
        "from_trajectory",
        "from_round",
        "branch_source_dir",
        "continuous",
        "max_rounds",
        "resume",
    }
    return {
        key: value
        for key, value in vars(args).items()
        if key not in excluded
        and isinstance(value, (str, int, float, bool, list, dict, type(None)))
    }


def _validate_trajectory_id(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", value):
        raise ValidationError(
            "trajectory id must be 1-96 characters using letters, digits, dot, underscore, or hyphen"
        )


def _default_trajectory_id(*, prefix: str = "evolution") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", prefix).strip("-.")
    return f"{normalized or 'evolution'}-{stamp}"


def _continuous_session_ledger(
    args: argparse.Namespace,
    *,
    output_dir: Path,
    fixed_spec: FixedEvolutionSpec,
    evolution_model: RegisteredModel,
    judge_model: RegisteredModel,
) -> ContinuousExternalSessionLedger:
    """Freeze a continuous external scope and restore its cumulative cost ledger."""

    corpus: dict[str, dict[str, str | None]] = {}
    for name, raw_path in (
        ("cases", args.cases_path),
        ("documents", args.documents_path),
        ("price_histories", args.price_histories_path),
        ("initial_genome", args.initial_genome),
        ("candidate_json", args.candidate_json),
        ("evolution_objective", "prompts/evolution_objective.md"),
    ):
        path = Path(raw_path) if raw_path else None
        corpus[name] = {
            "path": str(path) if path is not None else None,
            "sha256": _file_sha256(path) if path is not None and path.exists() else None,
        }
    scope = {
        "scope": "continuous_development_proposal_and_anonymous_judgment",
        "fixed_spec_hash": fixed_spec.content_hash,
        "evolution_model": evolution_model.to_public_dict(),
        "judge_model": judge_model.to_public_dict(),
        "corpus": corpus,
        "temperature": args.openrouter_temperature,
        "analysis_max_attempts": args.analysis_max_attempts,
        "provider_http_max_attempts": args.provider_http_max_attempts,
        "blind_max_output_tokens": args.blind_max_output_tokens,
        "blind_reasoning_effort": args.blind_reasoning_effort or None,
        "input_cost_per_million_tokens": args.input_cost_per_million_tokens,
        "output_cost_per_million_tokens": args.output_cost_per_million_tokens,
        "admission_starts": args.admission_starts,
        "admission_window_days": args.admission_window_days,
        "selected_folds": args.selected_folds,
        "children_per_generation": args.children_per_generation,
        "max_candidates": args.max_candidates,
        "fusion_preset": args.fusion_preset,
        "fusion_max_tool_calls": args.fusion_max_tool_calls,
        "fusion_inner_max_tokens": args.fusion_inner_max_tokens,
        "fusion_max_output_tokens": args.fusion_max_output_tokens,
        "final_test_in_scope": False,
        "production_promotion_allowed": False,
    }
    fingerprint = hashlib.sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    authorization_path = output_dir / "continuous_external_authorization.json"
    authorization = {
        "schema_version": "scheme-evolution-continuous-authorization-v1",
        "acknowledgement_method": "explicit_cli_flag",
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        "scope_fingerprint": fingerprint,
        "maximum_cost_usd": args.session_max_cost_usd,
        "secret_persisted": False,
        "scope": scope,
    }
    if authorization_path.exists():
        existing = json.loads(authorization_path.read_text(encoding="utf-8"))
        if existing.get("scope_fingerprint") != fingerprint:
            raise ValidationError("continuous external authorization scope changed on resume")
        if float(existing.get("maximum_cost_usd", 0.0)) > args.session_max_cost_usd:
            raise ValidationError("continuous external session cost cap cannot shrink")
    temporary = authorization_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(authorization, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(authorization_path)
    return ContinuousExternalSessionLedger(
        output_dir / "continuous_external_session.json",
        scope_fingerprint=fingerprint,
        maximum_cost_usd=args.session_max_cost_usd,
    )


def main() -> None:
    """Run, resume, or continuously supervise proposal-only evolution."""

    _load_local_env()
    args = _parse_args()
    if args.command == "models":
        _print_model_catalog()
        return
    if args.command == "trajectories":
        _print_trajectory_catalog(Path(args.evolution_root))
        return
    if args.command == "launch":
        _resolve_launch_selection(args)
    evolution_model, judge_model = _resolve_registered_models(args)
    if args.max_concurrency != 1:
        raise ValidationError(
            "v0.2 supports max_concurrency=1; provider concurrency remains external"
        )
    output_dir = Path(args.output_dir)
    initial = SchemeGenome.from_dict(
        json.loads(Path(args.initial_genome).read_text(encoding="utf-8"))
    )
    reviewed_proposer = FileSchemeProposer(args.candidate_json)
    state_store = EvolutionStateStore(output_dir, run_id=args.run_id or output_dir.name)
    if args.command == "status":
        state = state_store.load_state()
        try:
            status_lock = _acquire_run_lock(output_dir)
        except ValidationError:
            print("[scheme-evolution] dashboard_refresh=skipped active_writer=true")
        else:
            _refresh_evolution_dashboards(
                output_dir,
                evolution_root=Path(args.evolution_root),
            )
            status_lock.close()
        print(json.dumps(state, indent=2, sort_keys=True))
        return
    if args.command == "dashboard":
        state_store.load_state()
        dashboard_lock = _acquire_run_lock(output_dir)
        paths = _refresh_evolution_dashboards(
            output_dir,
            evolution_root=Path(args.evolution_root),
        )
        dashboard_lock.close()
        print(f"[scheme-evolution] dashboard={paths['dashboard']}")
        print(f"[scheme-evolution] run_dashboard={paths['run_dashboard']}")
        return
    if args.command == "resume":
        args.resume = True
    if args.dry_run:
        dry_run_lock = _acquire_run_lock(output_dir)
        _run_dry_validation(
            initial,
            reviewed_proposer,
            output_dir,
            count=args.children_per_generation,
        )
        dry_run_lock.close()
        return
    run_lock_handle = _acquire_run_lock(output_dir)
    execution_mode = "synthetic_mock_vertical_slice" if args.mock_llm else args.mode
    fixed_spec = _fixed_spec(args, synthetic=args.mock_llm)
    state_store.initialize(
        fixed_spec,
        config={
            "random_seed": args.random_seed,
            "initial_genome": str(args.initial_genome),
            "candidate_json": str(args.candidate_json),
            "mode": execution_mode,
            "evolution_model": evolution_model.alias,
            "judge_model": judge_model.alias,
            "evolution_model_registration": evolution_model.to_public_dict(),
            "judge_model_registration": judge_model.to_public_dict(),
            "experiment_config_path": str(args.config or ""),
            "run_arguments": _safe_run_arguments(args),
            "branch_source": (
                {
                    "run_directory": str(args.branch_source_dir),
                    "trajectory_id": str(args.from_trajectory),
                    "round": int(args.from_round),
                }
                if getattr(args, "branch_source_dir", None)
                else None
            ),
        },
    )
    state_store.write_objective_prompt(
        Path("prompts/evolution_objective.md").read_text(encoding="utf-8")
    )
    _restore_pending_branch_intent(args, state_store)
    if (
        getattr(args, "branch_source_dir", None)
        and int(state_store.load_state().get("current_iteration", 0)) == 0
    ):
        checkpoint = load_round_checkpoint(args.branch_source_dir, args.from_round)
        if checkpoint.get("fixed_spec_hash") != fixed_spec.content_hash:
            raise ValidationError("branch source uses a different fixed evolution spec")
        parent_history = json.loads(
            (Path(args.branch_source_dir) / "evolution_history.json").read_text(
                encoding="utf-8"
            )
        )
        state_store.seed_branch(
            checkpoint,
            parent_run_dir=args.branch_source_dir,
            parent_history=parent_history,
        )
    dashboard_paths = _refresh_evolution_dashboards(
        output_dir,
        evolution_root=Path(args.evolution_root),
    )
    if args.command == "init":
        print(f"[scheme-evolution] initialized={output_dir}")
        print(f"[scheme-evolution] dashboard={dashboard_paths['dashboard']}")
        return
    if args.command in {"fusion-preflight", "fusion-sample"}:
        fusion_proposer = _fusion_proposer(
            args,
            output_dir,
            preview_only=args.command == "fusion-preflight",
            evolution_model=evolution_model,
        )
        if args.command == "fusion-preflight":
            _run_fusion_proposal_preflight(initial, fusion_proposer, output_dir=output_dir)
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
    continuous = bool(getattr(args, "continuous", False))
    external_session = evolution_model.provider != "local" or judge_model.provider != "local"
    if continuous and external_session:
        if not args.continuous_external_session_authorized:
            raise ValidationError(
                "continuous external launch requires "
                "--continuous-external-session-authorized"
            )
        if args.session_max_cost_usd <= 0:
            raise ValidationError(
                "continuous external launch requires positive --session-max-cost-usd"
            )
    continuous_session_ledger = (
        _continuous_session_ledger(
            args,
            output_dir=output_dir,
            fixed_spec=fixed_spec,
            evolution_model=evolution_model,
            judge_model=judge_model,
        )
        if continuous and external_session
        else None
    )
    if (
        args.command in {"run", "resume"}
        and args.mode == "llm"
        and not continuous
        and not args.external_transmission_authorized
    ):
        raise ValidationError(
            "real llm run/resume requires --external-transmission-authorized"
        )
    blind_authorization_scope = None
    if args.command in {"run", "resume"} and args.mode == "llm" and not continuous:
        blind_authorization_scope = _validate_blind_run_authorization(
            args,
            output_dir=output_dir,
            judge_model=judge_model,
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
            judge_model=judge_model,
            continuous_session_ledger=continuous_session_ledger,
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
            reviewed_proposer,
            evaluator,
            folds,
            args=args,
            output_dir=output_dir,
            judge_model=judge_model,
        )
        return
    if blind_authorization_scope is not None:
        _record_blind_run_authorization(
            blind_authorization_scope,
            output_dir=output_dir,
            state_store=state_store,
        )
    incumbent, archive, meta_memory, mutation_requests = _restore_latest_context(
        state_store,
        initial=initial,
    )
    session_start_last_completed = int(
        state_store.load_state().get("last_completed_iteration", 0)
    )
    proposer = _evolution_proposer(
        args,
        output_dir=output_dir,
        evolution_model=evolution_model,
        reviewed_proposer=reviewed_proposer,
        continuous=continuous,
        continuous_session_ledger=continuous_session_ledger,
    )
    _print_launch_header(
        args,
        output_dir=output_dir,
        evolution_model=evolution_model,
        judge_model=judge_model,
        state=state_store.load_state(),
    )
    all_experiments = []
    all_rejections: list[CandidateRejection] = []
    last_paths: dict[str, Path] = {}
    completed_rounds = 0
    round_limit = (
        args.max_rounds
        if continuous and args.max_rounds is not None
        else 0
        if continuous
        else args.generations
    )
    try:
        while round_limit == 0 or completed_rounds < round_limit:
            state_before = state_store.load_state()
            current_round = int(state_before.get("current_iteration", 0))
            last_completed_round = int(
                state_before.get("last_completed_iteration", 0)
            )
            next_round = (
                current_round
                if current_round > last_completed_round
                else last_completed_round + 1
            )
            generation_proposer = proposer
            validator = None
            if args.mock_llm and (
                completed_rounds > 0
                or int(state_before.get("last_completed_iteration", 0)) > 0
            ):
                generation_proposer = _mock_continuous_proposer(incumbent, next_round)
                validator = CandidateValidator(near_duplicate_threshold=1.0)
            print(
                f"[scheme-evolution] supervisor next_round={next_round} "
                f"completed_this_session={completed_rounds} "
                f"limit={'ctrl-c' if round_limit == 0 else round_limit}"
                + (
                    f" session_cost_used={continuous_session_ledger.spent_or_reserved_cost_usd:.6f} "
                    f"session_cost_remaining={continuous_session_ledger.remaining_cost_usd:.6f}"
                    if continuous_session_ledger is not None
                    else ""
                )
            )
            engine = SchemeEvolutionEngine(
                proposer=generation_proposer,
                evaluator=evaluator,
                fixed_spec=fixed_spec,
                state_store=state_store,
                archive=archive,
                validator=validator,
                max_candidates=args.max_candidates,
                max_api_cost_usd=(
                    args.session_max_cost_usd
                    if continuous and args.session_max_cost_usd > 0
                    else args.max_api_cost
                ),
                progress=print,
            )
            result = engine.run(
                incumbent,
                folds,
                meta_memory=meta_memory,
                mutation_requests=mutation_requests,
                candidate_count=args.children_per_generation,
                resume=args.resume or continuous or completed_rounds > 0,
            )
            incumbent = result.incumbent
            archive = result.archive
            all_experiments.extend(result.experiments)
            all_rejections.extend(result.rejections)
            meta_memory = result.meta_lessons
            mutation_requests = result.mutation_requests
            last_paths = result.artifact_paths
            dashboard_paths = _refresh_evolution_dashboards(
                output_dir,
                evolution_root=Path(args.evolution_root),
            )
            last_paths = {**last_paths, **dashboard_paths}
            completed_rounds += 1
            if not result.experiments:
                if continuous:
                    raise ValidationError(
                        "evolution produced no evaluated child; continuous mode cannot "
                        "make progress until the evolution model supplies a new valid genome"
                    )
                break
    except KeyboardInterrupt:
        state = state_store.load_state()
        if state.get("status") != "paused_by_operator":
            state_store.pause("operator_ctrl_c")
            state = state_store.load_state()
        incumbent, archive, meta_memory, mutation_requests = _restore_latest_context(
            state_store,
            initial=initial,
        )
        completed_rounds = max(
            completed_rounds,
            int(state.get("last_completed_iteration", 0))
            - session_start_last_completed,
        )
        dashboard_paths = _refresh_evolution_dashboards(
            output_dir,
            evolution_root=Path(args.evolution_root),
        )
        summary_path = _write_evolution_summary(
            args,
            output_dir=output_dir,
            incumbent=incumbent,
            archive=archive,
            folds=folds,
            all_experiments=all_experiments,
            all_rejections=all_rejections,
            meta_memory=meta_memory,
            mutation_requests=mutation_requests,
            last_paths={**last_paths, **dashboard_paths},
            evaluator=evaluator,
            execution_mode=execution_mode,
            completed_rounds=completed_rounds,
            interrupted=True,
        )
        print(
            f"\n[scheme-evolution] paused_by_operator round={state.get('current_iteration')} "
            f"last_completed={state.get('last_completed_iteration', 0)} "
            f"summary={summary_path}",
            file=sys.stderr,
        )
        print(
            f"[scheme-evolution] resume=PYTHONPATH=src python "
            f"scripts/evolve_information_schemes.py launch --trajectory-action resume "
            f"--from-trajectory {state_store.run_id}",
            file=sys.stderr,
        )
        return
    summary_path = _write_evolution_summary(
        args,
        output_dir=output_dir,
        incumbent=incumbent,
        archive=archive,
        folds=folds,
        all_experiments=all_experiments,
        all_rejections=all_rejections,
        meta_memory=meta_memory,
        mutation_requests=mutation_requests,
        last_paths=last_paths,
        evaluator=evaluator,
        execution_mode=execution_mode,
        completed_rounds=completed_rounds,
        interrupted=False,
    )
    print(f"[scheme-evolution] incumbent={incumbent.genome_id}")
    print(f"[scheme-evolution] experiments={len(all_experiments)}")
    print(f"[scheme-evolution] archive_entries={len(archive.entries)}")
    print(f"[scheme-evolution] summary={summary_path}")
    print(f"[scheme-evolution] dashboard={dashboard_paths['dashboard']}")
    run_lock_handle.close()


def _restore_latest_context(
    state_store: EvolutionStateStore,
    *,
    initial: SchemeGenome,
):
    """Restore the last committed round while leaving a partial round resumable."""

    state = state_store.load_state()
    raw_completed = state.get("last_completed_iteration")
    if raw_completed is None:
        current = int(state.get("current_iteration", 0))
        last_completed = current if state.get("status") == "completed" else max(0, current - 1)
    else:
        last_completed = int(raw_completed)
    if last_completed < 1:
        return initial, TopKArchive(), [], []
    checkpoint = load_round_checkpoint(state_store.root, last_completed)
    return restore_round_context(checkpoint)


def _acquire_run_lock(output_dir: Path):
    """Hold one advisory writer lock for the lifetime of a mutating process."""

    output_dir.mkdir(parents=True, exist_ok=True)
    handle = (output_dir / ".evolution.lock").open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise ValidationError(
            f"another evolution process is already writing {output_dir}"
        ) from exc
    handle.seek(0)
    handle.truncate()
    handle.write(
        json.dumps(
            {
                "pid": os.getpid(),
                "acquired_at": datetime.now(timezone.utc).isoformat(),
            },
            sort_keys=True,
        )
        + "\n"
    )
    handle.flush()
    return handle


def _evolution_proposer(
    args: argparse.Namespace,
    *,
    output_dir: Path,
    evolution_model: RegisteredModel,
    reviewed_proposer: FileSchemeProposer,
    continuous: bool,
    continuous_session_ledger: ContinuousExternalSessionLedger | None,
):
    """Build the selected proposal adapter through its registered profile."""

    if evolution_model.proposal_profile == "reviewed_file":
        if continuous and not args.mock_llm and (args.max_rounds in {None, 0}):
            raise ValidationError(
                "codex-reviewed-file cannot autonomously supply infinite new genomes; "
                "choose a registered API evolution model or set a finite --max-rounds"
            )
        return reviewed_proposer
    if evolution_model.proposal_profile == "openrouter_fusion":
        if args.children_per_generation != 1:
            raise ValidationError("openrouter-fusion requires children_per_generation=1")
        return _fusion_proposer(
            args,
            output_dir,
            preview_only=False,
            evolution_model=evolution_model,
            continuous_session_ledger=continuous_session_ledger,
        )
    if evolution_model.proposal_profile == "plain_json":
        client = evolution_model.create_client(
            ModelClientSettings(
                preview_only=False,
                temperature=0.0,
                timeout_seconds=args.timeout_seconds,
                max_http_attempts=args.provider_http_max_attempts,
            )
        )
        return RegisteredLLMSchemeProposer(
            client,
            output_dir / "model_proposal_cache" / evolution_model.alias,
            objective_text=Path("prompts/evolution_objective.md").read_text(
                encoding="utf-8"
            ),
            provider=evolution_model.provider_identity,
            model=evolution_model.model,
            max_output_tokens=evolution_model.default_max_output_tokens,
            input_cost_per_million_tokens=(
                evolution_model.default_input_cost_per_million_tokens
            ),
            output_cost_per_million_tokens=(
                evolution_model.default_output_cost_per_million_tokens
            ),
            max_cost_usd=args.fusion_max_cost,
            session_ledger=continuous_session_ledger,
        )
    raise ValidationError(
        f"proposal profile is registered but not implemented: "
        f"{evolution_model.proposal_profile}"
    )


def _mock_continuous_proposer(
    incumbent: SchemeGenome,
    next_round: int,
) -> MockSchemeProposer:
    """Produce one unique deterministic child for continuous supervisor tests."""

    return MockSchemeProposer(
        [
            replace(
                incumbent,
                genome_id=f"{incumbent.genome_id}-local-refine-r{next_round}",
                parent_ids=[incumbent.genome_id],
                generation=incumbent.generation + 1,
                mutation_operator=MutationOperator.LOCAL_REFINE,
                hypothesis_of_change=(
                    "Test one persisted mock refinement under the unchanged fixed exam."
                ),
                changed_fields=["metadata.mock_supervisor_round"],
                expected_benefit="Exercise continuous checkpoint and resume semantics.",
                possible_side_effects=["Synthetic result has no effectiveness meaning."],
                falsification_test="Reject if the fixed mock evaluation contract changes.",
                target_failure_type="general",
                metadata={
                    **incumbent.metadata,
                    "mock_supervisor_round": next_round,
                },
            )
        ]
    )


def _print_launch_header(
    args: argparse.Namespace,
    *,
    output_dir: Path,
    evolution_model: RegisteredModel,
    judge_model: RegisteredModel,
    state: dict[str, object],
) -> None:
    """Print the fixed operator-visible context before any round starts."""

    action = getattr(args, "trajectory_action", "") or (
        "resume" if args.resume else "run"
    )
    source = (
        f"{args.from_trajectory}:round-{args.from_round}"
        if getattr(args, "from_trajectory", "") and args.from_round
        else "none"
    )
    print(
        f"[scheme-evolution] launch action={action} trajectory={state.get('run_id')} "
        f"source={source} output={output_dir}"
    )
    print(
        f"[scheme-evolution] models evolution={evolution_model.alias} "
        f"({evolution_model.provider_identity}/{evolution_model.model}) "
        f"judge={judge_model.alias} ({judge_model.provider_identity}/{judge_model.model})"
    )
    print(
        "[scheme-evolution] boundary=development proposal_only=true "
        "final_test=false production_promotion=false"
    )


def _write_evolution_summary(
    args: argparse.Namespace,
    *,
    output_dir: Path,
    incumbent: SchemeGenome,
    archive: TopKArchive,
    folds,
    all_experiments,
    all_rejections,
    meta_memory,
    mutation_requests,
    last_paths: dict[str, Path],
    evaluator,
    execution_mode: str,
    completed_rounds: int,
    interrupted: bool,
) -> Path:
    """Atomically persist one session summary, including operator interruption."""

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = Path(args.archive_export) if args.archive_export else output_dir / "top_k.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_temporary = archive_path.with_suffix(archive_path.suffix + ".tmp")
    archive_temporary.write_text(
        json.dumps(archive.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    archive_temporary.replace(archive_path)
    state = EvolutionStateStore(output_dir).load_state()
    summary_path = output_dir / "evolution_summary.json"
    payload = {
        "schema_version": "scheme-evolution-v0.2",
        "incumbent_genome_id": incumbent.genome_id,
        "completed_rounds_this_session": completed_rounds,
        "current_round": int(state.get("current_iteration", 0)),
        "last_completed_round": int(state.get("last_completed_iteration", 0)),
        "session_interrupted_by_operator": interrupted,
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
            getattr(
                getattr(evaluator, "analyzer", None),
                "cumulative_external_call_count",
                getattr(getattr(evaluator, "analyzer", None), "external_call_count", 0),
            )
        ),
        "blind_cache_hit_count": int(
            getattr(getattr(evaluator, "analyzer", None), "cache_hit_count", 0)
        ),
    }
    temporary = summary_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(summary_path)
    return summary_path


def _refresh_evolution_dashboards(
    output_dir: Path,
    *,
    evolution_root: Path = DEFAULT_EVOLUTION_ROOT,
) -> dict[str, Path]:
    """Refresh the portable run view and the one stable repository-level view."""

    run_paths = write_evolution_dashboard(output_dir)
    index_paths = write_evolution_dashboard_index(evolution_root)
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
            "models",
            "trajectories",
            "launch",
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
    parser.add_argument("--evolution-root", default=str(DEFAULT_EVOLUTION_ROOT))
    parser.add_argument("--trajectory-id", default="")
    parser.add_argument(
        "--trajectory-action",
        choices=("new", "resume", "branch"),
        default="",
    )
    parser.add_argument("--from-trajectory", default="")
    parser.add_argument("--from-round", type=int, default=0)
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Maximum new rounds for this launch; omit or use 0 to run until Ctrl+C.",
    )
    parser.add_argument("--evolution-model", default="")
    parser.add_argument("--judge-model", default="")
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
    parser.add_argument(
        "--openrouter-temperature",
        "--judge-temperature",
        dest="openrouter_temperature",
        type=float,
        default=0.0,
    )
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
        "--continuous-external-session-authorized",
        action="store_true",
        help="CLI-only acknowledgement for a fixed continuous external session scope.",
    )
    parser.add_argument(
        "--session-max-cost-usd",
        type=float,
        default=0.0,
        help="Cumulative external cost ceiling for continuous mode.",
    )
    parser.add_argument(
        "--authorized-extra-http-attempts",
        type=int,
        default=0,
        help="CLI-only explicit increment for a previously failed real-LLM resume.",
    )
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
            if attribute in {
                "external_transmission_authorized",
                "authorized_extra_http_attempts",
                "continuous_external_session_authorized",
                "session_max_cost_usd",
            }:
                parser.error("external session authorization and cost scope must be CLI-only")
            if not hasattr(args, attribute):
                parser.error(f"unknown config.cli field: {key}")
            setattr(args, attribute, value)
        args.evaluation_contract_config = config.get("evaluation_contract")
    else:
        args.evaluation_contract_config = None
    if args.generations < 1:
        parser.error("--generations must be positive")
    if args.max_rounds is not None and args.max_rounds < 0:
        parser.error("--max-rounds cannot be negative")
    if args.from_round < 0:
        parser.error("--from-round cannot be negative")
    if args.children_per_generation < 1:
        parser.error("--children-per-generation must be positive")
    if args.admission_window_days < 1:
        parser.error("admission window must be positive")
    if args.analysis_max_attempts < 1 or args.provider_http_max_attempts < 1:
        parser.error("LLM attempt bounds must be positive")
    if args.authorized_extra_http_attempts < 0:
        parser.error("--authorized-extra-http-attempts cannot be negative")
    if args.authorized_extra_http_attempts and args.command != "resume":
        parser.error("--authorized-extra-http-attempts is valid only with resume")
    if args.blind_max_output_tokens < 1:
        parser.error("--blind-max-output-tokens must be positive")
    if (
        args.fusion_max_tool_calls < 1
        or args.fusion_inner_max_tokens < 1
        or args.fusion_max_output_tokens < 1
        or args.fusion_max_cost <= 0
    ):
        parser.error("Fusion proposal bounds must be positive")
    if args.session_max_cost_usd < 0:
        parser.error("--session-max-cost-usd cannot be negative")
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
    evolution_model: RegisteredModel,
    continuous_session_ledger: ContinuousExternalSessionLedger | None = None,
) -> OpenRouterFusionSchemeProposer:
    if evolution_model.proposal_profile != "openrouter_fusion":
        raise ValidationError("selected evolution model is not a Fusion proposer")
    client = evolution_model.create_client(
        ModelClientSettings(
            preview_only=preview_only,
            temperature=0.0,
            timeout_seconds=args.timeout_seconds,
            max_http_attempts=args.provider_http_max_attempts,
        )
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
        session_ledger=continuous_session_ledger,
    )


def _run_fusion_proposal_preflight(
    initial: SchemeGenome,
    proposer: OpenRouterFusionSchemeProposer,
    *,
    output_dir: Path,
) -> None:
    preview = proposer.preview_request([initial], [], [], 1)
    estimated_cost = float(preview["pricing_snapshot_estimated_cost_usd"])
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
        f"requests=1 pricing_snapshot_estimate_usd={estimated_cost:.6f} external_calls=0"
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
    authorization_path = output_dir / "fusion_authorization.json"
    _write_authorization_record(
        authorization_path,
        {
            "scope": "fusion_scheme_proposal_only",
            "preflight_path": str(preflight_path),
            "preflight_sha256": _file_sha256(preflight_path),
            "request_count": 1,
            "model": preview["model"],
            "preset": preview["plugins"][0]["preset"],
            "web_enabled": True,
            "validation_packets_in_scope": False,
            "pricing_snapshot_estimated_cost_usd": preview[
                "pricing_snapshot_estimated_cost_usd"
            ],
        },
    )
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


def _validate_blind_run_authorization(
    args: argparse.Namespace,
    *,
    output_dir: Path,
    judge_model: RegisteredModel,
) -> dict[str, object]:
    preflight_path = output_dir / "external_disclosure_preflight.json"
    if not preflight_path.exists():
        raise ValidationError("real llm run requires a passed external disclosure preflight")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    expected_routing = (
        {
            "only": [judge_model.provider_route],
            "require_parameters": True,
            "allow_fallbacks": False,
        }
        if judge_model.provider_route
        else None
    )
    checks = {
        "passed": preflight.get("passed") is True,
        "no_prior_call": preflight.get("external_call_performed") is False,
        "model_alias": preflight.get("judge_model_alias", judge_model.alias)
        == judge_model.alias,
        "model": preflight.get("model") == judge_model.model,
        "provider": preflight.get("provider") == judge_model.provider_identity,
        "temperature": preflight.get("temperature") == args.openrouter_temperature,
        "routing": preflight.get("provider_routing") == expected_routing,
        "request_bound": 0 < int(preflight.get("request_count", 0)) <= 12,
        "hard_request_bound": preflight.get("hard_maximum_external_request_count")
        == preflight.get("request_count"),
        "analysis_attempt_bound": preflight.get("analysis_max_attempts")
        == args.analysis_max_attempts
        == 1,
        "http_attempt_bound": preflight.get("provider_http_max_attempts")
        == args.provider_http_max_attempts
        == 1,
        "input_price": preflight.get("input_cost_per_million_tokens")
        == args.input_cost_per_million_tokens,
        "output_price": preflight.get("output_cost_per_million_tokens")
        == args.output_cost_per_million_tokens,
        "cost_bound": float(preflight.get("maximum_total_cost_usd", float("inf")))
        <= args.max_api_cost,
        "configured_cost_cap": preflight.get("configured_cost_cap_usd")
        == args.max_api_cost,
        "no_findings": preflight.get("finding_count") == 0,
    }
    requests = preflight.get("requests")
    if not isinstance(requests, list) or not requests:
        checks["request_records"] = False
    else:
        checks["request_records"] = all(
            row.get("request", {}).get("model") == judge_model.model
            and row.get("request", {}).get("max_output_tokens")
            == args.blind_max_output_tokens
            and row.get("request", {}).get("reasoning")
            == (
                {"effort": args.blind_reasoning_effort, "exclude": True}
                if args.blind_reasoning_effort
                else None
            )
            and not row.get("finding_types")
            for row in requests
        )
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise ValidationError(
            f"external disclosure preflight differs from the authorized run: {failed}"
        )
    base_request_count = int(preflight["request_count"])
    authorized_attempt_count = base_request_count + args.authorized_extra_http_attempts
    return {
        "scope": "anonymous_no_web_blind_validation",
        "preflight_path": str(preflight_path),
        "preflight_sha256": _file_sha256(preflight_path),
        "model_alias": judge_model.alias,
        "model": judge_model.model,
        "provider": judge_model.provider_identity,
        "temperature": args.openrouter_temperature,
        "reasoning_effort": args.blind_reasoning_effort or None,
        "max_output_tokens": args.blind_max_output_tokens,
        "request_count": base_request_count,
        "authorized_extra_http_attempts": args.authorized_extra_http_attempts,
        "hard_maximum_external_http_attempts": authorized_attempt_count,
        "maximum_total_cost_usd": preflight["maximum_total_cost_usd"],
        "configured_cost_cap_usd": args.max_api_cost,
        "web_enabled": False,
        "provider_fallbacks_allowed": False,
    }


def _record_blind_run_authorization(
    scope: dict[str, object],
    *,
    output_dir: Path,
    state_store: EvolutionStateStore,
) -> None:
    authorization_path = output_dir / "external_authorization.json"
    _write_authorization_record(authorization_path, scope)
    state_store.append_event(
        "external_blind_run_authorized",
        {
            "authorization_path": str(authorization_path),
            "preflight_sha256": scope["preflight_sha256"],
            "request_count": scope["request_count"],
            "authorized_extra_http_attempts": scope[
                "authorized_extra_http_attempts"
            ],
            "hard_maximum_external_http_attempts": scope[
                "hard_maximum_external_http_attempts"
            ],
        },
    )


def _write_authorization_record(path: Path, scope: dict[str, object]) -> None:
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing_max = existing.get("hard_maximum_external_http_attempts")
        proposed_max = scope.get("hard_maximum_external_http_attempts")
        if (
            isinstance(existing_max, int)
            and isinstance(proposed_max, int)
            and proposed_max < existing_max
        ):
            raise ValidationError(
                "external HTTP attempt authorization cannot shrink on resume"
            )
    payload = {
        "schema_version": "scheme-evolution-external-authorization-v0.1",
        "acknowledgement_method": "explicit_cli_flag_after_user_approval",
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        "secret_persisted": False,
        **scope,
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_attempt_scope(
    preflight_path: Path,
    *,
    analyzer_settings: dict[str, object],
) -> str:
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    payload = {
        "reviewed_request_scope": {
            "schema_version": preflight.get("schema_version"),
            "provider": preflight.get("provider"),
            "model": preflight.get("model"),
            "temperature": preflight.get("temperature"),
            "provider_routing": preflight.get("provider_routing"),
            "analysis_max_attempts": preflight.get("analysis_max_attempts"),
            "provider_http_max_attempts": preflight.get("provider_http_max_attempts"),
            "configured_cost_cap_usd": preflight.get("configured_cost_cap_usd"),
            "requests": preflight.get("requests"),
        },
        "analyzer_settings": analyzer_settings,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _run_external_disclosure_preflight(
    initial: SchemeGenome,
    proposer: FileSchemeProposer,
    evaluator: RalphInformationPlanFoldEvaluator,
    folds,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    judge_model: RegisteredModel,
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
    contract_passed_request_count = 0
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
                contract_findings = blind_request_contract_findings(preview)
                request_findings.extend(contract_findings)
                request_findings = sorted(set(request_findings))
                if not contract_findings:
                    contract_passed_request_count += 1
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
                        "contract_finding_types": contract_findings,
                        "request": preview,
                    }
                )
    packet_preflights = sorted(
        str(path)
        for path in (output_dir / "packet_preflight").glob(
            "*/materialization_preflight.json"
        )
    )
    api_key_available = bool(
        judge_model.api_key_env_var
        and os.environ.get(judge_model.api_key_env_var)
    )
    state_path = output_dir / "state.json"
    state_payload = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists()
        else {}
    )
    final_test_accessed = bool(state_payload.get("final_test_accessed", False))
    passed = (
        bool(requests)
        and not findings
        and api_key_available
        and not final_test_accessed
        and maximum_cost_usd <= args.max_api_cost
        and len(packet_preflights) == len(genomes) * len(folds)
    )
    execution_readiness = _external_execution_readiness(
        requests,
        preflight_passed=passed,
        api_key_available=api_key_available,
        final_test_accessed=final_test_accessed,
        configured_cost_cap_usd=args.max_api_cost,
        cache_dir=(
            Path(args.blind_cache_dir)
            if args.blind_cache_dir
            else output_dir / "blind_analysis_cache"
        ),
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
        "judge_model_alias": judge_model.alias,
        "model": judge_model.model,
        "temperature": args.openrouter_temperature,
        "provider_routing": (
            requests[0]["request"]["provider_routing"] if requests else None
        ),
        "analysis_max_attempts": args.analysis_max_attempts,
        "provider_http_max_attempts": args.provider_http_max_attempts,
        "input_cost_per_million_tokens": args.input_cost_per_million_tokens,
        "output_cost_per_million_tokens": args.output_cost_per_million_tokens,
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
        "blind_request_contract": {
            "checked_request_count": len(requests),
            "passed_request_count": contract_passed_request_count,
            "all_requests_passed": contract_passed_request_count == len(requests),
            "checks": [
                "fixed_class_a_mapping",
                "fixed_class_b_mapping",
                "fixed_class_c_mapping",
                "negative_to_a_guard",
                "effective_prompt_hash",
                "exact_user_prompt_payload",
            ],
        },
        "execution_readiness": execution_readiness,
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


def _external_execution_readiness(
    requests: list[dict[str, object]],
    *,
    preflight_passed: bool,
    api_key_available: bool,
    final_test_accessed: bool,
    configured_cost_cap_usd: float,
    cache_dir: Path,
) -> dict[str, object]:
    """Summarize technical readiness without persisting credentials or authority."""

    request_costs = [
        float(dict(row["request"])["maximum_request_cost_usd"])
        for row in requests
    ]
    maximum_total_cost = sum(request_costs)
    maximum_request_cost = max(request_costs, default=0.0)
    safe_retry_buffer = 0
    while (
        maximum_request_cost > 0
        and maximum_total_cost
        + (safe_retry_buffer + 1) * maximum_request_cost
        <= configured_cost_cap_usd + 1e-12
    ):
        safe_retry_buffer += 1
    exact_cache_count = sum(
        (cache_dir / f"{row['cache_key']}.json").exists()
        for row in requests
    )
    technical_blockers: list[str] = []
    if not preflight_passed:
        technical_blockers.append("external_disclosure_preflight_not_passed")
    if not api_key_available:
        technical_blockers.append("openrouter_api_key_unavailable")
    if final_test_accessed:
        technical_blockers.append("final_test_accessed")
    technical_ready = not technical_blockers
    blockers = [*technical_blockers, "explicit_external_transmission_authorization"]
    return {
        "schema_version": "scheme-evolution-external-readiness-v0.1",
        "technical_ready_except_authorization": technical_ready,
        "blockers": blockers,
        "api_key_available_at_preflight": api_key_available,
        "credentials_persisted": False,
        "final_test_accessed": final_test_accessed,
        "logical_request_count": len(requests),
        "exact_cache_count": exact_cache_count,
        "uncached_request_count": len(requests) - exact_cache_count,
        "maximum_request_cost_usd": maximum_request_cost,
        "maximum_total_cost_usd": maximum_total_cost,
        "configured_cost_cap_usd": configured_cost_cap_usd,
        "maximum_safe_retry_buffer": safe_retry_buffer,
        "recommended_authorized_max_attempts": len(requests) + safe_retry_buffer,
        "maximum_cost_with_retry_buffer_usd": (
            maximum_total_cost + safe_retry_buffer * maximum_request_cost
        ),
    }


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
    judge_model: RegisteredModel,
    continuous_session_ledger: ContinuousExternalSessionLedger | None = None,
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
        cache_dir = (
            Path(args.blind_cache_dir)
            if args.blind_cache_dir
            else Path(args.output_dir) / "blind_analysis_cache"
        )
        client = judge_model.create_client(
            ModelClientSettings(
                preview_only=preview_only,
                temperature=args.openrouter_temperature,
                timeout_seconds=args.timeout_seconds,
                max_http_attempts=args.provider_http_max_attempts,
            )
        )
        attempt_ledger_path = None
        attempt_scope_fingerprint = None
        authorized_max_external_attempts = None
        continuous = bool(getattr(args, "continuous", False))
        if args.command in {"run", "resume"} and not continuous:
            preflight_path = Path(args.output_dir) / "external_disclosure_preflight.json"
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
            attempt_ledger_path = Path(args.output_dir) / "external_attempts.json"
            attempt_scope_fingerprint = _hash_attempt_scope(
                preflight_path,
                analyzer_settings={
                    "model_alias": judge_model.alias,
                    "model": judge_model.model,
                    "provider": judge_model.provider_identity,
                    "temperature": args.openrouter_temperature,
                    "max_output_tokens": args.blind_max_output_tokens,
                    "reasoning_effort": args.blind_reasoning_effort or None,
                    "input_cost_per_million_tokens": (
                        args.input_cost_per_million_tokens
                    ),
                    "output_cost_per_million_tokens": (
                        args.output_cost_per_million_tokens
                    ),
                    "max_cost_usd": args.max_api_cost,
                },
            )
            authorized_max_external_attempts = (
                int(preflight["request_count"])
                + args.authorized_extra_http_attempts
            )
        elif continuous:
            attempt_ledger_path = Path(args.output_dir) / "external_attempts.json"
            attempt_scope_fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "scope": "continuous_anonymous_no_web_development",
                        "fixed_spec_hash": fixed_spec.content_hash,
                        "judge_model": judge_model.to_public_dict(),
                        "temperature": args.openrouter_temperature,
                        "max_output_tokens": args.blind_max_output_tokens,
                        "reasoning_effort": args.blind_reasoning_effort or None,
                        "cases_path": str(Path(args.cases_path)),
                        "documents_path": str(Path(args.documents_path)),
                        "price_histories_path": str(Path(args.price_histories_path)),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            authorized_max_external_attempts = 2_147_483_647
        analyzer = OpenAIGenomeBlindAnalyzer(
            client,
            cache_dir,
            provider=judge_model.provider_identity,
            model=judge_model.model,
            temperature=args.openrouter_temperature,
            max_attempts=args.analysis_max_attempts,
            max_output_tokens=args.blind_max_output_tokens,
            reasoning_effort=args.blind_reasoning_effort or None,
            input_cost_per_million_tokens=args.input_cost_per_million_tokens,
            output_cost_per_million_tokens=args.output_cost_per_million_tokens,
            max_cost_usd=(
                args.session_max_cost_usd
                if continuous
                else args.max_api_cost
            ),
            attempt_ledger_path=attempt_ledger_path,
            attempt_scope_fingerprint=attempt_scope_fingerprint,
            authorized_max_external_attempts=authorized_max_external_attempts,
            session_ledger=continuous_session_ledger,
        )
        if attempt_ledger_path is not None and not continuous:
            capacity = analyzer.assert_authorized_capacity(preflight["requests"])
            print(
                "[scheme-evolution] external-attempt-capacity "
                f"logical={capacity['logical_request_count']} "
                f"cached={capacity['cached_request_count']} "
                f"outstanding={capacity['outstanding_request_count']} "
                f"remaining_authorized={capacity['remaining_authorized_attempts']}"
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
