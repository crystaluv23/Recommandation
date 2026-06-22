"""Ralph Loop information-scheme proposals for cold-start blind packets."""

from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from stock_opportunity_agent.cases.learning import ColdStartLearningResult, HistoricalCase
from stock_opportunity_agent.cases.outcomes import CaseOutcomeLabel
from stock_opportunity_agent.llm.openai import ChatMessage, OpenAIChatClient
from stock_opportunity_agent.models import EvidenceItem, EvidenceKind, FeatureRecord, ResearchPacket, ValidationError
from stock_opportunity_agent.research.cold_start import BlindCaseAnalysis
from stock_opportunity_agent.research.playbooks import SurgePlaybookSynthesis
from stock_opportunity_agent.themes import ThemeMapBuildResult


RALPH_LOOP_SCHEMA_VERSION = "ralph-loop-v0.1"
INFORMATION_SCHEME_SCHEMA_VERSION = "information-scheme-v0.1"
BLIND_SCHEME_PACKET_SCHEMA_VERSION = "ralph-blind-packet-v0.1"

HIGH_PRIORITY_SECTION_NAMES = (
    "Catalyst/Event Ledger",
    "Expectation Gap Summary",
    "Theme/Industry Transmission",
    "Materiality and Timing",
    "Contrary/Risk Evidence",
)
COMPRESSED_SECTION_NAMES = ("Compressed Fundamentals", "Compressed Market Confirmation")


@dataclass(frozen=True)
class InformationSection:
    """One ordered section in an information scheme."""

    name: str
    priority: int
    token_budget: int
    evidence_buckets: tuple[str, ...]
    compression_rule: str
    required: bool = True
    max_items: int = 4
    role: str = "primary"

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "section name")
        if self.priority < 1:
            raise ValidationError("section priority must be positive")
        if self.token_budget < 1:
            raise ValidationError("section token_budget must be positive")
        if self.max_items < 1:
            raise ValidationError("section max_items must be positive")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible section."""

        return {
            "name": self.name,
            "priority": self.priority,
            "token_budget": self.token_budget,
            "evidence_buckets": list(self.evidence_buckets),
            "compression_rule": self.compression_rule,
            "required": self.required,
            "max_items": self.max_items,
            "role": self.role,
        }


@dataclass(frozen=True)
class InformationScheme:
    """Versioned proposal for structuring cold-start blind packets."""

    scheme_id: str
    version: str
    sections: tuple[InformationSection, ...]
    total_token_budget: int
    max_compressed_context_share: float
    contrary_evidence_required: bool
    compression_rules: tuple[str, ...]
    proposal_status: str = "proposal_only"
    schema_version: str = INFORMATION_SCHEME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("scheme_id", "version", "proposal_status", "schema_version"):
            _require_non_empty(getattr(self, name), name)
        if not self.sections:
            raise ValidationError("information scheme requires sections")
        if self.total_token_budget < 1:
            raise ValidationError("information scheme total_token_budget must be positive")
        if not 0 < self.max_compressed_context_share < 1:
            raise ValidationError("max_compressed_context_share must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible scheme without case outcomes or identities."""

        return {
            "schema_version": self.schema_version,
            "scheme_id": self.scheme_id,
            "version": self.version,
            "proposal_status": self.proposal_status,
            "total_token_budget": self.total_token_budget,
            "max_compressed_context_share": self.max_compressed_context_share,
            "contrary_evidence_required": self.contrary_evidence_required,
            "sections": [section.to_dict() for section in self.sections],
            "compression_rules": list(self.compression_rules),
            "rubrics": _scheme_rubrics(),
            "prompt_output_schema": {
                "surge_candidate": "likely | possible | unlikely | insufficient_information",
                "confidence": "number between 0 and 1",
                "reason": "cite catalyst materiality, expectation gap, theme transmission, and contrary evidence",
                "missing_context": ["missing evidence bucket or ambiguity"],
            },
            "boundary_notes": [
                "Generated from retrospective diagnostics; proposal only.",
                "Not promoted to daily, weekly, or production prompt defaults.",
                "Blind packets rendered from this scheme remain anonymous and point-in-time.",
            ],
        }


@dataclass(frozen=True)
class EvidenceFamilyDiagnostic:
    """Retrospective evidence-family separation statistics."""

    family: str
    winner_hits: int
    non_winner_hits: int
    winner_prevalence: float
    non_winner_prevalence: float
    separation_lift: float
    example_case_refs: tuple[str, ...]
    reasoning_pattern: str
    false_positive_trap: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible diagnostic record."""

        return {
            "family": self.family,
            "winner_hits": self.winner_hits,
            "non_winner_hits": self.non_winner_hits,
            "winner_prevalence": self.winner_prevalence,
            "non_winner_prevalence": self.non_winner_prevalence,
            "separation_lift": self.separation_lift,
            "example_case_refs": list(self.example_case_refs),
            "reasoning_pattern": self.reasoning_pattern,
            "false_positive_trap": self.false_positive_trap,
        }


@dataclass(frozen=True)
class RalphDiagnosticReport:
    """Retrospective label-aware diagnosis used to synthesize a scheme."""

    stage_boundary: str
    case_count: int
    outcome_group_counts: dict[str, int]
    evidence_family_diagnostics: tuple[EvidenceFamilyDiagnostic, ...]
    top_distinguishing_families: tuple[str, ...]
    false_positive_traps: tuple[str, ...]
    source_artifacts: tuple[str, ...]
    coverage_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible diagnostic report."""

        return {
            "stage_boundary": self.stage_boundary,
            "case_count": self.case_count,
            "outcome_group_counts": dict(self.outcome_group_counts),
            "evidence_family_diagnostics": [
                item.to_dict() for item in self.evidence_family_diagnostics
            ],
            "top_distinguishing_families": list(self.top_distinguishing_families),
            "false_positive_traps": list(self.false_positive_traps),
            "source_artifacts": list(self.source_artifacts),
            "coverage_summary": dict(self.coverage_summary),
        }


@dataclass(frozen=True)
class BlindPacketSection:
    """Rendered section inside a Ralph blind packet."""

    name: str
    priority: int
    token_budget: int
    compression_rule: str
    items: tuple[dict[str, Any], ...]
    estimated_tokens: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible packet section."""

        return {
            "name": self.name,
            "priority": self.priority,
            "token_budget": self.token_budget,
            "compression_rule": self.compression_rule,
            "estimated_tokens": self.estimated_tokens,
            "items": list(self.items),
        }


@dataclass(frozen=True)
class BlindSchemePacket:
    """Anonymous as-of packet rendered from an information scheme."""

    source_case_id: str
    anonymous_case_id: str
    as_of_date: str
    scheme_id: str
    scheme_version: str
    sections: tuple[BlindPacketSection, ...]

    def to_prompt_dict(self) -> dict[str, Any]:
        """Return the exact identity-safe packet sent to a blind researcher."""

        return {
            "schema_version": BLIND_SCHEME_PACKET_SCHEMA_VERSION,
            "scheme_id": self.scheme_id,
            "scheme_version": self.scheme_version,
            "anonymous_case_id": self.anonymous_case_id,
            "as_of_date": self.as_of_date,
            "identity_masked": True,
            "web_tools_allowed": False,
            "task": (
                "Judge whether this anonymous as-of case looks like a potential "
                "3-6 month surge candidate. Use only the sections below."
            ),
            "sections": [section.to_dict() for section in self.sections],
            "required_json_schema": {
                "surge_candidate": "likely | possible | unlikely | insufficient_information",
                "surge_candidate_reason": "string",
                "expectation_gap": "string",
                "pre_surge_signals": ["string"],
                "contrary_evidence": ["string"],
                "catalyst_watch": ["string"],
                "confidence": "number between 0 and 1",
                "missing_context": ["string"],
            },
        }

    def to_dict(self) -> dict[str, Any]:
        """Return an artifact-safe packet without source case identity."""

        return self.to_prompt_dict()


@dataclass(frozen=True)
class RalphBlindAnalysis:
    """Blind analysis output for a scheme-rendered packet."""

    source_case_id: str
    anonymous_case_id: str
    as_of_date: str
    scheme_version: str
    surge_candidate: str
    surge_candidate_reason: str
    expectation_gap: str
    pre_surge_signals: tuple[str, ...]
    contrary_evidence: tuple[str, ...]
    catalyst_watch: tuple[str, ...]
    confidence: float
    raw_text: str
    missing_context: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible analysis without source case identity."""

        return {
            "anonymous_case_id": self.anonymous_case_id,
            "as_of_date": self.as_of_date,
            "scheme_version": self.scheme_version,
            "surge_candidate": self.surge_candidate,
            "surge_candidate_reason": self.surge_candidate_reason,
            "expectation_gap": self.expectation_gap,
            "pre_surge_signals": list(self.pre_surge_signals),
            "contrary_evidence": list(self.contrary_evidence),
            "catalyst_watch": list(self.catalyst_watch),
            "missing_context": list(self.missing_context),
            "confidence": self.confidence,
            "raw_text": self.raw_text,
        }


class RalphBlindResearcher(Protocol):
    """Researcher that evaluates a scheme-built blind packet."""

    def analyze(self, packet: BlindSchemePacket) -> RalphBlindAnalysis:
        """Analyze the anonymous packet with no web tools."""


class CachedRalphBlindResearcher:
    """Persist blind analyses per anonymous packet so interrupted runs can resume."""

    def __init__(self, inner: RalphBlindResearcher, cache_dir: str | Path) -> None:
        self.inner = inner
        self.cache_dir = Path(cache_dir)

    def analyze(self, packet: BlindSchemePacket) -> RalphBlindAnalysis:
        """Return a cached blind analysis or call the wrapped researcher and save it."""

        packet_hash = _blind_packet_sha256(packet)
        cache_path = self.cache_dir / f"{packet_hash}.json"
        if cache_path.exists():
            return _cached_ralph_analysis(packet, json.loads(cache_path.read_text(encoding="utf-8")))
        analysis = self.inner.analyze(packet)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            cache_path,
            {
                "schema_version": "ralph-blind-analysis-cache-v0.1",
                "packet_sha256": packet_hash,
                "anonymous_case_id": packet.anonymous_case_id,
                "as_of_date": packet.as_of_date,
                "scheme_version": packet.scheme_version,
                "web_tools_allowed": False,
                "analysis": analysis.to_dict(),
            },
        )
        return analysis


