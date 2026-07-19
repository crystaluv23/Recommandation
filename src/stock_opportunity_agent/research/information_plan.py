"""Broad Ralph information-plan research around packet-level schemes."""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.cases.learning import HistoricalCase
from stock_opportunity_agent.cases.outcomes import CaseOutcomeLabel
from stock_opportunity_agent.data.documents import DocumentContentScope, DocumentRecord
from stock_opportunity_agent.models import (
    DataQuality,
    EvidenceItem,
    EvidenceKind,
    ResearchPacket,
    ValidationError,
)
from stock_opportunity_agent.research.ralph_loop import (
    BlindPacketSection,
    BlindSchemePacket,
    InformationScheme,
    RalphBlindAnalysis,
    RalphBlindResearcher,
    SchemeEvaluation,
    evaluate_scheme_performance,
    identity_safe_blind_value,
)


INFORMATION_PLAN_SCHEMA_VERSION = "research-information-plan-v0.3"
ATOMIC_EVIDENCE_SCHEMA_VERSION = "atomic-evidence-v0.2"
RAW_PACKET_SCHEME_ID = "ralph-raw-source-baseline"
TARGET_INFORMATION_FAMILIES = (
    "deal_status_timing",
    "capital_structure_liquidity",
    "orders_contracts",
    "customer_capacity",
    "policy_regulatory",
    "theme_industry_transmission",
    "expectation_gap",
)


class RequirementCoverageState(str, Enum):
    """Requirement-level evidence availability and extraction state."""

    CONFIRMED = "confirmed"
    CONTRADICTED = "contradicted"
    NOT_APPLICABLE = "not_applicable"
    NOT_FOUND = "not_found"
    SOURCE_UNAVAILABLE = "source_unavailable"
    NOT_FETCHED = "not_fetched"
    EXTRACTION_FAILED = "extraction_failed"
    AMBIGUOUS = "ambiguous"


class AtomicFactStatus(str, Enum):
    """Point-in-time status of one extracted fact."""

    CONFIRMED = "confirmed"
    PROPOSED = "proposed"
    EXPECTED = "expected"
    COMPLETED = "completed"
    DELAYED = "delayed"
    TERMINATED = "terminated"
    CONTRADICTED = "contradicted"
    RISK = "risk"
    AMBIGUOUS = "ambiguous"


class FailureLayer(str, Enum):
    """Primary intervention layer for a failed blind judgment."""

    SOURCE_UNAVAILABLE = "source_unavailable"
    ACQUISITION_MISS = "acquisition_miss"
    EXTRACTION_ERROR = "extraction_error"
    SIGNAL_ERROR = "signal_error"
    REPRESENTATION_LOSS = "representation_loss"
    ANALYSIS_ERROR = "analysis_error"
    NOT_PREDICTABLY_SUPPORTED_AS_OF = "not_predictably_supported_as_of"


class DocumentContentState(str, Enum):
    """Observed usability of an archived point-in-time source body."""

    USABLE = "usable"
    SUMMARY_ONLY = "summary_only"
    LIKELY_TRUNCATED = "likely_truncated"
    METADATA_ONLY = "metadata_only"
    UNUSABLE = "unusable"


@dataclass(frozen=True)
class InformationRequirement:
    """One proposal-only evidence requirement in the broad information plan."""

    requirement_id: str
    family: str
    title: str
    description: str
    preferred_sources: tuple[str, ...]
    fallback_sources: tuple[str, ...]
    extraction_fields: tuple[str, ...]
    analysis_rubric: str
    version: str = "information-requirement-v0.2"
    proposal_status: str = "proposal_only"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible requirement."""

        return {
            "requirement_id": self.requirement_id,
            "family": self.family,
            "title": self.title,
            "description": self.description,
            "preferred_sources": list(self.preferred_sources),
            "fallback_sources": list(self.fallback_sources),
            "extraction_fields": list(self.extraction_fields),
            "analysis_rubric": self.analysis_rubric,
            "version": self.version,
            "proposal_status": self.proposal_status,
        }


@dataclass(frozen=True)
class RequirementDiagnostic:
    """Label-aware prevalence statistics for an information requirement."""

    requirement_id: str
    winner_case_count: int
    non_winner_case_count: int
    winner_prevalence: float
    non_winner_prevalence: float
    separation_lift: float
    observed_as_of_dates: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return retrospective requirement statistics."""

        return {
            "requirement_id": self.requirement_id,
            "winner_case_count": self.winner_case_count,
            "non_winner_case_count": self.non_winner_case_count,
            "winner_prevalence": self.winner_prevalence,
            "non_winner_prevalence": self.non_winner_prevalence,
            "separation_lift": self.separation_lift,
            "observed_as_of_dates": list(self.observed_as_of_dates),
        }


@dataclass(frozen=True)
class AtomicEvidence:
    """Source-linked atomic fact extracted without using outcome labels."""

    fact_id: str
    source_case_id: str
    requirement_id: str
    family: str
    subject_role: str
    event_type: str
    status: AtomicFactStatus
    statement: str
    source_span: str
    source_id: str
    source_kind: str
    as_of_date: str
    published_date: str | None
    counterparty_role: str | None = None
    amount: float | None = None
    unit: str | None = None
    period: str | None = None
    event_date: str | None = None
    negated: bool = False
    confidence: float = 1.0
    extraction_method: str = "deterministic_sentence_rule"
    derived_from_fact_ids: tuple[str, ...] = ()
    calculation: str | None = None
    schema_version: str = ATOMIC_EVIDENCE_SCHEMA_VERSION

    def to_dict(self, *, include_source_case_id: bool = True) -> dict[str, Any]:
        """Return a JSON-compatible atomic fact."""

        result = {
            "schema_version": self.schema_version,
            "fact_id": self.fact_id,
            "requirement_id": self.requirement_id,
            "family": self.family,
            "subject_role": self.subject_role,
            "counterparty_role": self.counterparty_role,
            "event_type": self.event_type,
            "status": self.status.value,
            "statement": self.statement,
            "source_span": self.source_span,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "as_of_date": self.as_of_date,
            "published_date": self.published_date,
            "event_date": self.event_date,
            "amount": self.amount,
            "unit": self.unit,
            "period": self.period,
            "negated": self.negated,
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
            "derived_from_fact_ids": list(self.derived_from_fact_ids),
            "calculation": self.calculation,
        }
        if include_source_case_id:
            result["source_case_id"] = self.source_case_id
        return result


