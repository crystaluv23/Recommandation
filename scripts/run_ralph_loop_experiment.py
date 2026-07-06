"""Run an artifact-backed Ralph Loop refinement/holdout experiment."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from stock_opportunity_agent.cases import CaseOutcomeLabel, HistoricalCase, learn_pre_surge_signal_logic
from stock_opportunity_agent.config import load_config
from stock_opportunity_agent.data.documents import DocumentRecord
from stock_opportunity_agent.data.sources.core import DataSourceError, UrllibJsonTransport
from stock_opportunity_agent.llm.openai import UrllibTransport
from stock_opportunity_agent.llm.openrouter import OpenRouterChatClient
from stock_opportunity_agent.models import DataQuality, EvidenceItem, EvidenceKind, ResearchPacket, ValidationError
from stock_opportunity_agent.research import (
    BlindCaseAnalysis,
    CachedRalphBlindResearcher,
    HeuristicRalphBlindResearcher,
    HeuristicSurgePlaybookSynthesizer,
    OpenAIRalphBlindResearcher,
    RalphBlindAnalysis,
    build_blind_scheme_packet,
    run_ralph_experiment,
    synthesize_information_scheme,
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
    selected = _select_cases(
        cases,
        winner_symbol_count=args.winner_symbol_count,
        control_symbol_count=args.control_symbol_count,
        refinement_per_label=args.refinement_per_label,
        selection_policy=args.selection_policy,
        holdout_symbols=_parse_symbol_set(args.holdout_symbols),
    )
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
        help="Optional formal cold-start documents artifact used to refresh source-detail excerpts.",
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
    parser.add_argument(
        "--holdout-feedback-iterations",
        type=int,
        default=0,
        help="Bounded label-aware holdout feedback proposal rounds after the initial holdout evaluation.",
    )
    parser.add_argument(
        "--selection-policy",
        choices=("alphabetical", "evidence-rich"),
        default="alphabetical",
        help="Choose latest cases alphabetically or prioritize packets with richer scheme evidence.",
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
        return {}
    documents: dict[str, tuple[DocumentRecord, ...]] = {}
    for symbol, records in records_by_symbol.items():
        if not isinstance(records, list):
            continue
        documents[str(symbol).upper()] = tuple(_document_from_record(record) for record in records)
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
                )
            )
        if refreshed_documents:
            refreshed_by_symbol[symbol] = tuple(refreshed_documents)
    return refreshed_by_symbol, tuple(warnings)


def _is_sec_archive_url(url: str) -> bool:
    return url.startswith("https://www.sec.gov/Archives/edgar/data/")


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
) -> dict[str, tuple[HistoricalCase, ...]]:
    if winner_symbol_count < 2 or control_symbol_count < 2:
        raise ValidationError("select at least two winner and two control symbols")
    winners = _ordered_latest_cases(cases, CaseOutcomeLabel.WINNER, selection_policy=selection_policy)
    controls = _ordered_latest_cases(cases, CaseOutcomeLabel.CONTROL, selection_policy=selection_policy)
    if len(winners) < winner_symbol_count or len(controls) < control_symbol_count:
        raise ValidationError("not enough winner/control symbols for requested Ralph experiment")
    if refinement_per_label < 1:
        raise ValidationError("refinement_per_label must be positive")
    if refinement_per_label >= min(winner_symbol_count, control_symbol_count):
        raise ValidationError("refinement_per_label must leave at least one holdout per label")
    if selection_policy not in {"alphabetical", "evidence-rich"}:
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


def _ordered_latest_cases(
    cases: Iterable[HistoricalCase],
    label: CaseOutcomeLabel,
    *,
    selection_policy: str,
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
        f"fp_rate={refinement.false_positive_rate:.4f} fn_rate={refinement.false_negative_rate:.4f} "
        f"passed={refinement.separation_passed}"
    )
    print(
        "[ralph-experiment] holdout "
        f"scheme={holdout.scheme_version} gap={holdout.confidence_gap:.4f} "
        f"positive_gap={holdout.positive_confidence_gap:.4f} "
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
            "holdout_false_positive_rate": holdout_evaluation.false_positive_rate,
            "holdout_false_negative_rate": holdout_evaluation.false_negative_rate,
            "refinement_confidence_gap": refinement_evaluation.confidence_gap,
            "refinement_positive_confidence_gap": refinement_evaluation.positive_confidence_gap,
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


def _leakage_report(packet_cases: list[tuple[Any, HistoricalCase]]) -> dict[str, Any]:
    case_reports = []
    global_terms = _global_leak_terms(case for _packet, case in packet_cases)
    for packet, case in packet_cases:
        prompt = json.dumps(packet.to_prompt_dict(), sort_keys=True)
        findings = _leakage_findings(prompt, case, global_terms)
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
) -> list[dict[str, str]]:
    findings = []
    for kind, value in _leak_terms(case):
        if value and re.search(_identity_token_pattern(value), prompt, flags=re.IGNORECASE):
            findings.append({"kind": kind, "value": value})
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