class HeuristicRalphBlindResearcher:
    """Deterministic Ralph blind validator for tests and offline dry runs."""

    def analyze(self, packet: BlindSchemePacket) -> RalphBlindAnalysis:
        """Score a scheme packet using only section presence and text cues."""

        sections = {section.name: section for section in packet.sections}
        high_priority_hits = sum(
            1 for name in HIGH_PRIORITY_SECTION_NAMES if sections.get(name) and sections[name].items
        )
        risk_section = sections.get("Contrary/Risk Evidence")
        risk_hits = len(risk_section.items) if risk_section is not None else 0
        confidence = min(0.82, 0.25 + 0.11 * high_priority_hits + 0.02 * risk_hits)
        if high_priority_hits >= 4:
            judgment = "likely"
        elif high_priority_hits >= 2:
            judgment = "possible"
        elif high_priority_hits == 0:
            judgment = "insufficient_information"
        else:
            judgment = "unlikely"
        return RalphBlindAnalysis(
            source_case_id=packet.source_case_id,
            anonymous_case_id=packet.anonymous_case_id,
            as_of_date=packet.as_of_date,
            scheme_version=packet.scheme_version,
            surge_candidate=judgment,
            surge_candidate_reason=(
                "Heuristic Ralph validation from prioritized catalyst, expectation, theme, timing, "
                "and risk sections only."
            ),
            expectation_gap=_first_item_summary(sections.get("Expectation Gap Summary")),
            pre_surge_signals=tuple(
                summary
                for summary in (
                    _first_item_summary(sections.get("Catalyst/Event Ledger")),
                    _first_item_summary(sections.get("Theme/Industry Transmission")),
                    _first_item_summary(sections.get("Materiality and Timing")),
                )
                if summary != "No scheme evidence supplied."
            )
            or ("No strong scheme-level pre-surge signal found.",),
            contrary_evidence=_section_summaries(sections.get("Contrary/Risk Evidence"))
            or ("No contrary evidence supplied by the scheme packet.",),
            catalyst_watch=_section_summaries(sections.get("Catalyst/Event Ledger")),
            missing_context=tuple(
                f"{name} has no concrete items."
                for name in HIGH_PRIORITY_SECTION_NAMES
                if sections.get(name) is None or not sections[name].items
            ),
            confidence=round(confidence, 4),
            raw_text="heuristic-ralph",
        )


class OpenAIRalphBlindResearcher:
    """OpenAI-backed blind validator for Ralph scheme packets."""

    def __init__(self, client: OpenAIChatClient, *, max_attempts: int = 2) -> None:
        if max_attempts < 1:
            raise ValidationError("max_attempts must be at least 1")
        self.client = client
        self.max_attempts = max_attempts

    def analyze(self, packet: BlindSchemePacket) -> RalphBlindAnalysis:
        """Analyze a scheme-built blind packet using no web tools."""

        last_error: ValidationError | None = None
        for attempt in range(self.max_attempts):
            response = self.client.complete(
                [
                    ChatMessage(
                        "developer",
                        (
                            "You are validating a proposed cold-start information scheme. "
                            "Use only the supplied anonymous as-of packet. Web search is disabled. "
                            "Do not infer or mention any hidden outcome group, ticker, company name, "
                            "future return, or post-as-of fact. Return strict concise JSON."
                            " Include missing_context for evidence buckets that prevent a confident judgment."
                        ),
                    ),
                    ChatMessage("user", json.dumps(packet.to_prompt_dict(), indent=2, sort_keys=True)),
                ],
                max_output_tokens=2200,
                response_format={"type": "json_object"},
            )
            try:
                return _ralph_analysis_from_json(packet, response.output_text)
            except ValidationError as exc:
                last_error = exc
                if attempt + 1 >= self.max_attempts:
                    break
        raise last_error or ValidationError("Ralph blind analysis failed")