@dataclass(frozen=True)
class RequirementCoverageEntry:
    """Coverage state for one case and one information requirement."""

    source_case_id: str
    requirement_id: str
    family: str
    state: RequirementCoverageState
    fact_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible coverage entry."""

        return {
            "source_case_id": self.source_case_id,
            "requirement_id": self.requirement_id,
            "family": self.family,
            "state": self.state.value,
            "fact_ids": list(self.fact_ids),
            "source_ids": list(self.source_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DocumentContentAudit:
    """Case-scoped completeness audit for one available source document."""

    source_case_id: str
    source_id: str
    source_kind: str
    content_scope: str
    state: DocumentContentState
    content_chars: int
    normalized_content_chars: int
    content_sha256: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return source-body audit metadata without the source text."""

        return {
            "source_case_id": self.source_case_id,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "content_scope": self.content_scope,
            "state": self.state.value,
            "content_chars": self.content_chars,
            "normalized_content_chars": self.normalized_content_chars,
            "content_sha256": self.content_sha256,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ResearchInformationPlan:
    """Broad, versioned, proposal-only Ralph information plan."""

    plan_id: str
    version: str
    requirements: tuple[InformationRequirement, ...]
    diagnostics: tuple[RequirementDiagnostic, ...]
    packet_scheme_version: str
    discovery_case_count: int
    discovery_symbol_count: int
    proposal_status: str = "proposal_only_pending_review"

    def to_dict(self) -> dict[str, Any]:
        """Return the label-aware plan proposal."""

        return {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "version": self.version,
            "stage_boundary": "retrospective_label_aware_refinement",
            "proposal_status": self.proposal_status,
            "packet_scheme_version": self.packet_scheme_version,
            "discovery_case_count": self.discovery_case_count,
            "discovery_symbol_count": self.discovery_symbol_count,
            "requirements": [item.to_dict() for item in self.requirements],
            "requirement_diagnostics": [item.to_dict() for item in self.diagnostics],
            "gold_packet_available": False,
            "optimization_claim": "best_validated_among_tested_sources_budgets_and_schemes",
        }


@dataclass(frozen=True)
class PreparedFamilyExperiment:
    """Source-backed add-back and ablation packets for one information family."""

    family: str
    available_fact_count: int
    add_back_packets: tuple[BlindSchemePacket, ...]
    ablation_packets: tuple[BlindSchemePacket, ...]
    status: str


@dataclass(frozen=True)
class PreparedInformationPlanExperiment:
    """Information-plan inputs ready for blind calls or preflight review."""

    run_id: str
    plan: ResearchInformationPlan
    active_scheme: InformationScheme
    holdout_case_ids: tuple[str, ...]
    atomic_evidence_by_case: dict[str, tuple[AtomicEvidence, ...]]
    coverage_entries: tuple[RequirementCoverageEntry, ...]
    source_pool_by_case: dict[str, tuple[str, ...]]
    source_documents_by_case: dict[str, tuple[DocumentRecord, ...]]
    document_content_audits: tuple[DocumentContentAudit, ...]
    raw_packets: tuple[BlindSchemePacket, ...]
    organized_packets: tuple[BlindSchemePacket, ...]
    family_add_back_baseline_packets: tuple[BlindSchemePacket, ...]
    family_experiments: tuple[PreparedFamilyExperiment, ...]
    context_budget: int


@dataclass(frozen=True)
class FamilyExperimentEvaluation:
    """Blind evaluation of one source-backed family add-back and ablation."""

    family: str
    status: str
    available_fact_count: int
    add_back_baseline_evaluation: SchemeEvaluation | None
    add_back_evaluation: SchemeEvaluation | None
    add_back_delta: dict[str, float] | None
    ablation_baseline_evaluation: SchemeEvaluation | None
    ablation_evaluation: SchemeEvaluation | None
    ablation_delta: dict[str, float] | None

    def to_dict(self) -> dict[str, Any]:
        """Return family experiment metrics."""

        return {
            "family": self.family,
            "status": self.status,
            "available_fact_count": self.available_fact_count,
            "add_back_baseline_evaluation": (
                self.add_back_baseline_evaluation.to_dict()
                if self.add_back_baseline_evaluation
                else None
            ),
            "add_back_evaluation": (
                self.add_back_evaluation.to_dict() if self.add_back_evaluation else None
            ),
            "add_back_delta": self.add_back_delta,
            "ablation_baseline_evaluation": (
                self.ablation_baseline_evaluation.to_dict()
                if self.ablation_baseline_evaluation
                else None
            ),
            "ablation_evaluation": (
                self.ablation_evaluation.to_dict() if self.ablation_evaluation else None
            ),
            "ablation_delta": self.ablation_delta,
        }


@dataclass(frozen=True)
class FailureAttribution:
    """Retrospective layered diagnosis for one failed blind case."""

    source_case_id: str
    primary_layer: FailureLayer
    secondary_layers: tuple[FailureLayer, ...]
    reasons: tuple[str, ...]
    proposed_intervention: str

    def to_dict(self) -> dict[str, Any]:
        """Return failure attribution without forward-return values."""

        return {
            "source_case_id": self.source_case_id,
            "primary_layer": self.primary_layer.value,
            "secondary_layers": [item.value for item in self.secondary_layers],
            "reasons": list(self.reasons),
            "proposed_intervention": self.proposed_intervention,
        }


@dataclass(frozen=True)
class InformationPlanExperimentResult:
    """Complete broad information-plan comparison result."""

    prepared: PreparedInformationPlanExperiment
    raw_analyses: tuple[RalphBlindAnalysis, ...]
    organized_analyses: tuple[RalphBlindAnalysis, ...]
    raw_evaluation: SchemeEvaluation
    organized_evaluation: SchemeEvaluation
    family_evaluations: tuple[FamilyExperimentEvaluation, ...]
    failure_attributions: tuple[FailureAttribution, ...]
    evaluation_method: str
    validation_role: str

    def comparison_dict(self) -> dict[str, Any]:
        """Return fair raw-versus-organized comparison metrics."""

        return {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": self.prepared.run_id,
            "stage_boundary": "retrospective_label_aware_holdout_evaluation",
            "comparison_contract": {
                "same_cases": True,
                "same_source_bundle": True,
                "same_researcher": True,
                "same_output_schema": True,
                "same_as_of_cutoff": True,
                "context_budget": self.prepared.context_budget,
                "gold_packet_available": False,
                "evaluation_method": self.evaluation_method,
                "validation_role": self.validation_role,
                "effectiveness_claim_allowed": (
                    self.evaluation_method == "plain_llm"
                    and self.validation_role == "untouched_company_holdout"
                ),
                "source_pool_case_count": len(self.prepared.holdout_case_ids),
                "source_pool_policy": (
                    "Both arms derive from the same available point-in-time source pool; "
                    "the organized arm may omit sources that yield no qualifying atomic fact."
                ),
                "document_content_readiness": document_content_readiness(self.prepared),
            },
            "raw_source_evaluation": self.raw_evaluation.to_dict(),
            "organized_evaluation": self.organized_evaluation.to_dict(),
            "organized_minus_raw": {
                "positive_confidence_gap": round(
                    self.organized_evaluation.positive_confidence_gap
                    - self.raw_evaluation.positive_confidence_gap,
                    4,
                ),
                "false_positive_rate": round(
                    self.organized_evaluation.false_positive_rate
                    - self.raw_evaluation.false_positive_rate,
                    4,
                ),
                "false_negative_rate": round(
                    self.organized_evaluation.false_negative_rate
                    - self.raw_evaluation.false_negative_rate,
                    4,
                ),
            },
        }


def default_information_requirements() -> tuple[InformationRequirement, ...]:
    """Return the initial broad inventory used for label-aware discovery."""

    common_fields = (
        "subject_role",
        "event_type",
        "status",
        "amount",
        "unit",
        "period",
        "event_date",
        "published_date",
        "source_span",
        "derived_from_fact_ids",
        "calculation",
    )
    return (
        _requirement(
            "business_identity",
            "Business identity and economics",
            "Identity-safe business model, products, customers, end markets, and revenue drivers.",
            ("SEC 10-K/10-Q", "company profile", "investor presentation"),
            ("transcript", "company news"),
            common_fields,
            "Use business context to decide whether later theme or customer evidence is economically direct.",
        ),
        _requirement(
            "deal_status_timing",
            "Deal status and timing",
            "Definitive terms, approvals, closing conditions, deadlines, redemption, and completion state.",
            ("SEC 8-K", "S-4/F-4", "DEFM14A", "transaction exhibits"),
            ("company news", "exchange notice"),
            common_fields,
            "Treat proposed, approved, closed, delayed, terminated, and extended transactions differently.",
        ),
        _requirement(
            "capital_structure_liquidity",
            "Capital structure and liquidity",
            "Cash runway, debt, covenants, facilities, dilution instruments, financing terms, and going concern.",
            ("SEC 10-Q/10-K", "XBRL", "credit exhibits", "prospectus"),
            ("earnings release", "transcript"),
            common_fields,
            "Judge financing per share and against runway, covenants, dilution, and maturity timing.",
        ),
        _requirement(
            "orders_contracts",
            "Orders and contracts",
            "Signed or awarded demand evidence with size, duration, customer status, and conversion timing.",
            ("SEC 8-K/exhibits", "earnings release", "transcript"),
            ("company news", "customer announcement"),
            common_fields,
            "Do not count generic contract language; require a concrete action and source-backed terms.",
        ),
        _requirement(
            "customer_capacity",
            "Customer pull-through and capacity",
            "Customer commitments, backlog, shipments, utilization, deployment, and capacity expansion.",
            ("earnings release", "transcript", "investor presentation"),
            ("company news", "counterparty evidence"),
            common_fields,
            "Require company-level pull-through and timing instead of broad end-market adjacency.",
        ),
        _requirement(
            "policy_regulatory",
            "Policy and regulatory events",
            "Approvals, permits, awards, compliance decisions, tariffs, or other dated regulatory actions.",
            ("regulator release", "SEC 8-K", "government award"),
            ("company news", "industry publication"),
            common_fields,
            "Count only actions that plausibly change addressable market, timing, cost, or eligibility.",
        ),
        _requirement(
            "theme_industry_transmission",
            "Theme and industry transmission",
            "Industry-chain position plus source-backed transmission into company economics.",
            ("company filings", "customer capex", "competitor earnings"),
            ("industry data", "theme news"),
            common_fields,
            "A theme mention is insufficient without orders, customers, capacity, guidance, revenue, or margins.",
        ),
        _requirement(
            "expectation_gap",
            "Expectation gap",
            "As-of consensus, guidance, valuation, disagreement, and market-implied expectations.",
            ("analyst estimates", "management guidance", "price history"),
            ("earnings surprise", "valuation snapshot"),
            common_fields,
            "Separate confidence in a fact from whether the market already priced that fact.",
        ),
        _requirement(
            "contrary_risk",
            "Contrary and disconfirming evidence",
            "The strongest listing, dilution, regulatory, execution, customer, valuation, or financing risk.",
            ("SEC risk factors", "exchange notice", "financial statements"),
            ("news", "transcript"),
            common_fields,
            "Preserve the strongest source-backed reason the positive setup may fail.",
        ),
        _requirement(
            "fundamentals",
            "Compressed fundamentals",
            "Revenue, margin, cash flow, leverage, guidance, and operating leverage.",
            ("SEC XBRL", "10-Q/10-K", "earnings release"),
            ("vendor financials",),
            common_fields,
            "Keep values point-in-time, unit-normalized, and compact; do not paste raw tables.",
        ),
        _requirement(
            "market_confirmation",
            "Market confirmation",
            "Price, volume, liquidity, relative strength, and tradability as-of the packet date.",
            ("daily price/volume", "exchange status"),
            ("sector benchmark",),
            common_fields,
            "Use market behavior as confirmation or caution, not as a substitute for company evidence.",
        ),
        _requirement(
            "other_or_unclassified",
            "Other or unclassified evidence",
            "Source-backed facts that do not fit the current ontology and may propose a new family.",
            ("all point-in-time sources",),
            (),
            common_fields,
            "Preserve the fact and source span without forcing it into the nearest existing category.",
        ),
    )


def extract_atomic_evidence_by_case(
    cases: Iterable[HistoricalCase],
    documents_by_symbol: Mapping[str, Iterable[DocumentRecord]] | None = None,
) -> dict[str, tuple[AtomicEvidence, ...]]:
    """Extract conservative source-linked atomic facts without reading labels."""

    result: dict[str, tuple[AtomicEvidence, ...]] = {}
    for case in cases:
        facts: list[AtomicEvidence] = []
        symbol = case.packet.company.ticker.symbol.upper()
        available_documents = tuple(
            document
            for document in (documents_by_symbol or {}).get(symbol, ())
            if document.available_as_of(case.packet.as_of.as_of_date)
        )
        full_document_source_ids = {document.source_id for document in available_documents}
        for evidence in case.packet.evidence:
            if evidence.source_id and (
                evidence.source_id.endswith(":fact-digest")
                or evidence.source_id in full_document_source_ids
            ):
                continue
            if (
                evidence.kind is EvidenceKind.NEWS
                and (evidence.source_id or "").startswith("alpha_vantage:")
                and not _source_text_mentions_issuer(case, evidence.summary)
            ):
                continue
            facts.extend(_facts_from_evidence(case, evidence))
        facts.extend(_facts_from_features(case))
        facts.extend(_facts_from_catalysts(case))
        for document in available_documents:
            facts.extend(_facts_from_document(case, document))
        source_facts = _dedupe_facts(facts)
        result[case.case_id] = _dedupe_facts(
            source_facts + _derived_atomic_evidence(case, source_facts)
        )
    return result


def audit_point_in_time_documents(
    cases: Iterable[HistoricalCase],
    documents_by_symbol: Mapping[str, Iterable[DocumentRecord]] | None,
) -> tuple[DocumentContentAudit, ...]:
    """Audit the source bodies actually available to each case as of its cutoff."""

    audits: list[DocumentContentAudit] = []
    for case in cases:
        symbol = case.packet.company.ticker.symbol.upper()
        for document in (documents_by_symbol or {}).get(symbol, ()):
            if not document.available_as_of(case.packet.as_of.as_of_date):
                continue
            normalized = _clean_source_text(document.text)
            state, reasons = _document_content_state(document, normalized)
            audits.append(
                DocumentContentAudit(
                    source_case_id=case.case_id,
                    source_id=document.source_id,
                    source_kind=document.kind.value,
                    content_scope=document.content_scope.value,
                    state=state,
                    content_chars=len(document.text),
                    normalized_content_chars=len(normalized),
                    content_sha256=hashlib.sha256(document.text.encode("utf-8")).hexdigest(),
                    reasons=reasons,
                )
            )
    return tuple(audits)


def document_content_readiness(
    prepared: PreparedInformationPlanExperiment,
) -> dict[str, Any]:
    """Return the source-body readiness gate for blind holdout calls."""

    holdout_ids = set(prepared.holdout_case_ids)
    audits = tuple(
        audit
        for audit in prepared.document_content_audits
        if audit.source_case_id in holdout_ids
    )
    audits_by_case: dict[str, list[DocumentContentAudit]] = {}
    for audit in audits:
        audits_by_case.setdefault(audit.source_case_id, []).append(audit)
    acceptable_states = {DocumentContentState.USABLE, DocumentContentState.SUMMARY_ONLY}
    cases_without_usable_sources = tuple(
        case_id
        for case_id in prepared.holdout_case_ids
        if not any(
            audit.state in acceptable_states
            for audit in audits_by_case.get(case_id, ())
        )
    )
    target_fact_source_ids = {
        fact.source_id
        for case_id in prepared.holdout_case_ids
        for fact in prepared.atomic_evidence_by_case.get(case_id, ())
        if fact.family in TARGET_INFORMATION_FAMILIES
        and fact.source_kind not in {"structured_feature", "structured_catalyst", "derived"}
    }
    critical_source_issues = tuple(
        {
            "source_case_id": audit.source_case_id,
            "source_id": audit.source_id,
            "state": audit.state.value,
        }
        for audit in audits
        if audit.source_id in target_fact_source_ids
        and audit.state not in acceptable_states
    )
    filing_required_families = {"deal_status_timing", "capital_structure_liquidity"}
    filing_body_issues: list[dict[str, str]] = []
    for case_id in prepared.holdout_case_ids:
        present_families = {
            fact.family
            for fact in prepared.atomic_evidence_by_case.get(case_id, ())
            if fact.family in filing_required_families
        }
        if not present_families:
            continue
        case_audits = audits_by_case.get(case_id, ())
        has_usable_filing = any(
            audit.source_kind == EvidenceKind.FILING.value
            and audit.state is DocumentContentState.USABLE
            for audit in case_audits
        )
        if not has_usable_filing:
            filing_body_issues.append(
                {
                    "source_case_id": case_id,
                    "state": "missing_usable_filing_body",
                    "families": ",".join(sorted(present_families)),
                }
            )
    all_critical_issues = critical_source_issues + tuple(filing_body_issues)
    state_counts = {
        state.value: sum(audit.state is state for audit in audits)
        for state in DocumentContentState
    }
    return {
        "passed": not cases_without_usable_sources and not all_critical_issues,
        "holdout_case_count": len(prepared.holdout_case_ids),
        "audited_document_count": len(audits),
        "state_counts": state_counts,
        "cases_without_usable_sources": list(cases_without_usable_sources),
        "critical_target_fact_source_issues": list(all_critical_issues),
        "policy": (
            "Each holdout case needs at least one usable or explicitly summary-only "
            "point-in-time source; target-family facts cannot depend on truncated, "
            "metadata-only, or unusable bodies; and deal/capital evidence requires at "
            "least one usable filing body for the case."
        ),
    }


def point_in_time_source_document_records(
    prepared: PreparedInformationPlanExperiment,
) -> list[dict[str, Any]]:
    """Return deduplicated full source records for retrospective audit only."""

    records: dict[tuple[str, str], dict[str, Any]] = {}
    for case_id, documents in prepared.source_documents_by_case.items():
        for document in documents:
            content_sha256 = hashlib.sha256(document.text.encode("utf-8")).hexdigest()
            key = (document.source_id, content_sha256)
            record = records.setdefault(
                key,
                {
                    "document_id": document.document_id,
                    "symbol": document.symbol,
                    "kind": document.kind.value,
                    "title": document.title,
                    "text": document.text,
                    "source_id": document.source_id,
                    "source_url": document.source_url,
                    "published_date": document.published_date.isoformat(),
                    "available_date": (
                        document.available_date.isoformat()
                        if document.available_date
                        else None
                    ),
                    "retrieved_at": document.retrieved_at.isoformat(),
                    "content_scope": document.content_scope.value,
                    "content_sha256": content_sha256,
                    "available_to_case_ids": [],
                },
            )
            record["available_to_case_ids"].append(case_id)
    result = list(records.values())
    for record in result:
        record["available_to_case_ids"] = sorted(set(record["available_to_case_ids"]))
    return sorted(result, key=lambda item: (item["symbol"], item["published_date"], item["source_id"]))


def discover_research_information_plan(
    discovery_cases: Iterable[HistoricalCase],
    *,
    packet_scheme_version: str,
    plan_version: str = INFORMATION_PLAN_SCHEMA_VERSION,
    documents_by_symbol: Mapping[str, Iterable[DocumentRecord]] | None = None,
) -> ResearchInformationPlan:
    """Build a label-aware requirement proposal from refinement cases only."""

    case_list = tuple(discovery_cases)
    if not case_list:
        raise ValidationError("information-plan discovery requires refinement cases")
    facts_by_case = extract_atomic_evidence_by_case(case_list, documents_by_symbol)
    requirements = default_information_requirements()
    diagnostics = tuple(
        _requirement_diagnostic(requirement, case_list, facts_by_case)
        for requirement in requirements
    )
    symbols = {case.packet.company.ticker.symbol for case in case_list}
    return ResearchInformationPlan(
        plan_id="ralph-research-information-plan",
        version=plan_version,
        requirements=requirements,
        diagnostics=diagnostics,
        packet_scheme_version=packet_scheme_version,
        discovery_case_count=len(case_list),
        discovery_symbol_count=len(symbols),
    )


def build_requirement_coverage_ledger(
    cases: Iterable[HistoricalCase],
    requirements: Iterable[InformationRequirement],
    atomic_evidence_by_case: Mapping[str, tuple[AtomicEvidence, ...]],
    documents_by_symbol: Mapping[str, Iterable[DocumentRecord]] | None = None,
) -> tuple[RequirementCoverageEntry, ...]:
    """Assess requirement-level coverage without treating keywords as facts."""

    entries: list[RequirementCoverageEntry] = []
    for case in cases:
        facts = atomic_evidence_by_case.get(case.case_id, ())
        symbol = case.packet.company.ticker.symbol.upper()
        available_documents = tuple(
            document
            for document in (documents_by_symbol or {}).get(symbol, ())
            if document.available_as_of(case.packet.as_of.as_of_date)
        )
        for requirement in requirements:
            family_facts = tuple(fact for fact in facts if fact.family == requirement.family)
            state, reason = _coverage_state(
                case,
                requirement.family,
                family_facts,
                available_documents,
            )
            entries.append(
                RequirementCoverageEntry(
                    source_case_id=case.case_id,
                    requirement_id=requirement.requirement_id,
                    family=requirement.family,
                    state=state,
                    fact_ids=tuple(fact.fact_id for fact in family_facts),
                    source_ids=tuple(sorted({fact.source_id for fact in family_facts})),
                    reason=reason,
                )
            )
    return tuple(entries)


def prepare_information_plan_experiment(
    discovery_cases: Iterable[HistoricalCase],
    holdout_cases: Iterable[HistoricalCase],
    *,
    active_scheme: InformationScheme,
    run_id: str,
    context_budget: int = 4500,
    families: Iterable[str] = TARGET_INFORMATION_FAMILIES,
    documents_by_symbol: Mapping[str, Iterable[DocumentRecord]] | None = None,
) -> PreparedInformationPlanExperiment:
    """Prepare fair raw/organized and source-backed family packet variants."""

    discovery = tuple(discovery_cases)
    holdout = tuple(holdout_cases)
    if not discovery or not holdout:
        raise ValidationError("information-plan experiment requires discovery and holdout cases")
    discovery_symbols = {case.packet.company.ticker.symbol for case in discovery}
    holdout_symbols = {case.packet.company.ticker.symbol for case in holdout}
    if discovery_symbols & holdout_symbols:
        raise ValidationError("information-plan discovery and holdout symbols must be disjoint")
    comparison_scheme = _scheme_for_context_budget(active_scheme, context_budget)
    plan = discover_research_information_plan(
        discovery,
        packet_scheme_version=comparison_scheme.version,
        documents_by_symbol=documents_by_symbol,
    )
    all_cases = discovery + holdout
    facts_by_case = extract_atomic_evidence_by_case(all_cases, documents_by_symbol)
    coverage = build_requirement_coverage_ledger(
        all_cases,
        plan.requirements,
        facts_by_case,
        documents_by_symbol,
    )
    source_pool_by_case = _source_pool_by_case(all_cases, documents_by_symbol)
    source_documents_by_case = _source_documents_by_case(all_cases, documents_by_symbol)
    source_identity_tokens_by_case = {
        case_id: point_in_time_document_identity_tokens(documents)
        for case_id, documents in source_documents_by_case.items()
    }
    document_content_audits = audit_point_in_time_documents(all_cases, documents_by_symbol)
    raw_packets = tuple(
        build_raw_source_blind_packet(
            case,
            anonymous_case_id=f"holdout_{index:03d}",
            context_budget=context_budget,
            documents=(documents_by_symbol or {}).get(
                case.packet.company.ticker.symbol.upper(),
                (),
            ),
        )
        for index, case in enumerate(holdout, start=1)
    )
    organized_packets = tuple(
        build_organized_atomic_blind_packet(
            case,
            comparison_scheme,
            facts_by_case[case.case_id],
            coverage,
            anonymous_case_id=f"holdout_{index:03d}",
            source_identity_tokens=source_identity_tokens_by_case.get(case.case_id, ()),
        )
        for index, case in enumerate(holdout, start=1)
    )
    core_families = _family_add_back_core_families()
    family_add_back_baseline_packets = tuple(
        build_organized_atomic_blind_packet(
            case,
            comparison_scheme,
            facts_by_case[case.case_id],
            coverage,
            anonymous_case_id=f"holdout_{index:03d}",
            include_families=core_families,
            source_identity_tokens=source_identity_tokens_by_case.get(case.case_id, ()),
        )
        for index, case in enumerate(holdout, start=1)
    )
    selected_families = tuple(dict.fromkeys(families))
    family_experiments = tuple(
        _prepare_family_experiment(
            family,
            holdout,
            comparison_scheme,
            facts_by_case,
            coverage,
            source_identity_tokens_by_case,
        )
        for family in selected_families
    )
    return PreparedInformationPlanExperiment(
        run_id=run_id,
        plan=plan,
        active_scheme=comparison_scheme,
        holdout_case_ids=tuple(case.case_id for case in holdout),
        atomic_evidence_by_case=facts_by_case,
        coverage_entries=coverage,
        source_pool_by_case=source_pool_by_case,
        source_documents_by_case=source_documents_by_case,
        document_content_audits=document_content_audits,
        raw_packets=raw_packets,
        organized_packets=organized_packets,
        family_add_back_baseline_packets=family_add_back_baseline_packets,
        family_experiments=family_experiments,
        context_budget=context_budget,
    )


def evaluate_information_plan_experiment(
    prepared: PreparedInformationPlanExperiment,
    holdout_cases: Iterable[HistoricalCase],
    *,
    blind_researcher: RalphBlindResearcher,
    family_experiment_mode: str = "packets_only",
    evaluation_method: str = "unspecified",
    validation_role: str = "development_diagnostic",
) -> InformationPlanExperimentResult:
    """Run blind raw/organized comparison and optional family variants."""

    holdout = tuple(holdout_cases)
    if tuple(case.case_id for case in holdout) != prepared.holdout_case_ids:
        raise ValidationError("holdout case order does not match prepared information-plan packets")
    if family_experiment_mode not in {"packets_only", "ablation", "add_back", "both"}:
        raise ValidationError("unsupported family_experiment_mode")
    if evaluation_method not in {"plain_llm", "heuristic", "unspecified"}:
        raise ValidationError("unsupported information-plan evaluation_method")
    if validation_role not in {"development_diagnostic", "untouched_company_holdout"}:
        raise ValidationError("unsupported information-plan validation_role")
    raw_analyses = tuple(blind_researcher.analyze(packet) for packet in prepared.raw_packets)
    organized_analyses = tuple(
        blind_researcher.analyze(packet) for packet in prepared.organized_packets
    )
    raw_evaluation = evaluate_scheme_performance(
        holdout,
        raw_analyses,
        scheme_version=RAW_PACKET_SCHEME_ID + ":holdout",
    )
    organized_evaluation = evaluate_scheme_performance(
        holdout,
        organized_analyses,
        scheme_version=prepared.active_scheme.version + ":atomic_organized_holdout",
    )
    add_back_baseline_evaluation = None
    if family_experiment_mode in {"add_back", "both"}:
        add_back_baseline_analyses = tuple(
            blind_researcher.analyze(packet)
            for packet in prepared.family_add_back_baseline_packets
        )
        add_back_baseline_evaluation = evaluate_scheme_performance(
            holdout,
            add_back_baseline_analyses,
            scheme_version="information-family:core-baseline",
        )
    family_evaluations = tuple(
        _evaluate_family_experiment(
            experiment,
            holdout,
            blind_researcher,
            mode=family_experiment_mode,
            add_back_baseline_evaluation=add_back_baseline_evaluation,
            organized_baseline_evaluation=organized_evaluation,
        )
        for experiment in prepared.family_experiments
    )
    attributions = attribute_information_plan_failures(
        holdout,
        prepared,
        raw_analyses,
        organized_analyses,
    )
    return InformationPlanExperimentResult(
        prepared=prepared,
        raw_analyses=raw_analyses,
        organized_analyses=organized_analyses,
        raw_evaluation=raw_evaluation,
        organized_evaluation=organized_evaluation,
        family_evaluations=family_evaluations,
        failure_attributions=attributions,
        evaluation_method=evaluation_method,
        validation_role=validation_role,
    )


def build_raw_source_blind_packet(
    case: HistoricalCase,
    *,
    anonymous_case_id: str,
    context_budget: int,
    documents: Iterable[DocumentRecord] = (),
) -> BlindSchemePacket:
    """Render minimally processed source and feature context under a fixed budget."""

    if context_budget < 100:
        raise ValidationError("raw-source context budget must be at least 100 tokens")
    packet = case.packet
    source_items = []
    document_list = tuple(
        item
        for item in documents
        if item.available_as_of(packet.as_of.as_of_date)
    )
    extra_identity_tokens = _document_identity_tokens(document_list)
    document_source_ids: set[str] = set()
    chunk_records: list[list[dict[str, Any]]] = []
    for document in sorted(
        document_list,
        key=lambda item: (item.published_date, item.source_id),
        reverse=True,
    ):
        document_source_ids.add(document.source_id)
        records: list[dict[str, Any]] = []
        for chunk_index, chunk in enumerate(_raw_document_chunks(document.text), start=1):
            records.append(
                {
                    "item_type": "raw_document_chunk",
                    "evidence_ref": _opaque_ref(case.case_id, document.source_id),
                    "chunk_index": chunk_index,
                    "source_kind": document.kind.value,
                    "published_date": document.published_date.isoformat(),
                    "data_quality": "confirmed",
                    "summary": f"{document.title}. {chunk}" if chunk_index == 1 else chunk,
                }
            )
        chunk_records.append(records)
    for chunk_index in range(max((len(records) for records in chunk_records), default=0)):
        for records in chunk_records:
            if chunk_index < len(records):
                source_items.append(records[chunk_index])
    for evidence in sorted(
        packet.evidence,
        key=lambda item: (item.published_date or item.as_of_date, item.kind.value),
        reverse=True,
    ):
        if evidence.source_id in document_source_ids:
            continue
        source_items.append(
            {
                "item_type": "raw_source_excerpt",
                "evidence_ref": _opaque_ref(case.case_id, evidence.source_id or evidence.summary),
                "source_kind": evidence.kind.value,
                "published_date": evidence.published_date.isoformat() if evidence.published_date else None,
                "data_quality": evidence.data_quality.value,
                "summary": evidence.summary,
            }
        )
    for catalyst in packet.catalysts:
        source_items.append(
            {
                "item_type": "raw_catalyst_record",
                "status": catalyst.status.value,
                "expected_date": catalyst.expected_date.isoformat(),
                "summary": catalyst.name,
            }
        )
    feature_items = [
        {
            "item_type": "raw_feature",
            "name": feature.name,
            "value": feature.value,
            "as_of_date": feature.as_of_date.isoformat(),
            "data_quality": feature.data_quality.value,
            "period_end_date": feature.period_end_date.isoformat() if feature.period_end_date else None,
        }
        for feature in packet.features
    ]
    safe_sources = [
        identity_safe_blind_value(
            packet,
            item,
            extra_identity_tokens=extra_identity_tokens,
        )
        for item in source_items
    ]
    safe_features = [identity_safe_blind_value(packet, item) for item in feature_items]
    source_budget = max(1, int(context_budget * 0.82))
    feature_budget = max(1, context_budget - source_budget)
    source_slice = _items_within_budget(safe_sources, source_budget)
    feature_slice = _items_within_budget(safe_features, feature_budget)
    sections = (
        BlindPacketSection(
            name="Raw Source Context",
            priority=1,
            token_budget=source_budget,
            compression_rule="Deterministic date ordering and truncation only; no thematic classification.",
            items=source_slice,
            estimated_tokens=_estimated_tokens(source_slice),
        ),
        BlindPacketSection(
            name="Raw Structured Context",
            priority=2,
            token_budget=feature_budget,
            compression_rule="Deterministic feature serialization without signal interpretation.",
            items=feature_slice,
            estimated_tokens=_estimated_tokens(feature_slice),
        ),
    )
    return BlindSchemePacket(
        source_case_id=case.case_id,
        anonymous_case_id=anonymous_case_id,
        as_of_date=packet.as_of.as_of_date.isoformat(),
        scheme_id=RAW_PACKET_SCHEME_ID,
        scheme_version=RAW_PACKET_SCHEME_ID + "-v0.1",
        sections=sections,
    )


def build_organized_atomic_blind_packet(
    case: HistoricalCase,
    scheme: InformationScheme,
    facts: Iterable[AtomicEvidence],
    coverage_entries: Iterable[RequirementCoverageEntry],
    *,
    anonymous_case_id: str,
    include_families: set[str] | None = None,
    exclude_families: set[str] | None = None,
    source_identity_tokens: Iterable[str] = (),
) -> BlindSchemePacket:
    """Render source-linked atomic facts once into their owning packet sections."""

    packet = case.packet
    include = include_families
    exclude = exclude_families or set()
    selected_facts = _dedupe_semantic_facts_for_packet(
        fact
        for fact in facts
        if (include is None or fact.family in include)
        and fact.family not in exclude
        and fact.family != "other_or_unclassified"
    )
    extra_identity_tokens = tuple(
        set(source_identity_tokens)
        | set(
            _document_identity_tokens_from_text(
                " ".join(fact.source_span for fact in selected_facts)
            )
        )
    )
    coverage_by_family = {
        entry.family: entry
        for entry in coverage_entries
        if entry.source_case_id == case.case_id
    }
    facts_by_section: dict[str, list[AtomicEvidence]] = {}
    for fact in selected_facts:
        facts_by_section.setdefault(_section_for_fact(fact), []).append(fact)
    sections: list[BlindPacketSection] = []
    for section in sorted(scheme.sections, key=lambda item: item.priority):
        section_facts = _balanced_atomic_facts(
            facts_by_section.get(section.name, ()),
            section.max_items,
        )
        items = [
            identity_safe_blind_value(
                packet,
                _atomic_blind_item(fact),
                extra_identity_tokens=extra_identity_tokens,
            )
            for fact in section_facts
        ]
        if not items:
            families = _families_for_section(section.name)
            missing = [
                coverage_by_family[family]
                for family in families
                if family in coverage_by_family
                and coverage_by_family[family].state is not RequirementCoverageState.CONFIRMED
            ]
            items = [
                {
                    "item_type": "requirement_coverage",
                    "family": entry.family,
                    "state": entry.state.value,
                    "summary": entry.reason,
                }
                for entry in missing[: section.max_items]
            ]
        safe_items = _items_within_budget(items, section.token_budget)
        sections.append(
            BlindPacketSection(
                name=section.name,
                priority=section.priority,
                token_budget=section.token_budget,
                compression_rule=section.compression_rule,
                items=safe_items,
                estimated_tokens=_estimated_tokens(safe_items),
            )
        )
    return BlindSchemePacket(
        source_case_id=case.case_id,
        anonymous_case_id=anonymous_case_id,
        as_of_date=packet.as_of.as_of_date.isoformat(),
        scheme_id=scheme.scheme_id,
        scheme_version=scheme.version + ":atomic_organized",
        sections=tuple(sections),
    )


def attribute_information_plan_failures(
    holdout_cases: Iterable[HistoricalCase],
    prepared: PreparedInformationPlanExperiment,
    raw_analyses: Iterable[RalphBlindAnalysis],
    organized_analyses: Iterable[RalphBlindAnalysis],
) -> tuple[FailureAttribution, ...]:
    """Route failed blind judgments to the most evidence-supported intervention layer."""

    raw_by_case = {analysis.source_case_id: analysis for analysis in raw_analyses}
    organized_by_case = {analysis.source_case_id: analysis for analysis in organized_analyses}
    audits_by_case: dict[str, list[DocumentContentAudit]] = {}
    for audit in prepared.document_content_audits:
        audits_by_case.setdefault(audit.source_case_id, []).append(audit)
    coverage_by_case: dict[str, list[RequirementCoverageEntry]] = {}
    for entry in prepared.coverage_entries:
        coverage_by_case.setdefault(entry.source_case_id, []).append(entry)
    attributions: list[FailureAttribution] = []
    for case in holdout_cases:
        organized = organized_by_case[case.case_id]
        if not _blind_judgment_is_error(case, organized):
            continue
        raw = raw_by_case[case.case_id]
        coverage = coverage_by_case.get(case.case_id, [])
        reasons = [organized.surge_candidate_reason] + list(organized.missing_context)
        relevant_families = _families_from_missing_context(reasons)
        relevant_coverage = [
            entry
            for entry in coverage
            if not relevant_families or entry.family in relevant_families
        ]
        states = {entry.state for entry in relevant_coverage}
        case_audits = audits_by_case.get(case.case_id, [])
        usable_source_states = {DocumentContentState.USABLE, DocumentContentState.SUMMARY_ONLY}
        source_content_failed = bool(case_audits) and not any(
            audit.state in usable_source_states for audit in case_audits
        )
        secondary: list[FailureLayer] = []
        if source_content_failed:
            primary = FailureLayer.ACQUISITION_MISS
            intervention = "Fetch complete point-in-time source bodies before changing extraction or analysis."
            reasons.append("Archived source bodies are truncated, metadata-only, or unusable.")
        elif RequirementCoverageState.SOURCE_UNAVAILABLE in states:
            primary = FailureLayer.SOURCE_UNAVAILABLE
            intervention = "Document the unsupported source capability and test a targeted source proposal."
        elif RequirementCoverageState.NOT_FETCHED in states:
            primary = FailureLayer.ACQUISITION_MISS
            intervention = "Run requirement-driven retrieval from existing preferred or fallback sources."
        elif states & {
            RequirementCoverageState.EXTRACTION_FAILED,
            RequirementCoverageState.AMBIGUOUS,
        }:
            primary = FailureLayer.EXTRACTION_ERROR
            intervention = "Repair sentence-scoped entity, status, amount, unit, or negation extraction."
        elif not _blind_judgment_is_error(case, raw):
            primary = FailureLayer.REPRESENTATION_LOSS
            intervention = "Restore the raw fact omitted or distorted by the organized packet."
        elif any(
            fact.family in TARGET_INFORMATION_FAMILIES
            for fact in prepared.atomic_evidence_by_case.get(case.case_id, ())
        ):
            primary = FailureLayer.ANALYSIS_ERROR
            intervention = "Keep the information plan fixed and test the analysis method separately."
        else:
            primary = FailureLayer.NOT_PREDICTABLY_SUPPORTED_AS_OF
            intervention = "Mark the outcome as unsupported by available as-of evidence."
        if RequirementCoverageState.EXTRACTION_FAILED in states and primary is not FailureLayer.EXTRACTION_ERROR:
            secondary.append(FailureLayer.EXTRACTION_ERROR)
        if _blind_judgment_is_error(case, raw) != _blind_judgment_is_error(case, organized):
            secondary.append(FailureLayer.REPRESENTATION_LOSS)
        attributions.append(
            FailureAttribution(
                source_case_id=case.case_id,
                primary_layer=primary,
                secondary_layers=tuple(dict.fromkeys(secondary)),
                reasons=tuple(reason for reason in reasons if reason),
                proposed_intervention=intervention,
            )
        )
    return tuple(attributions)


def write_information_plan_experiment_artifacts(
    result: InformationPlanExperimentResult,
    output_dir: str | Path,
    *,
    created_at: datetime,
    leakage_report: Mapping[str, Any] | None = None,
    extra_output_paths: Mapping[str, str | Path] | None = None,
) -> dict[str, Path]:
    """Write the broad information-plan artifacts and standard Ralph handles."""

    base_dir = Path(output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "research_information_plan": base_dir / "research_information_plan.json",
        "information_requirements": base_dir / "information_requirements.json",
        "evidence_coverage_ledger": base_dir / "evidence_coverage_ledger.json",
        "atomic_evidence_by_case": base_dir / "atomic_evidence_by_case.json",
        "point_in_time_source_documents": base_dir / "point_in_time_source_documents.json",
        "document_content_audit": base_dir / "document_content_audit.json",
        "raw_source_blind_packets": base_dir / "raw_source_blind_packets.json",
        "raw_vs_organized_evaluation": base_dir / "raw_vs_organized_evaluation.json",
        "information_family_experiments": base_dir / "information_family_experiments.json",
        "layered_failure_attribution": base_dir / "layered_failure_attribution.json",
        "information_scheme": base_dir / "information_scheme.json",
        "holdout_blind_packets_by_scheme": base_dir / "holdout_blind_packets_by_scheme.json",
        "holdout_blind_scheme_evaluation": base_dir / "holdout_blind_scheme_evaluation.json",
        "holdout_error_analysis": base_dir / "holdout_error_analysis.json",
        "ralph_experiment_summary": base_dir / "ralph_experiment_summary.json",
        "manifest": base_dir / "manifest.json",
    }
    if leakage_report is not None:
        paths["preflight_leakage_report"] = base_dir / "preflight_leakage_report.json"
    if extra_output_paths:
        paths.update({name: Path(path) for name, path in extra_output_paths.items()})
    prepared = result.prepared
    _write_json(paths["research_information_plan"], prepared.plan.to_dict())
    _write_json(
        paths["information_requirements"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "stage_boundary": "retrospective_label_aware_refinement",
            "requirements": [item.to_dict() for item in prepared.plan.requirements],
            "diagnostics": [item.to_dict() for item in prepared.plan.diagnostics],
        },
    )
    _write_json(
        paths["evidence_coverage_ledger"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
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
            "run_id": prepared.run_id,
            "stage_boundary": "retrospective_label_aware_audit",
            "atomic_evidence_by_case": {
                case_id: [fact.to_dict() for fact in facts]
                for case_id, facts in sorted(prepared.atomic_evidence_by_case.items())
            },
        },
    )
    content_readiness = document_content_readiness(prepared)
    _write_json(
        paths["point_in_time_source_documents"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "stage_boundary": "retrospective_label_aware_raw_source_audit",
            "documents": point_in_time_source_document_records(prepared),
        },
    )
    _write_json(
        paths["document_content_audit"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "stage_boundary": "retrospective_label_aware_raw_source_audit",
            "readiness": content_readiness,
            "audits": [audit.to_dict() for audit in prepared.document_content_audits],
        },
    )
    _write_json(
        paths["raw_source_blind_packets"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "stage_boundary": "anonymous_no_web_blind",
            "context_budget": prepared.context_budget,
            "packets": [packet.to_dict() for packet in prepared.raw_packets],
            "analyses": [analysis.to_dict() for analysis in result.raw_analyses],
        },
    )
    _write_json(paths["raw_vs_organized_evaluation"], result.comparison_dict())
    if leakage_report is not None:
        _write_json(paths["preflight_leakage_report"], dict(leakage_report))
    _write_json(
        paths["information_family_experiments"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "stage_boundary": "retrospective_label_aware_holdout_experiment",
            "experiments": [item.to_dict() for item in result.family_evaluations],
        },
    )
    _write_json(
        paths["layered_failure_attribution"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "stage_boundary": "retrospective_label_aware_error_attribution",
            "attributions": [item.to_dict() for item in result.failure_attributions],
        },
    )
    _write_json(
        paths["information_scheme"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "stage_boundary": "retrospective_label_aware_refinement",
            "active_scheme": prepared.active_scheme.to_dict(),
            "research_information_plan": prepared.plan.to_dict(),
            "promotion_status": "pending_human_review",
        },
    )
    _write_json(
        paths["holdout_blind_packets_by_scheme"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "stage_boundary": "anonymous_no_web_blind",
            "organized_packets": [packet.to_dict() for packet in prepared.organized_packets],
            "organized_analyses": [analysis.to_dict() for analysis in result.organized_analyses],
        },
    )
    _write_json(
        paths["holdout_blind_scheme_evaluation"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "stage_boundary": "retrospective_label_aware_holdout",
            "evaluation": result.organized_evaluation.to_dict(),
        },
    )
    _write_json(
        paths["holdout_error_analysis"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "stage_boundary": "retrospective_label_aware_holdout",
            "layered_failure_attribution": [item.to_dict() for item in result.failure_attributions],
        },
    )
    effectiveness_claim_allowed = (
        result.evaluation_method == "plain_llm"
        and result.validation_role == "untouched_company_holdout"
    )
    summary = {
        "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
        "run_id": prepared.run_id,
        "final_status": (
            "information_plan_holdout_separated"
            if effectiveness_claim_allowed and result.organized_evaluation.separation_passed
            else "information_plan_not_separated"
            if effectiveness_claim_allowed
            else "pipeline_diagnostic_only"
        ),
        "raw_vs_organized": result.comparison_dict(),
        "failure_layer_counts": _failure_layer_counts(result.failure_attributions),
        "promotion_status": "pending_human_review",
        "can_enter_multi_agent_phase": False,
        "gold_packet_available": False,
        "evaluation_method": result.evaluation_method,
        "validation_role": result.validation_role,
        "effectiveness_claim_allowed": effectiveness_claim_allowed,
        "document_content_readiness": content_readiness,
    }
    _write_json(paths["ralph_experiment_summary"], summary)
    _write_json(
        paths["manifest"],
        {
            "schema_version": INFORMATION_PLAN_SCHEMA_VERSION,
            "run_id": prepared.run_id,
            "created_at": created_at.isoformat(),
            "pipeline": "ralph_information_plan_experiment",
            "stage_boundary": "retrospective_refinement_then_anonymous_holdout",
            "holdout_case_count": len(prepared.holdout_case_ids),
            "packet_scheme_version": prepared.active_scheme.version,
            "raw_positive_confidence_gap": result.raw_evaluation.positive_confidence_gap,
            "organized_positive_confidence_gap": result.organized_evaluation.positive_confidence_gap,
            "organized_false_positive_rate": result.organized_evaluation.false_positive_rate,
            "organized_false_negative_rate": result.organized_evaluation.false_negative_rate,
            "leakage_passed": leakage_report.get("passed") if leakage_report else None,
            "family_experiment_count": len(result.family_evaluations),
            "evaluation_method": result.evaluation_method,
            "validation_role": result.validation_role,
            "effectiveness_claim_allowed": effectiveness_claim_allowed,
            "document_content_ready": content_readiness["passed"],
            "promotion_status": "pending_human_review",
            "can_enter_multi_agent_phase": False,
            "outputs": {name: str(path) for name, path in sorted(paths.items())},
        },
    )
    return paths


def _requirement(
    family: str,
    title: str,
    description: str,
    preferred_sources: tuple[str, ...],
    fallback_sources: tuple[str, ...],
    extraction_fields: tuple[str, ...],
    rubric: str,
) -> InformationRequirement:
    return InformationRequirement(
        requirement_id=f"information-requirement:{family}",
        family=family,
        title=title,
        description=description,
        preferred_sources=preferred_sources,
        fallback_sources=fallback_sources,
        extraction_fields=extraction_fields,
        analysis_rubric=rubric,
    )


def _scheme_for_context_budget(
    scheme: InformationScheme,
    context_budget: int,
) -> InformationScheme:
    if context_budget < 100:
        raise ValidationError("information-plan context budget must be at least 100 tokens")
    if scheme.total_token_budget == context_budget:
        return scheme
    source_total = sum(section.token_budget for section in scheme.sections)
    scaled_budgets = [
        max(1, round(section.token_budget * context_budget / source_total))
        for section in scheme.sections
    ]
    scaled_budgets[-1] += context_budget - sum(scaled_budgets)
    sections = tuple(
        replace(section, token_budget=budget)
        for section, budget in zip(scheme.sections, scaled_budgets, strict=True)
    )
    return replace(
        scheme,
        version=f"{scheme.version}:budget-{context_budget}",
        sections=sections,
        total_token_budget=context_budget,
    )


def _facts_from_evidence(case: HistoricalCase, evidence: EvidenceItem) -> list[AtomicEvidence]:
    facts: list[AtomicEvidence] = []
    source_spans = _source_spans(evidence.summary)
    classified_spans = [
        (span, _classify_source_span_all(span))
        for span in source_spans
    ]
    for left, right in zip(source_spans, source_spans[1:]):
        combined = f"{left}; {right}"
        if (
            _theme_transmission_span(combined.lower())
            and not _theme_transmission_span(left.lower())
            and not _theme_transmission_span(right.lower())
        ):
            classified_spans.append(
                (combined, (("theme_industry_transmission", "theme_pull_through"),))
            )

    for span, classifications in classified_spans:
        if not classifications:
            continue
        for family, event_type in classifications:
            if evidence.kind is EvidenceKind.THEME_CONTEXT and family not in {
                "business_identity",
                "theme_industry_transmission",
            }:
                continue
            status, negated = _fact_status(span, family)
            amount, unit = _amount_and_unit(span, family=family)
            period = _period_phrase(span)
            source_id = evidence.source_id or _opaque_ref(
                case.case_id,
                evidence.source_url or evidence.summary,
            )
            facts.append(
                AtomicEvidence(
                    fact_id=_fact_id(case.case_id, source_id, family, event_type, span),
                    source_case_id=case.case_id,
                    requirement_id=f"information-requirement:{family}",
                    family=family,
                    subject_role="issuer",
                    counterparty_role=_counterparty_role(span),
                    event_type=event_type,
                    status=status,
                    statement=_compact(span, 420),
                    source_span=_compact(span, 620),
                    source_id=source_id,
                    source_kind=evidence.kind.value,
                    as_of_date=evidence.as_of_date.isoformat(),
                    published_date=(
                        evidence.published_date.isoformat() if evidence.published_date else None
                    ),
                    event_date=(
                        _event_date_phrase(span)
                        or (evidence.published_date.isoformat() if evidence.published_date else None)
                    ),
                    amount=amount,
                    unit=unit,
                    period=period,
                    negated=negated,
                    confidence=0.95 if status is not AtomicFactStatus.AMBIGUOUS else 0.5,
                )
            )
    return facts


def _facts_from_document(case: HistoricalCase, document: DocumentRecord) -> list[AtomicEvidence]:
    """Extract facts from the full saved point-in-time document, not only packet excerpts."""

    if (
        document.kind is EvidenceKind.NEWS
        and document.source_id.startswith("alpha_vantage:")
        and not _source_text_mentions_issuer(
            case,
            f"{document.title}. {document.text}",
        )
    ):
        return []

    evidence = EvidenceItem(
        kind=document.kind,
        summary=f"{document.title}. {document.text}",
        as_of_date=case.packet.as_of.as_of_date,
        source_id=document.source_id,
        source_url=document.source_url,
        published_date=document.published_date,
        data_quality=DataQuality.CONFIRMED,
    )
    return _facts_from_evidence(case, evidence)


def _source_text_mentions_issuer(case: HistoricalCase, raw_text: str) -> bool:
    symbol = case.packet.company.ticker.symbol
    if re.search(rf"\b{re.escape(symbol)}\b", raw_text):
        return True
    company_name = case.packet.company.ticker.company_name or ""
    aliases: set[str] = set()
    for part in re.split(r"\s*/\s*", company_name):
        alias = re.sub(r"\([^)]*\)", " ", part)
        alias = re.sub(
            r",?\s+(?:Incorporated|Inc|Corporation|Corp|Company|Co|Limited|Ltd|PLC|LLC)\.?$",
            "",
            alias,
            flags=re.IGNORECASE,
        ).strip(" .,:;-")
        if len(alias) >= 4:
            aliases.add(alias.lower())
    lowered = raw_text.lower()
    return any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in aliases)


