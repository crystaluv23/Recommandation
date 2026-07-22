"""Run an artifact-backed Ralph Loop refinement/holdout experiment."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import random
import re
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.cases import CaseOutcomeLabel, HistoricalCase, learn_pre_surge_signal_logic
from stock_opportunity_agent.config import load_config
from stock_opportunity_agent.data import normalize_sec_company_facts
from stock_opportunity_agent.data.documents import DocumentContentScope, DocumentRecord
from stock_opportunity_agent.data.sources.alpha_vantage import AlphaVantageClient
from stock_opportunity_agent.data.sources.core import DataSourceError, FilingMetadata, UrllibJsonTransport, format_cik
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
from stock_opportunity_agent.llm.openai import UrllibTransport
from stock_opportunity_agent.llm.openrouter import OpenRouterChatClient
from stock_opportunity_agent.models import DataQuality, EvidenceItem, EvidenceKind, ResearchPacket, ValidationError
from stock_opportunity_agent.research import (
    ATOMIC_EVIDENCE_SCHEMA_VERSION,
    BlindCaseAnalysis,
    CachedRalphBlindResearcher,
    HeuristicRalphBlindResearcher,
    HeuristicSurgePlaybookSynthesizer,
    INFORMATION_PLAN_SCHEMA_VERSION,
    OpenAIRalphBlindResearcher,
    RalphBlindAnalysis,
    TARGET_INFORMATION_FAMILIES,
    build_blind_scheme_packet,
    document_content_readiness,
    evaluate_information_plan_experiment,
    extract_atomic_evidence_by_case,
    prepare_information_plan_experiment,
    point_in_time_document_identity_tokens,
    point_in_time_source_document_records,
    run_ralph_experiment,
    synthesize_information_scheme,
    write_information_plan_experiment_artifacts,
    write_ralph_experiment_artifacts,
)
from stock_opportunity_agent.research.ralph_loop import (
    _identity_token_pattern,
    _identity_tokens,
    analyze_scheme_errors,
    evaluate_scheme_performance,
    propose_next_information_scheme,
)
from stock_opportunity_agent.themes import build_cold_start_theme_maps


DEFAULT_FORMAL_RUN_DIR = Path(
    "runs/cold_start/formal/cold-start-formal-openrouter-2026-05-13-clean-universe"
)


def main() -> None:
    """Run a bounded Ralph experiment from saved cold-start artifacts."""

    args = _parse_args()
    if args.preflight_only and args.responses_path:
        raise ValidationError("--preflight-only and --responses-path cannot be used together")
    _load_local_env()
    created_at = datetime.now(timezone.utc)
    run_id = args.run_id or f"ralph-loop-experiment-{created_at.strftime('%Y%m%d-%H%M%S')}"
    output_dir = Path(args.output_dir) if args.output_dir else Path("runs/cold_start/ralph") / run_id
    cases = _load_cases(Path(args.cases_path))
    documents_by_symbol: dict[str, tuple[DocumentRecord, ...]] = {}
    if args.documents_path:
        documents_by_symbol = _load_documents_by_symbol(Path(args.documents_path))
        cases = _enrich_cases_with_documents(
            cases,
            documents_by_symbol,
        )
    excluded_symbols = _parse_symbol_set(args.exclude_symbols)
    if excluded_symbols:
        cases = tuple(
            case
            for case in cases
            if case.packet.company.ticker.symbol.upper() not in excluded_symbols
        )
    baseline = _load_blind_analyses(Path(args.baseline_blind_path))
    if args.selection_manifest:
        selected = _select_cases_from_manifest(cases, Path(args.selection_manifest))
    else:
        winner_count, control_count = _resolve_selection_counts(
            winner_symbol_count=args.winner_symbol_count,
            control_symbol_count=args.control_symbol_count,
            refinement_per_label=args.refinement_per_label,
            blind_holdout_size=args.blind_holdout_size,
            selection_seed=args.selection_seed,
        )
        args.winner_symbol_count = winner_count
        args.control_symbol_count = control_count
        selected = _select_cases(
            cases,
            winner_symbol_count=winner_count,
            control_symbol_count=control_count,
            refinement_per_label=args.refinement_per_label,
            selection_policy=args.selection_policy,
            holdout_symbols=_parse_symbol_set(args.holdout_symbols),
            documents_by_symbol=documents_by_symbol,
        )
    selected_case_tuple = tuple(selected["refinement"] + selected["holdout"])
    if args.augment_sec_company_facts:
        selected_case_tuple, company_facts_warnings = _augment_sec_company_facts_for_cases(
            selected_case_tuple,
            documents_by_symbol=documents_by_symbol,
            user_agent=load_config().data_sources.sec_user_agent,
        )
        for warning in company_facts_warnings:
            print(f"[ralph-experiment] warning={warning}")
        selected = _selected_cases_by_bucket(selected, selected_case_tuple)
    if args.augment_alpha_vantage_news:
        documents_by_symbol, news_warnings = _augment_alpha_vantage_news_for_cases(
            documents_by_symbol,
            selected_case_tuple,
            lookback_days=args.alpha_news_lookback_days,
            max_news_per_symbol=args.max_alpha_news_per_symbol,
        )
        for warning in news_warnings:
            print(f"[ralph-experiment] warning={warning}")
        selected = {
            "refinement": _enrich_cases_with_documents(selected["refinement"], documents_by_symbol),
            "holdout": _enrich_cases_with_documents(selected["holdout"], documents_by_symbol),
        }
    if args.augment_sec_submission_filings:
        documents_by_symbol, augmentation_warnings = _augment_sec_submission_documents_for_cases(
            documents_by_symbol,
            selected_case_tuple,
            user_agent=load_config().data_sources.sec_user_agent,
            forms=tuple(form.upper() for form in _parse_csv_values(args.sec_submission_forms)),
            lookback_days=args.sec_submission_lookback_days,
            max_filings_per_symbol=args.max_sec_submission_filings_per_symbol,
        )
        if augmentation_warnings:
            for warning in augmentation_warnings:
                print(f"[ralph-experiment] warning={warning}")
        selected = {
            "refinement": _enrich_cases_with_documents(selected["refinement"], documents_by_symbol),
            "holdout": _enrich_cases_with_documents(selected["holdout"], documents_by_symbol),
        }
    if args.refresh_sec_filing_text:
        refreshed_documents, refresh_warnings = _refresh_sec_filing_documents_for_cases(
            documents_by_symbol,
            tuple(selected["refinement"] + selected["holdout"]),
            user_agent=load_config().data_sources.sec_user_agent,
        )
        if refresh_warnings:
            for warning in refresh_warnings:
                print(f"[ralph-experiment] warning={warning}")
        selected = {
            "refinement": _enrich_cases_with_documents(selected["refinement"], refreshed_documents),
            "holdout": _enrich_cases_with_documents(selected["holdout"], refreshed_documents),
        }
        documents_by_symbol = refreshed_documents
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
    print(f"[ralph-experiment] run_id={run_id}")
    print(f"[ralph-experiment] output_dir={output_dir}")
    print("[ralph-experiment] selected symbols: " + ", ".join(_selection_symbols(selected)))
    print(
        "[ralph-experiment] refinement_cases="
        f"{len(refinement_cases)} holdout_cases={len(holdout_cases)} mode={args.mode}"
    )
    if args.experiment_kind == "information-plan":
        if args.responses_path:
            raise ValidationError(
                "--responses-path currently supports legacy-scheme preflight only; "
                "run the information-plan experiment directly or use --preflight-only"
            )
        discovery_cases = _information_plan_discovery_cases(
            cases,
            refinement_cases,
            documents_by_symbol,
        )
        _run_information_plan_path(
            args,
            output_dir=output_dir,
            run_id=run_id,
            created_at=created_at,
            discovery_cases=discovery_cases,
            refinement_cases=refinement_cases,
            holdout_cases=holdout_cases,
            learning_result=learning,
            theme_maps=theme_maps,
            playbook_synthesis=playbooks,
            selected=selected,
            documents_by_symbol=documents_by_symbol,
        )
        return
    if args.preflight_only:
        paths = _write_preflight_artifacts(
            output_dir,
            run_id=run_id,
            created_at=created_at,
            refinement_cases=refinement_cases,
            holdout_cases=holdout_cases,
            learning_result=learning,
            theme_maps=theme_maps,
            playbook_synthesis=playbooks,
        )
        print(f"[ralph-experiment] preflight_manifest={paths['preflight_manifest']}")
        return
    if args.responses_path:
        paths = _write_imported_response_artifacts(
            output_dir,
            run_id=run_id,
            created_at=created_at,
            refinement_cases=refinement_cases,
            holdout_cases=holdout_cases,
            learning_result=learning,
            theme_maps=theme_maps,
            playbook_synthesis=playbooks,
            responses_path=Path(args.responses_path),
        )
        manifest = json.loads(paths["imported_response_manifest"].read_text(encoding="utf-8"))
        print(
            "[ralph-experiment] imported holdout "
            f"gap={manifest['holdout_confidence_gap']:.4f} "
            f"positive_gap={manifest['holdout_positive_confidence_gap']:.4f} "
            f"confusion={manifest['holdout_confusion_matrix']} "
            f"fp_rate={manifest['holdout_false_positive_rate']:.4f} "
            f"fn_rate={manifest['holdout_false_negative_rate']:.4f} "
            f"status={manifest['final_status']}"
        )
        print(f"[ralph-experiment] imported_response_manifest={paths['imported_response_manifest']}")
        return

    blind_cache_dir = Path(args.blind_cache_dir) if args.blind_cache_dir else output_dir / "blind_analysis_cache"
    researcher = _ralph_researcher(args, cache_dir=blind_cache_dir)
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
        holdout_feedback_iterations=args.holdout_feedback_iterations,
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
        extra_output_paths={
            "case_selection_label_aware": selection_path,
            "blind_analysis_cache": blind_cache_dir,
        },
    )

    _print_metric_summary(result)
    print(f"[ralph-experiment] manifest={paths['manifest']}")


def _run_information_plan_path(
    args: argparse.Namespace,
    *,
    output_dir: Path,
    run_id: str,
    created_at: datetime,
    discovery_cases: tuple[HistoricalCase, ...],
    refinement_cases: tuple[HistoricalCase, ...],
    holdout_cases: tuple[HistoricalCase, ...],
    learning_result,
    theme_maps,
    playbook_synthesis,
    selected: dict[str, tuple[HistoricalCase, ...]],
    documents_by_symbol: dict[str, tuple[DocumentRecord, ...]],
) -> None:
    """Run or preflight the broad Ralph information-plan experiment."""

    scheme, _diagnostic = synthesize_information_scheme(
        refinement_cases,
        learning_result=learning_result,
        theme_maps=theme_maps,
        playbook_synthesis=playbook_synthesis,
    )
    families = _parse_csv_values(args.information_families)
    prepared = prepare_information_plan_experiment(
        discovery_cases,
        holdout_cases,
        active_scheme=scheme,
        run_id=run_id,
        context_budget=args.information_plan_context_budget,
        families=families,
        documents_by_symbol=documents_by_symbol,
    )
    ready_family_count = sum(
        experiment.status == "packet_variants_ready"
        for experiment in prepared.family_experiments
    )
    content_readiness = document_content_readiness(prepared)
    packet_cases = _information_plan_packet_cases(prepared, holdout_cases)
    leakage_report = _leakage_report(
        packet_cases,
        extra_identity_terms_by_case={
            case_id: point_in_time_document_identity_tokens(documents)
            for case_id, documents in prepared.source_documents_by_case.items()
        },
    )
    selection_path = _write_case_selection_artifact(
        output_dir,
        run_id=run_id,
        created_at=created_at,
        selected=selected,
        args=args,
        discovery_cases=discovery_cases,
    )
    if args.preflight_only:
        paths = _write_information_plan_preflight_artifacts(
            output_dir,
            run_id=run_id,
            created_at=created_at,
            prepared=prepared,
            leakage_report=leakage_report,
            selection_path=selection_path,
            evaluation_method=args.mode,
            validation_role=args.validation_role,
        )
        print(f"[ralph-experiment] information_plan_preflight={paths['preflight_manifest']}")
        return
    if ready_family_count == 0:
        raise ValidationError(
            "information-plan holdout has no source-backed target-family facts; "
            "improve acquisition or select atomic-evidence-rich cases before spending blind LLM budget"
        )
    if not leakage_report["passed"]:
        raise ValidationError("information-plan leakage scan failed")
    if args.mode == "llm" and not content_readiness["passed"]:
        raise ValidationError(
            "information-plan holdout source bodies failed content-readiness; "
            "repair truncated, metadata-only, or unusable documents before spending blind LLM budget"
        )
    blind_cache_dir = Path(args.blind_cache_dir) if args.blind_cache_dir else output_dir / "blind_analysis_cache"
    researcher = _ralph_researcher(args, cache_dir=blind_cache_dir)
    result = evaluate_information_plan_experiment(
        prepared,
        holdout_cases,
        blind_researcher=researcher,
        family_experiment_mode=args.family_experiment_mode,
        evaluation_method="plain_llm" if args.mode == "llm" else "heuristic",
        validation_role=args.validation_role,
    )
    paths = write_information_plan_experiment_artifacts(
        result,
        output_dir,
        created_at=created_at,
        leakage_report=leakage_report,
        extra_output_paths={
            "case_selection_label_aware": selection_path,
            "blind_analysis_cache": blind_cache_dir,
        },
    )
    print(
        "[ralph-experiment] information-plan holdout "
        f"raw_positive_gap={result.raw_evaluation.positive_confidence_gap:.4f} "
        f"organized_positive_gap={result.organized_evaluation.positive_confidence_gap:.4f} "
        f"raw_confusion={result.raw_evaluation.confusion_matrix} "
        f"organized_confusion={result.organized_evaluation.confusion_matrix} "
        f"fp_rate={result.organized_evaluation.false_positive_rate:.4f} "
        f"fn_rate={result.organized_evaluation.false_negative_rate:.4f}"
    )
    print(f"[ralph-experiment] manifest={paths['manifest']}")


def _information_plan_discovery_cases(
    all_cases: tuple[HistoricalCase, ...],
    refinement_cases: tuple[HistoricalCase, ...],
    documents_by_symbol: dict[str, tuple[DocumentRecord, ...]],
) -> tuple[HistoricalCase, ...]:
    """Return all available as-of windows for refinement symbols only."""

    symbols = {case.packet.company.ticker.symbol.upper() for case in refinement_cases}
    discovery = tuple(
        case
        for case in all_cases
        if case.packet.company.ticker.symbol.upper() in symbols
    )
    if documents_by_symbol:
        discovery = _enrich_cases_with_documents(discovery, documents_by_symbol)
    return tuple(
        sorted(
            discovery,
            key=lambda case: (
                case.packet.company.ticker.symbol,
                case.packet.as_of.as_of_date,
            ),
        )
    )


def _information_plan_packet_cases(prepared, holdout_cases):
    pairs = list(zip(prepared.raw_packets, holdout_cases, strict=True))
    pairs.extend(zip(prepared.organized_packets, holdout_cases, strict=True))
    pairs.extend(zip(prepared.family_add_back_baseline_packets, holdout_cases, strict=True))
    for experiment in prepared.family_experiments:
        if experiment.add_back_packets:
            pairs.extend(zip(experiment.add_back_packets, holdout_cases, strict=True))
        if experiment.ablation_packets:
            pairs.extend(zip(experiment.ablation_packets, holdout_cases, strict=True))
    return pairs


def _write_case_selection_artifact(
    output_dir: Path,
    *,
    run_id: str,
    created_at: datetime,
    selected: dict[str, tuple[HistoricalCase, ...]],
    args: argparse.Namespace,
    discovery_cases: tuple[HistoricalCase, ...],
) -> Path:
    path = output_dir / "case_selection_label_aware.json"
    winner_symbol_count = sum(
        case.label is CaseOutcomeLabel.WINNER
        for case in selected["refinement"] + selected["holdout"]
    )
    control_symbol_count = sum(
        case.label is CaseOutcomeLabel.CONTROL
        for case in selected["refinement"] + selected["holdout"]
    )
    holdout_label_counts = {
        label.value: sum(case.label is label for case in selected["holdout"])
        for label in (CaseOutcomeLabel.WINNER, CaseOutcomeLabel.CONTROL)
    }
    _write_json(
        path,
        {
            "schema_version": "ralph-case-selection-v0.3",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "stage_boundary": "retrospective_label_aware",
            "selection_policy": {
                "winner_symbol_count": winner_symbol_count,
                "control_symbol_count": control_symbol_count,
                "refinement_per_label": args.refinement_per_label,
                "blind_holdout_size": len(selected["holdout"]),
                "holdout_label_counts": holdout_label_counts,
                "selection_seed": args.selection_seed if not args.selection_manifest else None,
                "selection_manifest_source": args.selection_manifest,
                "random_ratio_applied_once": bool(args.blind_holdout_size)
                and not args.selection_manifest,
                "one_latest_case_per_symbol_for_blind_holdout": True,
                "all_available_refinement_windows_for_discovery": True,
                "frozen_case_ids_replayable": True,
            },
            "discovery_cases": [_case_selection_record(case) for case in discovery_cases],
            "refinement_cases": [_case_selection_record(case) for case in selected["refinement"]],
            "holdout_cases": [_case_selection_record(case) for case in selected["holdout"]],
        },
    )
    return path


def _write_information_plan_preflight_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    created_at: datetime,
    prepared,
    leakage_report: dict[str, Any],
    selection_path: Path,
    evaluation_method: str,
    validation_role: str,
) -> dict[str, Path]:
    """Write the information-plan contract without external blind calls."""

    output_dir.mkdir(parents=True, exist_ok=True)
    ready_family_count = sum(
        experiment.status == "packet_variants_ready"
        for experiment in prepared.family_experiments
    )
    content_readiness = document_content_readiness(prepared)
    paths = {
        "research_information_plan": output_dir / "research_information_plan.json",
        "information_requirements": output_dir / "information_requirements.json",
        "evidence_coverage_ledger": output_dir / "evidence_coverage_ledger.json",
        "atomic_evidence_by_case": output_dir / "atomic_evidence_by_case.json",
        "point_in_time_source_documents": output_dir / "point_in_time_source_documents.json",
        "document_content_audit": output_dir / "document_content_audit.json",
        "raw_source_blind_packets": output_dir / "raw_source_blind_packets.json",
        "holdout_blind_packets_by_scheme": output_dir / "holdout_blind_packets_by_scheme.json",
        "information_family_experiments": output_dir / "information_family_experiments.json",
        "information_scheme": output_dir / "information_scheme.json",
        "preflight_blind_llm_requests": output_dir / "preflight_blind_llm_requests.json",
        "preflight_leakage_report": output_dir / "preflight_leakage_report.json",
        "case_selection_label_aware": selection_path,
        "preflight_manifest": output_dir / "preflight_manifest.json",
    }
    _write_json(paths["research_information_plan"], prepared.plan.to_dict())
    _write_json(
        paths["information_requirements"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": run_id,
            "stage_boundary": "retrospective_label_aware_refinement",
            "requirements": [item.to_dict() for item in prepared.plan.requirements],
            "diagnostics": [item.to_dict() for item in prepared.plan.diagnostics],
        },
    )
    _write_json(
        paths["evidence_coverage_ledger"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": run_id,
            "stage_boundary": "retrospective_label_aware_audit",
            "source_pool_by_case": {
                case_id: list(source_ids)
                for case_id, source_ids in sorted(prepared.source_pool_by_case.items())
            },
            "entries": [item.to_dict() for item in prepared.coverage_entries],
        },
    )
    _write_json(
        paths["atomic_evidence_by_case"],
        {
            "schema_version": ATOMIC_EVIDENCE_SCHEMA_VERSION,
            "run_id": run_id,
            "stage_boundary": "retrospective_label_aware_audit",
            "atomic_evidence_by_case": {
                case_id: [fact.to_dict() for fact in facts]
                for case_id, facts in sorted(prepared.atomic_evidence_by_case.items())
            },
        },
    )
    _write_json(
        paths["point_in_time_source_documents"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": run_id,
            "stage_boundary": "retrospective_label_aware_raw_source_audit",
            "documents": point_in_time_source_document_records(prepared),
        },
    )
    _write_json(
        paths["document_content_audit"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": run_id,
            "stage_boundary": "retrospective_label_aware_raw_source_audit",
            "readiness": content_readiness,
            "audits": [audit.to_dict() for audit in prepared.document_content_audits],
        },
    )
    _write_json(
        paths["raw_source_blind_packets"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": run_id,
            "stage_boundary": "preflight_anonymous_blind_packet_export",
            "context_budget": prepared.context_budget,
            "packets": [packet.to_dict() for packet in prepared.raw_packets],
        },
    )
    _write_json(
        paths["holdout_blind_packets_by_scheme"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": run_id,
            "stage_boundary": "preflight_anonymous_blind_packet_export",
            "packets": [packet.to_dict() for packet in prepared.organized_packets],
        },
    )
    _write_json(
        paths["information_family_experiments"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": run_id,
            "stage_boundary": "preflight_anonymous_blind_packet_export",
            "experiments": [
                {
                    "family": experiment.family,
                    "status": experiment.status,
                    "available_fact_count": experiment.available_fact_count,
                    "add_back_packets": [packet.to_dict() for packet in experiment.add_back_packets],
                    "ablation_packets": [packet.to_dict() for packet in experiment.ablation_packets],
                }
                for experiment in prepared.family_experiments
            ],
            "add_back_core_baseline_packets": [
                packet.to_dict()
                for packet in prepared.family_add_back_baseline_packets
            ],
        },
    )
    _write_json(
        paths["information_scheme"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": run_id,
            "active_scheme": prepared.active_scheme.to_dict(),
            "research_information_plan": prepared.plan.to_dict(),
            "promotion_status": "pending_human_review",
        },
    )
    requests = [
        _blind_llm_request(packet, phase="raw_source_holdout")
        for packet in prepared.raw_packets
    ] + [
        _blind_llm_request(packet, phase="organized_holdout")
        for packet in prepared.organized_packets
    ]
    _write_json(
        paths["preflight_blind_llm_requests"],
        {
            "schema_version": "ralph-information-plan-preflight-v0.1",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "stage_boundary": "preflight_anonymous_blind_packet_export",
            "external_call_performed": False,
            "web_tools_allowed": False,
            "requests": requests,
        },
    )
    _write_json(paths["preflight_leakage_report"], leakage_report)
    _write_json(
        paths["preflight_manifest"],
        {
            "schema_version": "ralph-information-plan-preflight-v0.1",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "pipeline": "ralph_information_plan_experiment",
            "frozen_baseline_run_id": "ralph-loop-openrouter-rich-2026-07-07-12sym-sec-augment-live-v27",
            "external_call_performed": False,
            "leakage_passed": leakage_report["passed"],
            "raw_packet_count": len(prepared.raw_packets),
            "organized_packet_count": len(prepared.organized_packets),
            "family_experiment_count": len(prepared.family_experiments),
            "source_backed_family_experiment_count": ready_family_count,
            "document_content_readiness": content_readiness,
            "blind_execution_ready": (
                leakage_report["passed"]
                and ready_family_count > 0
                and content_readiness["passed"]
            ),
            "planned_evaluation_method": (
                "plain_llm" if evaluation_method == "llm" else "heuristic"
            ),
            "validation_role": validation_role,
            "effectiveness_claim_allowed": False,
            "gold_packet_available": False,
            "promotion_status": "pending_human_review",
            "outputs": {name: str(path) for name, path in sorted(paths.items())},
        },
    )
    if not leakage_report["passed"]:
        raise ValidationError("information-plan preflight leakage scan failed")
    return paths


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
    parser.add_argument(
        "--documents-path",
        default=str(DEFAULT_FORMAL_RUN_DIR / "04_documents/documents_and_catalysts.json"),
        help=(
            "Formal documents artifact or reusable point-in-time source archive used for "
            "content audit, extraction, and blind packet rendering."
        ),
    )
    parser.add_argument("--output-dir")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--experiment-kind",
        choices=("information-plan", "legacy-scheme"),
        default="information-plan",
        help="Run the broad information-plan experiment by default or the legacy packet-scheme loop.",
    )
    parser.add_argument("--mode", choices=("llm", "heuristic"), default="llm")
    parser.add_argument("--openrouter-model", default="openai/gpt-5.5")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--winner-symbol-count", type=int, default=4)
    parser.add_argument("--control-symbol-count", type=int, default=4)
    parser.add_argument("--refinement-per-label", type=int, default=2)
    parser.add_argument(
        "--blind-holdout-size",
        type=int,
        default=0,
        help=(
            "When positive, choose this many blind development symbols with a seeded random "
            "winner/control ratio while keeping at least one of each label."
        ),
    )
    parser.add_argument(
        "--selection-seed",
        type=int,
        default=0,
        help="Seed used once to choose the blind winner/control ratio; persist and replay the manifest.",
    )
    parser.add_argument(
        "--selection-manifest",
        help="Replay exact refinement and holdout case ids from a prior case-selection artifact.",
    )
    parser.add_argument("--max-iterations", type=int, default=2)
    parser.add_argument(
        "--information-plan-context-budget",
        type=int,
        default=4500,
        help="Shared documented context budget for raw and organized information-plan arms.",
    )
    parser.add_argument(
        "--information-families",
        default=",".join(TARGET_INFORMATION_FAMILIES),
        help="Comma-separated source-backed families prepared for add-back and ablation.",
    )
    parser.add_argument(
        "--family-experiment-mode",
        choices=("packets_only", "ablation", "add_back", "both"),
        default="packets_only",
        help="Evaluate family variants or only persist packet-ready experiment definitions.",
    )
    parser.add_argument(
        "--validation-role",
        choices=("development_diagnostic", "untouched_company_holdout"),
        default="development_diagnostic",
        help=(
            "Declare whether this run is development feedback or the one-shot untouched-company "
            "holdout; only the latter can support an effectiveness claim."
        ),
    )
    parser.add_argument(
        "--holdout-feedback-iterations",
        type=int,
        default=0,
        help="Bounded label-aware holdout feedback proposal rounds after the initial holdout evaluation.",
    )
    parser.add_argument(
        "--selection-policy",
        choices=("alphabetical", "evidence-rich", "atomic-evidence-rich"),
        default="atomic-evidence-rich",
        help=(
            "Choose latest cases alphabetically, by legacy keyword richness, or by conservative "
            "source-linked atomic evidence richness."
        ),
    )
    parser.add_argument(
        "--holdout-symbols",
        default="",
        help="Comma-separated symbols that must remain in the holdout split if selected.",
    )
    parser.add_argument(
        "--exclude-symbols",
        default="",
        help="Comma-separated symbols to exclude from the experiment selection.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Write anonymous packet export review artifacts without calling a blind LLM.",
    )
    parser.add_argument(
        "--responses-path",
        help="Evaluate externally generated blind LLM responses for the selected preflight packets.",
    )
    parser.add_argument(
        "--blind-cache-dir",
        help="Directory for per-packet blind LLM response cache; defaults to the run output directory.",
    )
    parser.add_argument(
        "--refresh-sec-filing-text",
        action="store_true",
        help="Refresh selected SEC filing document bodies from existing source URLs before packet rendering.",
    )
    parser.add_argument(
        "--augment-sec-submission-filings",
        action="store_true",
        help="Add selected SEC submissions filings as point-in-time source-detail documents for selected cases.",
    )
    parser.add_argument(
        "--augment-sec-company-facts",
        action="store_true",
        help="Add filing-date-bounded SEC XBRL financial features for selected cases.",
    )
    parser.add_argument(
        "--augment-alpha-vantage-news",
        action="store_true",
        help=(
            "Add bounded Alpha Vantage historical company-news summaries for selected "
            "development symbols."
        ),
    )
    parser.add_argument(
        "--alpha-news-lookback-days",
        type=int,
        default=365,
        help="Historical company-news lookback before each selected case cutoff.",
    )
    parser.add_argument(
        "--max-alpha-news-per-symbol",
        type=int,
        default=100,
        help="Maximum Alpha Vantage company-news summaries added per selected symbol.",
    )
    parser.add_argument(
        "--sec-submission-forms",
        default="8-K,10-Q,10-K,10-K/A,DEF 14A,424B5,S-3,S-3/A,F-4,F-4/A",
        help="Comma-separated SEC forms to add when --augment-sec-submission-filings is enabled.",
    )
    parser.add_argument(
        "--sec-submission-lookback-days",
        type=int,
        default=540,
        help="Lookback window for SEC submissions filing augmentation.",
    )
    parser.add_argument(
        "--max-sec-submission-filings-per-symbol",
        type=int,
        default=8,
        help="Maximum augmented SEC submissions filings per selected symbol.",
    )
    return parser.parse_args()


def _load_cases(path: Path) -> tuple[HistoricalCase, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("cases") or data.get("historical_cases")
    if not isinstance(records, list):
        raise ValidationError(f"{path} does not contain cases")
    return tuple(_case_from_record(record) for record in records)


def _load_documents_by_symbol(path: Path) -> dict[str, tuple[DocumentRecord, ...]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    records_by_symbol = data.get("documents_by_symbol")
    if not isinstance(records_by_symbol, dict):
        archive_records = data.get("documents")
        if not isinstance(archive_records, list):
            return {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for record in archive_records:
            if not isinstance(record, dict) or not isinstance(record.get("symbol"), str):
                continue
            grouped.setdefault(record["symbol"].upper(), []).append(record)
        records_by_symbol = grouped
    documents: dict[str, tuple[DocumentRecord, ...]] = {}
    for symbol, records in records_by_symbol.items():
        if not isinstance(records, list):
            continue
        deduped: dict[str, DocumentRecord] = {}
        for record in records:
            document = _document_from_record(record)
            key = document.source_url if document.source_url.startswith("http") else document.source_id
            current = deduped.get(key)
            if current is None or len(document.text) > len(current.text):
                deduped[key] = document
        documents[str(symbol).upper()] = tuple(
            sorted(deduped.values(), key=lambda item: (item.published_date, item.source_id))
        )
    return documents


def _document_from_record(record: dict[str, Any]) -> DocumentRecord:
    available = record.get("available_date")
    return DocumentRecord(
        document_id=_string(record, "document_id"),
        symbol=_string(record, "symbol"),
        kind=EvidenceKind(_string(record, "kind")),
        title=_string(record, "title"),
        text=_string(record, "text"),
        source_id=_string(record, "source_id"),
        source_url=_string(record, "source_url"),
        published_date=date.fromisoformat(_string(record, "published_date")),
        retrieved_at=datetime.fromisoformat(_string(record, "retrieved_at")),
        available_date=date.fromisoformat(str(available)) if isinstance(available, str) else None,
        content_scope=DocumentContentScope(str(record.get("content_scope", "unknown"))),
    )


def _enrich_cases_with_documents(
    cases: Iterable[HistoricalCase],
    documents_by_symbol: dict[str, tuple[DocumentRecord, ...]],
) -> tuple[HistoricalCase, ...]:
    enriched = []
    for case in cases:
        symbol = case.packet.company.ticker.symbol.upper()
        documents = documents_by_symbol.get(symbol, ())
        if not documents:
            enriched.append(case)
            continue
        as_of_date = case.packet.as_of.as_of_date
        document_source_ids = {document.source_id for document in documents if document.available_as_of(as_of_date)}
        document_digest_ids = {f"{source_id}:fact-digest" for source_id in document_source_ids}
        refreshed_evidence = [
            document.to_evidence(as_of_date)
            for document in documents
            if document.available_as_of(as_of_date)
        ]
        refreshed_evidence.extend(_source_fact_digest_evidence(document, as_of_date) for document in documents)
        refreshed_evidence = [item for item in refreshed_evidence if item is not None]
        if not refreshed_evidence:
            enriched.append(case)
            continue
        retained_evidence = [
            item
            for item in case.packet.evidence
            if item.source_id not in document_source_ids and item.source_id not in document_digest_ids
        ]
        refreshed_packet = replace(
            case.packet,
            evidence=retained_evidence + refreshed_evidence,
        )
        enriched.append(replace(case, packet=refreshed_packet))
    return tuple(enriched)


def _source_fact_digest_evidence(document: DocumentRecord, as_of_date: date) -> EvidenceItem | None:
    if not document.available_as_of(as_of_date):
        return None
    facts = _source_fact_digest_facts(document)
    if not facts:
        return None
    return EvidenceItem(
        kind=document.kind,
        summary=(
            f"{document.kind.value} fact digest from {document.title}: "
            + "; ".join(facts[:20])
        ),
        as_of_date=as_of_date,
        source_id=f"{document.source_id}:fact-digest",
        source_url=document.source_url,
        published_date=document.published_date,
        data_quality=DataQuality.CONFIRMED,
    )


def _source_fact_digest_facts(document: DocumentRecord) -> list[str]:
    text = _normalized_source_text(f"{document.title}. {document.text}")
    facts: list[str] = []
    facts.extend(_business_context_facts(text))
    facts.extend(_industry_chain_transmission_facts(text))
    facts.extend(_financing_transaction_facts(text))
    facts.extend(_operating_metric_facts(text))
    facts.extend(_listing_compliance_facts(text))
    facts.extend(_capital_liquidity_facts(text))
    return list(dict.fromkeys(fact for fact in facts if fact.strip()))


def _normalized_source_text(text: str) -> str:
    cleaned = html.unescape(text)
    cleaned = re.sub(r"(?is)<\?xml[^>]*\?>", " ", cleaned)
    cleaned = re.sub(r"(?is)<!--.*?-->", " ", cleaned)
    cleaned = re.sub(r"(?is)<(script|style|head|ix:header|xbrli:context|xbrli:unit)[^>]*>.*?</\1>", " ", cleaned)
    cleaned = re.sub(r"(?is)<\s*br\s*/?\s*>|</\s*(p|div|tr|li|h[1-6])\s*>", ". ", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned


def _business_context_facts(text: str) -> list[str]:
    lower = text.lower()
    facts: list[str] = []
    if any(marker in lower for marker in ("oil and gas", "barrels of oil equivalent", "boe/d", "crude oil")):
        facts.append("business context: oil and gas / energy operations")
    if any(marker in lower for marker in ("weight management", "weightwatchers", "weight watchers", "workshops")):
        facts.append("business context: consumer weight-management / wellness services")
    if "digital transformation" in lower and ("cybersecurity" in lower or "ai solution" in lower):
        facts.append("business context: digital transformation / cybersecurity / AI solutions")
    if "information technology stocks" in lower:
        facts.append("business context clue: information technology source bucket")
    if "energy stocks" in lower:
        facts.append("business context clue: energy source bucket")
    return facts


def _industry_chain_transmission_facts(text: str) -> list[str]:
    lower = text.lower()
    if not any(
        marker in lower
        for marker in (
            "artificial intelligence",
            " ai ",
            "ai solution",
            "machine learning",
            "data center",
            "datacenter",
            "cloud",
            "cybersecurity",
            "digital transformation",
        )
    ):
        return []

    stages: list[str] = []
    for label, markers in (
        ("enterprise digital-transformation demand", ("digital transformation", "modernization")),
        ("cybersecurity budget", ("cybersecurity", "security software", "security solution")),
        ("AI/software applications", ("artificial intelligence", "ai solution", "machine learning")),
        ("cloud-platform partnerships", ("microsoft", "aws", "azure", "cloud")),
        ("data-center infrastructure", ("data center", "datacenter", "server", "gpu")),
        ("power/cooling bottleneck", ("liquid cooling", "cooling", "power", "grid")),
    ):
        if any(marker in lower for marker in markers):
            stages.append(label)
    if not stages:
        return []

    facts = ["industry-chain lens: AI/cloud demand path through " + ", ".join(stages[:4])]
    pullthrough_markers = [
        label
        for label, markers in (
            ("orders/contracts", ("order", "contract", "backlog", "award")),
            ("customer or partner pull-through", ("customer", "client", "partnership", "partner")),
            ("capacity or shipments", ("capacity", "shipment", "deployment", "implementation")),
            ("funding/capex/guidance", ("funding", "financing", "capital", "capex", "guidance")),
            ("near-term revenue/profit metrics", ("revenue", "sales", "ebitda", "margin")),
        )
        if any(marker in lower for marker in markers)
    ]
    if pullthrough_markers:
        facts.append("company-level pull-through: " + ", ".join(pullthrough_markers[:4]))
    else:
        facts.append("industry-chain caution: AI/cloud theme lacks company-level pull-through marker")
    return facts


def _listing_compliance_facts(text: str) -> list[str]:
    lower = text.lower()
    facts: list[str] = []
    if "notice of delisting" in lower or "continued listing" in lower or "minimum bid" in lower:
        facts.append("listing risk: exchange notice or continued-listing deficiency disclosed")
    if "dropped from nasdaq composite index" in lower or "delisted from the nasdaq composite index" in lower:
        facts.append("listing/tradability risk: dropped from Nasdaq Composite Index or delisted from index")
    if "pursuing a nasdaq listing" in lower or "proposed nasdaq listing" in lower:
        facts.append("listing plan: pursuing proposed Nasdaq listing")
    minimum_bid = _first_amount(text, (r"minimum (?:closing )?bid price of at least\s+\$?([\d,.]+)\s*(?:per share)?",))
    if minimum_bid is not None:
        facts.append(f"listing requirement: minimum bid {minimum_bid} per share")
    if "stockholders' equity" in lower or "stockholders equity" in lower:
        facts.append("listing/capital requirement mentions stockholders' equity threshold")
    reported_equity = _first_amount(
        text,
        (
            r"reported stockholders[’']?\s+equity of\s+\$?\(?([\d,.]+)\)?\s*(million|billion|thousand)?",
        ),
    )
    if reported_equity is not None:
        sign = "-" if re.search(r"reported stockholders[’']?\s+equity of\s+\$?\(", text, flags=re.IGNORECASE) else ""
        facts.append(f"reported stockholders' equity: {sign}{reported_equity}")
    plan_due = _first_date_phrase(
        text,
        (r"submit a plan(?: of compliance)?[^.]{0,80}? by ([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})",),
    )
    if plan_due is not None:
        facts.append(f"listing remediation deadline: compliance plan due {plan_due}")
    if "plan to regain compliance" in lower or "acceptance of compliance plan" in lower:
        facts.append("listing remediation: compliance plan or cure-period language disclosed")
    if "reverse split" in lower or "reverse stock split" in lower:
        facts.append("listing remediation may involve reverse split or share-count action")
    return facts


def _capital_liquidity_facts(text: str) -> list[str]:
    facts: list[str] = []
    for label, patterns in (
        ("cash", (r"cash and cash equivalents(?:\s+(?:were|was|of|totaled))?\s+\$?([\d,.]+)\s*(million|billion|thousand)?",)),
        ("total debt", (r"total debt(?:\s+(?:was|of|outstanding|outstanding was|totaled))?\s+\$?([\d,.]+)\s*(million|billion|thousand)?",)),
        ("long-term debt", (r"long[- ]term debt(?:\s+(?:was|of|outstanding|totaled))?\s+\$?([\d,.]+)\s*(million|billion|thousand)?",)),
        ("stockholders' equity", (r"stockholders[’']?\s+equity(?:\s+(?:was|of|totaled|deficit of))?\s+\$?([\d,.]+)\s*(million|billion|thousand)?",)),
        ("net loss", (r"net loss(?:\s+(?:was|of|totaled))?\s+\$?([\d,.]+)\s*(million|billion|thousand)?",)),
        ("revolver draw", (r"borrowed approximately\s+\$?([\d,.]+)\s*(million|billion|thousand)?\s+under (?:the )?(?:senior secured )?revolving credit facility",)),
        ("revolver borrowings", (r"aggregate principal amount of borrowings[^.]{0,80}?\s+was\s+\$?([\d,.]+)\s*(million|billion|thousand)?",)),
    ):
        value = _first_amount(text, patterns)
        if value is not None:
            facts.append(f"{label}: {value}")
    lower = text.lower()
    if "going concern" in lower or "substantial doubt" in lower:
        facts.append("liquidity risk: going-concern or substantial-doubt language appears")
    if "senior secured" in lower or "credit facility" in lower or "direct financial obligation" in lower:
        facts.append("capital structure: credit facility or direct financial obligation disclosed")
    if "warrant" in lower or "at-the-market" in lower or "convertible" in lower:
        facts.append("dilution risk: warrant, ATM, or convertible language appears")
    return facts


def _operating_metric_facts(text: str) -> list[str]:
    facts: list[str] = []
    for label, patterns in (
        (
            "revenue/sales",
            (
                r"(?:revenue|sales)(?:\s+(?:was|were|of|totaled|reached|reaching))?\s+\$?([\d,.]+)\s*(million|billion|thousand)?",
            ),
        ),
        (
            "adjusted EBITDA",
            (
                r"adjusted\s+ebitda(?:\s+(?:was|of|totaled|increasing by [\d,.]+% to))?\s+\$?([\d,.]+)\s*(million|billion|thousand)?",
            ),
        ),
        ("production volume", (r"sales volumes? of\s+([\d,.]+)\s*(boe/d|barrels of oil equivalent per day)",)),
        ("capex", (r"(?:capital expenditures|capex)(?:\s+(?:was|were|of|totaled))?\s+\$?([\d,.]+)\s*(million|billion|thousand)?",)),
    ):
        value = _first_amount(text, patterns)
        if value is not None:
            facts.append(f"{label}: {value}")
    revenue_growth = _first_percent(
        text,
        (
            r"revenue[^.]{0,120}?\bup\s+([\d,.]+%)\s+year[- ]over[- ]year",
            r"revenue[^.]{0,120}?\bup\s+([\d,.]+%)\s+yoy",
        ),
    )
    if revenue_growth is not None:
        facts.append(f"target operating evidence: revenue growth {revenue_growth} year-over-year")
    ebitda_growth = _first_percent(
        text,
        (
            r"adjusted\s+ebitda[^.]{0,120}?\bincreasing by\s+([\d,.]+%)",
            r"adjusted\s+ebitda[^.]{0,120}?\bup\s+([\d,.]+%)",
        ),
    )
    if ebitda_growth is not None:
        facts.append(f"target operating evidence: adjusted EBITDA growth {ebitda_growth}")
    lower = text.lower()
    if "completed drilling operations" in lower or "wells online" in lower:
        facts.append("operating milestone: drilling completion or wells online disclosed")
    if "guidance" in lower:
        facts.append("expectation context: guidance language appears")
    return facts


def _financing_transaction_facts(text: str) -> list[str]:
    lower = text.lower()
    facts: list[str] = []
    if "business combination" in lower or "merger" in lower or "strategic transaction" in lower:
        facts.append("strategic transaction: merger/business-combination language appears")
    if ("form f-4" in lower or "form f-4/a" in lower) and "registration statement" in lower:
        facts.append("deal status: Form F-4 registration statement filed for proposed business combination")
    if "proposed business combination" in lower:
        facts.append("deal status: proposed business combination disclosed")
    if "definitive agreement" in lower:
        facts.append("deal status: definitive-agreement language appears")
    merger_deadline = _first_date_phrase(
        text,
        (
            r"merger deadline(?:\s+(?:was|has been))?\s+extended to ([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})",
            r"merger deadline to ([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})",
            r"business combination deadline(?:\s+(?:was|has been))?\s+extended to ([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})",
            r"business combination deadline to ([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})",
        ),
    )
    if merger_deadline is not None:
        facts.append(f"deal timing: merger deadline extended to {merger_deadline}")
    further_extension = _first_date_phrase(
        text,
        (r"further extensions? to ([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})",),
    )
    if further_extension is not None:
        facts.append(f"deal timing: possible further extension to {further_extension}")
    if "shareholder approval" in lower or "shareholders approved" in lower:
        facts.append("deal status: shareholder approval language appears")
    if "redeemed" in lower or "redemption" in lower:
        facts.append("deal/capital risk: shareholder redemption language appears")
    if "credit agreement" in lower or "amendment" in lower and "credit" in lower:
        facts.append("financing status: credit agreement or amendment language appears")
    if "dividend" in lower or "repurchase" in lower or "buyback" in lower:
        facts.append("capital return: dividend or repurchase language appears")
    return facts


def _first_amount(text: str, patterns: Iterable[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            amount = match.group(1).strip(" $.,;:")
            if not re.search(r"\d", amount):
                continue
            unit = match.group(2) if len(match.groups()) > 1 and match.group(2) else ""
            return f"{amount}{(' ' + unit) if unit else ''}"
    return None


def _first_date_phrase(text: str, patterns: Iterable[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(1).replace(".", "").split())
    return None


def _first_percent(text: str, patterns: Iterable[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,;:")
    return None


def _augment_alpha_vantage_news_for_cases(
    documents_by_symbol: Mapping[str, Iterable[DocumentRecord]],
    cases: Iterable[HistoricalCase],
    *,
    lookback_days: int,
    max_news_per_symbol: int,
    client: AlphaVantageClient | None = None,
) -> tuple[dict[str, tuple[DocumentRecord, ...]], tuple[str, ...]]:
    """Add bounded public provider summaries for selected point-in-time cases."""

    if lookback_days < 1:
        raise ValidationError("alpha news lookback days must be positive")
    if not 1 <= max_news_per_symbol <= 1000:
        raise ValidationError("max alpha news per symbol must be between 1 and 1000")

    result = {
        symbol.upper(): tuple(documents)
        for symbol, documents in documents_by_symbol.items()
    }
    cases_by_symbol: dict[str, list[HistoricalCase]] = {}
    for case in cases:
        cases_by_symbol.setdefault(case.packet.company.ticker.symbol.upper(), []).append(case)
    warnings: list[str] = []
    if not cases_by_symbol:
        return result, ()

    try:
        news_client = client or AlphaVantageClient.from_config(load_config().data_sources)
    except (DataSourceError, ValidationError) as exc:
        return result, (f"Alpha Vantage news augmentation unavailable: {exc}",)

    retrieved_at = datetime.now(timezone.utc)
    for symbol, symbol_cases in sorted(cases_by_symbol.items()):
        earliest_cutoff = min(case.packet.as_of.as_of_date for case in symbol_cases)
        latest_cutoff = max(case.packet.as_of.as_of_date for case in symbol_cases)
        start_date = earliest_cutoff - timedelta(days=lookback_days)
        try:
            response = news_client.news_sentiment(
                symbol,
                limit=max_news_per_symbol,
                time_from=datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
                time_to=datetime.combine(latest_cutoff, datetime.max.time(), tzinfo=timezone.utc),
                sort="EARLIEST",
            )
        except (DataSourceError, OSError) as exc:
            warnings.append(f"{symbol}: Alpha Vantage historical news unavailable: {exc}")
            continue
        feed = response.get("feed") if isinstance(response, dict) else None
        if not isinstance(feed, list):
            warnings.append(f"{symbol}: Alpha Vantage historical news response had no feed")
            continue
        additions = tuple(
            document
            for item in feed
            if (document := _alpha_vantage_news_record(symbol, item, retrieved_at)) is not None
            and start_date <= document.published_date <= latest_cutoff
        )
        merged: dict[str, DocumentRecord] = {}
        for document in (*result.get(symbol, ()), *additions):
            key = document.source_url if document.source_url.startswith("http") else document.source_id
            current = merged.get(key)
            if current is None or len(document.text) > len(current.text):
                merged[key] = document
        result[symbol] = tuple(
            sorted(merged.values(), key=lambda item: (item.published_date, item.source_id))
        )
    return result, tuple(warnings)


def _alpha_vantage_news_record(
    symbol: str,
    item: object,
    retrieved_at: datetime,
) -> DocumentRecord | None:
    if not isinstance(item, dict):
        return None
    raw_published = item.get("time_published")
    title = str(item.get("title") or "").strip()
    if not isinstance(raw_published, str) or not title:
        return None
    ticker_sentiment = item.get("ticker_sentiment")
    if isinstance(ticker_sentiment, list):
        matching_scores: list[float] = []
        for record in ticker_sentiment:
            if not isinstance(record, dict):
                continue
            if str(record.get("ticker") or "").upper() != symbol.upper():
                continue
            try:
                matching_scores.append(float(record.get("relevance_score", 0.0)))
            except (TypeError, ValueError):
                continue
        if not matching_scores or max(matching_scores) < 0.2:
            return None
    try:
        published = datetime.strptime(raw_published[:15], "%Y%m%dT%H%M%S").date()
    except ValueError:
        return None
    summary = str(item.get("summary") or "").strip()
    source_url = str(item.get("url") or "").strip()
    identity = source_url or f"{title}|{raw_published}"
    opaque_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    source_id = f"alpha_vantage:{symbol.upper()}:{opaque_id}"
    return DocumentRecord(
        document_id=source_id,
        symbol=symbol.upper(),
        kind=EvidenceKind.NEWS,
        title=title,
        text=f"{title}. {summary}".strip(),
        source_id=source_id,
        source_url=source_url or f"urn:{source_id}",
        published_date=published,
        available_date=published,
        retrieved_at=retrieved_at,
        content_scope=DocumentContentScope.SUMMARY_ONLY,
    )


def _augment_sec_company_facts_for_cases(
    cases: Iterable[HistoricalCase],
    *,
    documents_by_symbol: dict[str, tuple[DocumentRecord, ...]],
    user_agent: str,
    transport: Any | None = None,
) -> tuple[tuple[HistoricalCase, ...], tuple[str, ...]]:
    """Add filing-date-bounded SEC XBRL features to selected cases."""

    case_list = tuple(cases)
    if not case_list:
        return (), ()
    sec_client = SecEdgarClient(user_agent, transport=transport or UrllibJsonTransport())
    warnings: list[str] = []
    ciks_by_symbol = _sec_ciks_by_symbol(documents_by_symbol, case_list, sec_client, warnings)
    facts_by_symbol: dict[str, Mapping[str, Any]] = {}
    retrieved_at = datetime.now(timezone.utc)
    updated: list[HistoricalCase] = []
    for case in case_list:
        symbol = case.packet.company.ticker.symbol.upper()
        cik = ciks_by_symbol.get(symbol)
        if cik is None:
            warnings.append(f"{symbol}: SEC company facts skipped; no CIK available")
            updated.append(case)
            continue
        if symbol not in facts_by_symbol:
            try:
                facts_by_symbol[symbol] = sec_client.company_facts(cik)
            except (DataSourceError, OSError, ValueError) as exc:
                warnings.append(f"{symbol}: SEC company facts unavailable for CIK {cik}: {exc}")
                facts_by_symbol[symbol] = {}
        payload = facts_by_symbol[symbol]
        if not payload:
            updated.append(case)
            continue
        normalized = tuple(
            feature
            for feature in normalize_sec_company_facts(
                payload,
                case.packet.as_of.as_of_date,
                retrieved_at,
            )
            if feature.data_quality is not DataQuality.MISSING
        )
        if not normalized:
            warnings.append(f"{symbol}: SEC company facts had no values available by case cutoff")
            updated.append(case)
            continue
        normalized_names = {feature.name for feature in normalized}
        retained = tuple(
            feature for feature in case.packet.features if feature.name not in normalized_names
        )
        updated.append(
            replace(
                case,
                packet=replace(case.packet, features=list(retained + normalized)),
            )
        )
    return tuple(updated), tuple(dict.fromkeys(warnings))


def _augment_sec_submission_documents_for_cases(
    documents_by_symbol: dict[str, tuple[DocumentRecord, ...]],
    cases: Iterable[HistoricalCase],
    *,
    user_agent: str,
    forms: tuple[str, ...],
    lookback_days: int,
    max_filings_per_symbol: int,
    transport: Any | None = None,
) -> tuple[dict[str, tuple[DocumentRecord, ...]], tuple[str, ...]]:
    """Add selected as-of SEC filings from submissions JSON for Ralph experiments."""

    case_list = list(cases)
    if not case_list:
        return documents_by_symbol, ()
    if lookback_days < 1:
        raise ValidationError("--sec-submission-lookback-days must be positive")
    if max_filings_per_symbol < 1:
        raise ValidationError("--max-sec-submission-filings-per-symbol must be positive")

    sec_transport = transport or UrllibJsonTransport()
    sec_client = SecEdgarClient(user_agent, transport=sec_transport)
    warnings: list[str] = []
    ciks_by_symbol = _sec_ciks_by_symbol(documents_by_symbol, case_list, sec_client, warnings)
    if not ciks_by_symbol:
        return documents_by_symbol, tuple(warnings)

    augmented: dict[str, tuple[DocumentRecord, ...]] = dict(documents_by_symbol)
    existing_source_ids_by_symbol = {
        symbol: {document.source_id for document in documents}
        for symbol, documents in documents_by_symbol.items()
    }
    selected_by_symbol = _latest_case_by_symbol(case_list)
    identity_tokens_by_cik: dict[str, tuple[str, ...]] = {}
    form_set = {form.upper() for form in forms}
    for symbol, case in selected_by_symbol.items():
        cik = ciks_by_symbol.get(symbol)
        if cik is None:
            warnings.append(f"{symbol}: SEC submissions augmentation skipped; no CIK available")
            continue
        try:
            filings = sec_client.recent_filings_as_of(cik, case.packet.as_of.as_of_date)
        except (DataSourceError, OSError, ValueError) as exc:
            warnings.append(f"{symbol}: SEC submissions unavailable for CIK {cik}: {exc}")
            continue
        window_start = case.packet.as_of.as_of_date - timedelta(days=lookback_days)
        selected_filings = [
            filing
            for filing in filings
            if filing.form.upper() in form_set and window_start <= filing.filing_date <= case.packet.as_of.as_of_date
        ]
        selected_filings = sorted(
            selected_filings,
            key=lambda filing: (filing.filing_date, filing.accession_number),
            reverse=True,
        )[:max_filings_per_symbol]
        documents = list(augmented.get(symbol, ()))
        existing_source_ids = existing_source_ids_by_symbol.setdefault(symbol, set())
        for filing in selected_filings:
            source_id = f"sec:{filing.cik}:{filing.accession_number}"
            source_id_exists = source_id in existing_source_ids
            try:
                text = sec_client.filing_document_text(filing)
            except (DataSourceError, OSError) as exc:
                warnings.append(f"{symbol}: SEC filing text unavailable for {filing.accession_number}: {exc}")
                if source_id_exists:
                    continue
                text = f"{filing.form} filed on {filing.filing_date.isoformat()}."
            allowed_tokens = identity_tokens_by_cik.setdefault(
                filing.cik,
                _sec_submission_identity_tokens(filing.cik, sec_transport, user_agent, warnings),
            )
            declared_conflicts = _sec_declared_identity_conflicts(text, case, allowed_identity_tokens=allowed_tokens)
            if declared_conflicts:
                warnings.append(
                    f"{symbol}: SEC submissions filing skipped for {filing.accession_number}: "
                    f"declared identity conflicts {declared_conflicts}"
                )
                continue
            augmented_document = _document_from_sec_filing(symbol, case, filing, text)
            if source_id_exists:
                documents = [
                    augmented_document if document.source_id == source_id else document
                    for document in documents
                ]
            else:
                documents.append(augmented_document)
            existing_source_ids.add(source_id)
        if documents:
            augmented[symbol] = tuple(sorted(documents, key=lambda document: document.published_date))
    return augmented, tuple(warnings)


def _latest_case_by_symbol(cases: Iterable[HistoricalCase]) -> dict[str, HistoricalCase]:
    latest: dict[str, HistoricalCase] = {}
    for case in cases:
        symbol = case.packet.company.ticker.symbol.upper()
        current = latest.get(symbol)
        if current is None or case.packet.as_of.as_of_date > current.packet.as_of.as_of_date:
            latest[symbol] = case
    return latest


def _sec_ciks_by_symbol(
    documents_by_symbol: dict[str, tuple[DocumentRecord, ...]],
    cases: Iterable[HistoricalCase],
    client: SecEdgarClient,
    warnings: list[str],
) -> dict[str, str]:
    ciks_by_symbol: dict[str, str] = {}
    for symbol, documents in documents_by_symbol.items():
        cik = _first_document_cik(documents)
        if cik:
            ciks_by_symbol[symbol.upper()] = cik
    missing_symbols = sorted(
        {
            case.packet.company.ticker.symbol.upper()
            for case in cases
            if case.packet.company.ticker.symbol.upper() not in ciks_by_symbol
        }
    )
    if not missing_symbols:
        return ciks_by_symbol
    try:
        listings = client.company_tickers_exchange()
    except (DataSourceError, OSError, ValueError) as exc:
        warnings.append(f"SEC ticker mapping unavailable for submissions augmentation: {exc}")
        return ciks_by_symbol
    wanted = set(missing_symbols)
    for listing in listings:
        symbol = listing.symbol.upper()
        if symbol in wanted and listing.cik:
            ciks_by_symbol[symbol] = format_cik(listing.cik)
    return ciks_by_symbol


def _first_document_cik(documents: Iterable[DocumentRecord]) -> str | None:
    for document in documents:
        cik = _document_cik(document)
        if cik is not None:
            return cik
    return None


def _document_cik(document: DocumentRecord) -> str | None:
    for value in (document.source_id, document.source_url):
        match = re.search(r"(?:sec:|/data/)(0*\d{4,10})(?::|/)", value)
        if match:
            return format_cik(match.group(1))
    return None


def _document_from_sec_filing(
    symbol: str,
    case: HistoricalCase,
    filing: FilingMetadata,
    text: str,
) -> DocumentRecord:
    company_name = case.packet.company.ticker.company_name or symbol
    return DocumentRecord(
        document_id=f"sec-submissions:{filing.cik}:{filing.accession_number}",
        symbol=symbol,
        kind=EvidenceKind.FILING,
        title=f"{company_name} {filing.form} filed {filing.filing_date.isoformat()}",
        text=text,
        source_id=f"sec:{filing.cik}:{filing.accession_number}",
        source_url=filing.source_url,
        published_date=filing.filing_date,
        available_date=filing.filing_date,
        retrieved_at=filing.retrieved_at or datetime.now(timezone.utc),
        content_scope=(
            DocumentContentScope.METADATA_ONLY
            if re.fullmatch(r"\s*[A-Z0-9-]+ filed on \d{4}-\d{2}-\d{2}\.\s*", text)
            else DocumentContentScope.COMPLETE_BODY
        ),
    )


def _refresh_sec_filing_documents_for_cases(
    documents_by_symbol: dict[str, tuple[DocumentRecord, ...]],
    cases: Iterable[HistoricalCase],
    *,
    user_agent: str,
    transport: Any | None = None,
) -> tuple[dict[str, tuple[DocumentRecord, ...]], tuple[str, ...]]:
    selected_as_of_by_symbol: dict[str, date] = {}
    cases_by_symbol: dict[str, HistoricalCase] = {}
    for case in cases:
        symbol = case.packet.company.ticker.symbol.upper()
        cases_by_symbol.setdefault(symbol, case)
        current = selected_as_of_by_symbol.get(symbol)
        as_of_date = case.packet.as_of.as_of_date
        if current is None or as_of_date > current:
            selected_as_of_by_symbol[symbol] = as_of_date
    if not selected_as_of_by_symbol:
        return documents_by_symbol, ()

    text_transport = transport or UrllibJsonTransport()
    warnings: list[str] = []
    refreshed_by_symbol: dict[str, tuple[DocumentRecord, ...]] = dict(documents_by_symbol)
    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
    identity_tokens_by_cik: dict[str, tuple[str, ...]] = {}
    for symbol, latest_as_of in selected_as_of_by_symbol.items():
        refreshed_documents: list[DocumentRecord] = []
        for document in documents_by_symbol.get(symbol, ()):
            if (
                document.kind is not EvidenceKind.FILING
                or not document.available_as_of(latest_as_of)
                or not _is_sec_archive_url(document.source_url)
            ):
                refreshed_documents.append(document)
                continue
            try:
                text = text_transport.get_text(document.source_url, headers)
            except (DataSourceError, OSError) as exc:
                warnings.append(f"{symbol}: SEC filing text refresh failed for {document.source_id}: {exc}")
                refreshed_documents.append(document)
                continue
            cik = _document_cik(document)
            allowed_tokens = ()
            if cik is not None:
                allowed_tokens = identity_tokens_by_cik.setdefault(
                    cik,
                    _sec_submission_identity_tokens(cik, text_transport, user_agent, warnings),
                )
            declared_conflicts = _sec_declared_identity_conflicts(
                text,
                cases_by_symbol[symbol],
                allowed_identity_tokens=allowed_tokens,
            )
            if declared_conflicts:
                warnings.append(
                    f"{symbol}: SEC filing text refresh skipped for {document.source_id}: "
                    f"declared identity conflicts {declared_conflicts}"
                )
                refreshed_documents.append(document)
                continue
            contaminating_terms = _cross_case_identity_hits(text, cases_by_symbol[symbol], cases_by_symbol.values())
            if contaminating_terms:
                warnings.append(
                    f"{symbol}: SEC filing text refresh skipped for {document.source_id}: "
                    f"cross-case identity terms {contaminating_terms}"
                )
                refreshed_documents.append(document)
                continue
            refreshed_documents.append(
                replace(
                    document,
                    text=text,
                    retrieved_at=datetime.now(timezone.utc),
                    content_scope=DocumentContentScope.COMPLETE_BODY,
                )
            )
        if refreshed_documents:
            refreshed_by_symbol[symbol] = tuple(refreshed_documents)
    return refreshed_by_symbol, tuple(warnings)


def _is_sec_archive_url(url: str) -> bool:
    return url.startswith("https://www.sec.gov/Archives/edgar/data/")


def _sec_declared_identity_conflicts(
    text: str,
    case: HistoricalCase,
    *,
    allowed_identity_tokens: tuple[str, ...] = (),
) -> list[str]:
    cleaned = _normalized_source_text(text)
    conflicts: list[str] = []
    declared_symbols = _sec_declared_trading_symbols(cleaned)
    own_symbol = case.packet.company.ticker.symbol.upper()
    unexpected_symbols = sorted(symbol for symbol in declared_symbols if symbol != own_symbol)
    registrant = _sec_declared_registrant(cleaned)
    registrant_allowed = bool(registrant and _registrant_matches_tokens(registrant, allowed_identity_tokens))
    if declared_symbols and own_symbol not in declared_symbols and unexpected_symbols and not registrant_allowed:
        conflicts.append("trading symbols " + ", ".join(unexpected_symbols[:4]))
    if (
        registrant
        and not _registrant_matches_case(registrant, case)
        and not registrant_allowed
    ):
        conflicts.append(f"registrant {registrant}")
    return conflicts[:4]


def _sec_submission_identity_tokens(
    cik: str,
    transport: Any,
    user_agent: str,
    warnings: list[str],
) -> tuple[str, ...]:
    get_json = getattr(transport, "get_json", None)
    if get_json is None:
        return ()
    url = f"https://data.sec.gov/submissions/CIK{format_cik(cik)}.json"
    try:
        data = get_json(url, {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
    except (DataSourceError, OSError, ValueError) as exc:
        warnings.append(f"SEC submissions identity lookup failed for CIK {format_cik(cik)}: {exc}")
        return ()
    tokens: list[str] = []
    name = data.get("name")
    if isinstance(name, str):
        tokens.append(name)
    tickers = data.get("tickers")
    if isinstance(tickers, list):
        tokens.extend(str(ticker) for ticker in tickers if isinstance(ticker, str) and ticker.strip())
    former_names = data.get("formerNames")
    if isinstance(former_names, list):
        for item in former_names:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                tokens.append(item["name"])
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        expanded.extend(_company_name_variants_for_identity(token))
    return tuple(
        sorted(
            {token.strip() for token in expanded if token and len(token.strip()) >= 2},
            key=len,
            reverse=True,
        )
    )


def _sec_declared_trading_symbols(text: str) -> set[str]:
    match = re.search(
        r"Trading Symbol\(s\)(.*?)(?:Indicate by check mark|Emerging growth company|Item\s+\d+\.\d+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return set()
    stopwords = {
        "ACT",
        "CAPITAL",
        "CLASS",
        "COMMON",
        "EACH",
        "EXCHANGE",
        "LLC",
        "MARKET",
        "NAME",
        "NASDAQ",
        "NONE",
        "NYSE",
        "OF",
        "ON",
        "REGISTERED",
        "SECURITIES",
        "STOCK",
        "SYMBOL",
        "THE",
        "TITLE",
        "TRADING",
        "WHICH",
    }
    symbols = {
        candidate
        for candidate in re.findall(r"\b[A-Z][A-Z0-9.]{0,5}\b", match.group(1).upper())
        if candidate not in stopwords and not candidate.startswith("N/")
    }
    return symbols


def _sec_declared_registrant(text: str) -> str | None:
    match = re.search(
        r"\b([A-Z][A-Z0-9&.,' -]{2,120})\s+\(Exact name of registrant",
        text,
    )
    if not match:
        return None
    return " ".join(match.group(1).split()).strip(" .,:;-")


def _registrant_matches_case(registrant: str, case: HistoricalCase) -> bool:
    registrant_normalized = _normalized_identity_text(registrant)
    for _kind, value in _leak_terms(case):
        token = _normalized_identity_text(value)
        if len(token) < 3:
            continue
        if token in registrant_normalized or registrant_normalized in token:
            return True
    return False


def _registrant_matches_tokens(registrant: str, tokens: Iterable[str]) -> bool:
    registrant_normalized = _normalized_identity_text(registrant)
    for token in tokens:
        token_normalized = _normalized_identity_text(token)
        if len(token_normalized) < 3:
            continue
        if token_normalized in registrant_normalized or registrant_normalized in token_normalized:
            return True
    return False


def _company_name_variants_for_identity(company: str) -> list[str]:
    variants: list[str] = []
    for raw_piece in re.split(r"\s*/\s*|\s+\|\s+", company):
        piece = re.sub(r"\s+", " ", raw_piece).strip(" ,.;:-")
        if not piece:
            continue
        variants.append(piece)
        stripped = re.sub(
            r"\b(incorporated|inc|corporation|corp|company|co|ltd|plc)\.?(?:\s+\d+)?$",
            "",
            piece,
            flags=re.IGNORECASE,
        ).strip(" ,.;:-")
        if stripped:
            variants.append(stripped)
    return variants


def _normalized_identity_text(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return (
        normalized.replace("corp oration", "corporation")
        .replace("inc orporated", "incorporated")
        .replace("co mpany", "company")
    )


def _cross_case_identity_hits(text: str, case: HistoricalCase, all_cases: Iterable[HistoricalCase]) -> list[str]:
    own_terms = {value.lower() for _kind, value in _leak_terms(case)}
    hits: list[str] = []
    for other in all_cases:
        if other.case_id == case.case_id:
            continue
        for _kind, value in _leak_terms(other):
            if value.lower() in own_terms:
                continue
            if re.search(_identity_token_pattern(value), text, flags=re.IGNORECASE):
                hits.append(value)
    return sorted(set(hits), key=len, reverse=True)[:5]


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
    selection_policy: str = "alphabetical",
    holdout_symbols: frozenset[str] = frozenset(),
    documents_by_symbol: Mapping[str, tuple[DocumentRecord, ...]] | None = None,
) -> dict[str, tuple[HistoricalCase, ...]]:
    if winner_symbol_count < 2 or control_symbol_count < 2:
        raise ValidationError("select at least two winner and two control symbols")
    winners = _ordered_latest_cases(
        cases,
        CaseOutcomeLabel.WINNER,
        selection_policy=selection_policy,
        documents_by_symbol=documents_by_symbol,
    )
    controls = _ordered_latest_cases(
        cases,
        CaseOutcomeLabel.CONTROL,
        selection_policy=selection_policy,
        documents_by_symbol=documents_by_symbol,
    )
    if len(winners) < winner_symbol_count or len(controls) < control_symbol_count:
        raise ValidationError("not enough winner/control symbols for requested Ralph experiment")
    if refinement_per_label < 1:
        raise ValidationError("refinement_per_label must be positive")
    if refinement_per_label >= min(winner_symbol_count, control_symbol_count):
        raise ValidationError("refinement_per_label must leave at least one holdout per label")
    if selection_policy not in {"alphabetical", "evidence-rich", "atomic-evidence-rich"}:
        raise ValidationError(f"unsupported Ralph selection policy: {selection_policy}")
    selected_winners = tuple(winners[:winner_symbol_count])
    selected_controls = tuple(controls[:control_symbol_count])
    selected_symbols = {
        case.packet.company.ticker.symbol.upper()
        for case in selected_winners + selected_controls
    }
    missing_holdout_symbols = sorted(holdout_symbols - selected_symbols)
    if missing_holdout_symbols:
        raise ValidationError(f"--holdout-symbols were not selected: {missing_holdout_symbols}")
    winner_refinement, winner_holdout = _split_refinement_holdout(
        selected_winners,
        refinement_per_label=refinement_per_label,
        holdout_symbols=holdout_symbols,
    )
    control_refinement, control_holdout = _split_refinement_holdout(
        selected_controls,
        refinement_per_label=refinement_per_label,
        holdout_symbols=holdout_symbols,
    )
    refinement = winner_refinement + control_refinement
    holdout = winner_holdout + control_holdout
    return {
        "refinement": refinement,
        "holdout": holdout,
    }


def _resolve_selection_counts(
    *,
    winner_symbol_count: int,
    control_symbol_count: int,
    refinement_per_label: int,
    blind_holdout_size: int,
    selection_seed: int,
) -> tuple[int, int]:
    """Resolve a one-time seeded blind label mix while preserving refinement cases."""

    if blind_holdout_size == 0:
        return winner_symbol_count, control_symbol_count
    if blind_holdout_size < 2:
        raise ValidationError("--blind-holdout-size must be zero or at least two")
    if refinement_per_label < 1:
        raise ValidationError("refinement_per_label must be positive")
    winner_holdout_count = random.Random(selection_seed).randint(1, blind_holdout_size - 1)
    control_holdout_count = blind_holdout_size - winner_holdout_count
    return (
        winner_holdout_count + refinement_per_label,
        control_holdout_count + refinement_per_label,
    )


def _select_cases_from_manifest(
    cases: Iterable[HistoricalCase],
    manifest_path: Path,
) -> dict[str, tuple[HistoricalCase, ...]]:
    """Replay exact refinement and blind case ids from a frozen selection artifact."""

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases_by_id = {case.case_id: case for case in cases}
    selected: dict[str, tuple[HistoricalCase, ...]] = {}
    selected_ids: set[str] = set()
    for bucket, field in (("refinement", "refinement_cases"), ("holdout", "holdout_cases")):
        records = data.get(field)
        if not isinstance(records, list) or not records:
            raise ValidationError(f"selection manifest missing {field}")
        bucket_cases: list[HistoricalCase] = []
        for record in records:
            case_id = record.get("case_id") if isinstance(record, dict) else None
            if not isinstance(case_id, str) or case_id not in cases_by_id:
                raise ValidationError(f"selection manifest case unavailable: {case_id}")
            case = cases_by_id[case_id]
            if case_id in selected_ids:
                raise ValidationError(f"selection manifest repeats case: {case_id}")
            if record.get("label") != case.label.value:
                raise ValidationError(f"selection manifest label changed for {case_id}")
            if record.get("as_of_date") != case.packet.as_of.as_of_date.isoformat():
                raise ValidationError(f"selection manifest as-of changed for {case_id}")
            selected_ids.add(case_id)
            bucket_cases.append(case)
        selected[bucket] = tuple(bucket_cases)
    holdout_labels = {case.label for case in selected["holdout"]}
    if not {CaseOutcomeLabel.WINNER, CaseOutcomeLabel.CONTROL}.issubset(holdout_labels):
        raise ValidationError("selection manifest holdout must contain a winner and a control")
    return selected


def _selected_cases_by_bucket(
    selected: Mapping[str, tuple[HistoricalCase, ...]],
    updated_cases: Iterable[HistoricalCase],
) -> dict[str, tuple[HistoricalCase, ...]]:
    updated_by_id = {case.case_id: case for case in updated_cases}
    return {
        bucket: tuple(updated_by_id[case.case_id] for case in selected[bucket])
        for bucket in ("refinement", "holdout")
    }


def _split_refinement_holdout(
    selected_cases: tuple[HistoricalCase, ...],
    *,
    refinement_per_label: int,
    holdout_symbols: frozenset[str],
) -> tuple[tuple[HistoricalCase, ...], tuple[HistoricalCase, ...]]:
    refinement_candidates = tuple(
        case
        for case in selected_cases
        if case.packet.company.ticker.symbol.upper() not in holdout_symbols
    )
    if len(refinement_candidates) < refinement_per_label:
        raise ValidationError("not enough non-pinned cases remain for the requested refinement split")
    refinement = refinement_candidates[:refinement_per_label]
    refinement_ids = {case.case_id for case in refinement}
    holdout = tuple(case for case in selected_cases if case.case_id not in refinement_ids)
    return refinement, holdout


def _parse_symbol_set(raw: str) -> frozenset[str]:
    return frozenset(symbol.strip().upper() for symbol in raw.split(",") if symbol.strip())


def _parse_csv_values(raw: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in raw.split(",") if value.strip())


def _ordered_latest_cases(
    cases: Iterable[HistoricalCase],
    label: CaseOutcomeLabel,
    *,
    selection_policy: str,
    documents_by_symbol: Mapping[str, tuple[DocumentRecord, ...]] | None = None,
) -> list[HistoricalCase]:
    latest_cases = _latest_case_per_symbol(cases, label)
    if selection_policy == "alphabetical":
        return latest_cases
    if selection_policy == "evidence-rich":
        return sorted(
            latest_cases,
            key=lambda case: (_case_evidence_richness(case), case.packet.company.ticker.symbol),
            reverse=True,
        )
    if selection_policy == "atomic-evidence-rich":
        return sorted(
            latest_cases,
            key=lambda case: (
                _case_atomic_evidence_richness(case, documents_by_symbol),
                case.packet.company.ticker.symbol,
            ),
            reverse=True,
        )
    raise ValidationError(f"unsupported Ralph selection policy: {selection_policy}")


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


def _case_evidence_richness(case: HistoricalCase) -> tuple[int, int, int, int, int, int, int]:
    packet = case.packet
    features = {feature.name: feature for feature in packet.features}
    text = " ".join(
        [item.summary for item in packet.evidence]
        + [catalyst.name for catalyst in packet.catalysts]
        + [item.summary for catalyst in packet.catalysts for item in catalyst.evidence]
    ).lower()
    catalyst_count = len(packet.catalysts) + _keyword_hit_count(text, ("order", "contract", "approval", "launch", "funding", "financing"))
    materiality_count = _keyword_hit_count(text, ("material", "large", "backlog", "capacity", "shipment", "customer", "award"))
    risk_count = _keyword_hit_count(text, ("risk", "delay", "debt", "dilution", "cash burn", "execution", "regulatory"))
    theme_count = int(bool(packet.theme_ids)) + _keyword_hit_count(text, ("demand", "industry", "customer", "capacity", "supply chain"))
    fundamentals_count = sum(1 for name in features if name.startswith(("financial.", "valuation.", "profile.")))
    market_count = sum(1 for name in features if name.startswith("price."))
    evidence_count = len(packet.evidence)
    return (
        catalyst_count + materiality_count + risk_count + theme_count,
        catalyst_count,
        materiality_count,
        risk_count,
        fundamentals_count,
        market_count,
        evidence_count,
    )


def _case_atomic_evidence_richness(
    case: HistoricalCase,
    documents_by_symbol: Mapping[str, tuple[DocumentRecord, ...]] | None = None,
) -> tuple[int, int, int, int]:
    """Rank cases by conservative source-linked facts instead of document keywords."""

    facts = extract_atomic_evidence_by_case((case,), documents_by_symbol)[case.case_id]
    target_facts = [fact for fact in facts if fact.family in TARGET_INFORMATION_FAMILIES]
    target_families = {fact.family for fact in target_facts}
    source_facts = [fact for fact in facts if fact.extraction_method != "structured_feature"]
    confirmed = [fact for fact in target_facts if fact.status.value not in {"ambiguous"}]
    return len(target_families), len(confirmed), len(source_facts), len(facts)


def _keyword_hit_count(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _ralph_researcher(args: argparse.Namespace, *, cache_dir: Path):
    if args.mode == "heuristic":
        return HeuristicRalphBlindResearcher()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    client = OpenRouterChatClient(
        args.openrouter_model,
        api_key,
        transport=UrllibTransport(timeout_seconds=args.timeout_seconds, max_attempts=4),
    )
    return CachedRalphBlindResearcher(OpenAIRalphBlindResearcher(client), cache_dir)


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
        f"positive_gap={refinement.positive_confidence_gap:.4f} "
        f"confusion={refinement.confusion_matrix} "
        f"fp_rate={refinement.false_positive_rate:.4f} fn_rate={refinement.false_negative_rate:.4f} "
        f"passed={refinement.separation_passed}"
    )
    print(
        "[ralph-experiment] holdout "
        f"scheme={holdout.scheme_version} gap={holdout.confidence_gap:.4f} "
        f"positive_gap={holdout.positive_confidence_gap:.4f} "
        f"confusion={holdout.confusion_matrix} "
        f"fp_rate={holdout.false_positive_rate:.4f} fn_rate={holdout.false_negative_rate:.4f} "
        f"passed={holdout.separation_passed}"
    )
    if result.holdout_feedback_iterations:
        print(
            "[ralph-experiment] holdout_feedback_iterations="
            f"{len(result.holdout_feedback_iterations)} final_scheme={result.final_information_scheme.version}"
        )
    print(f"[ralph-experiment] final_status={result.final_status}")
    if result.final_status != "holdout_separated":
        print(f"[ralph-experiment] error={result.holdout_error_analysis.recommendation}")


def _write_preflight_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    created_at: datetime,
    refinement_cases: tuple[HistoricalCase, ...],
    holdout_cases: tuple[HistoricalCase, ...],
    learning_result,
    theme_maps,
    playbook_synthesis,
) -> dict[str, Path]:
    scheme, diagnostic = synthesize_information_scheme(
        refinement_cases,
        learning_result=learning_result,
        theme_maps=theme_maps,
        playbook_synthesis=playbook_synthesis,
    )
    refinement_packets = tuple(
        build_blind_scheme_packet(
            case,
            scheme,
            anonymous_case_id=f"case_{index:03d}",
        )
        for index, case in enumerate(refinement_cases, start=1)
    )
    holdout_packets = tuple(
        build_blind_scheme_packet(
            case,
            scheme,
            anonymous_case_id=f"holdout_{index:03d}",
        )
        for index, case in enumerate(holdout_cases, start=1)
    )
    packet_cases = list(zip(refinement_packets + holdout_packets, refinement_cases + holdout_cases, strict=True))
    requests = [
        _blind_llm_request(packet, phase="refinement_initial")
        for packet in refinement_packets
    ] + [
        _blind_llm_request(packet, phase="holdout_preview")
        for packet in holdout_packets
    ]
    leakage_report = _leakage_report(packet_cases)
    paths = {
        "preflight_blind_llm_requests": output_dir / "preflight_blind_llm_requests.json",
        "preflight_leakage_report": output_dir / "preflight_leakage_report.json",
        "preflight_scheme_diagnostic_label_aware": output_dir / "preflight_scheme_diagnostic_label_aware.json",
        "case_selection_label_aware": output_dir / "case_selection_label_aware.json",
        "preflight_manifest": output_dir / "preflight_manifest.json",
    }
    _write_json(
        paths["preflight_blind_llm_requests"],
        {
            "schema_version": "ralph-blind-export-preflight-v0.1",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "stage_boundary": "preflight_anonymous_blind_packet_export",
            "external_destination": "OpenRouter only after explicit user approval",
            "web_tools_allowed": False,
            "requests": requests,
        },
    )
    _write_json(paths["preflight_leakage_report"], leakage_report)
    _write_json(
        paths["preflight_scheme_diagnostic_label_aware"],
        {
            "schema_version": "ralph-preflight-diagnostic-v0.1",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "stage_boundary": "retrospective_label_aware",
            "scheme": scheme.to_dict(),
            "diagnostic_summary": diagnostic.to_dict(),
        },
    )
    _write_json(
        paths["case_selection_label_aware"],
        {
            "schema_version": "ralph-case-selection-v0.1",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "stage_boundary": "retrospective_label_aware",
            "refinement_cases": [_case_selection_record(case) for case in refinement_cases],
            "holdout_cases": [_case_selection_record(case) for case in holdout_cases],
        },
    )
    _write_json(
        paths["preflight_manifest"],
        {
            "schema_version": "ralph-preflight-manifest-v0.1",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "scheme_version": scheme.version,
            "request_count": len(requests),
            "packet_sha256": [request["packet_sha256"] for request in requests],
            "leakage_passed": leakage_report["passed"],
            "external_call_performed": False,
            "outputs": {name: str(path) for name, path in sorted(paths.items())},
            "next_step": (
                "Run without --preflight-only after explicit approval to send these anonymous "
                "blind packets to the configured LLM provider."
            ),
        },
    )
    if not leakage_report["passed"]:
        raise ValidationError("preflight leakage scan failed")
    return paths


def _write_imported_response_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    created_at: datetime,
    refinement_cases: tuple[HistoricalCase, ...],
    holdout_cases: tuple[HistoricalCase, ...],
    learning_result,
    theme_maps,
    playbook_synthesis,
    responses_path: Path,
) -> dict[str, Path]:
    scheme, diagnostic = synthesize_information_scheme(
        refinement_cases,
        learning_result=learning_result,
        theme_maps=theme_maps,
        playbook_synthesis=playbook_synthesis,
    )
    refinement_packets = tuple(
        build_blind_scheme_packet(
            case,
            scheme,
            anonymous_case_id=f"case_{index:03d}",
        )
        for index, case in enumerate(refinement_cases, start=1)
    )
    holdout_packets = tuple(
        build_blind_scheme_packet(
            case,
            scheme,
            anonymous_case_id=f"holdout_{index:03d}",
        )
        for index, case in enumerate(holdout_cases, start=1)
    )
    all_packets = refinement_packets + holdout_packets
    records = _load_external_response_records(responses_path)
    analyses_by_id, integrity_warnings = _analyses_from_response_records(all_packets, records)
    missing = sorted(packet.anonymous_case_id for packet in all_packets if packet.anonymous_case_id not in analyses_by_id)
    if missing:
        raise ValidationError(f"missing external blind responses for: {missing}")
    refinement_analyses = tuple(analyses_by_id[packet.anonymous_case_id] for packet in refinement_packets)
    holdout_analyses = tuple(analyses_by_id[packet.anonymous_case_id] for packet in holdout_packets)
    refinement_evaluation = evaluate_scheme_performance(
        refinement_cases,
        refinement_analyses,
        scheme_version=scheme.version + ":imported_refinement",
    )
    holdout_evaluation = evaluate_scheme_performance(
        holdout_cases,
        holdout_analyses,
        scheme_version=scheme.version + ":imported_holdout",
    )
    refinement_error = analyze_scheme_errors(refinement_evaluation, diagnostic)
    holdout_error = analyze_scheme_errors(holdout_evaluation, diagnostic)
    next_scheme_proposal = None if holdout_evaluation.separation_passed else propose_next_information_scheme(
        scheme,
        holdout_error,
    )
    final_status = "holdout_separated" if holdout_evaluation.separation_passed else "holdout_not_separated"
    paths = {
        "imported_blind_responses": output_dir / "imported_blind_responses.json",
        "imported_blind_scheme_evaluation": output_dir / "imported_blind_scheme_evaluation.json",
        "imported_error_analysis": output_dir / "imported_error_analysis.json",
        "imported_next_scheme_proposal": output_dir / "imported_next_scheme_proposal.json",
        "case_selection_label_aware": output_dir / "case_selection_label_aware.json",
        "imported_response_manifest": output_dir / "imported_response_manifest.json",
    }
    _write_json(
        paths["imported_blind_responses"],
        {
            "schema_version": "ralph-imported-blind-responses-v0.1",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "stage_boundary": "external_blind_response_import",
            "provider_call_performed_by_script": False,
            "source_responses_path": str(responses_path),
            "scheme": scheme.to_dict(),
            "refinement_blind_analyses": [analysis.to_dict() for analysis in refinement_analyses],
            "holdout_blind_analyses": [analysis.to_dict() for analysis in holdout_analyses],
            "integrity_warnings": integrity_warnings,
        },
    )
    _write_json(
        paths["imported_blind_scheme_evaluation"],
        {
            "schema_version": "ralph-imported-evaluation-v0.1",
            "run_id": run_id,
            "stage_boundary": "retrospective_label_aware_imported_blind_evaluation",
            "refinement_evaluation": refinement_evaluation.to_dict(),
            "holdout_evaluation": holdout_evaluation.to_dict(),
        },
    )
    _write_json(
        paths["imported_error_analysis"],
        {
            "schema_version": "ralph-imported-error-analysis-v0.1",
            "run_id": run_id,
            "stage_boundary": "retrospective_label_aware_imported_blind_evaluation",
            "refinement_error_analysis": refinement_error.to_dict(),
            "holdout_error_analysis": holdout_error.to_dict(),
        },
    )
    _write_json(
        paths["imported_next_scheme_proposal"],
        {
            "schema_version": "ralph-imported-next-scheme-v0.1",
            "run_id": run_id,
            "stage_boundary": "retrospective_label_aware_feedback",
            "base_scheme": scheme.to_dict(),
            "next_scheme_proposal": next_scheme_proposal.to_dict() if next_scheme_proposal is not None else None,
            "promotion_status": "pending_human_review",
            "can_enter_long_running_default": False,
        },
    )
    _write_json(
        paths["case_selection_label_aware"],
        {
            "schema_version": "ralph-case-selection-v0.1",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "stage_boundary": "retrospective_label_aware",
            "refinement_cases": [_case_selection_record(case) for case in refinement_cases],
            "holdout_cases": [_case_selection_record(case) for case in holdout_cases],
        },
    )
    _write_json(
        paths["imported_response_manifest"],
        {
            "schema_version": "ralph-imported-response-manifest-v0.1",
            "run_id": run_id,
            "created_at": created_at.isoformat(),
            "scheme_version": scheme.version,
            "response_count": len(records),
            "provider_call_performed_by_script": False,
            "final_status": final_status,
            "holdout_confidence_gap": holdout_evaluation.confidence_gap,
            "holdout_positive_confidence_gap": holdout_evaluation.positive_confidence_gap,
            "holdout_confusion_matrix": dict(holdout_evaluation.confusion_matrix),
            "holdout_classification_metrics": dict(
                holdout_evaluation.classification_metrics
            ),
            "holdout_false_positive_rate": holdout_evaluation.false_positive_rate,
            "holdout_false_negative_rate": holdout_evaluation.false_negative_rate,
            "refinement_confidence_gap": refinement_evaluation.confidence_gap,
            "refinement_positive_confidence_gap": refinement_evaluation.positive_confidence_gap,
            "refinement_confusion_matrix": dict(refinement_evaluation.confusion_matrix),
            "refinement_classification_metrics": dict(
                refinement_evaluation.classification_metrics
            ),
            "integrity_warning_count": len(integrity_warnings),
            "promotion_status": "pending_human_review",
            "can_enter_long_running_default": False,
            "outputs": {name: str(path) for name, path in sorted(paths.items())},
        },
    )
    return paths


def _blind_llm_request(packet, *, phase: str) -> dict[str, Any]:
    payload = packet.to_prompt_dict()
    return {
        "request_id": packet.anonymous_case_id,
        "phase": phase,
        "scheme_version": packet.scheme_version,
        "packet_sha256": _sha256(payload),
        "developer_message": (
            "Use only this anonymous point-in-time packet. Web search/tools are disabled. "
            "Do not infer hidden outcome labels, ticker, company identity, future return, or post-as-of facts."
        ),
        "packet": payload,
    }


def _load_external_response_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("responses") if isinstance(data, dict) else data
    if not isinstance(records, list):
        raise ValidationError("external response file must contain a responses list")
    if not all(isinstance(record, dict) for record in records):
        raise ValidationError("external response records must be objects")
    return records


def _analyses_from_response_records(
    packets: tuple[Any, ...],
    records: list[dict[str, Any]],
) -> tuple[dict[str, RalphBlindAnalysis], list[str]]:
    packets_by_id = {packet.anonymous_case_id: packet for packet in packets}
    analyses: dict[str, RalphBlindAnalysis] = {}
    warnings: list[str] = []
    for record in records:
        request_id = record.get("request_id") or record.get("anonymous_case_id")
        if not isinstance(request_id, str) or request_id not in packets_by_id:
            raise ValidationError(f"unknown external response request_id: {request_id!r}")
        if request_id in analyses:
            raise ValidationError(f"duplicate external response request_id: {request_id}")
        packet = packets_by_id[request_id]
        expected_hash = _sha256(packet.to_prompt_dict())
        provided_hash = record.get("packet_sha256")
        if provided_hash is None:
            warnings.append(f"{request_id}: response did not include packet_sha256")
        elif provided_hash != expected_hash:
            warnings.append(f"{request_id}: packet_sha256 mismatch")
        analyses[request_id] = _analysis_from_external_response(packet, record)
    return analyses, warnings


def _analysis_from_external_response(packet, record: dict[str, Any]) -> RalphBlindAnalysis:
    data, raw_text = _external_response_payload(record)
    return RalphBlindAnalysis(
        source_case_id=packet.source_case_id,
        anonymous_case_id=packet.anonymous_case_id,
        as_of_date=packet.as_of_date,
        scheme_version=packet.scheme_version,
        surge_candidate=_string(data, "surge_candidate"),
        surge_candidate_reason=_string_any(data, ("surge_candidate_reason", "reason")),
        expectation_gap=_string(data, "expectation_gap"),
        pre_surge_signals=tuple(_string_list(data, "pre_surge_signals")),
        contrary_evidence=tuple(_string_list(data, "contrary_evidence")),
        catalyst_watch=tuple(_string_list(data, "catalyst_watch")),
        confidence=_confidence(data.get("confidence")),
        raw_text=raw_text,
        missing_context=tuple(_optional_string_list(data, "missing_context")),
    )


def _external_response_payload(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if isinstance(record.get("output"), dict):
        output = record["output"]
        return output, json.dumps(output, sort_keys=True)
    if _looks_like_response_payload(record):
        return record, json.dumps(record, sort_keys=True)
    text = record.get("output_text") or record.get("raw_text")
    if not isinstance(text, str) or not text.strip():
        raise ValidationError("external response must include output, output_text, or raw_text")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("external response text was not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValidationError("external response text must decode to an object")
    return data, text


def _looks_like_response_payload(record: dict[str, Any]) -> bool:
    return all(key in record for key in ("surge_candidate", "expectation_gap", "confidence"))


def _leakage_report(
    packet_cases: list[tuple[Any, HistoricalCase]],
    *,
    extra_identity_terms_by_case: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    case_reports = []
    global_terms = _global_leak_terms(case for _packet, case in packet_cases)
    for source_case_id, terms in (extra_identity_terms_by_case or {}).items():
        global_terms.extend(
            (source_case_id, "source_identity_token", value)
            for value in terms
            if value
        )
    for packet, case in packet_cases:
        prompt = json.dumps(packet.to_prompt_dict(), sort_keys=True)
        findings = _leakage_findings(
            prompt,
            case,
            global_terms,
            extra_identity_terms=(extra_identity_terms_by_case or {}).get(case.case_id, ()),
        )
        case_reports.append(
            {
                "anonymous_case_id": packet.anonymous_case_id,
                "packet_sha256": _sha256(packet.to_prompt_dict()),
                "finding_count": len(findings),
                "findings": findings,
            }
        )
    return {
        "schema_version": "ralph-preflight-leakage-report-v0.1",
        "passed": not any(report["findings"] for report in case_reports),
        "case_reports": case_reports,
    }


def _leakage_findings(
    prompt: str,
    case: HistoricalCase,
    global_terms: list[tuple[str, str, str]] | None = None,
    extra_identity_terms: Iterable[str] = (),
) -> list[dict[str, str]]:
    findings = []
    for kind, value in _leak_terms(case):
        if value and re.search(_identity_token_pattern(value), prompt, flags=re.IGNORECASE):
            findings.append({"kind": kind, "value": value})
    for value in extra_identity_terms:
        if value and re.search(_identity_token_pattern(value), prompt, flags=re.IGNORECASE):
            findings.append({"kind": "source_identity_token", "value": value})
    for source_case_id, kind, value in global_terms or ():
        if source_case_id == case.case_id:
            continue
        if value and re.search(_identity_token_pattern(value), prompt, flags=re.IGNORECASE):
            findings.append({"kind": f"cross_case_{kind}", "value": value})
    if "http://" in prompt or "https://" in prompt:
        findings.append({"kind": "source_url", "value": "url-like text"})
    for forbidden_key in ('"label"', '"outcome_return"', '"hidden_outcome_summary"', '"source_case_id"'):
        if forbidden_key in prompt:
            findings.append({"kind": "forbidden_key", "value": forbidden_key})
    return findings


def _leak_terms(case: HistoricalCase) -> list[tuple[str, str]]:
    ticker = case.packet.company.ticker
    terms = [
        ("case_id", case.case_id),
        ("packet_id", case.packet.packet_id),
        ("symbol", ticker.symbol),
        ("company_name", ticker.company_name or ""),
        ("figi", ticker.figi or ""),
    ]
    terms.extend(("identity_token", token) for token in _identity_tokens(case.packet))
    return [(kind, value) for kind, value in terms if value]


def _global_leak_terms(cases: Iterable[HistoricalCase]) -> list[tuple[str, str, str]]:
    terms: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for case in cases:
        for kind, value in _leak_terms(case):
            key = (case.case_id, kind, value)
            if key not in seen:
                terms.append(key)
                seen.add(key)
    return terms


def _sha256(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _optional_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"{key} must be a string list")
    return value


def _string_any(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    raise ValidationError(f"missing non-empty {'/'.join(keys)}")


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