@dataclass(frozen=True)
class SchemeEvaluation:
    """Retrospective evaluation of blind judgments against known outcomes."""

    stage_boundary: str
    scheme_version: str
    case_count: int
    confidence_gap: float
    average_confidence_by_group: dict[str, float]
    judgment_distribution_by_group: dict[str, dict[str, int]]
    false_positive_controls: tuple[str, ...]
    false_negative_winners: tuple[str, ...]
    false_positive_rate: float
    false_negative_rate: float
    unable_to_judge_reasons: tuple[str, ...]
    separation_passed: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible evaluation."""

        return {
            "stage_boundary": self.stage_boundary,
            "scheme_version": self.scheme_version,
            "case_count": self.case_count,
            "confidence_gap": self.confidence_gap,
            "average_confidence_by_group": dict(self.average_confidence_by_group),
            "judgment_distribution_by_group": {
                group: dict(counts)
                for group, counts in self.judgment_distribution_by_group.items()
            },
            "false_positive_controls": list(self.false_positive_controls),
            "false_negative_winners": list(self.false_negative_winners),
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "unable_to_judge_reasons": list(self.unable_to_judge_reasons),
            "separation_passed": self.separation_passed,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RalphErrorAnalysis:
    """Explanation of why a scheme did or did not separate winners and controls."""

    stage_boundary: str
    scheme_version: str
    separation_passed: bool
    missing_evidence_families: tuple[str, ...]
    structure_issues: tuple[str, ...]
    false_positive_controls: tuple[str, ...]
    false_negative_winners: tuple[str, ...]
    unable_to_judge_reasons: tuple[str, ...]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible error analysis."""

        return {
            "stage_boundary": self.stage_boundary,
            "scheme_version": self.scheme_version,
            "separation_passed": self.separation_passed,
            "missing_evidence_families": list(self.missing_evidence_families),
            "structure_issues": list(self.structure_issues),
            "false_positive_controls": list(self.false_positive_controls),
            "false_negative_winners": list(self.false_negative_winners),
            "unable_to_judge_reasons": list(self.unable_to_judge_reasons),
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class RalphLoopIteration:
    """One Ralph diagnosis, validation, evaluation, and feedback pass."""

    iteration: int
    scheme: InformationScheme
    diagnostic: RalphDiagnosticReport
    evaluation: SchemeEvaluation
    error_analysis: RalphErrorAnalysis
    next_scheme_proposal: InformationScheme | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible iteration record."""

        return {
            "iteration": self.iteration,
            "scheme": self.scheme.to_dict(),
            "diagnostic": self.diagnostic.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "error_analysis": self.error_analysis.to_dict(),
            "next_scheme_proposal": (
                self.next_scheme_proposal.to_dict() if self.next_scheme_proposal is not None else None
            ),
        }


@dataclass(frozen=True)
class RalphLoopResult:
    """Complete Ralph Loop output before artifact persistence."""

    run_id: str
    information_scheme: InformationScheme
    baseline_evaluation: SchemeEvaluation
    iterations: tuple[RalphLoopIteration, ...]
    blind_packets_by_scheme: dict[str, tuple[BlindSchemePacket, ...]]
    blind_analyses_by_scheme: dict[str, tuple[RalphBlindAnalysis, ...]]
    next_scheme_proposal: InformationScheme | None
    warnings: tuple[str, ...]

    @property
    def latest_evaluation(self) -> SchemeEvaluation:
        """Return the most recent validated scheme evaluation."""

        return self.iterations[-1].evaluation

    @property
    def latest_error_analysis(self) -> RalphErrorAnalysis:
        """Return the most recent scheme error analysis."""

        return self.iterations[-1].error_analysis

    def information_scheme_artifact(self, created_at: datetime) -> dict[str, Any]:
        """Return the `information_scheme.json` artifact body."""

        return {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": self.run_id,
            "created_at": created_at.isoformat(),
            "stage_boundary": "retrospective_label_aware",
            "active_scheme": self.information_scheme.to_dict(),
            "next_scheme_proposal": (
                self.next_scheme_proposal.to_dict() if self.next_scheme_proposal is not None else None
            ),
            "promotion_status": "pending_human_review",
        }

    def iterations_artifact(self) -> dict[str, Any]:
        """Return the `ralph_loop_iterations.json` artifact body."""

        return {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": self.run_id,
            "iterations": [iteration.to_dict() for iteration in self.iterations],
            "warnings": list(self.warnings),
        }

    def blind_packets_artifact(self) -> dict[str, Any]:
        """Return the `blind_packets_by_scheme.json` artifact body."""

        return {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": self.run_id,
            "blind_packets_by_scheme": {
                version: [packet.to_dict() for packet in packets]
                for version, packets in sorted(self.blind_packets_by_scheme.items())
            },
            "blind_analyses_by_scheme": {
                version: [analysis.to_dict() for analysis in analyses]
                for version, analyses in sorted(self.blind_analyses_by_scheme.items())
            },
        }

    def evaluation_artifact(self) -> dict[str, Any]:
        """Return the `blind_scheme_evaluation.json` artifact body."""

        return {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": self.run_id,
            "stage_boundary": "retrospective_label_aware",
            "baseline": self.baseline_evaluation.to_dict(),
            "evaluated_schemes": [iteration.evaluation.to_dict() for iteration in self.iterations],
            "side_by_side": [
                {
                    "baseline_scheme_version": self.baseline_evaluation.scheme_version,
                    "ralph_scheme_version": iteration.evaluation.scheme_version,
                    "baseline_confidence_gap": self.baseline_evaluation.confidence_gap,
                    "ralph_confidence_gap": iteration.evaluation.confidence_gap,
                    "baseline_false_positive_controls": list(
                        self.baseline_evaluation.false_positive_controls
                    ),
                    "ralph_false_positive_controls": list(iteration.evaluation.false_positive_controls),
                    "baseline_false_negative_winners": list(
                        self.baseline_evaluation.false_negative_winners
                    ),
                    "ralph_false_negative_winners": list(iteration.evaluation.false_negative_winners),
                }
                for iteration in self.iterations
            ],
        }

    def error_analysis_artifact(self) -> dict[str, Any]:
        """Return the `ralph_error_analysis.json` artifact body."""

        return {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": self.run_id,
            "stage_boundary": "retrospective_label_aware",
            "error_analyses": [iteration.error_analysis.to_dict() for iteration in self.iterations],
        }


@dataclass(frozen=True)
class RalphHoldoutFeedbackIteration:
    """One holdout-feedback proposal and blind re-evaluation pass."""

    iteration: int
    scheme: InformationScheme
    packets: tuple[BlindSchemePacket, ...]
    analyses: tuple[RalphBlindAnalysis, ...]
    evaluation: SchemeEvaluation
    error_analysis: RalphErrorAnalysis

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible holdout feedback artifacts."""

        return {
            "iteration": self.iteration,
            "scheme": self.scheme.to_dict(),
            "holdout_blind_packets": [packet.to_dict() for packet in self.packets],
            "holdout_blind_analyses": [analysis.to_dict() for analysis in self.analyses],
            "holdout_evaluation": self.evaluation.to_dict(),
            "holdout_error_analysis": self.error_analysis.to_dict(),
        }


@dataclass(frozen=True)
class RalphExperimentResult:
    """Train/holdout Ralph experiment result."""

    run_id: str
    refinement_case_ids: tuple[str, ...]
    holdout_case_ids: tuple[str, ...]
    refinement_loop: RalphLoopResult
    holdout_packets: tuple[BlindSchemePacket, ...]
    holdout_analyses: tuple[RalphBlindAnalysis, ...]
    holdout_evaluation: SchemeEvaluation
    holdout_error_analysis: RalphErrorAnalysis
    initial_holdout_evaluation: SchemeEvaluation
    initial_holdout_error_analysis: RalphErrorAnalysis
    holdout_feedback_iterations: tuple[RalphHoldoutFeedbackIteration, ...]
    final_status: str
    final_recommendation: str

    @property
    def final_information_scheme(self) -> InformationScheme:
        """Return the final scheme evaluated on holdout."""

        if self.holdout_feedback_iterations:
            return self.holdout_feedback_iterations[-1].scheme
        return self.refinement_loop.information_scheme

    def to_summary_dict(self) -> dict[str, Any]:
        """Return a concise JSON-compatible experiment summary."""

        return {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": self.run_id,
            "refinement_case_ids": list(self.refinement_case_ids),
            "holdout_case_ids": list(self.holdout_case_ids),
            "final_information_scheme": self.final_information_scheme.to_dict(),
            "refinement_latest_evaluation": self.refinement_loop.latest_evaluation.to_dict(),
            "initial_holdout_evaluation": self.initial_holdout_evaluation.to_dict(),
            "initial_holdout_error_analysis": self.initial_holdout_error_analysis.to_dict(),
            "holdout_feedback_iterations": [
                {
                    "iteration": iteration.iteration,
                    "scheme_version": iteration.scheme.version,
                    "holdout_evaluation": iteration.evaluation.to_dict(),
                    "holdout_error_analysis": iteration.error_analysis.to_dict(),
                }
                for iteration in self.holdout_feedback_iterations
            ],
            "holdout_evaluation": self.holdout_evaluation.to_dict(),
            "holdout_error_analysis": self.holdout_error_analysis.to_dict(),
            "refinement_schema_diffs": [
                _scheme_diff(iteration.scheme, iteration.next_scheme_proposal)
                for iteration in self.refinement_loop.iterations
                if iteration.next_scheme_proposal is not None
            ],
            "final_status": self.final_status,
            "final_recommendation": self.final_recommendation,
            "can_enter_long_running_default": False,
        }


def run_ralph_loop(
    cases: Iterable[HistoricalCase],
    *,
    baseline_blind_analyses: Iterable[BlindCaseAnalysis],
    learning_result: ColdStartLearningResult,
    theme_maps: ThemeMapBuildResult,
    playbook_synthesis: SurgePlaybookSynthesis,
    run_id: str,
    blind_researcher: RalphBlindResearcher | None = None,
    max_iterations: int = 1,
    coverage_reports: Mapping[str, Any] | None = None,
) -> RalphLoopResult:
    """Run bounded Ralph Loop diagnosis, scheme validation, and feedback."""

    if max_iterations < 1 or max_iterations > 4:
        raise ValidationError("Ralph Loop v1 supports one to four bounded iterations")
    case_list = list(cases)
    if not case_list:
        raise ValidationError("Ralph Loop requires at least one historical case")
    baseline = evaluate_scheme_performance(
        case_list,
        tuple(baseline_blind_analyses),
        scheme_version="baseline_blind_prompt",
    )
    researcher = blind_researcher or HeuristicRalphBlindResearcher()
    iterations: list[RalphLoopIteration] = []
    packets_by_scheme: dict[str, tuple[BlindSchemePacket, ...]] = {}
    analyses_by_scheme: dict[str, tuple[RalphBlindAnalysis, ...]] = {}
    previous_error: RalphErrorAnalysis | None = None
    next_proposal: InformationScheme | None = None

    for iteration_number in range(1, max_iterations + 1):
        synthesized_scheme, diagnostic = synthesize_information_scheme(
            case_list,
            learning_result=learning_result,
            theme_maps=theme_maps,
            playbook_synthesis=playbook_synthesis,
            iteration=iteration_number,
            previous_error=previous_error,
            coverage_reports=coverage_reports,
        )
        scheme = next_proposal or synthesized_scheme
        packets = tuple(
            build_blind_scheme_packet(
                case,
                scheme,
                anonymous_case_id=f"case_{index:03d}",
            )
            for index, case in enumerate(case_list, start=1)
        )
        analyses = tuple(researcher.analyze(packet) for packet in packets)
        evaluation = evaluate_scheme_performance(case_list, analyses, scheme_version=scheme.version)
        error_analysis = analyze_scheme_errors(evaluation, diagnostic)
        next_proposal = None if evaluation.separation_passed else propose_next_information_scheme(
            scheme,
            error_analysis,
        )
        iterations.append(
            RalphLoopIteration(
                iteration=iteration_number,
                scheme=scheme,
                diagnostic=diagnostic,
                evaluation=evaluation,
                error_analysis=error_analysis,
                next_scheme_proposal=next_proposal,
            )
        )
        packets_by_scheme[scheme.version] = packets
        analyses_by_scheme[scheme.version] = analyses
        if evaluation.separation_passed or iteration_number == max_iterations:
            break
        previous_error = error_analysis

    warnings = tuple(
        warning
        for iteration in iterations
        for warning in iteration.evaluation.warnings
    )
    return RalphLoopResult(
        run_id=run_id,
        information_scheme=iterations[-1].scheme,
        baseline_evaluation=baseline,
        iterations=tuple(iterations),
        blind_packets_by_scheme=packets_by_scheme,
        blind_analyses_by_scheme=analyses_by_scheme,
        next_scheme_proposal=next_proposal,
        warnings=warnings,
    )


def run_ralph_experiment(
    refinement_cases: Iterable[HistoricalCase],
    holdout_cases: Iterable[HistoricalCase],
    *,
    baseline_refinement_blind_analyses: Iterable[BlindCaseAnalysis],
    learning_result: ColdStartLearningResult,
    theme_maps: ThemeMapBuildResult,
    playbook_synthesis: SurgePlaybookSynthesis,
    run_id: str,
    blind_researcher: RalphBlindResearcher,
    max_iterations: int = 2,
    refinement_coverage_reports: Mapping[str, Any] | None = None,
    holdout_feedback_iterations: int = 0,
) -> RalphExperimentResult:
    """Run Ralph on refinement cases, then evaluate the final scheme on holdout cases."""

    if holdout_feedback_iterations < 0 or holdout_feedback_iterations > 3:
        raise ValidationError("holdout feedback supports zero to three bounded iterations")
    refinement_list = list(refinement_cases)
    holdout_list = list(holdout_cases)
    if not refinement_list or not holdout_list:
        raise ValidationError("Ralph experiment requires refinement and holdout cases")
    refinement_ids = {case.case_id for case in refinement_list}
    holdout_ids = {case.case_id for case in holdout_list}
    if refinement_ids & holdout_ids:
        raise ValidationError("Ralph refinement and holdout cases must not overlap")
    refinement_loop = run_ralph_loop(
        refinement_list,
        baseline_blind_analyses=baseline_refinement_blind_analyses,
        learning_result=learning_result,
        theme_maps=theme_maps,
        playbook_synthesis=playbook_synthesis,
        run_id=run_id,
        blind_researcher=blind_researcher,
        max_iterations=max_iterations,
        coverage_reports=refinement_coverage_reports,
    )
    final_scheme = refinement_loop.information_scheme
    holdout_packets = tuple(
        build_blind_scheme_packet(
            case,
            final_scheme,
            anonymous_case_id=f"holdout_{index:03d}",
        )
        for index, case in enumerate(holdout_list, start=1)
    )
    holdout_analyses = tuple(blind_researcher.analyze(packet) for packet in holdout_packets)
    holdout_evaluation = evaluate_scheme_performance(
        holdout_list,
        holdout_analyses,
        scheme_version=final_scheme.version + ":holdout",
    )
    _, holdout_diagnostic = synthesize_information_scheme(
        refinement_list,
        learning_result=learning_result,
        theme_maps=theme_maps,
        playbook_synthesis=playbook_synthesis,
        iteration=len(refinement_loop.iterations),
        coverage_reports=refinement_coverage_reports,
    )
    holdout_error = analyze_scheme_errors(holdout_evaluation, holdout_diagnostic)
    initial_holdout_evaluation = holdout_evaluation
    initial_holdout_error = holdout_error
    feedback_iterations: list[RalphHoldoutFeedbackIteration] = []
    active_scheme = final_scheme
    for feedback_number in range(1, holdout_feedback_iterations + 1):
        if holdout_evaluation.separation_passed:
            break
        active_scheme = propose_next_information_scheme(active_scheme, holdout_error)
        holdout_packets = tuple(
            build_blind_scheme_packet(
                case,
                active_scheme,
                anonymous_case_id=f"holdout_{index:03d}",
            )
            for index, case in enumerate(holdout_list, start=1)
        )
        holdout_analyses = tuple(blind_researcher.analyze(packet) for packet in holdout_packets)
        holdout_evaluation = evaluate_scheme_performance(
            holdout_list,
            holdout_analyses,
            scheme_version=active_scheme.version + ":holdout_feedback",
        )
        holdout_error = analyze_scheme_errors(holdout_evaluation, holdout_diagnostic)
        feedback_iterations.append(
            RalphHoldoutFeedbackIteration(
                iteration=feedback_number,
                scheme=active_scheme,
                packets=holdout_packets,
                analyses=holdout_analyses,
                evaluation=holdout_evaluation,
                error_analysis=holdout_error,
            )
        )
    final_status = "holdout_separated" if holdout_evaluation.separation_passed else "holdout_not_separated"
    recommendation = (
        "Information scheme separated winners and controls in the small holdout experiment; keep as reviewed proposal."
        if holdout_evaluation.separation_passed
        else "Do not promote; inspect missing evidence and continue Ralph refinement before long-running use."
    )
    return RalphExperimentResult(
        run_id=run_id,
        refinement_case_ids=tuple(case.case_id for case in refinement_list),
        holdout_case_ids=tuple(case.case_id for case in holdout_list),
        refinement_loop=refinement_loop,
        holdout_packets=holdout_packets,
        holdout_analyses=holdout_analyses,
        holdout_evaluation=holdout_evaluation,
        holdout_error_analysis=holdout_error,
        initial_holdout_evaluation=initial_holdout_evaluation,
        initial_holdout_error_analysis=initial_holdout_error,
        holdout_feedback_iterations=tuple(feedback_iterations),
        final_status=final_status,
        final_recommendation=recommendation,
    )


def synthesize_information_scheme(
    cases: Iterable[HistoricalCase],
    *,
    learning_result: ColdStartLearningResult,
    theme_maps: ThemeMapBuildResult,
    playbook_synthesis: SurgePlaybookSynthesis,
    iteration: int = 1,
    previous_error: RalphErrorAnalysis | None = None,
    coverage_reports: Mapping[str, Any] | None = None,
) -> tuple[InformationScheme, RalphDiagnosticReport]:
    """Create an information scheme from retrospective cold-start artifacts."""

    case_list = list(cases)
    diagnostics = _evidence_family_diagnostics(case_list)
    top_families = tuple(
        item.family
        for item in sorted(diagnostics, key=lambda item: item.separation_lift, reverse=True)
        if item.separation_lift > 0
    )[:5]
    sections = _default_sections()
    if previous_error is not None:
        sections = _sections_after_feedback(sections, previous_error)
    scheme = InformationScheme(
        scheme_id="ralph-information-scheme",
        version=f"information-scheme-v0.{iteration}",
        sections=sections,
        total_token_budget=sum(section.token_budget for section in sections),
        max_compressed_context_share=0.30,
        contrary_evidence_required=True,
        compression_rules=(
            "Prioritize source-backed events, expectation gaps, theme transmission, materiality, timing, and risks.",
            "Compress fundamentals and market confirmation to a short background snapshot.",
            "Exclude source URLs, source ids, ticker, company name, future returns, and outcome groups from blind packets.",
            "Include missing-evidence notes rather than filling gaps with narrative.",
        ),
    )
    diagnostic = RalphDiagnosticReport(
        stage_boundary="retrospective_label_aware",
        case_count=len(case_list),
        outcome_group_counts=_group_counts(case_list),
        evidence_family_diagnostics=diagnostics,
        top_distinguishing_families=top_families,
        false_positive_traps=_false_positive_traps(learning_result, playbook_synthesis),
        source_artifacts=(
            "historical_cases",
            "documents/catalysts",
            "coverage_report",
            "blind_case_analyses",
            "case_signal_observations",
            "theme_maps",
            "surge_research_playbooks",
        ),
        coverage_summary=_coverage_summary(coverage_reports),
    )
    return scheme, diagnostic


def build_blind_scheme_packet(
    case: HistoricalCase,
    scheme: InformationScheme,
    *,
    anonymous_case_id: str,
) -> BlindSchemePacket:
    """Render an anonymous blind packet according to an information scheme."""

    packet = case.packet
    tokens = _identity_tokens(packet)
    sections = tuple(
        _render_section(packet, section, tokens)
        for section in sorted(scheme.sections, key=lambda item: item.priority)
    )
    return BlindSchemePacket(
        source_case_id=case.case_id,
        anonymous_case_id=anonymous_case_id,
        as_of_date=packet.as_of.as_of_date.isoformat(),
        scheme_id=scheme.scheme_id,
        scheme_version=scheme.version,
        sections=sections,
    )


def evaluate_scheme_performance(
    cases: Iterable[HistoricalCase],
    analyses: Iterable[BlindCaseAnalysis | RalphBlindAnalysis],
    *,
    scheme_version: str,
    confidence_threshold: float = 0.45,
    min_confidence_gap: float = 0.12,
    max_false_positive_rate: float = 0.25,
    max_false_negative_rate: float = 0.0,
) -> SchemeEvaluation:
    """Calculate winner/control separation metrics for blind judgments."""

    case_list = list(cases)
    analysis_by_case = {_analysis_case_id(analysis): analysis for analysis in analyses}
    by_group: dict[str, list[BlindCaseAnalysis | RalphBlindAnalysis]] = {}
    distributions: dict[str, dict[str, int]] = {}
    false_positive_controls: list[str] = []
    false_negative_winners: list[str] = []
    unable_to_judge: list[str] = []
    warnings: list[str] = []

    for case in case_list:
        analysis = analysis_by_case.get(case.case_id)
        if analysis is None:
            warnings.append(f"missing blind analysis for {case.case_id}")
            continue
        group = case.label.value
        by_group.setdefault(group, []).append(analysis)
        distributions.setdefault(group, {})
        judgment = _analysis_judgment(analysis)
        distributions[group][judgment] = distributions[group].get(judgment, 0) + 1
        positive = judgment in {"likely", "possible"} and _analysis_confidence(analysis) >= confidence_threshold
        if case.label is CaseOutcomeLabel.CONTROL and positive:
            false_positive_controls.append(case.case_id)
            unable_to_judge.append(_analysis_reason(analysis))
            unable_to_judge.extend(_analysis_missing_context(analysis))
        if case.label is CaseOutcomeLabel.WINNER and not positive:
            false_negative_winners.append(case.case_id)
            unable_to_judge.append(_analysis_reason(analysis))
            unable_to_judge.extend(_analysis_missing_context(analysis))
        if judgment == "insufficient_information":
            unable_to_judge.append(_analysis_reason(analysis))
        if judgment == "insufficient_information" or _analysis_confidence(analysis) < confidence_threshold:
            unable_to_judge.extend(_analysis_missing_context(analysis))

    averages = {
        group: round(_average(_analysis_confidence(item) for item in group_analyses), 4)
        for group, group_analyses in sorted(by_group.items())
    }
    winner_average = averages.get(CaseOutcomeLabel.WINNER.value, 0.0)
    control_average = averages.get(CaseOutcomeLabel.CONTROL.value, 0.0)
    gap = round(winner_average - control_average, 4)
    control_count = len(by_group.get(CaseOutcomeLabel.CONTROL.value, ()))
    winner_count = len(by_group.get(CaseOutcomeLabel.WINNER.value, ()))
    false_positive_rate = round(_safe_ratio(len(false_positive_controls), control_count), 4)
    false_negative_rate = round(_safe_ratio(len(false_negative_winners), winner_count), 4)
    separation_passed = (
        gap >= min_confidence_gap
        and false_positive_rate <= max_false_positive_rate
        and false_negative_rate <= max_false_negative_rate
    )
    if CaseOutcomeLabel.WINNER.value not in averages:
        warnings.append("no winner analyses available for separation metrics")
    if CaseOutcomeLabel.CONTROL.value not in averages:
        warnings.append("no control analyses available for separation metrics")
    return SchemeEvaluation(
        stage_boundary="retrospective_label_aware",
        scheme_version=scheme_version,
        case_count=len(case_list),
        confidence_gap=gap,
        average_confidence_by_group=averages,
        judgment_distribution_by_group=distributions,
        false_positive_controls=tuple(false_positive_controls),
        false_negative_winners=tuple(false_negative_winners),
        false_positive_rate=false_positive_rate,
        false_negative_rate=false_negative_rate,
        unable_to_judge_reasons=tuple(unable_to_judge),
        separation_passed=separation_passed,
        warnings=tuple(warnings),
    )


def analyze_scheme_errors(
    evaluation: SchemeEvaluation,
    diagnostic: RalphDiagnosticReport,
) -> RalphErrorAnalysis:
    """Explain remaining separation failures and likely information gaps."""

    weak_families = tuple(
        item.family
        for item in diagnostic.evidence_family_diagnostics
        if item.family in _priority_family_names() and item.winner_prevalence < 0.5
    )
    coverage_missing = tuple(
        bucket
        for bucket, count in sorted(diagnostic.coverage_summary.get("missing_bucket_counts", {}).items())
        if count
    )
    structure_issues: list[str] = []
    if evaluation.false_positive_controls:
        structure_issues.append(
            "Controls still look positive; require stronger materiality, timing, and contrary-evidence contrast."
        )
    if evaluation.false_negative_winners:
        structure_issues.append(
            "Winners still look weak; missing or underweighted catalyst, expectation-gap, or theme-transmission evidence."
        )
    if evaluation.confidence_gap < 0.12:
        structure_issues.append(
            "Winner/control confidence gap remains too small; packet weighting or evidence specificity is insufficient."
        )
    if evaluation.unable_to_judge_reasons:
        structure_issues.append("Some cases remain insufficient because required evidence buckets are missing.")
    feedback_missing = _feedback_missing_families_from_reasons(evaluation.unable_to_judge_reasons)
    recommendation = (
        "Keep scheme proposal in cold-start artifacts for human review."
        if evaluation.separation_passed
        else "Generate a next proposal that increases concrete catalyst, expectation-gap, theme, timing, and risk budgets."
    )
    return RalphErrorAnalysis(
        stage_boundary="retrospective_label_aware",
        scheme_version=evaluation.scheme_version,
        separation_passed=evaluation.separation_passed,
        missing_evidence_families=tuple(dict.fromkeys(feedback_missing + weak_families + coverage_missing)),
        structure_issues=tuple(structure_issues or ("No material separation issue detected.",)),
        false_positive_controls=evaluation.false_positive_controls,
        false_negative_winners=evaluation.false_negative_winners,
        unable_to_judge_reasons=evaluation.unable_to_judge_reasons,
        recommendation=recommendation,
    )


def propose_next_information_scheme(
    scheme: InformationScheme,
    error_analysis: RalphErrorAnalysis,
) -> InformationScheme:
    """Generate a proposal-only next scheme from Ralph error analysis."""

    sections = []
    missing = set(error_analysis.missing_evidence_families)
    for section in scheme.sections:
        budget = section.token_budget
        max_items = section.max_items
        rule = section.compression_rule
        if section.name in HIGH_PRIORITY_SECTION_NAMES:
            budget += 100
            max_items += 1
        if section.name in COMPRESSED_SECTION_NAMES:
            budget = max(120, budget - 60)
            max_items = max(3, max_items - 1)
        if missing and any(bucket in missing for bucket in section.evidence_buckets):
            rule = rule + " Require explicit missing-evidence notes when this bucket is thin."
        sections.append(
            InformationSection(
                name=section.name,
                priority=section.priority,
                token_budget=budget,
                evidence_buckets=section.evidence_buckets,
                compression_rule=rule,
                required=section.required,
                max_items=max_items,
                role=section.role,
            )
        )
    return InformationScheme(
        scheme_id=scheme.scheme_id,
        version=_next_scheme_version(scheme.version),
        sections=tuple(sections),
        total_token_budget=sum(section.token_budget for section in sections),
        max_compressed_context_share=scheme.max_compressed_context_share,
        contrary_evidence_required=scheme.contrary_evidence_required,
        compression_rules=scheme.compression_rules
        + (
            "Feedback proposal: reduce raw table dominance and force explicit evidence-gap notes.",
        ),
        proposal_status="proposal_only_pending_review",
    )


def write_ralph_loop_artifacts(
    result: RalphLoopResult,
    output_dir: str | Path,
    *,
    created_at: datetime,
    proposal_memory_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Write Ralph Loop artifacts and optional local proposal memory."""

    base_dir = Path(output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "information_scheme": base_dir / "information_scheme.json",
        "ralph_loop_iterations": base_dir / "ralph_loop_iterations.json",
        "blind_packets_by_scheme": base_dir / "blind_packets_by_scheme.json",
        "blind_scheme_evaluation": base_dir / "blind_scheme_evaluation.json",
        "ralph_error_analysis": base_dir / "ralph_error_analysis.json",
    }
    _write_json(paths["information_scheme"], result.information_scheme_artifact(created_at))
    _write_json(paths["ralph_loop_iterations"], result.iterations_artifact())
    _write_json(paths["blind_packets_by_scheme"], result.blind_packets_artifact())
    _write_json(paths["blind_scheme_evaluation"], result.evaluation_artifact())
    _write_json(paths["ralph_error_analysis"], result.error_analysis_artifact())
    if proposal_memory_dir is not None:
        paths["information_scheme_proposal_memory"] = write_information_scheme_proposal_memory(
            proposal_memory_dir,
            result,
            created_at=created_at,
        )
    return paths


def write_ralph_experiment_artifacts(
    result: RalphExperimentResult,
    output_dir: str | Path,
    *,
    created_at: datetime,
    proposal_memory_dir: str | Path | None = None,
    extra_output_paths: Mapping[str, str | Path] | None = None,
) -> dict[str, Path]:
    """Write refinement and holdout Ralph experiment artifacts."""

    base_dir = Path(output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    paths = write_ralph_loop_artifacts(
        result.refinement_loop,
        base_dir,
        created_at=created_at,
        proposal_memory_dir=proposal_memory_dir,
    )
    experiment_paths = {
        "ralph_experiment_summary": base_dir / "ralph_experiment_summary.json",
        "holdout_blind_packets_by_scheme": base_dir / "holdout_blind_packets_by_scheme.json",
        "holdout_blind_scheme_evaluation": base_dir / "holdout_blind_scheme_evaluation.json",
        "holdout_error_analysis": base_dir / "holdout_error_analysis.json",
        "holdout_feedback_iterations": base_dir / "holdout_feedback_iterations.json",
        "manifest": base_dir / "manifest.json",
    }
    paths.update(experiment_paths)
    if extra_output_paths:
        paths.update({name: Path(path) for name, path in extra_output_paths.items()})
    _write_json(experiment_paths["ralph_experiment_summary"], result.to_summary_dict())
    _write_json(
        experiment_paths["holdout_blind_packets_by_scheme"],
        {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": result.run_id,
            "scheme_version": result.final_information_scheme.version,
            "holdout_blind_packets": [packet.to_dict() for packet in result.holdout_packets],
            "holdout_blind_analyses": [analysis.to_dict() for analysis in result.holdout_analyses],
            "initial_holdout_evaluation": result.initial_holdout_evaluation.to_dict(),
        },
    )
    _write_json(
        experiment_paths["holdout_blind_scheme_evaluation"],
        {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": result.run_id,
            "stage_boundary": "retrospective_label_aware_holdout",
            "evaluation": result.holdout_evaluation.to_dict(),
        },
    )
    _write_json(
        experiment_paths["holdout_error_analysis"],
        {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": result.run_id,
            "stage_boundary": "retrospective_label_aware_holdout",
            "error_analysis": result.holdout_error_analysis.to_dict(),
        },
    )
    _write_json(
        experiment_paths["holdout_feedback_iterations"],
        {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": result.run_id,
            "stage_boundary": "retrospective_label_aware_holdout_feedback",
            "initial_holdout_evaluation": result.initial_holdout_evaluation.to_dict(),
            "initial_holdout_error_analysis": result.initial_holdout_error_analysis.to_dict(),
            "iterations": [iteration.to_dict() for iteration in result.holdout_feedback_iterations],
            "promotion_status": "pending_human_review",
            "can_enter_long_running_default": False,
        },
    )
    _write_json(
        experiment_paths["manifest"],
        {
            "schema_version": RALPH_LOOP_SCHEMA_VERSION,
            "run_id": result.run_id,
            "created_at": created_at.isoformat(),
            "pipeline": "ralph_loop_experiment",
            "stage_boundary": "retrospective_label_aware_refinement_then_blind_holdout",
            "scheme_version": result.final_information_scheme.version,
            "iteration_count": len(result.refinement_loop.iterations),
            "holdout_feedback_iteration_count": len(result.holdout_feedback_iterations),
            "refinement_case_count": len(result.refinement_case_ids),
            "holdout_case_count": len(result.holdout_case_ids),
            "final_status": result.final_status,
            "final_recommendation": result.final_recommendation,
            "holdout_confidence_gap": result.holdout_evaluation.confidence_gap,
            "holdout_false_positive_rate": result.holdout_evaluation.false_positive_rate,
            "holdout_false_negative_rate": result.holdout_evaluation.false_negative_rate,
            "promotion_status": "pending_human_review",
            "can_enter_long_running_default": False,
            "outputs": {name: str(path) for name, path in sorted(paths.items())},
            "warnings": list(result.refinement_loop.warnings)
            + list(result.holdout_evaluation.warnings),
        },
    )
    return paths


def write_information_scheme_proposal_memory(
    proposal_memory_dir: str | Path,
    result: RalphLoopResult,
    *,
    created_at: datetime,
) -> Path:
    """Append the latest Ralph scheme proposal to local proposal memory."""

    root = Path(proposal_memory_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "information_scheme_proposals.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    proposals = data.get("proposals")
    if not isinstance(proposals, list):
        proposals = []
    proposal = result.next_scheme_proposal or result.information_scheme
    proposals.append(
        {
            "created_at": created_at.isoformat(),
            "run_id": result.run_id,
            "approval_state": "pending_human_review",
            "source": "ralph_loop",
            "scheme": proposal.to_dict(),
            "evaluation_summary": result.latest_evaluation.to_dict(),
            "error_analysis": result.latest_error_analysis.to_dict(),
        }
    )
    _write_json(
        path,
        {
            "schema_version": "information-scheme-proposal-memory-v0.1",
            "proposals": proposals,
        },
    )
    return path


def _default_sections() -> tuple[InformationSection, ...]:
    return (
        InformationSection(
            "Catalyst/Event Ledger",
            1,
            900,
            (
                "catalyst_event",
                "source_detail_digest",
                "deal_status_timing",
                "orders_contracts",
                "policy_regulatory",
                "funding_subsidy",
            ),
            "List concrete source-backed events first; prefer orders, contracts, approvals, funding, and deadlines.",
            max_items=5,
        ),
        InformationSection(
            "Expectation Gap Summary",
            2,
            760,
            ("expectation_gap", "guidance_revision", "analyst_disagreement"),
            "Summarize why expectations could lag as-of facts; exclude later outcomes.",
            max_items=4,
        ),
        InformationSection(
            "Theme/Industry Transmission",
            3,
            720,
            ("theme_industry_transmission", "customer_capacity", "ai_chain_bottleneck_transmission"),
            (
                "Explain how industry-chain or customer demand may transmit to this anonymous company. "
                "For AI-related evidence, map model/application demand through compute, data-center, "
                "power, cooling, networking, component, and customer-capex bottlenecks."
            ),
            max_items=4,
        ),
        InformationSection(
            "Materiality and Timing",
            4,
            620,
            (
                "materiality_timing",
                "source_detail_digest",
                "deal_status_timing",
                "customer_capacity",
                "orders_contracts",
            ),
            "Prefer evidence that is large enough and close enough to matter inside a 3-6 month window.",
            max_items=4,
        ),
        InformationSection(
            "Contrary/Risk Evidence",
            5,
            620,
            ("contrary_risk", "valuation_risk", "execution_risk", "capital_structure_liquidity"),
            "Name the best disconfirming facts and narrative traps before any positive conclusion.",
            max_items=4,
        ),
        InformationSection(
            "Compressed Fundamentals",
            6,
            260,
            ("fundamentals", "valuation"),
            "Use only a compact snapshot; do not paste raw financial tables.",
            max_items=3,
            role="compressed",
        ),
        InformationSection(
            "Compressed Market Confirmation",
            7,
            240,
            ("market_confirmation", "price_volume"),
            "Use only a compact trend and liquidity snapshot.",
            max_items=3,
            role="compressed",
        ),
    )


def _scheme_rubrics() -> dict[str, list[str]]:
    return {
        "catalyst_materiality": [
            "Prefer signed orders, contracts, funding awards, approvals, rate decisions, capacity openings, or management changes with dated as-of evidence.",
            "High materiality requires plausible revenue, cash flow, regulatory, financing, or sentiment impact inside 3-6 months.",
            "Downgrade vague calendar items, generic filings, or sector headlines with no company-level transmission.",
        ],
        "theme_transmission": [
            "Name the industry-chain path from theme to company economics.",
            "Distinguish direct beneficiaries from broad theme tourists.",
            "Require timing evidence that the theme can affect the as-of company within the evaluation horizon.",
        ],
        "ai_chain_bottleneck_transmission": [
            "For AI/data-center cases, map upstream and downstream bottlenecks from demand to company economics.",
            "Prefer direct exposure to compute, memory, networking, power, cooling, grid, construction, or customer capex over generic AI mentions.",
            "Require source-backed orders, capacity, funding, customer pull-through, or margin leverage before treating an AI-chain narrative as high conviction.",
        ],
        "contrary_evidence": [
            "Always include the strongest reason the case may be a false positive.",
            "Flag dilution, cash burn, debt, execution delay, regulatory opposition, already-priced momentum, and valuation stretch.",
            "If contrary evidence is missing, require the blind LLM to lower confidence or return insufficient_information.",
        ],
    }


def _sections_after_feedback(
    sections: tuple[InformationSection, ...],
    error_analysis: RalphErrorAnalysis,
) -> tuple[InformationSection, ...]:
    proposal = propose_next_information_scheme(
        InformationScheme(
            scheme_id="ralph-information-scheme",
            version=error_analysis.scheme_version,
            sections=sections,
            total_token_budget=sum(section.token_budget for section in sections),
            max_compressed_context_share=0.30,
            contrary_evidence_required=True,
            compression_rules=(),
        ),
        error_analysis,
    )
    return proposal.sections


def _render_section(
    packet: ResearchPacket,
    section: InformationSection,
    identity_tokens: tuple[str, ...],
) -> BlindPacketSection:
    raw_items = _section_items(packet, section.name)
    safe_items = tuple(
        _mask_identity_in_value(_strip_source_metadata(item), identity_tokens)
        for item in raw_items[: section.max_items]
    )
    return BlindPacketSection(
        name=section.name,
        priority=section.priority,
        token_budget=section.token_budget,
        compression_rule=section.compression_rule,
        items=safe_items,
        estimated_tokens=min(section.token_budget, _estimated_tokens(safe_items)),
    )


def _section_items(packet: ResearchPacket, section_name: str) -> list[dict[str, Any]]:
    if section_name == "Catalyst/Event Ledger":
        return _dedupe_items(
            _catalyst_items(packet)
            + _recent_source_detail_items(packet, _event_keywords())
            + _evidence_items(packet, _event_keywords())
        )
    if section_name == "Expectation Gap Summary":
        return _expectation_items(packet)
    if section_name == "Theme/Industry Transmission":
        return _theme_items(packet)
    if section_name == "Materiality and Timing":
        return _materiality_items(packet)
    if section_name == "Contrary/Risk Evidence":
        return _risk_items(packet)
    if section_name == "Compressed Fundamentals":
        return _feature_items(
            packet,
            ("financial.revenue_growth_yoy", "financial.earnings_growth_yoy", "financial.operating_margin_ttm",
             "valuation.pe_ratio", "valuation.price_to_sales_ttm", "valuation.market_cap_usd",
             "profile.sector", "profile.industry"),
        )
    if section_name == "Compressed Market Confirmation":
        return _feature_items(
            packet,
            ("price.return_20d", "price.return_60d", "price.latest_volume",
             "price.average_daily_dollar_volume_20d", "price.average_daily_dollar_volume_60d",
             "price.return_120d", "price.average_daily_dollar_volume_120d"),
        )
    return []


def _catalyst_items(packet: ResearchPacket) -> list[dict[str, Any]]:
    items = []
    for catalyst in packet.catalysts:
        days = (catalyst.expected_date - packet.as_of.as_of_date).days
        if -210 <= days <= 210:
            items.append(
                {
                    "item_type": "catalyst",
                    "summary": catalyst.name,
                    "expected_date": catalyst.expected_date.isoformat(),
                    "relative_timing_days": days,
                    "status": catalyst.status.value,
                    "supporting_evidence": [
                        _evidence_summary(item)
                        for item in catalyst.evidence[:2]
                    ],
                }
            )
    return items


def _expectation_items(packet: ResearchPacket) -> list[dict[str, Any]]:
    items = []
    market_gap = _market_expectation_item(packet)
    if market_gap is not None:
        items.append(market_gap)
    items.extend(_feature_items(packet, ("analyst.target_price", "price.latest_close")))
    features = {feature.name: feature.value for feature in packet.features}
    target = _numeric(features.get("analyst.target_price"))
    close = _numeric(features.get("price.latest_close"))
    if target > 0 and close > 0:
        items.insert(
            0,
            {
                "item_type": "expectation_gap",
                "summary": f"As-of target/price gap is {round((target / close) - 1, 4)}.",
            },
        )
    items.extend(_evidence_items(packet, ("expectation", "guidance", "estimate", "revision", "upside")))
    return items


def _market_expectation_item(packet: ResearchPacket) -> dict[str, Any] | None:
    features = {feature.name: feature.value for feature in packet.features}
    return_20d = _numeric(features.get("price.return_20d"))
    return_60d = _numeric(features.get("price.return_60d"))
    latest_close = _numeric(features.get("price.latest_close"))
    has_event_context = bool(packet.catalysts) or any(
        _contains_any(item.summary, _event_keywords()) for item in packet.evidence
    )
    if not has_event_context or (return_20d > -0.15 and return_60d > -0.25):
        return None
    return {
        "item_type": "expectation_gap",
        "summary": (
            "Depressed market setup before source-backed events: "
            f"20d return {round(return_20d, 4)}, 60d return {round(return_60d, 4)}, "
            f"latest close {round(latest_close, 4)}."
        ),
    }


def _theme_items(packet: ResearchPacket) -> list[dict[str, Any]]:
    items = [
        {
            "item_type": "theme_context",
            "summary": f"Theme exposure ids: {', '.join(packet.theme_ids[:3])}.",
        }
    ] if packet.theme_ids else []
    items.extend(_ai_chain_transmission_items(packet))
    items.extend(
        _evidence_by_kind(packet, {EvidenceKind.THEME_CONTEXT, EvidenceKind.RESEARCH_REPORT})
    )
    items.extend(
        _evidence_items(
            packet,
            (
                "supply chain",
                "capacity",
                "customer",
                "demand",
                "industry",
                "technology",
                "sensor",
                "screening",
                "clinical",
                "media",
                "ecommerce",
                "business combination",
                "merger",
                "listing",
            ),
        )
    )
    return items


def _ai_chain_transmission_items(packet: ResearchPacket) -> list[dict[str, Any]]:
    text = _packet_evidence_text(packet)
    if not _matches_ai_chain_keywords(text, _ai_chain_anchors()[0][1]):
        return []
    anchors = [
        label
        for label, keywords in _ai_chain_anchors()
        if _matches_ai_chain_keywords(text, keywords)
    ]
    if not anchors:
        return []
    return [
        {
            "item_type": "ai_chain_transmission",
            "summary": (
                "AI/data-center chain exposure detected from as-of evidence: "
                + ", ".join(anchors[:5])
                + ". Judge whether this is a direct bottleneck beneficiary with company-level orders, "
                "capacity, funding, or customer pull-through, not only a broad AI theme mention."
            ),
        }
    ]


def _materiality_items(packet: ResearchPacket) -> list[dict[str, Any]]:
    keywords = _materiality_keywords()
    items: list[dict[str, Any]] = []
    items.extend(_recent_source_detail_items(packet, keywords))
    for catalyst in packet.catalysts:
        days = (catalyst.expected_date - packet.as_of.as_of_date).days
        if -120 <= days <= 210:
            timing = (
                f"expected in {days} days"
                if days >= 0
                else f"observed {abs(days)} days before as-of"
            )
            items.append(
                {
                    "item_type": "timing",
                    "summary": f"Known catalyst {timing}.",
                    "expected_date": catalyst.expected_date.isoformat(),
                    "relative_timing_days": days,
                }
            )
    items.extend(_timed_evidence_items(packet, keywords))
    items.extend(_evidence_items(packet, keywords))
    return _dedupe_items(items)


def _materiality_keywords() -> tuple[str, ...]:
    return (
        "material",
        "large",
        "backlog",
        "capacity",
        "shipment",
        "customer",
        "contract",
        "order",
        "award",
        "offering",
        "financing",
        "funding",
        "merger",
        "combination",
        "deadline",
        "listing",
        "suspension",
        "resumption",
        "compliance",
        "fda",
        "clinical",
        "screening",
        "approval",
        "sales",
        "earnings",
        "eps",
        "8-k",
        "form f-4",
        "registration statement",
    )


def _timed_evidence_items(packet: ResearchPacket, keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in packet.evidence:
        if item.published_date is None or not _contains_any(item.summary, keywords):
            continue
        if _low_information_source_summary(item.summary):
            continue
        days = (item.published_date - packet.as_of.as_of_date).days
        if not -180 <= days <= 30:
            continue
        if days == 0:
            timing = "published on the as-of date"
        elif days > 0:
            timing = f"scheduled {days} days after as-of"
        else:
            timing = f"observed {abs(days)} days before as-of"
        items.append(
            {
                "item_type": "materiality_timing",
                "summary": f"Source event {timing}: {item.summary}",
                "published_date": item.published_date.isoformat(),
                "relative_timing_days": days,
                "data_quality": item.data_quality.value,
            }
        )
    return items


def _recent_source_detail_items(packet: ResearchPacket, keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in sorted(
        packet.evidence,
        key=lambda evidence: evidence.published_date or evidence.as_of_date,
        reverse=True,
    ):
        if item.published_date is None or not _contains_any(item.summary, keywords):
            continue
        if _low_information_source_summary(item.summary):
            continue
        days = (item.published_date - packet.as_of.as_of_date).days
        if not -180 <= days <= 30:
            continue
        items.append(
            {
                "item_type": "source_detail",
                "summary": f"Recent source detail {_relative_timing_phrase(days)}: {_compact_summary(item.summary)}",
                "published_date": item.published_date.isoformat(),
                "relative_timing_days": days,
                "data_quality": item.data_quality.value,
            }
        )
    return items


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = json.dumps(item, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _risk_items(packet: ResearchPacket) -> list[dict[str, Any]]:
    items = _evidence_items(packet, _risk_keywords())
    stretched = _feature_items(packet, ("valuation.pe_ratio", "valuation.price_to_sales_ttm"))
    if stretched:
        items.append(
            {
                "item_type": "valuation_context",
                "summary": "Valuation snapshot included as possible contrary evidence.",
                "features": stretched[:2],
            }
        )
    return items


def _feature_items(packet: ResearchPacket, names: tuple[str, ...]) -> list[dict[str, Any]]:
    lookup = {feature.name: feature for feature in packet.features}
    return [
        {
            "item_type": "feature",
            "name": name,
            "value": lookup[name].value,
            "as_of_date": lookup[name].as_of_date.isoformat(),
            "data_quality": lookup[name].data_quality.value,
        }
        for name in names
        if name in lookup
    ]


def _evidence_by_kind(packet: ResearchPacket, kinds: set[EvidenceKind]) -> list[dict[str, Any]]:
    return [_evidence_summary(item) for item in packet.evidence if item.kind in kinds]


def _evidence_items(packet: ResearchPacket, keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        _evidence_summary(item)
        for item in packet.evidence
        if _contains_any(item.summary, keywords)
        and not _low_information_source_summary(item.summary)
    ]


def _evidence_summary(item: EvidenceItem) -> dict[str, Any]:
    return {
        "item_type": item.kind.value,
        "summary": item.summary,
        "as_of_date": item.as_of_date.isoformat(),
        "published_date": item.published_date.isoformat() if item.published_date else None,
        "data_quality": item.data_quality.value,
    }


def _packet_evidence_text(packet: ResearchPacket) -> str:
    return " ".join(
        [item.summary for item in packet.evidence]
        + [catalyst.name for catalyst in packet.catalysts]
        + [item.summary for catalyst in packet.catalysts for item in catalyst.evidence]
        + [str(feature.value) for feature in packet.features if isinstance(feature.value, str)]
    ).lower()


def _evidence_family_diagnostics(cases: list[HistoricalCase]) -> tuple[EvidenceFamilyDiagnostic, ...]:
    refs = {case.case_id: f"case_{index:03d}" for index, case in enumerate(cases, start=1)}
    winners = [case for case in cases if case.label is CaseOutcomeLabel.WINNER]
    non_winners = [case for case in cases if case.label is not CaseOutcomeLabel.WINNER]
    diagnostics = []
    for family in _family_definitions():
        winner_hits = [case for case in winners if _case_has_family(case, family)]
        non_winner_hits = [case for case in non_winners if _case_has_family(case, family)]
        winner_prev = _safe_ratio(len(winner_hits), len(winners))
        non_winner_prev = _safe_ratio(len(non_winner_hits), len(non_winners))
        diagnostics.append(
            EvidenceFamilyDiagnostic(
                family=family,
                winner_hits=len(winner_hits),
                non_winner_hits=len(non_winner_hits),
                winner_prevalence=round(winner_prev, 4),
                non_winner_prevalence=round(non_winner_prev, 4),
                separation_lift=round(winner_prev - non_winner_prev, 4),
                example_case_refs=tuple(refs[case.case_id] for case in winner_hits[:3]),
                reasoning_pattern=_reasoning_pattern(family),
                false_positive_trap=_false_positive_trap(family),
            )
        )
    return tuple(diagnostics)


def _case_has_family(case: HistoricalCase, family: str) -> bool:
    packet = case.packet
    text = " ".join(
        [item.summary for item in packet.evidence]
        + [catalyst.name for catalyst in packet.catalysts]
        + [item.summary for catalyst in packet.catalysts for item in catalyst.evidence]
    ).lower()
    features = {feature.name: feature for feature in packet.features}
    if family == "catalyst_event":
        return bool(packet.catalysts) or _contains_any(text, _event_keywords())
    if family == "orders_contracts":
        return _contains_any(text, ("order", "contract", "award", "backlog", "customer win"))
    if family == "funding_subsidy":
        return _contains_any(text, ("funding", "grant", "subsidy", "incentive", "financing"))
    if family == "policy_regulatory":
        return _contains_any(text, ("policy", "approval", "regulatory", "tariff", "fda", "rate case"))
    if family == "customer_capacity":
        return _contains_any(text, ("customer", "capacity", "shipment", "production", "factory"))
    if family == "theme_industry_transmission":
        return bool(packet.theme_ids) or any(item.kind is EvidenceKind.THEME_CONTEXT for item in packet.evidence)
    if family == "expectation_gap":
        target = _numeric(features.get("analyst.target_price").value if features.get("analyst.target_price") else None)
        close = _numeric(features.get("price.latest_close").value if features.get("price.latest_close") else None)
        return (target > 0 and close > 0 and target > close) or _contains_any(
            text,
            ("expectation", "guidance", "estimate", "revision", "upside"),
        )
    if family == "contrary_risk":
        return _contains_any(text, _risk_keywords())
    if family == "fundamentals":
        return any(name.startswith(("financial.", "valuation.")) for name in features)
    if family == "market_confirmation":
        return any(name.startswith("price.") for name in features)
    return False


def _family_definitions() -> tuple[str, ...]:
    return (
        "catalyst_event",
        "orders_contracts",
        "funding_subsidy",
        "policy_regulatory",
        "customer_capacity",
        "theme_industry_transmission",
        "expectation_gap",
        "contrary_risk",
        "fundamentals",
        "market_confirmation",
    )


def _priority_family_names() -> tuple[str, ...]:
    return _family_definitions()[:8]


def _group_counts(cases: list[HistoricalCase]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.label.value] = counts.get(case.label.value, 0) + 1
    return counts


def _false_positive_traps(
    learning_result: ColdStartLearningResult,
    playbook_synthesis: SurgePlaybookSynthesis,
) -> tuple[str, ...]:
    traps = []
    for signal in learning_result.signal_logic:
        traps.extend(signal.false_positive_patterns)
    for playbook in playbook_synthesis.playbooks:
        traps.extend(playbook.false_positive_traps)
    traps.extend(
        (
            "Generic theme mention without company-level event evidence.",
            "Raw price rebound without new catalyst or expectation gap.",
            "Strong historical growth already reflected in valuation.",
        )
    )
    return tuple(dict.fromkeys(item for item in traps if item.strip()))[:12]


def _coverage_summary(coverage_reports: Mapping[str, Any] | None) -> dict[str, Any]:
    if not coverage_reports:
        return {
            "provided": False,
            "case_count": 0,
            "sufficient_context_count": 0,
            "missing_bucket_counts": {},
        }
    sufficient = 0
    missing_counts: dict[str, int] = {}
    for report in coverage_reports.values():
        if _coverage_sufficient(report):
            sufficient += 1
        for bucket in _coverage_missing_buckets(report):
            missing_counts[bucket] = missing_counts.get(bucket, 0) + 1
    return {
        "provided": True,
        "case_count": len(coverage_reports),
        "sufficient_context_count": sufficient,
        "missing_bucket_counts": missing_counts,
    }


def _coverage_sufficient(report: Any) -> bool:
    if hasattr(report, "sufficient_context"):
        return bool(report.sufficient_context)
    if isinstance(report, Mapping):
        return bool(report.get("sufficient_context"))
    return False


def _coverage_missing_buckets(report: Any) -> tuple[str, ...]:
    if hasattr(report, "missing_buckets"):
        return tuple(str(item) for item in report.missing_buckets)
    if isinstance(report, Mapping):
        value = report.get("missing_buckets", ())
        if isinstance(value, list):
            return tuple(str(item) for item in value)
        if isinstance(value, tuple):
            return tuple(str(item) for item in value)
    return ()


def _reasoning_pattern(family: str) -> str:
    patterns = {
        "catalyst_event": "Concrete as-of events should anchor the case before price or table data.",
        "orders_contracts": "Orders/contracts matter when they are material, recent, and not already stale.",
        "funding_subsidy": "Funding and subsidies matter when timing and recipients are specific.",
        "policy_regulatory": "Policy or regulatory changes matter only when transmission to the company is clear.",
        "customer_capacity": "Customer/capacity evidence helps separate company-specific beneficiaries from theme tourists.",
        "theme_industry_transmission": "Theme evidence should explain the industry-chain path, not merely name a theme.",
        "expectation_gap": "The packet should state what expectations miss and why that gap could close.",
        "contrary_risk": "The best risk evidence must be visible so the model can reject weak positives.",
        "fundamentals": "Fundamentals are background confirmation, not the main context budget.",
        "market_confirmation": "Market confirmation is useful only after event and expectation context.",
    }
    return patterns[family]


def _false_positive_trap(family: str) -> str:
    traps = {
        "catalyst_event": "Treating a low-materiality calendar item as a repricing catalyst.",
        "orders_contracts": "Counting vague customer language without order size or timing.",
        "funding_subsidy": "Assuming sector funding reaches the anonymous company.",
        "policy_regulatory": "Overweighting broad policy headlines with weak company linkage.",
        "customer_capacity": "Mistaking industry demand for this company's capacity or customer win.",
        "theme_industry_transmission": "Theme mention only, with no transmission path.",
        "expectation_gap": "Target-price upside that is stale or mechanically follows price weakness.",
        "contrary_risk": "Missing dilution, execution, debt, or valuation risk.",
        "fundamentals": "Raw growth from a depressed base with no new catalyst.",
        "market_confirmation": "Momentum after most repricing has already occurred.",
    }
    return traps[family]


def _ralph_analysis_from_json(packet: BlindSchemePacket, text: str) -> RalphBlindAnalysis:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("Ralph blind analysis was not valid JSON") from exc
    return RalphBlindAnalysis(
        source_case_id=packet.source_case_id,
        anonymous_case_id=packet.anonymous_case_id,
        as_of_date=packet.as_of_date,
        scheme_version=packet.scheme_version,
        surge_candidate=_string(data, "surge_candidate"),
        surge_candidate_reason=_string(data, "surge_candidate_reason"),
        expectation_gap=_string(data, "expectation_gap"),
        pre_surge_signals=tuple(_string_list(data, "pre_surge_signals")),
        contrary_evidence=tuple(_string_list(data, "contrary_evidence")),
        catalyst_watch=tuple(_string_list(data, "catalyst_watch")),
        confidence=_confidence(data.get("confidence")),
        raw_text=text,
        missing_context=tuple(_optional_string_list(data, "missing_context")),
    )


def _cached_ralph_analysis(packet: BlindSchemePacket, data: dict[str, Any]) -> RalphBlindAnalysis:
    if data.get("packet_sha256") != _blind_packet_sha256(packet):
        raise ValidationError("cached Ralph blind analysis packet hash mismatch")
    analysis = data.get("analysis")
    if not isinstance(analysis, dict):
        raise ValidationError("cached Ralph blind analysis missing analysis object")
    return RalphBlindAnalysis(
        source_case_id=packet.source_case_id,
        anonymous_case_id=packet.anonymous_case_id,
        as_of_date=packet.as_of_date,
        scheme_version=packet.scheme_version,
        surge_candidate=_string(analysis, "surge_candidate"),
        surge_candidate_reason=_string(analysis, "surge_candidate_reason"),
        expectation_gap=_string(analysis, "expectation_gap"),
        pre_surge_signals=tuple(_string_list(analysis, "pre_surge_signals")),
        contrary_evidence=tuple(_string_list(analysis, "contrary_evidence")),
        catalyst_watch=tuple(_string_list(analysis, "catalyst_watch")),
        confidence=_confidence(analysis.get("confidence")),
        raw_text=_string(analysis, "raw_text"),
        missing_context=tuple(_optional_string_list(analysis, "missing_context")),
    )


def _blind_packet_sha256(packet: BlindSchemePacket) -> str:
    body = json.dumps(packet.to_prompt_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _analysis_case_id(analysis: BlindCaseAnalysis | RalphBlindAnalysis) -> str:
    return analysis.source_case_id if isinstance(analysis, RalphBlindAnalysis) else analysis.case_id


def _analysis_judgment(analysis: BlindCaseAnalysis | RalphBlindAnalysis) -> str:
    return analysis.surge_candidate.strip().lower()


def _analysis_confidence(analysis: BlindCaseAnalysis | RalphBlindAnalysis) -> float:
    return analysis.confidence


def _analysis_reason(analysis: BlindCaseAnalysis | RalphBlindAnalysis) -> str:
    return analysis.surge_candidate_reason


def _analysis_missing_context(analysis: BlindCaseAnalysis | RalphBlindAnalysis) -> tuple[str, ...]:
    if isinstance(analysis, RalphBlindAnalysis):
        return analysis.missing_context
    return ()


def _scheme_diff(before: InformationScheme, after: InformationScheme | None) -> dict[str, Any]:
    if after is None:
        return {}
    before_by_name = {section.name: section for section in before.sections}
    changed_sections = []
    for section in after.sections:
        prior = before_by_name.get(section.name)
        if prior is None:
            changed_sections.append(
                {
                    "section": section.name,
                    "change": "added",
                    "token_budget_after": section.token_budget,
                    "max_items_after": section.max_items,
                }
            )
            continue
        budget_delta = section.token_budget - prior.token_budget
        max_items_delta = section.max_items - prior.max_items
        rule_changed = section.compression_rule != prior.compression_rule
        if budget_delta or max_items_delta or rule_changed:
            changed_sections.append(
                {
                    "section": section.name,
                    "token_budget_before": prior.token_budget,
                    "token_budget_after": section.token_budget,
                    "token_budget_delta": budget_delta,
                    "max_items_before": prior.max_items,
                    "max_items_after": section.max_items,
                    "max_items_delta": max_items_delta,
                    "compression_rule_changed": rule_changed,
                }
            )
    return {
        "from_version": before.version,
        "to_version": after.version,
        "changed_sections": changed_sections,
        "compression_rules_added": [
            rule for rule in after.compression_rules if rule not in before.compression_rules
        ],
        "proposal_status": after.proposal_status,
    }


def _first_item_summary(section: BlindPacketSection | None) -> str:
    if section is None or not section.items:
        return "No scheme evidence supplied."
    summary = section.items[0].get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary
    return json.dumps(section.items[0], sort_keys=True)


def _section_summaries(section: BlindPacketSection | None) -> tuple[str, ...]:
    if section is None:
        return ()
    summaries = []
    for item in section.items:
        summary = item.get("summary")
        if isinstance(summary, str) and summary.strip():
            summaries.append(summary)
    return tuple(summaries)


def _strip_source_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_source_metadata(item)
            for key, item in value.items()
            if key not in {"source_id", "source_url", "symbol", "company_name", "figi"}
        }
    if isinstance(value, list):
        return [_strip_source_metadata(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_source_metadata(item) for item in value)
    return value


def _identity_tokens(packet: ResearchPacket) -> tuple[str, ...]:
    ticker = packet.company.ticker
    tokens = [ticker.symbol, ticker.company_name or ""]
    company = ticker.company_name or ""
    tokens.extend(_company_name_variants(company))
    return tuple(sorted({token for token in tokens if token and token.strip()}, key=len, reverse=True))


def _company_name_variants(company: str) -> list[str]:
    variants: list[str] = []
    for raw_piece in re.split(r"\s*/\s*|\s+\|\s+", company):
        piece = re.sub(r"\s+", " ", raw_piece).strip(" ,.;:-")
        if not piece:
            continue
        variants.append(piece)
        without_class = re.sub(r"\s+-\s+class\s+.+$", "", piece, flags=re.IGNORECASE).strip(" ,.;:-")
        if without_class:
            variants.append(without_class)
        without_terminal_number = re.sub(r"\s+\d+\b.*$", "", without_class or piece).strip(" ,.;:-")
        if without_terminal_number:
            variants.append(without_terminal_number)
        for candidate in (piece, without_class, without_terminal_number):
            stripped = re.sub(
                r"\b(incorporated|inc|corporation|corp|company|co|ltd|plc)\.?(?:\s+\d+)?$",
                "",
                candidate,
                flags=re.IGNORECASE,
            ).strip(" ,.;:-")
            if stripped:
                variants.append(stripped)
                words = re.findall(r"[A-Za-z0-9]+", stripped)
                if len(words) >= 2 and len(words[-1]) > 3:
                    variants.append(" ".join(words[:-1] + [words[-1][:3]]))
    return variants


def _mask_identity_in_value(value: Any, tokens: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        masked = value
        for token in tokens:
            masked = re.sub(_identity_token_pattern(token), "MASKED", masked, flags=re.IGNORECASE)
        return masked
    if isinstance(value, list):
        return [_mask_identity_in_value(item, tokens) for item in value]
    if isinstance(value, tuple):
        return tuple(_mask_identity_in_value(item, tokens) for item in value)
    if isinstance(value, dict):
        return {key: _mask_identity_in_value(item, tokens) for key, item in value.items()}
    return value


def _identity_token_pattern(token: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", token)
    if not words:
        return re.escape(token)
    return r"\b" + r"[\s,.\-/&']+".join(re.escape(word) for word in words) + r"\.?\b"


def _estimated_tokens(items: tuple[dict[str, Any], ...]) -> int:
    text = json.dumps(items, sort_keys=True)
    return max(1, len(text.split()))


def _event_keywords() -> tuple[str, ...]:
    return (
        "catalyst",
        "contract",
        "order",
        "award",
        "approval",
        "launch",
        "partnership",
        "guidance",
        "backlog",
        "customer",
        "sales",
        "growth",
        "earnings",
        "eps",
        "offering",
        "financing",
        "funding",
        "deadline",
        "listing",
        "compliance",
        "suspension",
        "resumption",
        "merger",
        "combination",
        "transaction",
        "extension",
        "effective",
        "8-k",
        "registration statement",
        "form f-4",
        "regulatory",
        "fda",
        "webcast",
    )


def _risk_keywords() -> tuple[str, ...]:
    return (
        "risk",
        "dilution",
        "debt",
        "cash burn",
        "going concern",
        "lawsuit",
        "investigation",
        "delist",
        "execution",
        "valuation",
        "delay",
    )


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in keywords)


def _unable_to_judge_mentions_source_detail_gap(reasons: tuple[str, ...]) -> bool:
    text = " ".join(reasons).lower()
    return any(
        marker in text
        for marker in (
            "full text",
            "full 8-k",
            "8-k contents",
            "filing contents",
            "specific disclosed events",
            "substance and materiality",
            "disclosed events",
        )
    )


def _feedback_missing_families_from_reasons(reasons: tuple[str, ...]) -> tuple[str, ...]:
    text = " ".join(reasons).lower()
    families: list[str] = []
    if _unable_to_judge_mentions_source_detail_gap(reasons) or any(
        marker in text
        for marker in (
            "current status",
            "business combination",
            "transaction",
            "merger",
            "closing",
            "termination",
            "shareholder vote",
            "latest filings",
        )
    ):
        families.extend(["source_detail_digest", "deal_status_timing"])
    if any(
        marker in text
        for marker in (
            "cash",
            "trust",
            "redemption",
            "debt",
            "runway",
            "warrant",
            "dilution",
            "float",
            "short interest",
            "liquidity",
            "borrow",
        )
    ):
        families.append("capital_structure_liquidity")
    if any(marker in text for marker in ("fda", "regulatory", "listing", "compliance")):
        families.append("policy_regulatory")
    if any(marker in text for marker in ("customer", "order", "contract", "backlog", "capacity")):
        families.append("orders_contracts")
    if any(marker in text for marker in ("ai/data-center", "ai", "data center", "bottleneck")):
        families.append("ai_chain_bottleneck_transmission")
    return tuple(dict.fromkeys(families))


def _relative_timing_phrase(days: int) -> str:
    if days == 0:
        return "published on the as-of date"
    if days > 0:
        return f"scheduled {days} days after as-of"
    return f"observed {abs(days)} days before as-of"


def _compact_summary(summary: str, *, max_chars: int = 520) -> str:
    compact = " ".join(summary.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _low_information_source_summary(summary: str) -> bool:
    lower = summary.lower()
    if "field: set" in lower or "xmlns" in lower or "xbrl" in lower or "excerpt: </" in lower:
        return True
    words = re.findall(r"[A-Za-z]{3,}", summary)
    return len(words) < 8


def _matches_ai_chain_keywords(text: str, keywords: tuple[str, ...]) -> bool:
    return any(re.search(_keyword_pattern(keyword), text, flags=re.IGNORECASE) for keyword in keywords)


def _keyword_pattern(keyword: str) -> str:
    if keyword == "ai":
        return r"\bAI\b"
    return r"\b" + r"\s+".join(re.escape(part) for part in keyword.split()) + r"\b"


def _ai_chain_anchors() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        ("model/application demand", ("ai", "artificial intelligence", "generative ai", "machine learning")),
        ("compute/cloud capex", ("cloud", "hyperscaler", "data center", "datacenter", "ai factory")),
        ("accelerators and memory", ("gpu", "accelerator", "hbm", "memory", "asic")),
        ("networking and servers", ("networking", "ethernet", "infiniband", "server", "rack")),
        ("power and cooling", ("power", "cooling", "liquid cooling", "thermal", "grid", "substation")),
        ("supply/capacity bottleneck", ("capacity", "backlog", "order", "contract", "shipment", "lead time")),
    )


def _numeric(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _average(values: Iterable[float]) -> float:
    value_list = list(values)
    return sum(value_list) / len(value_list) if value_list else 0.0


def _next_scheme_version(version: str) -> str:
    match = re.search(r"v0\.(\d+)$", version)
    if not match:
        return version + "-proposal"
    return version[: match.start(1)] + str(int(match.group(1)) + 1)


def _string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Ralph blind analysis missing {key}")
    return value


def _string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"Ralph blind analysis {key} must be a non-empty string list")
    return value


def _optional_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"Ralph blind analysis {key} must be a string list")
    return value


def _confidence(value: Any) -> float:
    if not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValidationError("Ralph blind analysis confidence must be between 0 and 1")
    return float(value)


def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValidationError(f"{name} must not be empty")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