def _facts_from_features(case: HistoricalCase) -> list[AtomicEvidence]:
    facts: list[AtomicEvidence] = []
    for feature in case.packet.features:
        family = _feature_family(feature.name)
        if family is None or feature.data_quality is DataQuality.MISSING:
            continue
        statement = f"{feature.name} = {feature.value}"
        source_id = feature.source_id or f"feature:{feature.source}:{feature.name}"
        monetary_feature = feature.name in {
            "valuation.market_cap_usd",
            "financial.revenue_ttm",
            "financial.cash_and_equivalents_usd",
            "financial.total_debt_usd",
        }
        amount = (
            float(feature.value)
            if monetary_feature and isinstance(feature.value, (int, float))
            else None
        )
        facts.append(
            AtomicEvidence(
                fact_id=_fact_id(case.case_id, source_id, family, "structured_feature", statement),
                source_case_id=case.case_id,
                requirement_id=f"information-requirement:{family}",
                family=family,
                subject_role="issuer",
                event_type="structured_feature",
                status=AtomicFactStatus.CONFIRMED,
                statement=statement,
                source_span=statement,
                source_id=source_id,
                source_kind="structured_feature",
                as_of_date=feature.as_of_date.isoformat(),
                published_date=None,
                amount=amount,
                unit="USD" if amount is not None else None,
                period=feature.period_end_date.isoformat() if feature.period_end_date else None,
                confidence=1.0,
                extraction_method="structured_feature",
            )
        )
    return facts


