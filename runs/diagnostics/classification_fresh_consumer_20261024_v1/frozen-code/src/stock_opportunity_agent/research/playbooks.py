"""Cross-case research playbook synthesis for cold-start learning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from stock_opportunity_agent.cases import CaseOutcomeLabel, ColdStartLearningResult, HistoricalCase, PreSurgeSignalLogic
from stock_opportunity_agent.llm.openai import ChatMessage, OpenAIChatClient, OpenAIClientError
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.cold_start import BlindCaseAnalysis
from stock_opportunity_agent.themes import ThemeMapBuildResult


PLAYBOOK_SCHEMA_VERSION = "surge-playbook-v0.1"
PROMOTION_STATUSES = {"candidate", "approved", "rejected", "retired"}


@dataclass(frozen=True)
class PlaybookQuestion:
    """One reusable research question inside a surge playbook."""

    question_id: str
    prompt: str
    evidence_types: tuple[str, ...]
    positive_indicators: tuple[str, ...]
    negative_indicators: tuple[str, ...]
    linked_signal_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.question_id, "question_id")
        _require_non_empty(self.prompt, "prompt")
        if not self.evidence_types:
            raise ValidationError("playbook question requires evidence_types")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible question record."""

        return {
            "question_id": self.question_id,
            "prompt": self.prompt,
            "evidence_types": list(self.evidence_types),
            "positive_indicators": list(self.positive_indicators),
            "negative_indicators": list(self.negative_indicators),
            "linked_signal_ids": list(self.linked_signal_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlaybookQuestion":
        """Build a question record from JSON-compatible data."""

        return cls(
            question_id=_string(data, "question_id"),
            prompt=_string(data, "prompt"),
            evidence_types=tuple(_string_list(data, "evidence_types")),
            positive_indicators=tuple(_string_list(data, "positive_indicators")),
            negative_indicators=tuple(_string_list(data, "negative_indicators")),
            linked_signal_ids=tuple(_string_list(data, "linked_signal_ids")),
        )


@dataclass(frozen=True)
class PlaybookReasoningStep:
    """One step in a reusable research reasoning sequence."""

    step_id: str
    name: str
    question: str
    inputs: tuple[str, ...]
    output: str
    common_failure_mode: str

    def __post_init__(self) -> None:
        _require_non_empty(self.step_id, "step_id")
        _require_non_empty(self.name, "name")
        _require_non_empty(self.question, "question")
        _require_non_empty(self.output, "output")
        _require_non_empty(self.common_failure_mode, "common_failure_mode")
        if not self.inputs:
            raise ValidationError("playbook reasoning step requires inputs")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible reasoning-step record."""

        return {
            "step_id": self.step_id,
            "name": self.name,
            "question": self.question,
            "inputs": list(self.inputs),
            "output": self.output,
            "common_failure_mode": self.common_failure_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlaybookReasoningStep":
        """Build a reasoning-step record from JSON-compatible data."""

        return cls(
            step_id=_string(data, "step_id"),
            name=_string(data, "name"),
            question=_string(data, "question"),
            inputs=tuple(_string_list(data, "inputs")),
            output=_string(data, "output"),
            common_failure_mode=_string(data, "common_failure_mode"),
        )


@dataclass(frozen=True)
class SurgeResearchPlaybook:
    """Reusable thinking pattern for finding possible surge stocks."""

    playbook_id: str
    name: str
    purpose: str
    version: str
    applies_when: tuple[str, ...]
    core_questions: tuple[PlaybookQuestion, ...]
    reasoning_steps: tuple[PlaybookReasoningStep, ...]
    positive_patterns: tuple[str, ...]
    counter_patterns: tuple[str, ...]
    false_positive_traps: tuple[str, ...]
    linked_signal_ids: tuple[str, ...]
    linked_theme_ids: tuple[str, ...]
    evidence_case_refs: dict[str, tuple[str, ...]]
    confidence: float
    promotion_status: str
    hindsight_risk_notes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.playbook_id, "playbook_id")
        _require_non_empty(self.name, "name")
        _require_non_empty(self.purpose, "purpose")
        _require_non_empty(self.version, "version")
        if not self.core_questions:
            raise ValidationError("surge research playbook requires core_questions")
        if not self.reasoning_steps:
            raise ValidationError("surge research playbook requires reasoning_steps")
        if not 0 <= self.confidence <= 1:
            raise ValidationError("playbook confidence must be between 0 and 1")
        if self.promotion_status not in PROMOTION_STATUSES:
            raise ValidationError("playbook promotion_status is invalid")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible playbook record."""

        return {
            "playbook_id": self.playbook_id,
            "name": self.name,
            "purpose": self.purpose,
            "version": self.version,
            "applies_when": list(self.applies_when),
            "core_questions": [question.to_dict() for question in self.core_questions],
            "reasoning_steps": [step.to_dict() for step in self.reasoning_steps],
            "positive_patterns": list(self.positive_patterns),
            "counter_patterns": list(self.counter_patterns),
            "false_positive_traps": list(self.false_positive_traps),
            "linked_signal_ids": list(self.linked_signal_ids),
            "linked_theme_ids": list(self.linked_theme_ids),
            "evidence_case_refs": {
                name: list(refs)
                for name, refs in sorted(self.evidence_case_refs.items())
            },
            "confidence": self.confidence,
            "promotion_status": self.promotion_status,
            "hindsight_risk_notes": list(self.hindsight_risk_notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurgeResearchPlaybook":
        """Build a playbook record from JSON-compatible data."""

        raw_refs = data.get("evidence_case_refs", {})
        if not isinstance(raw_refs, dict):
            raise ValidationError("playbook evidence_case_refs must be an object")
        return cls(
            playbook_id=_string(data, "playbook_id"),
            name=_string(data, "name"),
            purpose=_string(data, "purpose"),
            version=_string(data, "version"),
            applies_when=tuple(_string_list(data, "applies_when")),
            core_questions=tuple(
                PlaybookQuestion.from_dict(item)
                for item in _dict_list(data, "core_questions")
            ),
            reasoning_steps=tuple(
                PlaybookReasoningStep.from_dict(item)
                for item in _dict_list(data, "reasoning_steps")
            ),
            positive_patterns=tuple(_string_list(data, "positive_patterns")),
            counter_patterns=tuple(_string_list(data, "counter_patterns")),
            false_positive_traps=tuple(_string_list(data, "false_positive_traps")),
            linked_signal_ids=tuple(_string_list(data, "linked_signal_ids")),
            linked_theme_ids=tuple(_string_list(data, "linked_theme_ids")),
            evidence_case_refs={
                str(name): tuple(str(ref) for ref in refs if isinstance(ref, str) and ref.strip())
                for name, refs in raw_refs.items()
                if isinstance(refs, list)
            },
            confidence=_confidence(data.get("confidence")),
            promotion_status=_string(data, "promotion_status"),
            hindsight_risk_notes=tuple(_string_list(data, "hindsight_risk_notes")),
        )


@dataclass(frozen=True)
class SurgePlaybookSynthesis:
    """Cross-case playbook synthesis result."""

    schema_version: str
    generated_by: str
    playbooks: tuple[SurgeResearchPlaybook, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.schema_version, "schema_version")
        _require_non_empty(self.generated_by, "generated_by")
        if not self.playbooks:
            raise ValidationError("surge playbook synthesis requires at least one playbook")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible synthesis record."""

        return {
            "schema_version": self.schema_version,
            "generated_by": self.generated_by,
            "playbooks": [playbook.to_dict() for playbook in self.playbooks],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurgePlaybookSynthesis":
        """Build a synthesis record from JSON-compatible data."""

        return cls(
            schema_version=str(data.get("schema_version") or PLAYBOOK_SCHEMA_VERSION),
            generated_by=str(data.get("generated_by") or "unknown"),
            playbooks=tuple(
                SurgeResearchPlaybook.from_dict(item)
                for item in _dict_list(data, "playbooks")
            ),
            warnings=tuple(_string_list(data, "warnings")),
        )


class SurgePlaybookSynthesizer(Protocol):
    """Synthesizes cross-case surge research playbooks."""

    def synthesize(
        self,
        cases: Iterable[HistoricalCase],
        blind_analyses: Iterable[BlindCaseAnalysis],
        learning_result: ColdStartLearningResult,
        theme_maps: ThemeMapBuildResult,
    ) -> SurgePlaybookSynthesis:
        """Create reusable research playbooks from cold-start outputs."""


class HeuristicSurgePlaybookSynthesizer:
    """Offline deterministic synthesizer used for tests and fallback runs."""

    def synthesize(
        self,
        cases: Iterable[HistoricalCase],
        blind_analyses: Iterable[BlindCaseAnalysis],
        learning_result: ColdStartLearningResult,
        theme_maps: ThemeMapBuildResult,
    ) -> SurgePlaybookSynthesis:
        """Create playbooks without another model call."""

        case_list = list(cases)
        if not case_list:
            raise ValidationError("playbook synthesis requires cases")
        analysis_by_case = {analysis.case_id: analysis for analysis in blind_analyses}
        promoted = tuple(signal for signal in learning_result.signal_logic if signal.promoted)
        linked_signal_ids = tuple(signal.signal_id for signal in promoted)
        linked_theme_ids = tuple(theme.theme_id for theme in theme_maps.theme_maps)
        playbooks = [
            _general_playbook(
                case_list,
                analysis_by_case,
                promoted,
                linked_signal_ids=linked_signal_ids,
                linked_theme_ids=linked_theme_ids,
            )
        ]
        playbooks.extend(_signal_playbook(signal, linked_theme_ids) for signal in promoted)
        warnings = []
        if not promoted:
            warnings.append("No promoted deterministic signals; general research playbook is heuristic-only.")
        if not analysis_by_case:
            warnings.append("No blind analyses were available; playbook patterns rely on deterministic signals only.")
        return SurgePlaybookSynthesis(
            schema_version=PLAYBOOK_SCHEMA_VERSION,
            generated_by=self.__class__.__name__,
            playbooks=tuple(playbooks),
            warnings=tuple(warnings),
        )


class OpenAISurgePlaybookSynthesizer:
    """LLM-backed cross-case synthesizer for reusable surge research playbooks."""

    def __init__(
        self,
        client: OpenAIChatClient,
        *,
        max_cases: int = 40,
        max_attempts: int = 2,
        fallback: SurgePlaybookSynthesizer | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValidationError("max_attempts must be at least 1")
        self.client = client
        self.max_cases = max_cases
        self.max_attempts = max_attempts
        self.fallback = fallback or HeuristicSurgePlaybookSynthesizer()

    def synthesize(
        self,
        cases: Iterable[HistoricalCase],
        blind_analyses: Iterable[BlindCaseAnalysis],
        learning_result: ColdStartLearningResult,
        theme_maps: ThemeMapBuildResult,
    ) -> SurgePlaybookSynthesis:
        """Ask the model to summarize cross-case thinking patterns."""

        case_list = list(cases)
        blind_list = list(blind_analyses)
        prompt = _openai_playbook_prompt(
            case_list[: self.max_cases],
            blind_list,
            learning_result,
            theme_maps,
        )
        last_error: Exception | None = None
        for _attempt in range(self.max_attempts):
            try:
                response = self.client.complete(
                    [
                        ChatMessage(
                            "developer",
                            (
                                "You are synthesizing retrospective cold-start stock-research playbooks. "
                                "You may compare historical winner, control, and failure labels, but these "
                                "labels are retrospective and must never be framed as as-of evidence. "
                                "Do not use web search. Do not infer ticker or company identity. Return only "
                                "valid compact JSON. Create at most two playbooks, at most three core questions "
                                "per playbook, and at most four short strings in each list."
                            ),
                        ),
                        ChatMessage("user", prompt),
                    ],
                    max_output_tokens=4000,
                    response_format={"type": "json_object"},
                )
                synthesis = _synthesis_from_json(response.output_text)
                return SurgePlaybookSynthesis(
                    schema_version=synthesis.schema_version,
                    generated_by=self.__class__.__name__,
                    playbooks=synthesis.playbooks,
                    warnings=synthesis.warnings,
                )
            except (OpenAIClientError, ValidationError) as exc:
                last_error = exc
        fallback = self.fallback.synthesize(case_list, blind_list, learning_result, theme_maps)
        warning = (
            f"LLM playbook synthesis failed after {self.max_attempts} attempt(s): "
            f"{last_error or 'unknown error'}"
        )
        return SurgePlaybookSynthesis(
            schema_version=fallback.schema_version,
            generated_by=f"{self.__class__.__name__}(fallback={fallback.generated_by})",
            playbooks=fallback.playbooks,
            warnings=(*fallback.warnings, warning),
        )


def _synthesis_from_json(text: str) -> SurgePlaybookSynthesis:
    try:
        return SurgePlaybookSynthesis.from_dict(json.loads(text))
    except json.JSONDecodeError as exc:
        raise ValidationError("surge playbook synthesis was not valid JSON") from exc


def _general_playbook(
    cases: list[HistoricalCase],
    analysis_by_case: dict[str, BlindCaseAnalysis],
    promoted: tuple[PreSurgeSignalLogic, ...],
    *,
    linked_signal_ids: tuple[str, ...],
    linked_theme_ids: tuple[str, ...],
) -> SurgeResearchPlaybook:
    winner_refs = tuple(case.case_id for case in cases if case.label is CaseOutcomeLabel.WINNER)
    counter_refs = tuple(case.case_id for case in cases if case.label is not CaseOutcomeLabel.WINNER)
    positive_patterns = _patterns_from_analyses(
        (analysis_by_case.get(case.case_id) for case in cases if case.label is CaseOutcomeLabel.WINNER),
        "pre_surge_signals",
    ) or tuple(signal.description for signal in promoted[:4])
    counter_patterns = _patterns_from_analyses(
        (analysis_by_case.get(case.case_id) for case in cases if case.label is not CaseOutcomeLabel.WINNER),
        "contrary_evidence",
    )
    traps = _unique(pattern for signal in promoted for pattern in signal.false_positive_patterns)
    evidence_types = _evidence_types(cases)
    return SurgeResearchPlaybook(
        playbook_id="pb-cross-case-surge-research-v0.1",
        name="Cross-case surge candidate research",
        purpose=(
            "Guide future research on whether an as-of stock setup has enough "
            "business change, evidence quality, market confirmation, and remaining "
            "expectation gap to look like a possible 3-6 month surge candidate."
        ),
        version="playbook-v0.1",
        applies_when=evidence_types,
        core_questions=_general_questions(evidence_types, linked_signal_ids),
        reasoning_steps=_general_steps(),
        positive_patterns=positive_patterns or ("Winner cases shared multiple pre-surge signals before repricing.",),
        counter_patterns=counter_patterns or ("Non-winner cases lacked enough cross-evidence confirmation.",),
        false_positive_traps=traps or ("Narrative evidence without measurable business or market confirmation.",),
        linked_signal_ids=linked_signal_ids,
        linked_theme_ids=linked_theme_ids,
        evidence_case_refs={"positive": winner_refs, "counterexamples": counter_refs},
        confidence=_average_confidence(analysis_by_case.values()),
        promotion_status="candidate",
        hindsight_risk_notes=(
            "This playbook was synthesized after labels were known; use it as a research checklist, not as as-of evidence.",
            "Future prompt changes derived from this playbook require versioning and review.",
        ),
    )


def _signal_playbook(signal: PreSurgeSignalLogic, linked_theme_ids: tuple[str, ...]) -> SurgeResearchPlaybook:
    evidence_types = tuple(sorted({name.split(".", 1)[0] for name in signal.source_feature_names})) or ("research_packet",)
    return SurgeResearchPlaybook(
        playbook_id=f"pb-{signal.signal_id.replace('sig-', '')}-v0.1",
        name=f"Research lens: {signal.name}",
        purpose=f"Turn the signal '{signal.name}' into a reusable qualitative research lens.",
        version="playbook-v0.1",
        applies_when=evidence_types,
        core_questions=(
            PlaybookQuestion(
                question_id=f"q-{signal.signal_id}-evidence",
                prompt=f"What concrete evidence supports or weakens this signal: {signal.description}",
                evidence_types=evidence_types,
                positive_indicators=(signal.logic,),
                negative_indicators=signal.false_positive_patterns,
                linked_signal_ids=(signal.signal_id,),
            ),
        ),
        reasoning_steps=(
            PlaybookReasoningStep(
                step_id="step-evidence-quality",
                name="Evidence quality",
                question="Is the signal backed by source-linked facts rather than a narrative label?",
                inputs=evidence_types,
                output="evidence_quality_assessment",
                common_failure_mode="Treating a theme mention as company-level evidence.",
            ),
            PlaybookReasoningStep(
                step_id="step-contrast",
                name="Winner-control contrast",
                question="Does this signal appear more clearly in winners than controls or failures?",
                inputs=("case_signal_observations", "pre_surge_signal_logic"),
                output="contrast_assessment",
                common_failure_mode="Promoting a signal that is common in both winners and non-winners.",
            ),
        ),
        positive_patterns=(signal.promotion_reason,),
        counter_patterns=signal.counterexamples,
        false_positive_traps=signal.false_positive_patterns,
        linked_signal_ids=(signal.signal_id,),
        linked_theme_ids=linked_theme_ids,
        evidence_case_refs={
            "positive": signal.positive_examples,
            "counterexamples": signal.counterexamples,
        },
        confidence=_clamp(0.45 + signal.statistics.prevalence_lift + signal.statistics.average_score_lift),
        promotion_status="candidate",
        hindsight_risk_notes=signal.hindsight_risk_notes
        or ("Signal-derived playbook requires forward validation before it affects prompt defaults.",),
    )


def _general_questions(evidence_types: tuple[str, ...], linked_signal_ids: tuple[str, ...]) -> tuple[PlaybookQuestion, ...]:
    return (
        PlaybookQuestion(
            question_id="q-novelty",
            prompt="What is newly changing versus the prior 6-12 months, and is it visible in source-linked evidence?",
            evidence_types=evidence_types,
            positive_indicators=("New orders, contracts, backlog, customer adoption, guidance, or management commentary.",),
            negative_indicators=("Generic theme mentions or stale historical growth with no new inflection.",),
            linked_signal_ids=linked_signal_ids,
        ),
        PlaybookQuestion(
            question_id="q-business-translation",
            prompt="How could the change translate into revenue, margins, utilization, valuation, or analyst expectations?",
            evidence_types=("filing", "news", "transcript", "financial", "valuation"),
            positive_indicators=("Clear mechanism from catalyst to financial or valuation impact.",),
            negative_indicators=("No company-specific exposure or only one-off/non-recurring impact.",),
            linked_signal_ids=linked_signal_ids,
        ),
        PlaybookQuestion(
            question_id="q-market-confirmation",
            prompt="Is the market beginning to confirm the setup without already making it too crowded?",
            evidence_types=("price_volume", "analyst", "valuation"),
            positive_indicators=("Early momentum, liquidity expansion, and still-plausible valuation room.",),
            negative_indicators=("Fully priced move, crowded story, or weak price-volume confirmation.",),
            linked_signal_ids=linked_signal_ids,
        ),
    )


def _general_steps() -> tuple[PlaybookReasoningStep, ...]:
    return (
        PlaybookReasoningStep(
            step_id="step-observe",
            name="Observe the new fact pattern",
            question="What changed before the repricing window, and which source proves it was known then?",
            inputs=("research_packet.evidence", "research_packet.catalysts"),
            output="new_fact_pattern",
            common_failure_mode="Using future explanations or unsourced narrative shortcuts.",
        ),
        PlaybookReasoningStep(
            step_id="step-triangulate",
            name="Triangulate across sources",
            question="Do filings, news, transcript commentary, fundamentals, and price-volume agree or conflict?",
            inputs=("documents", "features", "blind_analysis", "signal_observations"),
            output="cross_evidence_assessment",
            common_failure_mode="Trusting one strong headline while other evidence remains missing.",
        ),
        PlaybookReasoningStep(
            step_id="step-conclude",
            name="Conclude with disconfirmation",
            question="Would this still look like a surge candidate after naming the best contrary evidence?",
            inputs=("pre_surge_signals", "contrary_evidence", "false_positive_patterns"),
            output="surge_candidate_judgment",
            common_failure_mode="Writing a bullish story without explicit falsifiers.",
        ),
    )


def _openai_playbook_prompt(
    cases: list[HistoricalCase],
    blind_analyses: list[BlindCaseAnalysis],
    learning_result: ColdStartLearningResult,
    theme_maps: ThemeMapBuildResult,
) -> str:
    analysis_by_case = {analysis.case_id: analysis for analysis in blind_analyses}
    ref_by_case_id = {case.case_id: f"case_{index:03d}" for index, case in enumerate(cases, start=1)}
    payload = {
        "task": (
            "Synthesize reusable research playbooks for finding possible 3-6 month surge stocks. "
            "Compare winner/control/failure cases retrospectively, but write playbooks as future-facing research checklists."
        ),
        "schema_version": PLAYBOOK_SCHEMA_VERSION,
        "cases": [
            _case_prompt_summary(case, ref_by_case_id[case.case_id], analysis_by_case.get(case.case_id))
            for case in cases
        ],
        "learned_signals": [
            _signal_prompt_summary(signal, ref_by_case_id)
            for signal in learning_result.signal_logic
        ],
        "theme_ids": [theme.theme_id for theme in theme_maps.theme_maps],
        "required_json_schema": {
            "schema_version": PLAYBOOK_SCHEMA_VERSION,
            "playbooks": [
                {
                    "playbook_id": "string",
                    "name": "string",
                    "purpose": "string",
                    "version": "playbook-v0.1",
                    "applies_when": ["string"],
                    "core_questions": [
                        {
                            "question_id": "string",
                            "prompt": "string",
                            "evidence_types": ["filing | news | transcript | financial | price_volume | analyst | valuation | catalyst"],
                            "positive_indicators": ["string"],
                            "negative_indicators": ["string"],
                            "linked_signal_ids": ["string"],
                        }
                    ],
                    "reasoning_steps": [
                        {
                            "step_id": "string",
                            "name": "string",
                            "question": "string",
                            "inputs": ["string"],
                            "output": "string",
                            "common_failure_mode": "string",
                        }
                    ],
                    "positive_patterns": ["string"],
                    "counter_patterns": ["string"],
                    "false_positive_traps": ["string"],
                    "linked_signal_ids": ["string"],
                    "linked_theme_ids": ["string"],
                    "evidence_case_refs": {
                        "positive": ["case_001"],
                        "counterexamples": ["case_002"],
                    },
                    "confidence": "number between 0 and 1",
                    "promotion_status": "candidate",
                    "hindsight_risk_notes": ["string"],
                }
            ],
            "warnings": ["string"],
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _case_prompt_summary(
    case: HistoricalCase,
    case_ref: str,
    analysis: BlindCaseAnalysis | None,
) -> dict[str, Any]:
    packet = case.packet
    return {
        "case_ref": case_ref,
        "label": case.label.value,
        "as_of_date": packet.as_of.as_of_date.isoformat(),
        "sector": packet.company.sector,
        "industry": packet.company.industry,
        "evidence_kinds": sorted({item.kind.value for item in packet.evidence}),
        "catalyst_count": len(packet.catalysts),
        "blind_analysis": _blind_prompt_summary(analysis),
    }


def _blind_prompt_summary(analysis: BlindCaseAnalysis | None) -> dict[str, Any] | None:
    if analysis is None:
        return None
    return {
        "as_of_date": analysis.as_of_date,
        "surge_candidate": analysis.surge_candidate,
        "surge_candidate_reason": analysis.surge_candidate_reason,
        "expectation_gap": analysis.expectation_gap,
        "pre_surge_signals": list(analysis.pre_surge_signals),
        "contrary_evidence": list(analysis.contrary_evidence),
        "catalyst_watch": list(analysis.catalyst_watch),
        "confidence": analysis.confidence,
    }


def _signal_prompt_summary(signal: PreSurgeSignalLogic, ref_by_case_id: dict[str, str]) -> dict[str, Any]:
    data = signal.to_dict()
    data["positive_examples"] = [
        ref_by_case_id[case_id]
        for case_id in signal.positive_examples
        if case_id in ref_by_case_id
    ]
    data["counterexamples"] = [
        ref_by_case_id[case_id]
        for case_id in signal.counterexamples
        if case_id in ref_by_case_id
    ]
    return data


def _patterns_from_analyses(
    analyses: Iterable[BlindCaseAnalysis | None],
    attribute: str,
) -> tuple[str, ...]:
    return _unique(
        item
        for analysis in analyses
        if analysis is not None
        for item in getattr(analysis, attribute)
    )[:8]


def _evidence_types(cases: list[HistoricalCase]) -> tuple[str, ...]:
    values = {
        item.kind.value
        for case in cases
        for item in case.packet.evidence
    }
    values.update(name.split(".", 1)[0] for case in cases for name in _feature_names(case))
    return tuple(sorted(values or {"research_packet"}))


def _feature_names(case: HistoricalCase) -> tuple[str, ...]:
    return tuple(feature.name for feature in case.packet.features)


def _average_confidence(analyses: Iterable[BlindCaseAnalysis]) -> float:
    values = [analysis.confidence for analysis in analyses]
    if not values:
        return 0.35
    return round(sum(values) / len(values), 4)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen = set()
    result = []
    for value in values:
        cleaned = " ".join(str(value).split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return tuple(result)


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _require_non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must not be empty")


def _string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"playbook missing {key}")
    return value


def _string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"playbook {key} must be a string list")
    return value


def _dict_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValidationError(f"playbook {key} must be an object list")
    return value


def _confidence(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
        raise ValidationError("playbook confidence must be between 0 and 1")
    return float(value)