def _facts_from_catalysts(case: HistoricalCase) -> list[AtomicEvidence]:
    facts: list[AtomicEvidence] = []
    for catalyst in case.packet.catalysts:
        family = _catalyst_family(catalyst.name)
        source = catalyst.evidence[0]
        source_id = source.source_id or _opaque_ref(case.case_id, catalyst.name)
        statement = f"{catalyst.name}; status={catalyst.status.value}; expected={catalyst.expected_date.isoformat()}"
        facts.append(
            AtomicEvidence(
                fact_id=_fact_id(case.case_id, source_id, family, "catalyst", statement),
                source_case_id=case.case_id,
                requirement_id=f"information-requirement:{family}",
                family=family,
                subject_role="issuer",
                event_type="catalyst",
                status=AtomicFactStatus.EXPECTED,
                statement=statement,
                source_span=source.summary,
                source_id=source_id,
                source_kind=source.kind.value,
                as_of_date=case.packet.as_of.as_of_date.isoformat(),
                published_date=source.published_date.isoformat() if source.published_date else None,
                event_date=catalyst.expected_date.isoformat(),
                confidence=1.0,
                extraction_method="structured_catalyst",
            )
        )
    return facts


def _derived_atomic_evidence(
    case: HistoricalCase,
    facts: tuple[AtomicEvidence, ...],
) -> tuple[AtomicEvidence, ...]:
    """Build auditable comparison features without replacing their source facts."""

    return _materiality_ratio_facts(case, facts) + _expectation_timeline_facts(case, facts)


def _materiality_ratio_facts(
    case: HistoricalCase,
    facts: tuple[AtomicEvidence, ...],
) -> tuple[AtomicEvidence, ...]:
    revenue_fact = _latest_reported_revenue_fact(facts)
    market_cap_fact = next(
        (
            fact
            for fact in facts
            if fact.statement.startswith("valuation.market_cap_usd = ")
            and fact.amount is not None
            and fact.amount > 0
        ),
        None,
    )
    denominators: list[tuple[AtomicEvidence, str, str | None]] = []
    if revenue_fact is not None and revenue_fact.amount is not None:
        denominators.append(
            (revenue_fact, "reported revenue", _revenue_period_label(revenue_fact))
        )
    if market_cap_fact is not None:
        denominators.append((market_cap_fact, "as-of market capitalization", "as-of"))
    if not denominators:
        return ()
    events = tuple(
        fact
        for fact in facts
        if fact.family == "orders_contracts"
        and fact.amount is not None
        and fact.amount > 0
        and fact.unit == "USD"
        and fact.status not in {AtomicFactStatus.CONTRADICTED, AtomicFactStatus.TERMINATED}
        and fact.extraction_method != "deterministic_materiality_ratio"
    )
    derived: list[AtomicEvidence] = []
    for event in events:
        for denominator, denominator_name, denominator_period in denominators:
            if denominator.amount is None:
                continue
            ratio = event.amount / denominator.amount
            ratio_percent = round(ratio * 100, 2)
            if ratio_percent <= 0 or ratio_percent > 10_000:
                continue
            calculation = (
                f"{event.amount:.2f} / {denominator.amount:.2f} * 100 = "
                f"{ratio_percent:.2f}%"
            )
            period_note = denominator_period or "reported period with duration unavailable"
            statement = (
                f"Materiality normalization: the source-reported event amount is "
                f"{ratio_percent:.2f}% of {denominator_name} ({period_note}). Contract "
                f"duration, revenue recognition, and margin are not inferred when absent."
            )
            source_id = f"derived:materiality:{event.fact_id}:{denominator.fact_id}"
            publication_dates = tuple(
                value
                for value in (event.published_date, denominator.published_date)
                if value is not None
            )
            derived.append(
                AtomicEvidence(
                    fact_id=_fact_id(
                        case.case_id,
                        source_id,
                        event.family,
                        "materiality_ratio",
                        statement,
                    ),
                    source_case_id=case.case_id,
                    requirement_id=event.requirement_id,
                    family=event.family,
                    subject_role=event.subject_role,
                    counterparty_role=event.counterparty_role,
                    event_type="materiality_ratio",
                    status=AtomicFactStatus.CONFIRMED,
                    statement=statement,
                    source_span=(
                        f"Event evidence: {event.source_span} Denominator evidence: "
                        f"{denominator.source_span}"
                    ),
                    source_id=source_id,
                    source_kind="derived",
                    as_of_date=case.packet.as_of.as_of_date.isoformat(),
                    published_date=max(publication_dates) if publication_dates else None,
                    event_date=event.event_date,
                    amount=ratio_percent,
                    unit=(
                        "percent_of_market_cap"
                        if denominator_name == "as-of market capitalization"
                        else "percent_of_reported_revenue"
                    ),
                    period=denominator_period,
                    confidence=min(event.confidence, denominator.confidence),
                    extraction_method="deterministic_materiality_ratio",
                    derived_from_fact_ids=(event.fact_id, denominator.fact_id),
                    calculation=calculation,
                )
            )
    return tuple(derived)


def _latest_reported_revenue_fact(
    facts: tuple[AtomicEvidence, ...],
) -> AtomicEvidence | None:
    candidates = []
    for fact in facts:
        text = fact.statement.lower()
        if (
            fact.family != "fundamentals"
            or fact.amount is None
            or fact.amount < 1_000_000
            or fact.unit != "USD"
            or not (
                re.search(r"\b(?:revenue|net sales)\b", text)
                or text.startswith("financial.revenue_ttm = ")
            )
            or any(
                phrase in text
                for phrase in (
                    "revenue requirement",
                    "purchased power",
                    "targeted revenue",
                    "revenue recognition",
                    "revenues are recognized",
                )
            )
        ):
            continue
        period = _revenue_period_label(fact)
        candidates.append((int(period is not None), _fact_date(fact), fact))
    return max(candidates, default=(0, date.min, None), key=lambda item: item[:2])[2]


def _revenue_period_label(fact: AtomicEvidence) -> str | None:
    text = fact.statement.lower()
    if text.startswith("financial.revenue_ttm = "):
        return "ttm"
    if re.search(r"\bq[1-4]\b|\bquarterly\b|\bthree months\b", text):
        return "quarter"
    if "six months" in text:
        return "six months"
    if "nine months" in text:
        return "nine months"
    if re.search(r"\b(?:fiscal year|full year|year ended|annual)\b", text):
        return "year"
    return fact.period


def _expectation_timeline_facts(
    case: HistoricalCase,
    facts: tuple[AtomicEvidence, ...],
) -> tuple[AtomicEvidence, ...]:
    expectation_facts = tuple(
        fact
        for fact in facts
        if fact.family == "expectation_gap" and fact.source_kind != "derived"
    )
    if not expectation_facts:
        return ()
    dated = tuple(sorted(expectation_facts, key=_fact_date))
    first = dated[0]
    latest = dated[-1]
    as_of = case.packet.as_of.as_of_date
    latest_age_days = max(0, (as_of - _fact_date(latest)).days)
    price_returns = []
    for fact in facts:
        if fact.family != "market_confirmation":
            continue
        match = re.fullmatch(r"price\.return_(20|60|120)d = (-?\d+(?:\.\d+)?)", fact.statement)
        if match:
            price_returns.append(f"{match.group(1)}d={float(match.group(2)):.2%}")
    market_context = ", ".join(sorted(price_returns)) or "not available"
    first_observed = first.published_date or first.event_date or first.as_of_date
    latest_observed = latest.published_date or latest.event_date or latest.as_of_date
    statement = (
        f"Expectation timeline: {len(expectation_facts)} source-backed expectation item(s); "
        f"first observed {first_observed}, latest observed "
        f"{latest_observed} ({latest_age_days} days before as-of); "
        f"pre-as-of price returns: {market_context}. This records novelty and market response "
        f"proxies but does not claim the event was unpriced."
    )
    source_id = "derived:expectation-timeline:" + hashlib.sha256(
        "|".join(fact.fact_id for fact in dated).encode("utf-8")
    ).hexdigest()[:16]
    return (
        AtomicEvidence(
            fact_id=_fact_id(
                case.case_id,
                source_id,
                "expectation_gap",
                "expectation_timeline",
                statement,
            ),
            source_case_id=case.case_id,
            requirement_id="information-requirement:expectation_gap",
            family="expectation_gap",
            subject_role="issuer",
            event_type="expectation_timeline",
            status=AtomicFactStatus.CONFIRMED,
            statement=statement,
            source_span=" ".join(fact.source_span for fact in dated),
            source_id=source_id,
            source_kind="derived",
            as_of_date=as_of.isoformat(),
            published_date=latest.published_date,
            event_date=latest.event_date,
            amount=float(latest_age_days),
            unit="days_before_as_of",
            confidence=min(fact.confidence for fact in expectation_facts),
            extraction_method="deterministic_expectation_timeline",
            derived_from_fact_ids=tuple(fact.fact_id for fact in dated),
            calculation="Count and date source-backed expectation facts; append structured pre-as-of returns.",
        ),
    )


def _fact_date(fact: AtomicEvidence) -> date:
    for value in (fact.published_date, fact.event_date, fact.as_of_date):
        if value:
            return date.fromisoformat(value)
    return date.min


def _source_spans(text: str) -> tuple[str, ...]:
    cleaned = _clean_source_text(text)

    pieces = re.split(r"(?<=[.!?])\s+|\s*;\s*|(?=\bItem\s+\d+\.\d+\b)", cleaned)
    return tuple(piece.strip(" .;:") for piece in pieces if len(piece.strip()) >= 12)


def _clean_source_text(text: str) -> str:
    cleaned = html.unescape(text)
    cleaned = re.sub(r"(?is)<!--.*?-->", " ", cleaned)
    cleaned = re.sub(r"(?is)<(script|style|head|ix:header)[^>]*>.*?</\1>", " ", cleaned)
    cleaned = re.sub(r"(?is)<\s*br\s*/?\s*>|</\s*(p|div|tr|li|h[1-6])\s*>", ". ", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    return " ".join(cleaned.split())


def _document_content_state(
    document: DocumentRecord,
    normalized: str,
) -> tuple[DocumentContentState, tuple[str, ...]]:
    reasons: list[str] = []
    text = document.text.strip()
    if document.content_scope is DocumentContentScope.METADATA_ONLY or re.fullmatch(
        r"[A-Z0-9-]+ filed on \d{4}-\d{2}-\d{2}\.?",
        text,
        flags=re.IGNORECASE,
    ):
        return DocumentContentState.METADATA_ONLY, ("Only filing metadata was archived.",)
    summary_like = (
        document.content_scope is DocumentContentScope.SUMMARY_ONLY
        or document.kind
        in {EvidenceKind.NEWS, EvidenceKind.RESEARCH_REPORT, EvidenceKind.THEME_CONTEXT}
    )
    if summary_like:
        if len(normalized) < 40:
            return DocumentContentState.UNUSABLE, ("Summary-only source has too little readable content.",)
        return DocumentContentState.SUMMARY_ONLY, ("Provider exposed a summary rather than a full body.",)
    if text.endswith("..."):
        reasons.append("Archived text ends with an acquisition-layer ellipsis.")
    if document.kind in {EvidenceKind.FILING, EvidenceKind.TRANSCRIPT} and len(text) in range(1400, 1501):
        reasons.append("Body length matches the legacy 1,500-character acquisition cap.")
    if reasons:
        return DocumentContentState.LIKELY_TRUNCATED, tuple(reasons)
    if len(normalized) < 80:
        return DocumentContentState.UNUSABLE, ("Too little readable source content remained after cleaning.",)
    boilerplate_markers = sum(
        marker in text.lower()
        for marker in ("xmlns", "inline xbrl", "xbrli:context", "field: set")
    )
    substantive_markers = sum(
        marker in normalized.lower()
        for marker in (
            "item ",
            "revenue",
            "agreement",
            "business",
            "customer",
            "cash",
            "risk",
        )
    )
    if boilerplate_markers >= 2 and substantive_markers == 0:
        return DocumentContentState.UNUSABLE, ("Inline-XBRL/header material has no substantive body text.",)
    return DocumentContentState.USABLE, ("Readable point-in-time source content is available.",)


def _raw_document_chunks(text: str, *, words_per_chunk: int = 100) -> tuple[str, ...]:
    words = _clean_source_text(text).split()
    return tuple(
        " ".join(words[index : index + words_per_chunk])
        for index in range(0, len(words), words_per_chunk)
        if words[index : index + words_per_chunk]
    )


def point_in_time_document_identity_tokens(
    documents: Iterable[DocumentRecord],
) -> tuple[str, ...]:
    """Return organization aliases and trading symbols that must be masked."""

    tokens: set[str] = set()
    for document in documents:
        tokens.update(
            _document_identity_tokens_from_text(f"{document.title}. {document.text}")
        )
    return tuple(sorted(tokens, key=len, reverse=True))


def _document_identity_tokens(documents: Iterable[DocumentRecord]) -> tuple[str, ...]:
    return point_in_time_document_identity_tokens(documents)


def _document_identity_tokens_from_text(text: str) -> tuple[str, ...]:
    tokens: set[str] = set()
    organization_pattern = (
        r"\b((?:[A-Z][A-Za-z0-9&'-]*\s+){0,6}"
        r"[A-Z][A-Za-z0-9&'-]*(?:,\s*|\s+)"
        r"(?:Incorporated|Inc|Corporation|Corp|Company|Co|Limited|Ltd|PLC|LLC)\.?)"
        r"(?=\s|$|[(/])"
    )
    for match in re.finditer(organization_pattern, text):
        token = " ".join(match.group(1).split()).strip(" .,:;-")
        if _safe_document_identity_token(token):
            variants = _document_company_name_variants(token)
            tokens.update(variants)
            words = re.findall(r"[A-Za-z0-9&'-]+", variants[-1] if variants else token)
            if words and _document_short_alias_is_used(text, words[0]):
                tokens.add(words[0])
    for match in re.finditer(
        r"\b([A-Z][A-Za-z0-9&'-]{2,40})(?:[’']s|\s+(?:CEO|reported|announced|"
        r"distributed|completed|filed|extended|entered|owns|owned|acquired|issued))\b",
        text,
    ):
        token = match.group(1)
        if _safe_document_identity_token(token):
            tokens.add(token)
    for match in re.finditer(
        r"\b(?:NASDAQ|NasdaqCM|NYSE|NYSEAmerican)\s*:\s*([A-Z][A-Z0-9.]{1,5})\b",
        text,
        flags=re.IGNORECASE,
    ):
        tokens.add(match.group(1).upper())
    return tuple(sorted(tokens, key=len, reverse=True))


def _document_company_name_variants(company: str) -> tuple[str, ...]:
    variants = {company}
    without_suffix = re.sub(
        r",?\s+(?:Incorporated|Inc|Corporation|Corp|Company|Co|Limited|Ltd|PLC|LLC)\.?$",
        "",
        company,
        flags=re.IGNORECASE,
    ).strip(" .,:;-")
    if without_suffix:
        variants.add(without_suffix)
    without_holding = re.sub(
        r"\s+Holdings?$",
        "",
        without_suffix,
        flags=re.IGNORECASE,
    ).strip(" .,:;-")
    if without_holding:
        variants.add(without_holding)
    return tuple(
        sorted(
            (variant for variant in variants if _safe_document_identity_token(variant)),
            key=len,
            reverse=True,
        )
    )


def _document_short_alias_is_used(text: str, alias: str) -> bool:
    if len(alias) < 4 or alias.lower() in {
        "bank",
        "city",
        "community",
        "federal",
        "financial",
        "first",
        "national",
        "public",
        "resource",
        "returns",
        "safety",
        "source",
        "stock",
        "the",
        "west",
    }:
        return False
    pattern = (
        rf"\b{re.escape(alias)}(?:[’']s|\s+(?:CEO|reported|announced|distributed|"
        r"completed|filed|extended|entered|owns|owned|acquired|issued))\b"
    )
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _safe_document_identity_token(token: str) -> bool:
    lowered = token.lower()
    blocked = (
        "cash and cash equivalents",
        "emerging growth company",
        "exact name of registrant",
        "initial public offering",
        "public company",
        "smaller reporting company",
        "net cash",
        "special purpose acquisition company",
        "securities and exchange commission",
        "united states",
        "the company",
    )
    blocked_exact = {
        "agreement",
        "american",
        "and",
        "amount",
        "amounts",
        "bank",
        "biden",
        "capital",
        "ceo",
        "city",
        "company",
        "company's",
        "costs",
        "corp",
        "defendants",
        "director",
        "district",
        "electric",
        "energy",
        "entities",
        "foundation",
        "general",
        "generation",
        "irs",
        "notes",
        "our",
        "plaintiff",
        "power",
        "registrant",
        "returns",
        "securities",
        "shares",
        "shareholders",
        "source",
        "state",
        "states",
        "stockholders",
        "that",
        "the",
        "trump",
        "what",
        "york",
    }
    return (
        3 <= len(token) <= 120
        and lowered not in blocked_exact
        and not any(value in lowered for value in blocked)
    )


def _classify_source_span(span: str) -> tuple[str, str] | None:
    text = span.lower()
    if re.search(r"\bitem\s+5\.02\b|\b(?:director|officer)\b.*\b(?:appointed|resigned|departure)\b", text):
        return "other_or_unclassified", "governance_routine"
    if "dropped from nasdaq composite index" in text or "removed from" in text and "index" in text:
        return "contrary_risk", "market_index_membership"
    if _deal_span(text):
        return "deal_status_timing", "strategic_transaction"
    if _orders_span(text):
        return "orders_contracts", "order_or_contract"
    if _customer_capacity_span(text):
        return "customer_capacity", "customer_or_capacity"
    if _capital_span(text):
        return "capital_structure_liquidity", "capital_or_liquidity"
    if _policy_span(text):
        return "policy_regulatory", "policy_or_regulatory"
    if _theme_transmission_span(text):
        return "theme_industry_transmission", "theme_pull_through"
    if _expectation_span(text):
        return "expectation_gap", "expectation_or_guidance"
    if _risk_span(text):
        return "contrary_risk", "contrary_risk"
    if _fundamental_span(text):
        return "fundamentals", "operating_metric"
    if _business_span(text):
        return "business_identity", "business_context"
    return None


def _classify_source_span_all(span: str) -> tuple[tuple[str, str], ...]:
    """Preserve independently supported target-family meanings in one span."""

    primary = _classify_source_span(span)
    if primary and primary[1] in {"governance_routine", "market_index_membership"}:
        return (primary,)

    text = span.lower()
    target_classifiers = (
        (_deal_span, "deal_status_timing", "strategic_transaction"),
        (_orders_span, "orders_contracts", "order_or_contract"),
        (_customer_capacity_span, "customer_capacity", "customer_or_capacity"),
        (_capital_span, "capital_structure_liquidity", "capital_or_liquidity"),
        (_policy_span, "policy_regulatory", "policy_or_regulatory"),
        (_theme_transmission_span, "theme_industry_transmission", "theme_pull_through"),
        (_expectation_span, "expectation_gap", "expectation_or_guidance"),
    )
    classifications = tuple(
        (family, event_type)
        for predicate, family, event_type in target_classifiers
        if predicate(text)
    )
    if classifications:
        supporting = []
        if _fundamental_span(text):
            supporting.append(("fundamentals", "operating_metric"))
        if _business_span(text):
            supporting.append(("business_identity", "business_context"))
        return classifications + tuple(supporting)
    return (primary,) if primary else ()


def _deal_span(text: str) -> bool:
    direct_phrases = (
        "merger agreement",
        "business combination agreement",
        "proposed business combination",
        "form f-4",
        "form s-4",
        "completed the acquisition",
        "terminated the merger",
        "merger deadline",
    )
    if any(phrase in text for phrase in direct_phrases):
        return True
    transaction_terms = ("merger", "business combination", "acquisition", "strategic transaction")
    if not any(term in text for term in transaction_terms):
        return False
    return any(
        phrase in text
        for phrase in (
            "registration statement",
            "shareholder approval",
            "stockholder approval",
            "closing conditions",
            "consummated",
            "redemption",
        )
    )


def _orders_span(text: str) -> bool:
    explicit_negative = bool(
        re.search(r"\b(?:no|without)\s+(?:customer\s+)?orders?\b", text)
        or re.search(r"\b(?:has|have|had)\s+not\s+(?:received|secured|booked)\b.*\border\b", text)
    )
    if explicit_negative:
        return True
    if _generic_or_hypothetical(text) or any(
        phrase in text
        for phrase in (
            "restricted stock",
            "equity award",
            "equity awards",
            "compensation award",
            "recognition of",
            "boy scouts",
            "extend credit",
            "letter of credit",
            "payment on drafts",
            "underlying credit documents",
            "customer refundable deposit agreement",
        )
    ):
        return False
    if "purchase order" in text or "customer order" in text or "backlog" in text:
        return _contains_phrase(
            text,
            (
                "entered into",
                "was awarded",
                "received",
                "signed",
                "secured",
                "won",
                "increased",
                "totaled",
                "booked",
                "reported",
            ),
        )
    commercial_terms = (
        "customer",
        "client",
        "supply agreement",
        "sales agreement",
        "service agreement",
        "services agreement",
        "annual agreement",
        "government contract",
        "federal contract",
        "defense contract",
        "commercial contract",
    )
    return (
        any(term in text for term in ("contract", "award", "agreement"))
        and any(term in text for term in commercial_terms)
        and _contains_phrase(
            text,
            (
                "entered into",
                "was awarded",
                "received",
                "signed",
                "signs",
                "signing of",
                "secured",
                "won",
            ),
        )
    )


def _customer_capacity_span(text: str) -> bool:
    if _generic_or_hypothetical(text) or re.search(r"\b(?:may|might|could|would)\b", text):
        return False
    customer_pullthrough = (
        any(term in text for term in ("customer", "client"))
        and _contains_phrase(
            text,
            (
                "selected",
                "ordered",
                "signed",
                "signing",
                "deployed",
                "demand increased",
            ),
        )
    )
    signed_service_adoption = any(
        term in text for term in ("service agreement", "services agreement")
    ) and _contains_phrase(text, ("signed", "signs", "signing of", "entered into"))
    reported_demand = bool(
        re.search(r"driven by (?:strong|growing|increased) customer demand", text)
        or re.search(
            r"customer demand (?:was|is|remained)?\s*(?:strong|increased|grew|accelerated)",
            text,
        )
    )
    deployed_adoption = bool(
        re.search(
            r"currently deployed by (?:leading )?(?:[a-z-]+ )?"
            r"(?:banks|customers|clients|enterprises|agencies)",
            text,
        )
    )
    capacity_action = "capacity" in text and any(
        action in text
        for action in (
            "expanded",
            "increased",
            "opened",
            "commissioned",
            "reached",
            "added",
            "boost",
            "boosted",
        )
    )
    construction_progress = bool(
        re.search(r"\b(?:plant|facility|fab)\b.{0,80}\bnearing completion\b", text)
        or re.search(r"\bnearing completion\b.{0,80}\b(?:plant|facility|fab)\b", text)
    )
    shipment_action = any(term in text for term in ("shipment", "shipments")) and any(
        action in text for action in ("increased", "began", "commenced", "totaled", "reached")
    )
    utilization_action = "utilization" in text and any(
        action in text for action in ("increased", "improved", "reached", "rose")
    )
    return (
        customer_pullthrough
        or signed_service_adoption
        or reported_demand
        or deployed_adoption
        or capacity_action
        or construction_progress
        or shipment_action
        or utilization_action
    )


def _capital_span(text: str) -> bool:
    if any(
        phrase in text
        for phrase in (
            "description of securities we are offering",
            "following description",
            "holders of the pre-funded warrants",
            "not considered in the calculations",
            "carrying amount is a reasonable estimate of fair value",
            "form of pre-funded warrant",
            "must inform themselves",
            "may issue warrants",
            "may sell the securities",
            "no fractional shares",
            "terms of any rights",
            "qualified in their entirety",
            "qualified in its entirety",
            "you should carefully read",
        )
    ):
        return False
    numeric = bool(
        re.search(r"(?:\$|\b)\d[\d,.]*(?:\s*(?:million|billion|thousand|%))?", text)
    )
    if any(phrase in text for phrase in ("going concern", "substantial doubt", "covenant default")):
        return True
    if "cash and cash equivalents" in text:
        return numeric and any(
            marker in text
            for marker in (
                "as of",
                "at end of period",
                "at the end of the period",
                "beginning of the period",
                "increase",
                "decrease",
                "net cash",
                "reported",
                "of $",
            )
        )
    debt_terms = (
        "credit agreement",
        "credit facility",
        "revolving facility",
        "long-term debt",
        "total debt",
        "convertible note",
        "promissory note",
    )
    if any(term in text for term in debt_terms):
        return numeric and any(
            action in text
            for action in (
                "entered into",
                "amended",
                "borrowed",
                "converted",
                "due",
                "outstanding",
                "paid",
                "repaid",
                "reported",
            )
        )
    financing_terms = (
        "at-the-market",
        "public offering",
        "private placement",
        "registered direct offering",
        "securities purchase agreement",
    )
    if any(term in text for term in financing_terms):
        return numeric and any(
            action in text
            for action in (
                "agreed to sell",
                "closed",
                "completed",
                "consummated",
                "entered into",
                "gross proceeds",
                "net proceeds",
                "net cash received",
                "offering price",
                "sold",
            )
        )
    if any(phrase in text for phrase in ("stockholders' equity", "stockholders equity")):
        return numeric
    return "warrant" in text and numeric and any(
        action in text
        for action in (
            "agreed to sell and issue",
            "exercised",
            "issued",
            "outstanding",
            "redeemed",
            "sold in the offering",
        )
    )


def _policy_span(text: str) -> bool:
    if _generic_or_hypothetical(text):
        return False
    actual_status = any(
        phrase in text
        for phrase in (
            "received approval",
            "approval was granted",
            "approval has been granted",
            "permit was granted",
        )
    )
    planned_status = bool(
        re.search(
            r"\b(?:plan(?:s|ned)?|intend(?:s|ed)?|expect(?:s|ed)?|seek(?:s|ing)?|aim(?:s|ed)?)\b"
            r".{0,80}\b(?:approval|clearance|permit|submission|proposal|award)\b",
            text,
        )
        or re.search(r"\b(?:invited|selected) to submit\b", text)
    )
    if planned_status and not actual_status:
        return False
    if actual_status:
        return True
    if "funding award" in text and _contains_phrase(
        text,
        (
            "received",
            "was awarded",
            "entered into",
            "definitive direct funding award agreement",
        ),
    ):
        return True
    if "clinical hold" in text and _contains_phrase(
        text,
        ("placed", "imposed", "lifted", "removed"),
    ):
        return True
    if "warning letter" in text and _contains_phrase(
        text,
        ("received", "issued", "sent", "fda warning letter"),
    ):
        return True
    if (
        any(term in text for term in ("chips funding", "chips and science act funding"))
        and _contains_phrase(
            text,
            ("set to receive", "selected to receive", "was awarded", "awarded", "received"),
        )
    ):
        return True
    if "ferc ruling" in text and _contains_phrase(text, ("approved", "rejected", "issued")):
        return True
    return "tariff" in text and any(
        action in text
        for action in ("imposed", "announced", "enacted", "effective", "raised", "lowered", "removed")
    )


def _theme_transmission_span(text: str) -> bool:
    technology_theme = bool(
        "artificial intelligence" in text
        or re.search(r"\bai\b", text)
        or any(term in text for term in ("data center", "datacenter", "cloud"))
    )
    industry_theme = any(
        term in text
        for term in (
            "electric vehicle",
            "automotive demand",
            "industrial and energy",
            "renewable energy",
            "power demand",
            "electricity demand",
            "semiconductor supply chain",
            "silicon carbide",
            "grid modernization",
            "directed energy",
        )
    )
    if re.search(
        r"\b(?:no|not|without)\b.{0,50}\b(?:orders?|contracts?|customers?|deployments?)\b",
        text,
    ):
        return False
    company_economics = _orders_span(text) or _customer_capacity_span(text) or any(
        phrase in text
        for phrase in (
            "revenue from",
            "revenue decreased",
            "revenue increased",
            "guidance reflects",
            "capacity expansion",
            "weak demand",
            "softening of demand",
            "driven by demand",
        )
    )
    causal_link = any(
        phrase in text
        for phrase in (
            "due to",
            "driven by",
            "impact",
            "dependent on",
            "used in",
            "supply",
            "powers",
            "crucial for",
        )
    )
    return (technology_theme or industry_theme) and company_economics and (
        technology_theme or causal_link
    )


def _expectation_span(text: str) -> bool:
    if any(
        phrase in text
        for phrase in (
            "authoritative guidance",
            "accounting guidance",
            "revised guidance",
            "guidance for pensions",
            "guidance for postretirement",
        )
    ):
        return False
    direct = any(
        phrase in text
        for phrase in (
            "raised guidance",
            "lowered guidance",
            "reaffirmed guidance",
            "analyst estimate",
            "consensus estimate",
            "earnings surprise",
            "price target",
            "revenue beat",
            "earnings beat",
            "revenue miss",
            "earnings miss",
            "exceeded consensus",
            "exceeded expectations",
            "below consensus",
            "against an anticipated",
        )
    )
    issuer_outlook = bool(
        re.search(
            r"\b(?:company|management|we)\b.{0,80}\bguidance for\b"
            r"|\bguidance for\b.{0,40}\b(?:fiscal|fy|quarter|year)\b",
            text,
        )
    )
    return direct or issuer_outlook


def _risk_span(text: str) -> bool:
    if _generic_or_hypothetical(text) or re.search(r"\b(?:may|might|could|would)\b", text):
        return False
    return any(
        phrase in text
        for phrase in (
            "notice of delisting",
            "continued listing",
            "minimum bid",
            "non-compliance",
            "dilution",
            "covenant default",
            "material weakness",
            "customer concentration",
            "lawsuit",
            "investigation",
        )
    )


def _fundamental_span(text: str) -> bool:
    if re.match(r"^(?:condensed\s+)?consolidated statements? of", text):
        return False
    if any(
        phrase in text
        for phrase in (
            "accounting standards codification",
            "asc 606",
            "could remain an emerging growth company",
            "collectively referred to as the financial statements",
            "proceeds on sales of available for sale securities",
            "related consolidated statements",
            "sales price for our common stock",
            "sales of investment securities",
            "proceeds from sales",
            "revenue recognition",
            "revenues are recognized",
            "recognizes revenue when",
            "total annual gross revenues of",
            "internal revenue code",
            "employment agreement",
            "change in control for purposes of section 280g",
            "interest rate step-down condition",
            "statements of cash flows",
            "present fairly, in all material respects",
            "following table provides a summary",
        )
    ):
        return False
    if _generic_or_hypothetical(text) or re.search(r"\b(?:may|might|could|would)\b", text):
        return False
    metric_pattern = (
        r"(?:revenue|net sales|adjusted ebitda|ebitda|gross margin|operating margin|"
        r"cash (?:flow|from operating activities)|operating cash flow)"
    )
    if not re.search(metric_pattern, text):
        return False
    numeric = bool(
        re.search(r"(?:\$|\b)\d[\d,.]*(?:\s*(?:million|billion|thousand|%))?", text)
    )
    if not numeric:
        return False
    actual_context = bool(
        re.search(
            rf"\b(?:reported|generated|recorded)\b.{{0,80}}{metric_pattern}"
            rf"|{metric_pattern}.{{0,50}}\b(?:was|were|reached|totaled|increased|grew|rose|"
            r"decreased|declined|fell|of|during|for the|year-over-year|year over year)\b",
            text,
        )
    )
    table_row = bool(re.search(rf"^\s*{metric_pattern}\s+[($]?\d", text))
    return actual_context or table_row


def _business_span(text: str) -> bool:
    return bool(
        re.search(
            r"(?:\bbusiness context:|\bprincipal business\b|\bwe develop\b|"
            r"\bwe manufacture\b|\bwe provide\b|\boperates in\b)",
            text,
        )
    )


def _generic_or_hypothetical(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "may enter into",
            "could enter into",
            "risk that",
            "form of contract",
            "employment contract",
            "contractual obligations",
            "may be required",
            "could materially",
            "may request",
            "may not",
            "if we are unable",
            "in the event that",
        )
    )


def _contains_phrase(text: str, phrases: Iterable[str]) -> bool:
    return any(
        re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text)
        for phrase in phrases
    )


def _fact_status(span: str, family: str) -> tuple[AtomicFactStatus, bool]:
    text = span.lower()
    negated = _fact_is_negated(text, family)
    if negated:
        return AtomicFactStatus.CONTRADICTED, True
    if any(term in text for term in ("terminate", "terminated", "cancelled", "canceled", "liquidation")):
        return AtomicFactStatus.TERMINATED, False
    if any(term in text for term in ("delayed", "extended", "postponed")):
        return AtomicFactStatus.DELAYED, False
    if any(term in text for term in ("proposed", "intends to", "plans to", "pursuing")):
        return AtomicFactStatus.PROPOSED, False
    if any(term in text for term in ("expected", "scheduled", "guidance", "set to receive")):
        return AtomicFactStatus.EXPECTED, False
    if any(term in text for term in ("closed", "completed", "consummated", "received approval", "was awarded")):
        return AtomicFactStatus.COMPLETED, False
    if family in {"contrary_risk", "capital_structure_liquidity"} and any(
        term in text for term in ("risk", "going concern", "substantial doubt", "default", "non-compliance")
    ):
        return AtomicFactStatus.RISK, False
    return AtomicFactStatus.CONFIRMED, False


def _fact_is_negated(text: str, family: str) -> bool:
    patterns = {
        "orders_contracts": (
            r"\b(?:no|without)\s+(?:customer\s+)?(?:orders?|contracts?|backlog|awards?)\b",
            r"\b(?:did|has|have) not\b.{0,40}\b(?:receive|secure|sign|win|book)\b",
        ),
        "customer_capacity": (
            r"\bno\s+(?:customer demand|customers?|capacity|shipments?|utilization)\b",
            r"\b(?:did|has|have) not\b.{0,40}\b(?:deploy|expand|ship|open)\b",
        ),
        "capital_structure_liquidity": (
            r"\bno\s+(?:restricted\s+)?(?:cash|debt|borrowings?|liquidity|credit facility)\b",
            r"\b(?:did|has|have) not\b.{0,40}\b(?:close|raise|receive|borrow|repay)\b",
        ),
        "policy_regulatory": (
            r"\bno\s+(?:regulatory |fda )?(?:approval|clearance|permit|award)\b",
            r"\b(?:did|has|have) not\b.{0,40}\b(?:approve|grant|receive|issue)\b",
        ),
        "theme_industry_transmission": (
            r"\bno\b.{0,40}\b(?:ai|artificial intelligence|data center|cloud)\b"
            r".{0,40}\b(?:orders?|contracts?|customers?|deployment)\b",
        ),
        "expectation_gap": (
            r"\bno\s+(?:guidance|estimate|expectation|price target)\b",
            r"\b(?:did|has|have) not\b.{0,40}\b(?:raise|lower|reaffirm|beat|miss)\b",
        ),
        "fundamentals": (
            r"\bno\s+(?:revenue|sales|ebitda|cash flow)\b",
        ),
        "contrary_risk": (
            r"\bno\s+(?:material weakness|default|non-compliance|lawsuit|investigation)\b",
        ),
    }
    return any(re.search(pattern, text) for pattern in patterns.get(family, ()))


def _amount_and_unit(
    span: str,
    *,
    family: str | None = None,
) -> tuple[float | None, str | None]:
    amount_pattern = (
        r"\(?\s*(?P<currency>\$|usd\s*)(?P<amount>\d[\d,]*(?:\.\d+)?)\s*\)?\s*"
        r"(?P<scale>billion|million|thousand)?"
        r"|(?P<amount_scaled>\d[\d,]*(?:\.\d+)?)\s*"
        r"(?P<scale_only>billion|million|thousand|%|percent)\b"
    )
    match = None
    if family == "fundamentals":
        preferred = re.search(
            r"\b(?:revenue|net sales)\b.{0,120}?"
            r"\b(?:reaching|to|was|were|totaled|of)\s+"
            + amount_pattern,
            span,
            flags=re.IGNORECASE,
        )
        if preferred:
            match = preferred
    if match is None:
        match = re.search(amount_pattern, span, flags=re.IGNORECASE)
    if not match:
        return None, None
    raw_amount = match.group("amount") or match.group("amount_scaled")
    amount = float(raw_amount.replace(",", ""))
    scale = (match.group("scale") or match.group("scale_only") or "").lower()
    multiplier = {"thousand": 1_000.0, "million": 1_000_000.0, "billion": 1_000_000_000.0}.get(scale, 1.0)
    amount *= multiplier
    if scale in {"%", "percent"}:
        return amount, "percent"
    if match.group("currency"):
        return amount, "USD"
    return amount, scale or "reported_units"


def _period_phrase(span: str) -> str | None:
    match = re.search(
        r"\b(?:fiscal\s+)?(?:year|quarter|three months|six months|nine months)\s+(?:ended\s+)?"
        r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4}|20\d{2})",
        span,
        flags=re.IGNORECASE,
    )
    return match.group(0) if match else None


def _event_date_phrase(span: str) -> str | None:
    month_match = re.search(
        r"\b(?:on\s+|as of\s+)?"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}),\s+(20\d{2})\b",
        span,
        flags=re.IGNORECASE,
    )
    if month_match:
        raw = " ".join(month_match.groups())
        return datetime.strptime(raw.title(), "%B %d %Y").date().isoformat()
    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", span)
    return iso_match.group(1) if iso_match else None


def _counterparty_role(span: str) -> str | None:
    if re.search(r"\bwith\s+(?:a|an|the)?\s*(?:customer|client|partner|supplier)\b", span, flags=re.IGNORECASE):
        return "commercial_counterparty"
    if "business combination" in span.lower() or "merger" in span.lower():
        return "transaction_counterparty"
    return None


def _feature_family(name: str) -> str | None:
    if name.startswith("profile."):
        return "business_identity"
    if name.startswith("financial.") or name.startswith("valuation."):
        return "fundamentals"
    if name.startswith("analyst."):
        return "expectation_gap"
    if name.startswith("price."):
        return "market_confirmation"
    return None


def _catalyst_family(name: str) -> str:
    classified = _classify_source_span(name)
    return classified[0] if classified else "other_or_unclassified"


def _requirement_diagnostic(
    requirement: InformationRequirement,
    cases: tuple[HistoricalCase, ...],
    facts_by_case: Mapping[str, tuple[AtomicEvidence, ...]],
) -> RequirementDiagnostic:
    winners = [case for case in cases if case.label is CaseOutcomeLabel.WINNER]
    non_winners = [case for case in cases if case.label is not CaseOutcomeLabel.WINNER]
    winner_hits = sum(
        1
        for case in winners
        if any(fact.family == requirement.family for fact in facts_by_case.get(case.case_id, ()))
    )
    non_winner_hits = sum(
        1
        for case in non_winners
        if any(fact.family == requirement.family for fact in facts_by_case.get(case.case_id, ()))
    )
    winner_prevalence = winner_hits / len(winners) if winners else 0.0
    non_winner_prevalence = non_winner_hits / len(non_winners) if non_winners else 0.0
    dates = sorted({case.packet.as_of.as_of_date.isoformat() for case in cases})
    return RequirementDiagnostic(
        requirement_id=requirement.requirement_id,
        winner_case_count=winner_hits,
        non_winner_case_count=non_winner_hits,
        winner_prevalence=round(winner_prevalence, 4),
        non_winner_prevalence=round(non_winner_prevalence, 4),
        separation_lift=round(winner_prevalence - non_winner_prevalence, 4),
        observed_as_of_dates=tuple(dates),
    )


def _coverage_state(
    case: HistoricalCase,
    family: str,
    facts: tuple[AtomicEvidence, ...],
    external_documents: tuple[DocumentRecord, ...] = (),
) -> tuple[RequirementCoverageState, str]:
    packet = case.packet
    if facts:
        statuses = {fact.status for fact in facts}
        if statuses == {AtomicFactStatus.CONTRADICTED}:
            return RequirementCoverageState.CONTRADICTED, "Source explicitly contradicts the proposed positive fact."
        if statuses == {AtomicFactStatus.AMBIGUOUS}:
            return RequirementCoverageState.AMBIGUOUS, "Only ambiguous source-linked facts were extracted."
        return RequirementCoverageState.CONFIRMED, f"Extracted {len(facts)} source-linked atomic fact(s)."
    missing_features = [
        feature
        for feature in packet.features
        if feature.data_quality is DataQuality.MISSING and _feature_family(feature.name) == family
    ]
    if missing_features:
        return RequirementCoverageState.SOURCE_UNAVAILABLE, "Provider explicitly reported required structured data unavailable."
    external_states = {
        _document_content_state(document, _clean_source_text(document.text))[0]
        for document in external_documents
    }
    if (
        external_states
        and not external_states
        & {DocumentContentState.USABLE, DocumentContentState.SUMMARY_ONLY}
        and family not in {"market_confirmation", "fundamentals"}
    ):
        return (
            RequirementCoverageState.NOT_FETCHED,
            "Only truncated, metadata-only, or unusable source bodies were archived; full content was not fetched.",
        )
    packet_documents = [
        item
        for item in packet.evidence
        if (item.source_id or item.source_url)
        and item.kind
        in {
            EvidenceKind.FILING,
            EvidenceKind.TRANSCRIPT,
            EvidenceKind.NEWS,
            EvidenceKind.RESEARCH_REPORT,
            EvidenceKind.THEME_CONTEXT,
        }
    ]
    if (
        not packet_documents
        and not external_documents
        and family not in {"market_confirmation", "fundamentals"}
    ):
        return RequirementCoverageState.NOT_FETCHED, "No source document for this requirement was fetched into the packet."
    unusable_external_source_ids = {
        document.source_id
        for document in external_documents
        if _document_content_state(document, _clean_source_text(document.text))[0]
        not in {DocumentContentState.USABLE, DocumentContentState.SUMMARY_ONLY}
    }
    candidate_texts = [
        item.summary
        for item in packet_documents
        if item.source_id not in unusable_external_source_ids
        and not (
            (item.source_id or "").startswith("alpha_vantage:")
            and not _source_text_mentions_issuer(case, item.summary)
        )
    ] + [
        f"{document.title}. {document.text}"
        for document in external_documents
        if _document_content_state(document, _clean_source_text(document.text))[0]
        in {DocumentContentState.USABLE, DocumentContentState.SUMMARY_ONLY}
        and not (
            document.source_id.startswith("alpha_vantage:")
            and not _source_text_mentions_issuer(
                case,
                f"{document.title}. {document.text}",
            )
        )
    ]
    if _family_has_qualifying_candidate(family, candidate_texts):
        return RequirementCoverageState.EXTRACTION_FAILED, "Candidate source terms exist but no qualifying atomic fact was extracted."
    return RequirementCoverageState.NOT_FOUND, "Fetched point-in-time sources contain no qualifying fact for this requirement."


def _source_pool_by_case(
    cases: Iterable[HistoricalCase],
    documents_by_symbol: Mapping[str, Iterable[DocumentRecord]] | None,
) -> dict[str, tuple[str, ...]]:
    pools: dict[str, tuple[str, ...]] = {}
    for case in cases:
        source_ids = {
            item.source_id
            for item in case.packet.evidence
            if item.source_id
        }
        symbol = case.packet.company.ticker.symbol.upper()
        if documents_by_symbol:
            source_ids.update(
                document.source_id
                for document in documents_by_symbol.get(symbol, ())
                if document.available_as_of(case.packet.as_of.as_of_date)
            )
        pools[case.case_id] = tuple(sorted(source_ids))
    return pools


def _source_documents_by_case(
    cases: Iterable[HistoricalCase],
    documents_by_symbol: Mapping[str, Iterable[DocumentRecord]] | None,
) -> dict[str, tuple[DocumentRecord, ...]]:
    documents: dict[str, tuple[DocumentRecord, ...]] = {}
    for case in cases:
        symbol = case.packet.company.ticker.symbol.upper()
        documents[case.case_id] = tuple(
            document
            for document in (documents_by_symbol or {}).get(symbol, ())
            if document.available_as_of(case.packet.as_of.as_of_date)
        )
    return documents


def _family_candidate_keywords(family: str, text: str) -> bool:
    keywords = {
        "business_identity": ("business", "product", "service", "customer"),
        "deal_status_timing": ("merger", "business combination", "transaction", "redemption"),
        "capital_structure_liquidity": ("cash", "debt", "credit", "warrant", "liquidity"),
        "orders_contracts": ("order", "contract", "backlog", "award"),
        "customer_capacity": ("customer", "capacity", "shipment", "utilization"),
        "policy_regulatory": ("approval", "regulatory", "fda", "permit", "tariff"),
        "theme_industry_transmission": ("artificial intelligence", "ai", "data center", "cloud"),
        "expectation_gap": ("guidance", "estimate", "expectation", "price target"),
        "contrary_risk": ("risk", "dilution", "delist", "non-compliance", "lawsuit"),
        "fundamentals": ("revenue", "sales", "margin", "ebitda", "cash flow"),
        "market_confirmation": ("price", "volume", "trading"),
        "other_or_unclassified": (),
    }
    return any(keyword in text for keyword in keywords.get(family, ()))


def _family_has_qualifying_candidate(family: str, source_texts: Iterable[str]) -> bool:
    action_qualified = {
        "orders_contracts": _orders_span,
        "customer_capacity": _customer_capacity_span,
        "policy_regulatory": _policy_span,
        "theme_industry_transmission": _theme_transmission_span,
    }
    predicate = action_qualified.get(family)
    if predicate:
        return any(
            predicate(span.lower())
            for source_text in source_texts
            for span in _source_spans(source_text)
        )
    return _family_candidate_keywords(family, " ".join(source_texts).lower())


def _families_from_missing_context(reasons: Iterable[str]) -> set[str]:
    text = " ".join(reasons).lower()
    mapping = {
        "business_identity": ("business", "sector", "industry", "product", "end market"),
        "deal_status_timing": ("deal", "transaction", "business combination", "merger", "redemption"),
        "capital_structure_liquidity": ("capital", "cash", "liquidity", "debt", "dilution", "covenant"),
        "orders_contracts": ("order", "contract", "backlog", "award"),
        "customer_capacity": ("customer", "capacity", "shipment", "utilization"),
        "policy_regulatory": ("policy", "regulatory", "approval", "permit", "fda"),
        "theme_industry_transmission": ("theme", "industry transmission", "ai", "data center", "cloud"),
        "expectation_gap": ("expectation", "guidance", "estimate", "valuation", "consensus"),
        "contrary_risk": ("risk", "listing", "execution"),
        "fundamentals": ("revenue", "margin", "earnings", "cash flow", "fundamental"),
        "market_confirmation": ("price", "volume", "market confirmation", "liquidity"),
    }
    return {
        family
        for family, keywords in mapping.items()
        if any(keyword in text for keyword in keywords)
    }


def _prepare_family_experiment(
    family: str,
    holdout: tuple[HistoricalCase, ...],
    scheme: InformationScheme,
    facts_by_case: Mapping[str, tuple[AtomicEvidence, ...]],
    coverage: tuple[RequirementCoverageEntry, ...],
    source_identity_tokens_by_case: Mapping[str, tuple[str, ...]],
) -> PreparedFamilyExperiment:
    fact_count = sum(
        1
        for case in holdout
        for fact in facts_by_case.get(case.case_id, ())
        if fact.family == family
    )
    if fact_count == 0:
        return PreparedFamilyExperiment(
            family=family,
            available_fact_count=0,
            add_back_packets=(),
            ablation_packets=(),
            status="no_source_backed_facts",
        )
    core_families = _family_add_back_core_families()
    add_back_packets = tuple(
        build_organized_atomic_blind_packet(
            case,
            scheme,
            facts_by_case[case.case_id],
            coverage,
            anonymous_case_id=f"holdout_{index:03d}",
            include_families=core_families | {family},
            source_identity_tokens=source_identity_tokens_by_case.get(case.case_id, ()),
        )
        for index, case in enumerate(holdout, start=1)
    )
    ablation_packets = tuple(
        build_organized_atomic_blind_packet(
            case,
            scheme,
            facts_by_case[case.case_id],
            coverage,
            anonymous_case_id=f"holdout_{index:03d}",
            exclude_families={family},
            source_identity_tokens=source_identity_tokens_by_case.get(case.case_id, ()),
        )
        for index, case in enumerate(holdout, start=1)
    )
    return PreparedFamilyExperiment(
        family=family,
        available_fact_count=fact_count,
        add_back_packets=add_back_packets,
        ablation_packets=ablation_packets,
        status="packet_variants_ready",
    )


def _family_add_back_core_families() -> set[str]:
    return {
        requirement.family for requirement in default_information_requirements()
    } - set(TARGET_INFORMATION_FAMILIES)


def _evaluate_family_experiment(
    experiment: PreparedFamilyExperiment,
    holdout: tuple[HistoricalCase, ...],
    researcher: RalphBlindResearcher,
    *,
    mode: str,
    add_back_baseline_evaluation: SchemeEvaluation | None,
    organized_baseline_evaluation: SchemeEvaluation,
) -> FamilyExperimentEvaluation:
    if experiment.status != "packet_variants_ready" or mode == "packets_only":
        return FamilyExperimentEvaluation(
            family=experiment.family,
            status=(
                experiment.status
                if experiment.status != "packet_variants_ready"
                else "packets_ready_not_evaluated"
            ),
            available_fact_count=experiment.available_fact_count,
            add_back_baseline_evaluation=None,
            add_back_evaluation=None,
            add_back_delta=None,
            ablation_baseline_evaluation=None,
            ablation_evaluation=None,
            ablation_delta=None,
        )
    add_back_evaluation = None
    ablation_evaluation = None
    add_back_delta = None
    ablation_delta = None
    if mode in {"add_back", "both"}:
        if add_back_baseline_evaluation is None:
            raise ValidationError("add-back evaluation requires a fixed core baseline")
        analyses = tuple(researcher.analyze(packet) for packet in experiment.add_back_packets)
        add_back_evaluation = evaluate_scheme_performance(
            holdout,
            analyses,
            scheme_version=f"information-family:{experiment.family}:add_back",
        )
        add_back_delta = _evaluation_delta(add_back_evaluation, add_back_baseline_evaluation)
    if mode in {"ablation", "both"}:
        analyses = tuple(researcher.analyze(packet) for packet in experiment.ablation_packets)
        ablation_evaluation = evaluate_scheme_performance(
            holdout,
            analyses,
            scheme_version=f"information-family:{experiment.family}:ablation",
        )
        ablation_delta = _evaluation_delta(organized_baseline_evaluation, ablation_evaluation)
    return FamilyExperimentEvaluation(
        family=experiment.family,
        status="evaluated",
        available_fact_count=experiment.available_fact_count,
        add_back_baseline_evaluation=(
            add_back_baseline_evaluation if mode in {"add_back", "both"} else None
        ),
        add_back_evaluation=add_back_evaluation,
        add_back_delta=add_back_delta,
        ablation_baseline_evaluation=(
            organized_baseline_evaluation if mode in {"ablation", "both"} else None
        ),
        ablation_evaluation=ablation_evaluation,
        ablation_delta=ablation_delta,
    )


def _evaluation_delta(
    candidate: SchemeEvaluation,
    baseline: SchemeEvaluation,
) -> dict[str, float]:
    return {
        "positive_confidence_gap": round(
            candidate.positive_confidence_gap - baseline.positive_confidence_gap,
            4,
        ),
        "confidence_gap": round(candidate.confidence_gap - baseline.confidence_gap, 4),
        "false_positive_rate": round(
            candidate.false_positive_rate - baseline.false_positive_rate,
            4,
        ),
        "false_negative_rate": round(
            candidate.false_negative_rate - baseline.false_negative_rate,
            4,
        ),
    }


def _section_for_family(family: str) -> str:
    mapping = {
        "orders_contracts": "Catalyst/Event Ledger",
        "policy_regulatory": "Catalyst/Event Ledger",
        "expectation_gap": "Expectation Gap Summary",
        "business_identity": "Theme/Industry Transmission",
        "customer_capacity": "Theme/Industry Transmission",
        "theme_industry_transmission": "Theme/Industry Transmission",
        "deal_status_timing": "Materiality and Timing",
        "capital_structure_liquidity": "Materiality and Timing",
        "contrary_risk": "Contrary/Risk Evidence",
        "other_or_unclassified": "Contrary/Risk Evidence",
        "fundamentals": "Compressed Fundamentals",
        "market_confirmation": "Compressed Market Confirmation",
    }
    return mapping.get(family, "Contrary/Risk Evidence")


def _section_for_fact(fact: AtomicEvidence) -> str:
    if fact.event_type == "materiality_ratio":
        return "Materiality and Timing"
    if fact.event_type == "expectation_timeline":
        return "Expectation Gap Summary"
    if fact.family != "capital_structure_liquidity":
        return _section_for_family(fact.family)
    text = fact.source_span.lower()
    if fact.status is AtomicFactStatus.RISK or any(
        marker in text
        for marker in (
            "dilution",
            "going concern",
            "substantial doubt",
            "covenant default",
        )
    ):
        return "Contrary/Risk Evidence"
    return "Materiality and Timing"


def _families_for_section(section_name: str) -> tuple[str, ...]:
    return tuple(
        family
        for family in (requirement.family for requirement in default_information_requirements())
        if _section_for_family(family) == section_name
    )


def _atomic_blind_item(fact: AtomicEvidence) -> dict[str, Any]:
    observed_date = _fact_date(fact)
    as_of_age_days = max(0, (date.fromisoformat(fact.as_of_date) - observed_date).days)
    if fact.source_kind == "derived":
        return {
            "item_type": "derived_evidence",
            "fact_ref": fact.fact_id,
            "family": fact.family,
            "event_type": fact.event_type,
            "status": fact.status.value,
            "amount": fact.amount,
            "unit": fact.unit,
            "period": fact.period,
            "event_date": fact.event_date,
            "published_date": fact.published_date,
            "as_of_age_days": as_of_age_days,
            "summary": fact.statement,
            "derived_from_fact_refs": list(fact.derived_from_fact_ids),
            "calculation": fact.calculation,
        }
    return {
        "item_type": "atomic_evidence",
        "fact_ref": fact.fact_id,
        "family": fact.family,
        "subject_role": fact.subject_role,
        "counterparty_role": fact.counterparty_role,
        "event_type": fact.event_type,
        "status": fact.status.value,
        "amount": fact.amount,
        "unit": fact.unit,
        "period": fact.period,
        "event_date": fact.event_date,
        "published_date": fact.published_date,
        "as_of_age_days": as_of_age_days,
        "negated": fact.negated,
        "summary": fact.statement,
        "supporting_span": fact.source_span,
        "derived_from_fact_refs": list(fact.derived_from_fact_ids),
        "calculation": fact.calculation,
    }


def _blind_judgment_is_error(case: HistoricalCase, analysis: RalphBlindAnalysis) -> bool:
    positive = analysis.surge_candidate in {"likely", "possible"} and analysis.confidence >= 0.45
    if case.label is CaseOutcomeLabel.WINNER:
        return not positive
    if case.label is CaseOutcomeLabel.CONTROL:
        return positive
    return False


def _failure_layer_counts(attributions: Iterable[FailureAttribution]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in attributions:
        key = item.primary_layer.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _dedupe_facts(facts: Iterable[AtomicEvidence]) -> tuple[AtomicEvidence, ...]:
    deduped: list[AtomicEvidence] = []
    seen: set[tuple[str, str, str, str]] = set()
    for fact in facts:
        key = (
            fact.source_id,
            fact.family,
            fact.event_type,
            re.sub(r"\W+", " ", fact.statement.lower()).strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return tuple(deduped)


def _dedupe_semantic_facts_for_packet(
    facts: Iterable[AtomicEvidence],
) -> tuple[AtomicEvidence, ...]:
    selected: dict[tuple[str, str, str, str], AtomicEvidence] = {}
    for fact in facts:
        normalized = _packet_semantic_fact_key(fact)
        key = (fact.family, fact.event_type, fact.status.value, normalized)
        current = selected.get(key)
        if current is None or _atomic_fact_priority(fact) > _atomic_fact_priority(current):
            selected[key] = fact
    return tuple(selected.values())


def _packet_semantic_fact_key(fact: AtomicEvidence) -> str:
    text = fact.statement.lower()
    if fact.family == "capital_structure_liquidity" and "cash and cash equivalents" in text:
        date_key = fact.event_date or fact.published_date or fact.as_of_date
        return f"cash-and-cash-equivalents:{date_key}"
    if fact.family == "expectation_gap" and "price target" in text:
        date_key = fact.event_date or fact.published_date or fact.as_of_date
        return f"price-target:{date_key}"
    if fact.family == "contrary_risk" and "dilution" in text:
        date_key = fact.event_date or fact.published_date or fact.as_of_date
        return f"dilution:{date_key}"
    return re.sub(r"\W+", " ", text).strip()


def _balanced_atomic_facts(
    facts: Iterable[AtomicEvidence],
    max_items: int,
) -> tuple[AtomicEvidence, ...]:
    """Choose recent high-quality facts without letting one family consume a section."""

    grouped: dict[str, list[AtomicEvidence]] = {}
    for fact in facts:
        if fact.family == "business_identity" and _low_signal_business_context(fact):
            continue
        grouped.setdefault(fact.family, []).append(fact)
    for family_facts in grouped.values():
        family_facts.sort(key=_atomic_fact_sort_key, reverse=True)
    family_order = sorted(
        grouped,
        key=lambda family: (_atomic_fact_sort_key(grouped[family][0]), family),
        reverse=True,
    )
    selected: list[AtomicEvidence] = []
    depth = 0
    while len(selected) < max_items:
        added = False
        for family in family_order:
            family_facts = grouped[family]
            if depth >= len(family_facts):
                continue
            selected.append(family_facts[depth])
            added = True
            if len(selected) == max_items:
                break
        if not added:
            break
        depth += 1
    return tuple(selected)


def _low_signal_business_context(fact: AtomicEvidence) -> bool:
    """Drop generic governance and boilerplate that cannot identify company economics."""

    text = fact.source_span.lower()
    return any(
        phrase in text
        for phrase in (
            "complex market and regulatory environment",
            "provide limited perquisites",
            "say-on-pay vote",
            "standard warranty periods",
        )
    )


def _atomic_fact_priority(fact: AtomicEvidence) -> tuple[int, int, int]:
    boilerplate = any(
        phrase in fact.source_span.lower()
        for phrase in (
            "pursuant to rule",
            "qualified in its entirety",
            "qualified in their entirety",
            "form of ",
            "filed as exhibit",
            "deemed not filed",
            "internal revenue code",
            "employment agreement",
            "following table provides a summary",
            "present fairly, in all material respects",
        )
    )
    status_priority = {
        AtomicFactStatus.COMPLETED: 6,
        AtomicFactStatus.TERMINATED: 6,
        AtomicFactStatus.DELAYED: 5,
        AtomicFactStatus.CONTRADICTED: 5,
        AtomicFactStatus.PROPOSED: 4,
        AtomicFactStatus.EXPECTED: 4,
        AtomicFactStatus.RISK: 3,
        AtomicFactStatus.CONFIRMED: 3,
        AtomicFactStatus.AMBIGUOUS: 1,
    }[fact.status]
    if fact.family == "contrary_risk" and fact.negated:
        status_priority = 1
    specificity = int(fact.amount is not None) + int(fact.period is not None) + int(
        fact.counterparty_role is not None
    )
    source_quality = 0 if fact.source_kind == "derived" else 1
    return (0 if boilerplate else source_quality, status_priority, specificity)


def _atomic_fact_sort_key(fact: AtomicEvidence) -> tuple[int, str, int, int, str]:
    quality, status, specificity = _atomic_fact_priority(fact)
    return (
        quality,
        fact.event_date or fact.published_date or fact.as_of_date,
        status,
        specificity,
        fact.fact_id,
    )


def _fact_id(case_id: str, source_id: str, family: str, event_type: str, span: str) -> str:
    payload = "|".join((case_id, source_id, family, event_type, span)).encode("utf-8")
    return "fact_" + hashlib.sha256(payload).hexdigest()[:16]


def _opaque_ref(case_id: str, value: str) -> str:
    return "ref_" + hashlib.sha256(f"{case_id}|{value}".encode("utf-8")).hexdigest()[:16]


def _items_within_budget(items: Iterable[dict[str, Any]], token_budget: int) -> tuple[dict[str, Any], ...]:
    selected: list[dict[str, Any]] = []
    used = 0
    for item in items:
        remaining = token_budget - used
        if remaining <= 0:
            break
        candidate = _item_within_remaining_budget(item, remaining)
        if candidate is None:
            break
        item_tokens = max(1, len(json.dumps(candidate, sort_keys=True).split()))
        selected.append(candidate)
        used += item_tokens
        if used >= token_budget:
            break
    return tuple(selected)


def _item_within_remaining_budget(
    item: dict[str, Any],
    remaining: int,
) -> dict[str, Any] | None:
    if len(json.dumps(item, sort_keys=True).split()) <= remaining:
        return item
    summary = item.get("summary")
    if not isinstance(summary, str) or remaining < 20:
        return None
    candidate = dict(item)
    words = summary.split()
    while words:
        candidate["summary"] = " ".join(words) + "..."
        if len(json.dumps(candidate, sort_keys=True).split()) <= remaining:
            return candidate
        shrink = max(1, len(words) // 4)
        words = words[:-shrink]
    return None


def _estimated_tokens(items: Iterable[dict[str, Any]]) -> int:
    return max(1, len(json.dumps(list(items), sort_keys=True).split()))


def _compact(value: str, max_chars: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
