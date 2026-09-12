"""Signal Update, Mining, and execution model-role adapters."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import (
    StructuredValidationError,
    ValidationError,
    ValidationIssue,
)
from stock_opportunity_agent.research.scheme_evolution import (
    AgentStep,
    CandidateExecutionRejected,
    RuntimeBudgetExceeded,
    SignalMiningDecision,
    SignalMiningHypothesis,
    SignalMiningModel,
    SignalMiningObservation,
    SignalMiningSignature,
    SignalUpdateDecision,
    SignalUpdateModel,
    SIGNAL_UPDATE_MUTABLE_PATHS,
    _normalized_projection_text,
    validate_signal_update_candidate,
    validate_signal_mining_signatures,
)
from stock_opportunity_agent.signal_library import (
    LLMSignalBatchInput,
    SignalExecutionStatus,
    SignalResult,
    SignalSpec,
    SignalValue,
    signal_execution_failure_result,
    validate_signal_result,
)
from stock_opportunity_agent.research.evolution_settings import (
    LLM_SIGNAL_CONTEXT_CHUNK_CHARS,
    LLM_SIGNAL_CONTEXT_CHUNK_OVERLAP,
    MAX_LLM_SIGNAL_CONTEXT_CHARS,
    ROLE_OUTPUT_TOKEN_LIMITS,
    _LLM_SIGNAL_QUERY_STOP_WORDS,
)
from stock_opportunity_agent.research.evolution_transport import (
    ExternalBudgetExhausted,
    JSONRoleCaller,
    _complete_json_with_invalid_value,
    _scan_payload,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _SIGNAL_BATCH_RESULT_OUTPUT,
    _UNTRUSTED_DATA_INSTRUCTION,
    _complete_parsed_role,
    _fixed_semantics_match,
    _parse_role_output,
)
from stock_opportunity_agent.research.evolution_research_validation import (
    _normalize_signal_result_output,
)


_SIGNAL_MINING_HYPOTHESES_V3_OUTPUT = (
    ' Output contract signal-mining-hypothesis-v7: return exactly {"conclusion":'
    '"hypotheses"|"no_testable_hypothesis","hypotheses":[],"no_hypothesis":'
    'object|null,"need_dispositions":[]}. For conclusion="hypotheses", '
    "no_hypothesis is null and each "
    "hypothesis has exactly proposal_ref (copied from hypothesis_slots), measurement "
    "(exactly observable, value_kind, normalization), where value_kind is exactly "
    "boolean, ordinal, numeric, or categorical; applicability (exactly rule "
    "and values), "
    "expected_direction, retrieval_intent (exactly source_types and query), "
    "falsifiers, and need_refs. Each falsifier has exactly condition and "
    "expected_observation. expected_direction is one of higher_in_positive, "
    "lower_in_positive, more_frequent_in_positive, less_frequent_in_positive, or "
    "different_between_groups. For conclusion=no_testable_hypothesis, hypotheses is "
    "empty and no_hypothesis has exactly reason_code, rationale, and need_refs. "
    "reason_code is no_new_measurable_gap, insufficient_retrieval_basis, or "
    "prior_attempts_exhausted. Each need_dispositions item has exactly need_refs, "
    "disposition, signal_refs, and rationale. disposition is new_measurement, "
    "deferred_measurement, update_existing, repair_dependency, already_covered, "
    "not_testable, or fast_plan_action. Every "
    "rationale field is a non-empty array of short strings. Every supplied "
    "signal_need_items need_ref and every ordinary backlog items request_id is a "
    "runtime need_ref and must appear exactly once; only supplied stable signal_refs "
    "may be cited. update_existing and already_covered require exactly one stable "
    "signal_ref per row. new_measurement, deferred_measurement, repair_dependency, "
    "not_testable, and fast_plan_action require signal_refs=[]. "
    "deferred_measurement means the need defines a reusable measurement but is "
    "outside this bounded portfolio; it remains unresolved. An item whose "
    "kind=unmatched_signal_need cannot be already_covered. It may be "
    "update_existing only when every grouped need contains one of the cited "
    "card's exact routing_answer_need_phrases. A backlog row already carrying the "
    "cited signal_ref is also an explicit update basis. fast_plan_action is valid only for "
    "meta_reflection_action refs whose retrieval, analysis, or prediction-policy "
    "change already flows through meta-memory to the next Fast proposer. Group "
    "need_refs only when the same measurement or dependency "
    "reason genuinely addresses every ref; never pool semantically unrelated refs "
    "to shorten the ledger. Each hypothesis may cite only need_refs directly "
    "addressed by its one measurement. The union of all hypothesis need_refs must "
    "exactly equal the refs dispositioned as new_measurement; every other need "
    "must use another disposition. no_hypothesis.need_refs is only a "
    "small explanatory subset and need not repeat the complete disposition ledger. "
    "Never add Markdown or company identities."
)


def _request_trace_cursor(caller: JSONRoleCaller) -> int:
    """Return a stable cursor into an optional exact-request trace."""

    trace = getattr(caller, "request_hash_trace", ())
    return len(trace) if isinstance(trace, (list, tuple)) else 0


def _request_refs_since(caller: JSONRoleCaller, cursor: int) -> tuple[str, ...]:
    """Return exact request hashes emitted since ``cursor`` when available."""

    trace = getattr(caller, "request_hash_trace", ())
    if not isinstance(trace, (list, tuple)):
        return ()
    return tuple(str(item) for item in trace[cursor:])


def _complete_parsed_role_with_trace(
    caller: JSONRoleCaller, **kwargs: Any
) -> tuple[Any, AgentUsage, tuple[str, ...]]:
    """Run one logical role and retain every initial/correction request ref."""

    cursor = _request_trace_cursor(caller)
    try:
        value, usage = _complete_parsed_role(caller, **kwargs)
    except CandidateExecutionRejected as exc:
        raise CandidateExecutionRejected(
            exc.stage,
            str(exc),
            exc.usage,
            details={
                **dict(exc.details),
                "request_refs": list(_request_refs_since(caller, cursor)),
            },
        ) from exc
    return value, usage, _request_refs_since(caller, cursor)


def _request_slow_source_refs(
    caller: JSONRoleCaller,
    payload: Mapping[str, Any],
    *,
    identity_guard_aliases: Iterable[str],
) -> AgentStep[tuple[str, ...]]:
    """Return one typed bounded source-read selection without source contents."""

    available = tuple(
        str(item.get("ref"))
        for item in payload.get("available_sources", ())
        if isinstance(item, Mapping) and item.get("ref")
    )

    def parse(value: Mapping[str, Any]) -> tuple[str, ...]:
        if set(value) != {"read_source_refs"} or not isinstance(
            value.get("read_source_refs"), list
        ):
            raise ValidationError(
                "Slow source read requires exactly read_source_refs array"
            )
        refs = tuple(str(item) for item in value["read_source_refs"])
        if len(refs) > 8 or len(set(refs)) != len(refs) or not set(refs) <= set(available):
            raise ValidationError(
                "Slow source read refs must be unique supplied opaque refs, at most 8"
            )
        return refs

    value, usage, request_refs = _complete_parsed_role_with_trace(
        caller,
        stage="slow_source_read",
        system_prompt=(
            "Select only complete opaque Slow source refs needed for the named role. "
            "Do not infer source contents from ref names. Return exactly "
            '{"read_source_refs":[]} using only supplied refs; an empty list means '
            "the current complete view is sufficient."
            + _UNTRUSTED_DATA_INSTRUCTION
        ),
        payload=payload,
        parser=parse,
        allow_outcomes=False,
        anonymous_aliases=(),
        reject_output_aliases=identity_guard_aliases,
        max_output_tokens=512,
        temperature=0.0,
        stable_correction_prefix=True,
    )
    return AgentStep(value, usage, metadata={"request_refs": request_refs})


def _h1_redundant_signal_ref_fallback(
    failed_output: Mapping[str, Any], failure: ValidationError
) -> tuple[dict[str, Any], dict[str, tuple[str, ...]]] | None:
    """Remove only a redundant legacy singular H1 Signal-ref field."""

    del failure
    raw_rows = failed_output.get("need_dispositions")
    if not isinstance(raw_rows, list):
        return None
    result = deepcopy(dict(failed_output))
    result_rows = result.get("need_dispositions")
    if not isinstance(result_rows, list):
        return None
    removed_paths: list[str] = []
    for index, row in enumerate(result_rows):
        if not isinstance(row, dict) or "signal_ref" not in row:
            continue
        plural = row.get("signal_refs")
        if (
            not isinstance(plural, list)
            or len(plural) != 1
            or row.get("signal_ref") != plural[0]
        ):
            return None
        row.pop("signal_ref")
        removed_paths.append(f"need_dispositions[{index}].signal_ref")
    if not removed_paths:
        return None
    return result, {
        "source_substitution_paths": (),
        "removed_paths": tuple(removed_paths),
    }


_H1_WITHHELD_CONTEXT_RATIONALE = re.compile(
    r"(?:\b(?:no|without|absent|missing|hidden|withheld|not\s+visible)\b"
    r".{0,160}\b(?:case(?:[- ]level)?.{0,60}(?:text|evidence)|case\s+labels?|"
    r"(?:full\s+)?source\s+excerpts?|candidate\s+roster|group\s+membership)\b|"
    r"\b(?:case(?:[- ]level)?.{0,60}(?:text|evidence)|case\s+labels?|"
    r"(?:full\s+)?source\s+excerpts?|candidate\s+roster|group\s+membership)\b"
    r".{0,160}\b(?:absent|missing|hidden|withheld|not\s+visible)\b)",
    re.IGNORECASE,
)


_H1_GENERIC_TOPIC_TERMS = frozenset(
    {
        "about",
        "after",
        "against",
        "before",
        "case",
        "company",
        "compare",
        "control",
        "could",
        "from",
        "have",
        "into",
        "latest",
        "more",
        "pattern",
        "positive",
        "recent",
        "show",
        "signal",
        "than",
        "that",
        "their",
        "these",
        "they",
        "this",
        "those",
        "what",
        "when",
        "where",
        "which",
        "with",
        "would",
    }
)


_H1_OUTCOME_TERM = (
    r"(?:earnings\s+surprise|revenue\s+growth|returns?|price|growth|"
    r"performance|outcomes?|market\s+reaction|stock\s+movement)"
)
_H1_FUTURE_HORIZON = (
    r"(?:short[- ]term|within\s+\d+\s+(?:calendar\s+|trading\s+)?days?|"
    r"(?:over|during|in)\s+the\s+next\s+"
    r"(?:(?:one|two|three|four|five|six|\d+)\s+)?"
    r"(?:quarters?|months?|years?|trading\s+days?)|"
    r"(?:next|subsequent|following)\b.{0,30}\b"
    r"(?:quarter(?:ly)?|quarters?|months?|years?|trading\s+days?))"
)
_H1_ALTERNATE_TEST_OUTCOME = re.compile(
    rf"\b(?:event\s+stud(?:y|ies)|"
    rf"{_H1_FUTURE_HORIZON}.{{0,80}}\b{_H1_OUTCOME_TERM}|"
    rf"{_H1_OUTCOME_TERM}.{{0,80}}\b{_H1_FUTURE_HORIZON}|"
    r"(?:price|market|stock)\s+"
    r"(?:reaction|movement|change|increase|decrease|returns?|trend|momentum|"
    r"performance)|(?:stocks?\s+)?(?:outperform|underperform)\w*)\b",
    re.IGNORECASE,
)


_H1_POST_CUTOFF_SOURCE = re.compile(
    r"\b(?:post[- ](?:series|cutoff|prediction(?:[- ]time)?)|"
    r"after\s+(?:the\s+)?(?:point-in-time\s+)?(?:market|price|source|evidence)\s+"
    r"series\s+(?:end|ends|ended)|after\s+(?:the\s+)?prediction[- ](?:time|date)|"
    r"subsequent\s+to\s+(?:the\s+)?cutoff)\b",
    re.IGNORECASE,
)


_H1_HIDDEN_APPLICABILITY_TOPIC = re.compile(
    r"\b(?:analyst\s+(?:coverage|estimates?)|consensus|estimates?|guidance|"
    r"decomposition|breakdown|actual\s+(?:results?|metrics?)|"
    r"market\s+data|standard\s+industry\s+codes?|classification|"
    r"(?:segment|revenue[- ]driver)\b.{0,30}\bdisclosures?)\b",
    re.IGNORECASE,
)


_H1_APPLICABILITY_RULE_PATTERN = re.compile(
    r"^(business_description_topics|industry_values|sector_values|"
    r"exchange_values|market_cap_bucket_values|listing_age_bucket_values|"
    r"raw_info_source_type_values):([^:;\n]+)$"
)


def _h1_topic_terms(value: str) -> frozenset[str]:
    """Return deterministic topic terms for demand-grounding validation."""

    value = re.sub(r"\byear[- ]over[- ]year\b", " yoy ", value, flags=re.IGNORECASE)
    result: set[str] = set()
    for raw in re.findall(r"[A-Za-z0-9]+", value.casefold()):
        if (len(raw) < 4 and raw != "yoy") or raw in _H1_GENERIC_TOPIC_TERMS:
            continue
        if raw in {"revise", "revised", "revises", "revision", "revisions"}:
            term = "revision"
        else:
            term = raw[:-3] + "y" if raw.endswith("ies") else raw
        if term.endswith("s") and len(term) > 4 and not term.endswith("ss"):
            term = term[:-1]
        if term in _H1_GENERIC_TOPIC_TERMS:
            continue
        result.add(term)
    return frozenset(result)


def _h1_applicability_rule(
    value: str,
    *,
    contract: Mapping[str, Any] | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Parse one non-conjunctive rule over the actual anonymous H2 brief schema."""

    if value == "all_ready_issuers":
        return value, ()
    match = _H1_APPLICABILITY_RULE_PATTERN.fullmatch(value)
    if match is None:
        raise ValidationError(
            "applicability must be all_ready_issuers or one canonical "
            "<field_rule>:<value>|... rule"
        )
    rule_name = match.group(1)
    values = tuple(item.strip() for item in match.group(2).split("|"))
    if (
        not 1 <= len(values) <= 6
        or any(not item for item in values)
        or len({item.casefold() for item in values}) != len(values)
        or value != f"{rule_name}:{'|'.join(values)}"
    ):
        raise ValidationError(
            "applicability values must contain 1-6 unique canonical entries"
        )
    if rule_name == "business_description_topics":
        hidden = next(
            (
                matched.group(0)
                for item in values
                if (matched := _H1_HIDDEN_APPLICABILITY_TOPIC.search(item))
                is not None
            ),
            None,
        )
        topic_sets = tuple(_h1_topic_terms(item) for item in values)
        if hidden is not None:
            raise ValidationError(
                "business-description applicability cannot require hidden content; "
                f"matched {hidden!r}"
            )
        if any(not 1 <= len(terms) <= 4 for terms in topic_sets) or len(
            set().union(*topic_sets)
        ) > 8:
            raise ValidationError(
                "business-description applicability requires 1-6 short topics "
                "with at most 8 total normalized terms"
            )
        return rule_name, values
    if contract is None:
        return rule_name, values
    observed = (
        contract.get("observed_values", {})
        if isinstance(contract, Mapping)
        else {}
    )
    allowed = {
        str(item).casefold()
        for item in (
            observed.get(rule_name, ()) if isinstance(observed, Mapping) else ()
        )
    }
    unsupported = [item for item in values if item.casefold() not in allowed]
    if unsupported:
        raise ValidationError(
            f"applicability {rule_name} must use supplied observed values; "
            "unsupported: " + ", ".join(unsupported)
        )
    return rule_name, values


def _h2_applicability_matches(
    applicability: str,
    brief: Mapping[str, Any],
) -> bool:
    """Return whether one anonymous brief satisfies a canonical H1 screen."""

    try:
        rule_name, values = _h1_applicability_rule(applicability)
    except ValidationError:
        return False
    if rule_name == "all_ready_issuers":
        return True
    if rule_name == "business_description_topics":
        description_terms = _h1_topic_terms(str(brief.get("business_description", "")))
        return any(_h1_topic_terms(item) <= description_terms for item in values)
    field_by_rule = {
        "industry_values": "industry",
        "sector_values": "sector",
        "exchange_values": "exchange",
        "market_cap_bucket_values": "market_cap_bucket",
        "listing_age_bucket_values": "listing_age_bucket",
    }
    if rule_name == "raw_info_source_type_values":
        coverage = brief.get("raw_info_coverage", {})
        visible = (
            coverage.get("source_types", ())
            if isinstance(coverage, Mapping)
            else ()
        )
    else:
        visible = (brief.get(field_by_rule[rule_name]),)
    visible_values = {
        str(item).casefold() for item in visible if item is not None and str(item)
    }
    return any(item.casefold() in visible_values for item in values)


_SIGNAL_MINING_RANKING_OUTPUT = (
    ' Output contract for SignalMiningRankings: return exactly {"rankings":[]}, '
    "where rankings is a JSON array with one object per supplied hypothesis. "
    "Each ranking object has exactly hypothesis_id (a supplied string) and cases "
    "(an array from zero through rules.max_case_refs_per_hypothesis items). Each "
    "case object has exactly case_ref (a supplied opaque string), profile_evidence "
    "(a string), and applicability_reason (a string). Return every supplied "
    "hypothesis exactly once, only supplied case_ref values, no wrapper keys, and "
    "no Markdown."
)


_H2_SELF_DISQUALIFYING_REASON_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in (
        r"\b(?:lack|lacks|lacking|missing|absent|unavailable|insufficient)\b",
        r"\b(?:too|only)\s+(?:generic|broad|indirect|speculative)\b",
        r"\b(?:cannot|can't|does not|doesn't|fails? to)\b.{0,60}"
        r"\b(?:confirm|establish|demonstrate|show|support)\b",
        r"\b(?:no|not|never)\b.{0,80}"
        r"\b(?:provided|available|shown|disclosed|mentioned|included|present)\b",
        r"\b(?:could|may|might)\b.{0,60}"
        r"\b(?:apply|applicable|relevant|support|lead)\b",
    )
)


_H2_INFERENTIAL_REASON_PATTERN = re.compile(
    r"\b(?:suggests?|implies?|indicates?|aligns?|likely|typically|apparently|"
    r"appears?|seems?|potentially|presumably|may|might|could)\b",
    re.IGNORECASE,
)


def _h2_reason_disclaims_applicability(value: str) -> bool:
    """Return whether an H2 reason admits it lacks positive profile support."""

    return any(
        pattern.search(value) is not None
        for pattern in _H2_SELF_DISQUALIFYING_REASON_PATTERNS
    )


_SIGNAL_MINING_DECISIONS_OUTPUT = (
    " Return one JSON object with exactly decisions (an array). Each decision "
    "has exactly hypothesis_id (string), disposition (string), rationale "
    "(non-empty array of evidence-grounded strings), and candidate (object or null). "
    ' disposition must be "supported", "refine", "rejected", or "inconclusive". '
    "Use inconclusive only for semantically insufficient visible evidence. Only supported "
    "may carry a candidate object, which must contain exactly spec, skill, and tests "
    "under the supplied candidate_contract; otherwise candidate must be null."
)


_SIGNAL_MINING_EXPLORATION_DECISIONS_OUTPUT = (
    " Return one JSON object with exactly decisions and no_candidate. decisions is "
    "a bounded array and each row describes one recurring cross-case pattern, never "
    "one supplied case. Each row has exactly hypothesis_id, disposition, rationale, "
    "contrast, and candidate. hypothesis_id must copy one unused supplied "
    "decision_slots value. disposition must be supported. rationale is a non-empty "
    "array of evidence-grounded strings. contrast has exactly positive_case_refs, "
    "control_case_refs, and observable_difference; both ref arrays are non-empty, "
    "unique subsets of the corresponding supplied labels, and observable_difference "
    "is a non-empty statement of how those groups differ. candidate must contain "
    "exactly spec, skill, and tests under candidate_contract. case_ref is not a "
    "decision field. When "
    "decisions is non-empty, no_candidate must "
    "be null. When decisions is empty, no_candidate has exactly reason_code, "
    "rationale, and considered_case_refs. reason_code is no_measurable_pattern, "
    "insufficient_evidence, or already_covered. rationale is a non-empty array of "
    "short strings and considered_case_refs must copy every supplied signature "
    "case_ref exactly once in supplied order. A rationale that identifies a "
    "specific missing, absent, truncated, partial, or unavailable source input "
    "must be its own canonical gap citation: copy exactly one supplied "
    "evidence_gaps string and prefix it with [case_ref] and one space. Never "
    "paraphrase, combine, or extend source gaps. Generic evidence-insufficiency "
    "conclusions that name no particular absent input need no gap citation. "
    "Do not restate any case_ref together with positive or control in rationale; "
    "the runtime owns and records exact case-to-label mappings separately."
)


_MINING_EVIDENCE_ABSENCE = re.compile(
    r"\b(?:lack(?:s|ed|ing)?|missing|insufficient|unrelated|"
    r"do(?:es)?\s+not\s+(?:contain|include)|"
    r"no\s+basis\s+to\s+evaluate|cannot\s+evaluate|unable\s+to\s+evaluate)\b",
    flags=re.IGNORECASE,
)


_E2_VISIBLE_LABEL_DENIAL = re.compile(
    r"(?:\b(?:outcome|label)s?[- ]hidden\b|"
    r"\blabels?\b.{0,50}\b(?:hidden|unavailable|absent|not\s+visible|"
    r"cannot\s+be\s+compared|uncomparable)\b)",
    re.IGNORECASE,
)


_E2_GROUP_LABEL = re.compile(r"\b(?:positive|control)(?:s|\s+cases?)?\b", re.IGNORECASE)


_E2_SOURCE_GAP_MARKER = (
    r"(?:missing|absent|truncated|partial(?:ly)?|incomplete|unavailable|"
    r"do(?:es)?\s+not\s+(?:show|contain|include|provide)|"
    r"not\s+(?:shown|provided|included|present|available))"
)
_E2_SOURCE_INPUT_NOUN = (
    r"(?:source|input|data|evidence|document|record|excerpt|context|figure|"
    r"statement|disclosure|filing|financial)s?"
)
_E2_SPECIFIC_SOURCE_GAP = re.compile(
    rf"(?:\b{_E2_SOURCE_GAP_MARKER}\b.{{0,80}}\b{_E2_SOURCE_INPUT_NOUN}\b|"
    rf"\b{_E2_SOURCE_INPUT_NOUN}\b.{{0,80}}\b{_E2_SOURCE_GAP_MARKER}\b)",
    re.IGNORECASE,
)


_E2_PROFILE_ATTRIBUTE_PATTERNS = (
    ("sector", re.compile(r"\bsectors?\b", re.IGNORECASE)),
    ("industry", re.compile(r"\bindustr(?:y|ies)\b", re.IGNORECASE)),
    ("business model", re.compile(r"\bbusiness\s+models?\b", re.IGNORECASE)),
    (
        "market-cap class",
        re.compile(
            r"\b(?:market\s+cap(?:italization)?|(?:micro|small|mid|large)[- ]cap)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "geography",
        re.compile(
            r"\b(?:geograph(?:y|ic|ical|ically)|countries|country|regions?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "listing venue",
        re.compile(
            r"\b(?:listing\s+venue|stock\s+exchange|exchanges?)\b",
            re.IGNORECASE,
        ),
    ),
)


def _e2_profile_claims_without_literal_support(
    claims: Iterable[str],
    signatures: Iterable[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return profile attributes claimed by E2 but absent from literal projections."""

    claim_text = "\n".join(str(item) for item in claims)
    source_text = "\n".join(
        str(observation.get(field, ""))
        for signature in signatures
        if isinstance(signature, Mapping)
        for observation in signature.get("observations", ())
        if isinstance(observation, Mapping)
        for field in ("exact_span", "summary")
    )
    return tuple(
        name
        for name, pattern in _E2_PROFILE_ATTRIBUTE_PATTERNS
        if pattern.search(claim_text) and not pattern.search(source_text)
    )


def _e2_uncited_source_gap_claim_indexes(
    claims: Iterable[str],
    signatures: Iterable[Mapping[str, Any]],
) -> tuple[int, ...]:
    """Return E2 rationale indexes that invent or paraphrase a source gap."""

    canonical = {
        f"[{signature['case_ref']}] {gap}"
        for signature in signatures
        if isinstance(signature, Mapping)
        and isinstance(signature.get("case_ref"), str)
        for gap in signature.get("evidence_gaps", ())
        if isinstance(gap, str) and gap.strip()
    }
    return tuple(
        index
        for index, claim in enumerate(claims)
        if _E2_SPECIFIC_SOURCE_GAP.search(str(claim))
        and str(claim) not in canonical
    )


def _e2_free_text_label_assignment_indexes(
    claims: Iterable[str],
    signatures: Iterable[Mapping[str, Any]],
) -> tuple[int, ...]:
    """Reject prose label mappings in favor of the exact runtime-owned map."""

    rows = tuple(item for item in signatures if isinstance(item, Mapping))
    refs = tuple(
        str(item["case_ref"])
        for item in rows
        if isinstance(item.get("case_ref"), str) and item["case_ref"]
    )
    canonical_gaps = {
        f"[{item['case_ref']}] {gap}"
        for item in rows
        for gap in item.get("evidence_gaps", ())
        if isinstance(gap, str) and gap.strip()
    }

    def mentions_ref(claim: str, ref: str) -> bool:
        return bool(
            re.search(
                rf"(?<![A-Za-z0-9_-]){re.escape(ref)}(?![A-Za-z0-9_-])",
                claim,
            )
        )

    return tuple(
        index
        for index, raw_claim in enumerate(claims)
        if (claim := str(raw_claim)) not in canonical_gaps
        and _E2_GROUP_LABEL.search(claim)
        and any(mentions_ref(claim, ref) for ref in refs)
    )


_SIGNAL_MINING_SIGNATURES_OUTPUT = (
    " Return one JSON object with exactly signatures (an array). Each signature "
    "has exactly case_ref (a supplied opaque string), observations (an array), "
    "and evidence_gaps (an array of strings). Each observation has exactly summary "
    "(a grounded interpretation), document_ref (copied from that case's evidence), "
    "and exact_span (an exact contiguous 8-240 character substring copied from that "
    "document's content_excerpt or one structured_context concept record's "
    "exact_span). A citation must stay inside one record; wrapper concept/label/unit "
    "fields and text joined across records are not facts. For structured_context "
    "with two records for one concept, prefer observations for both supplied record "
    "exact_spans before unrelated one-period concepts, so later comparison can "
    "observe within-case direction. Return at most six "
    "observations per case. When no "
    "visible excerpt supports an observation, return observations=[] and at least one "
    "specific evidence gap; never invent an observation to make the array non-empty. "
    "Return one signature for every supplied case_ref and do not infer outcomes."
)


_SIGNAL_UPDATE_V2_OUTPUT = (
    " Return one JSON object with exactly signal_ref, disposition, problem_type, "
    "rationale, case_diagnostics, changed_paths, and candidate. rationale and "
    "changed_paths are arrays of strings. changed_paths must exactly declare the "
    "effective mutable spec or skill fields changed from the supplied vNext template; "
    "it is empty unless disposition is update. Copy changed_paths only from "
    "candidate_contract.changed_paths_allowed. Copy candidate.tests byte-for-byte "
    "from candidate_contract.vnext_template.tests. Never include spec.version, "
    "spec.definition, tests, or whole-section aliases. "
    "The unchanged fixtures must still execute to their expected values under the "
    "updated retrieval and parameters; do not add minimum observations, periods, "
    "span, or source-group requirements that those fixtures do not contain. "
    "case_diagnostics must contain "
    "exactly one object per supplied case_ref, with exactly case_ref, "
    "evidence_verdict, facts, evidence_gaps, outcome_relation, and "
    "outcome_explanation. evidence_verdict is supported, contradicted, or "
    "insufficient. Every fact has exactly document_ref and exact_span; "
    "document_ref and exact_span must be copied from that case's source evidence. "
    "outcome_relation is aligned, misaligned, or not_assessable. disposition is "
    "no_change, defer, or update; only update may carry the supplied candidate."
)


class LLMSignalUpdateModel(SignalUpdateModel):
    """One semantic update decision after local target and induction selection."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller
        self.identity_guard_aliases: tuple[str, ...] = ()
        self.candidate_validator: Callable[
            [str, Mapping[str, Any], tuple[str, ...]], None
        ] | None = None

    def set_identity_guard_aliases(self, value: Iterable[str]) -> None:
        self.identity_guard_aliases = tuple(value)

    def request_slow_sources(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[str, ...]]:
        """Request one bounded runtime-resolved source view for Update."""

        return _request_slow_source_refs(
            self.caller,
            payload,
            identity_guard_aliases=self.identity_guard_aliases,
        )

    def set_candidate_validator(
        self,
        value: Callable[[str, Mapping[str, Any], tuple[str, ...]], None],
    ) -> None:
        """Bind a side-effect-free runtime candidate validator."""

        self.candidate_validator = value

    @property
    def work_identity(self) -> Mapping[str, Any]:
        """Return the stable role/model identity used by Slow search work."""

        registration = getattr(self.caller, "registration", None)
        return {
            "adapter": f"{type(self).__module__}.{type(self).__qualname__}",
            "model_alias": getattr(registration, "alias", None),
            "provider": getattr(registration, "provider", None),
            "model": getattr(registration, "model", None),
            "proposal_profile": getattr(registration, "proposal_profile", None),
            "source_read_contract": "slow-source-read-v1",
        }

    def update(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[SignalUpdateDecision]:
        """Run the sole production Signal Update v2 contract."""

        return self._update_v2(payload)

    def _update_v2(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[SignalUpdateDecision]:
        """Require source-grounded facts before outcome association."""

        target = payload.get("target", {})
        if not isinstance(target, Mapping) or not target.get("signal_ref"):
            raise ValidationError("Signal Update requires one local target")
        target_ref = str(target["signal_ref"])
        packets = tuple(
            item
            for item in payload.get("induction_cases", ())
            if isinstance(item, Mapping) and item.get("case_ref")
        )
        packet_by_ref = {str(item["case_ref"]): item for item in packets}
        if len(packet_by_ref) != len(packets):
            raise ValidationError("Signal Update v2 case_ref values must be unique")

        def evidence_by_ref(packet: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
            observation = packet.get("evidence_observation", {})
            rows = (
                observation.get("evidence", ())
                if isinstance(observation, Mapping)
                else ()
            )
            literals: dict[str, list[str]] = {}
            for item in rows:
                if isinstance(item, Mapping) and item.get("document_ref"):
                    document_ref = str(item["document_ref"])
                    literals.setdefault(document_ref, []).append(
                        str(item.get("content_excerpt", ""))
                    )
                    structured = item.get("structured_context")
                    if isinstance(structured, Mapping):
                        for concept in structured.get("concepts", ()):
                            if not isinstance(concept, Mapping):
                                continue
                            for record in concept.get("records", ()):
                                if isinstance(record, Mapping):
                                    literals[document_ref].append(
                                        str(record.get("exact_span", ""))
                                    )
            executed = (
                observation.get("executed_evidence", ())
                if isinstance(observation, Mapping)
                else ()
            )
            for item in executed:
                if isinstance(item, Mapping) and item.get("document_ref"):
                    literals.setdefault(str(item["document_ref"]), []).append(
                        str(item.get("exact_span", ""))
                    )
            return {key: tuple(values) for key, values in literals.items()}

        def parse(value: Mapping[str, Any]) -> SignalUpdateDecision:
            try:
                if set(value) != {
                    "signal_ref",
                    "disposition",
                    "problem_type",
                    "rationale",
                    "case_diagnostics",
                    "changed_paths",
                    "candidate",
                }:
                    raise ValidationError(
                        "new Signal Update output requires exactly signal_ref, "
                        "disposition, problem_type, rationale, case_diagnostics, "
                        "changed_paths, and candidate"
                    )
                decision = SignalUpdateDecision.from_dict(value)
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="signal_update_v2_shape_invalid",
                            message=str(exc),
                            paths=(
                                "signal_ref",
                                "disposition",
                                "problem_type",
                                "rationale",
                                "case_diagnostics",
                                "changed_paths",
                                "candidate",
                            ),
                            path_policy="any",
                        )
                    ]
                ) from exc
            if decision.signal_ref != target_ref:
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="signal_update_target_mismatch",
                            message="Signal Update must preserve target signal_ref",
                            paths=("signal_ref",),
                            source_refs=(target_ref,),
                        )
                    ]
                )
            diagnostics_by_ref: dict[str, Mapping[str, Any]] = {}
            issues: list[ValidationIssue] = []
            for index, diagnostic in enumerate(decision.case_diagnostics):
                path = f"case_diagnostics[{index}]"
                case_ref = str(diagnostic.get("case_ref", ""))
                if set(diagnostic) != {
                    "case_ref",
                    "evidence_verdict",
                    "facts",
                    "evidence_gaps",
                    "outcome_relation",
                    "outcome_explanation",
                }:
                    issues.append(
                        ValidationIssue(
                            code="signal_update_case_diagnostic_shape_invalid",
                            message=f"{path} has unexpected fields",
                            paths=(path,),
                            item_id=(case_ref or None),
                            item_id_field="case_ref",
                            allowed_repairs=("replace",),
                        )
                    )
                    continue
                if case_ref not in packet_by_ref or case_ref in diagnostics_by_ref:
                    issues.append(
                        ValidationIssue(
                            code="signal_update_case_ref_invalid",
                            message=f"{path}.case_ref is unknown or duplicated",
                            paths=(path,),
                            item_id=(case_ref if case_ref in packet_by_ref else None),
                            item_id_field="case_ref",
                            allowed_repairs=("replace",),
                        )
                    )
                    continue
                diagnostics_by_ref[case_ref] = diagnostic
                verdict = str(diagnostic.get("evidence_verdict", ""))
                outcome_relation = str(diagnostic.get("outcome_relation", ""))
                facts = diagnostic.get("facts")
                gaps = diagnostic.get("evidence_gaps")
                if verdict not in {"supported", "contradicted", "insufficient"}:
                    issues.append(
                        ValidationIssue(
                            code="signal_update_evidence_verdict_invalid",
                            message=f"{path}.evidence_verdict is invalid",
                            paths=(path,),
                            item_id=case_ref,
                            item_id_field="case_ref",
                            allowed_repairs=("replace",),
                        )
                    )
                    continue
                if outcome_relation not in {"aligned", "misaligned", "not_assessable"}:
                    issues.append(
                        ValidationIssue(
                            code="signal_update_outcome_relation_invalid",
                            message=f"{path}.outcome_relation is invalid",
                            paths=(path,),
                            item_id=case_ref,
                            item_id_field="case_ref",
                            allowed_repairs=("replace",),
                        )
                    )
                    continue
                expected_relation = packet_by_ref[case_ref].get(
                    "outcome_relation", {}
                )
                expected_relation = (
                    str(expected_relation.get("current_signal_relation", ""))
                    if isinstance(expected_relation, Mapping)
                    else ""
                )
                if outcome_relation != expected_relation:
                    issues.append(
                        ValidationIssue(
                            code="signal_update_outcome_relation_mismatch",
                            message=(
                                f"{path}.outcome_relation must copy the runtime-computed "
                                "relation"
                            ),
                            paths=(path,),
                            item_id=case_ref,
                            item_id_field="case_ref",
                            allowed_repairs=("replace",),
                        )
                    )
                if not isinstance(facts, list) or not isinstance(gaps, list):
                    issues.append(
                        ValidationIssue(
                            code="signal_update_fact_list_invalid",
                            message=f"{path} facts and evidence_gaps must be arrays",
                            paths=(path,),
                            item_id=case_ref,
                            item_id_field="case_ref",
                            allowed_repairs=("replace",),
                        )
                    )
                    continue
                visible = evidence_by_ref(packet_by_ref[case_ref])
                fact_invalid = False
                for fact in facts:
                    if not isinstance(fact, Mapping) or set(fact) != {
                        "document_ref",
                        "exact_span",
                    }:
                        fact_invalid = True
                        break
                    document_ref = str(fact.get("document_ref", ""))
                    exact_span = str(fact.get("exact_span", ""))
                    if (
                        not exact_span.strip()
                        or not any(
                            exact_span in literal
                            for literal in visible.get(document_ref, ())
                        )
                    ):
                        fact_invalid = True
                        break
                if fact_invalid or (verdict != "insufficient" and not facts):
                    issues.append(
                        ValidationIssue(
                            code="signal_update_fact_not_grounded",
                            message=(
                                f"{path} requires source-cited literal facts before "
                                "outcome association"
                            ),
                            paths=(path,),
                            item_id=case_ref,
                            item_id_field="case_ref",
                            allowed_repairs=("replace",),
                        )
                    )
                if verdict == "insufficient" and not any(
                    isinstance(item, str) and item.strip() for item in gaps
                ):
                    issues.append(
                        ValidationIssue(
                            code="signal_update_evidence_gap_missing",
                            message=f"{path} insufficient verdict requires a gap",
                            paths=(path,),
                            item_id=case_ref,
                            item_id_field="case_ref",
                            allowed_repairs=("replace",),
                        )
                    )
            missing = sorted(set(packet_by_ref) - set(diagnostics_by_ref))
            for offset, case_ref in enumerate(missing):
                issues.append(
                    ValidationIssue(
                        code="signal_update_case_diagnostics_missing",
                        message=(
                            "Signal Update omitted the required case diagnostic for "
                            f"{case_ref}"
                        ),
                        paths=(
                            f"case_diagnostics[{len(decision.case_diagnostics) + offset}]",
                        ),
                        item_id=case_ref,
                        item_id_field="case_ref",
                        allowed_repairs=("add",),
                        source_refs=(case_ref,),
                    )
                )
            if decision.candidate is not None:
                stable_spec = target.get("stable_spec")
                if isinstance(stable_spec, Mapping):
                    candidate_contract = payload.get("candidate_contract", {})
                    vnext_template = (
                        candidate_contract.get("vnext_template", {})
                        if isinstance(candidate_contract, Mapping)
                        else {}
                    )
                    stable_tests = (
                        vnext_template.get("tests")
                        if isinstance(vnext_template, Mapping)
                        else None
                    )
                    try:
                        validate_signal_update_candidate(
                            target_ref, decision.candidate,
                            SignalSpec.from_dict(stable_spec),
                            stable_skill=(
                                str(target["stable_skill"])
                                if target.get("stable_skill") is not None
                                else None
                            ),
                            stable_tests=(
                                stable_tests
                                if isinstance(stable_tests, list)
                                else None
                            ),
                            changed_paths=decision.changed_paths,
                        )
                    except (KeyError, TypeError, ValueError, ValidationError) as exc:
                        issues.append(
                            ValidationIssue(
                                code="signal_update_candidate_invalid",
                                message=str(exc),
                                paths=("candidate", "changed_paths"),
                                path_policy="any",
                                allowed_repairs=("replace",),
                                repair_context={
                                    "changed_paths_allowed": list(
                                        SIGNAL_UPDATE_MUTABLE_PATHS
                                    ),
                                    "changed_paths_excluded": [
                                        "spec.version",
                                        "spec.definition",
                                        "tests",
                                        "whole-section aliases",
                                    ],
                                },
                            )
                        )
                    else:
                        if self.candidate_validator is not None:
                            try:
                                self.candidate_validator(
                                    target_ref,
                                    decision.candidate,
                                    decision.changed_paths,
                                )
                            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                                issues.append(
                                    ValidationIssue(
                                        code="signal_update_candidate_fixture_invalid",
                                        message=str(exc),
                                        paths=("candidate", "changed_paths"),
                                        path_policy="any",
                                        allowed_repairs=("replace",),
                                    )
                                )
            if issues:
                raise StructuredValidationError(issues)
            return decision

        value, usage, request_refs = _complete_parsed_role_with_trace(
            self.caller,
            stage="signal_update_decision",
            system_prompt=(
                "Diagnose one exact stable Signal. For each case, first compare the "
                "current Signal result with evidence_observation and cite literal source "
                "facts. Only after that evidence verdict may outcome_relation be used to "
                "assess association. The supplied label cannot establish that financing, "
                "a clinical result, an order, guidance, or any other source fact exists. "
                "Use insufficient when the visible source cannot support or contradict "
                "the result. Then choose no_change, defer, or one complete vNext update; "
                "keep holdout and identities hidden."
                + _UNTRUSTED_DATA_INSTRUCTION
                + _SIGNAL_UPDATE_V2_OUTPUT
            ),
            payload=payload,
            parser=parse,
            allow_outcomes=True,
            anonymous_aliases=(),
            temperature=0.0,
            reject_output_aliases=self.identity_guard_aliases,
            max_output_tokens=8_000,
            enforce_scoped_correction=True,
            stable_correction_prefix=True,
        )
        return AgentStep(value, usage, metadata={"request_refs": request_refs})


class LLMSignalMiningModel(SignalMiningModel):
    """Concrete five-role adapter for locally orchestrated Signal Mining."""

    supports_exploration_fallback = True

    def __init__(
        self,
        caller: JSONRoleCaller,
        *,
        creative_temperature: float = 1.0,
        h1_max_output_tokens: int = ROLE_OUTPUT_TOKEN_LIMITS["h1"],
    ):
        if not 0 <= creative_temperature <= 1:
            raise ValidationError("Signal Mining creative temperature must be in [0, 1]")
        if h1_max_output_tokens < 1:
            raise ValidationError("Signal Mining H1 output limit must be positive")
        self.caller = caller
        self.creative_temperature = creative_temperature
        self.h1_max_output_tokens = int(h1_max_output_tokens)
        self.identity_guard_aliases: tuple[str, ...] = ()
        self.request_token_budget: int | None = None

    def set_request_token_budget(self, value: int) -> None:
        self.request_token_budget = int(value)

    def set_identity_guard_aliases(self, value: Iterable[str]) -> None:
        self.identity_guard_aliases = tuple(value)

    def request_slow_sources(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[str, ...]]:
        """Request one bounded runtime-resolved source view for a Mining role."""

        return _request_slow_source_refs(
            self.caller,
            payload,
            identity_guard_aliases=self.identity_guard_aliases,
        )

    @property
    def work_identity(self) -> Mapping[str, Any]:
        """Return the stable role/model identity used by Mining work keys."""

        registration = getattr(self.caller, "registration", None)
        return {
            "adapter": f"{type(self).__module__}.{type(self).__qualname__}",
            "creative_temperature": self.creative_temperature,
            "h1_max_output_tokens": self.h1_max_output_tokens,
            "h1_contract": "signal-mining-hypothesis-v7",
            "reflection_contract": "signal-mining-reflect-v2",
            "source_read_contract": "slow-source-read-v1",
            "need_ref_projection": "compact-reflection-action-v2",
            "h3_evidence_scope": "comparison-nested-v1",
            "e2_decision_contract": "contrast-bound-slots-v1",
            "model_alias": getattr(registration, "alias", None),
            "provider": getattr(registration, "provider", None),
            "model": getattr(registration, "model", None),
            "proposal_profile": getattr(registration, "proposal_profile", None),
        }

    def reflect_feedback(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[Mapping[str, Any]]:
        """Append evidence-linked episode reflections and method lessons."""

        episode_slots = {
            str(item) for item in payload.get("episode_slots", ())
        }
        lesson_slots = {str(item) for item in payload.get("lesson_slots", ())}
        feedback_refs = {
            str(item.get("feedback_ref"))
            for item in payload.get("feedback_units", ())
            if isinstance(item, Mapping) and item.get("feedback_ref")
        }
        prior_lesson_refs = {
            str(lesson.get("lesson_id"))
            for memory in payload.get("prior_memory", ())
            if isinstance(memory, Mapping)
            for lesson in memory.get("lesson_additions", ())
            if isinstance(lesson, Mapping) and lesson.get("lesson_id")
        }
        nested_ref_owners: dict[str, set[str]] = {}

        def nested_slow_refs(value: Any) -> Iterable[str]:
            if isinstance(value, Mapping):
                for nested in value.values():
                    yield from nested_slow_refs(nested)
            elif isinstance(value, (list, tuple)):
                for nested in value:
                    yield from nested_slow_refs(nested)
            elif isinstance(value, str) and value.startswith("slow-history:"):
                yield value

        for unit in payload.get("feedback_units", ()):
            if not isinstance(unit, Mapping) or not unit.get("feedback_ref"):
                continue
            owner = str(unit["feedback_ref"])
            for nested_ref in nested_slow_refs(unit):
                if nested_ref != owner:
                    nested_ref_owners.setdefault(nested_ref, set()).add(owner)
        canonicalized_nested_refs: dict[str, str] = {}

        def canonicalize_refs(value: Any, *, allowed: set[str]) -> Any:
            if not isinstance(value, list):
                return value
            mapped: list[Any] = []
            for item in value:
                replacement = item
                if isinstance(item, str) and item not in allowed:
                    owners = nested_ref_owners.get(item, set())
                    if len(owners) == 1:
                        replacement = next(iter(owners))
                        canonicalized_nested_refs[item] = replacement
                if replacement not in mapped:
                    mapped.append(replacement)
            return mapped

        def parse(value: Mapping[str, Any]) -> Mapping[str, Any]:
            canonicalized_nested_refs.clear()
            if set(value) != {"episode_reflections", "lesson_additions"}:
                raise ValidationError(
                    "Signal reflection requires episode_reflections and lesson_additions"
                )
            episodes = value.get("episode_reflections")
            lessons = value.get("lesson_additions")
            if not isinstance(episodes, list) or not isinstance(lessons, list):
                raise ValidationError("Signal reflection outputs must be arrays")
            episodes = [
                {
                    **raw,
                    "source_refs": canonicalize_refs(
                        raw.get("source_refs"), allowed=feedback_refs
                    ),
                }
                if isinstance(raw, Mapping)
                else raw
                for raw in episodes
            ]
            resolvable = (
                feedback_refs | episode_slots | lesson_slots | prior_lesson_refs
            )
            lessons = [
                {
                    **raw,
                    **{
                        key: canonicalize_refs(raw.get(key), allowed=resolvable)
                        for key in (
                            "support_refs",
                            "counterevidence_refs",
                            "qualifies_refs",
                            "challenges_refs",
                        )
                    },
                }
                if isinstance(raw, Mapping)
                else raw
                for raw in lessons
            ]
            issues: list[ValidationIssue] = []
            seen_episodes: set[str] = set()
            covered_feedback_refs: set[str] = set()
            for index, raw in enumerate(episodes):
                path = f"episode_reflections[{index}]"
                if not isinstance(raw, Mapping) or set(raw) != {
                    "episode_ref",
                    "source_refs",
                    "reflection",
                    "unresolved_questions",
                }:
                    issues.append(
                        ValidationIssue(
                            code="reflection_episode_shape_invalid",
                            message=f"{path} shape is invalid",
                            paths=(path,),
                            allowed_repairs=("replace", "remove"),
                        )
                    )
                    continue
                episode_ref = str(raw.get("episode_ref", ""))
                source_refs = raw.get("source_refs")
                if (
                    episode_ref not in episode_slots
                    or episode_ref in seen_episodes
                    or not isinstance(source_refs, list)
                    or not source_refs
                    or not set(str(item) for item in source_refs) <= feedback_refs
                    or not str(raw.get("reflection", "")).strip()
                    or not isinstance(raw.get("unresolved_questions"), list)
                ):
                    issues.append(
                        ValidationIssue(
                            code="reflection_episode_invalid",
                            message=(
                                f"{path} must use one unique episode slot, cite "
                                "only top-level feedback_units feedback_ref values, "
                                "and contain reflection text plus an unresolved "
                                "questions array"
                            ),
                            paths=(path,),
                            item_id=(episode_ref or None),
                            item_id_field="episode_ref",
                            allowed_repairs=("replace", "remove"),
                        )
                    )
                    continue
                seen_episodes.add(episode_ref)
                covered_feedback_refs.update(str(item) for item in source_refs)
            missing_feedback_refs = sorted(
                feedback_refs - covered_feedback_refs
            )
            if missing_feedback_refs:
                issues.append(
                    ValidationIssue(
                        code="reflection_feedback_coverage_missing",
                        message=(
                            "episode_reflections source_refs must cover every "
                            "selected top-level feedback_ref"
                        ),
                        paths=("episode_reflections",),
                        allowed_repairs=("add", "replace"),
                        source_refs=tuple(missing_feedback_refs),
                        repair_context={
                            "missing_feedback_refs": missing_feedback_refs,
                        },
                    )
                )
            seen_lessons: set[str] = set()
            for index, raw in enumerate(lessons):
                path = f"lesson_additions[{index}]"
                if not isinstance(raw, Mapping) or set(raw) != {
                    "lesson_id",
                    "guidance",
                    "applicable_scope",
                    "support_refs",
                    "counterevidence_refs",
                    "limitations",
                    "qualifies_refs",
                    "challenges_refs",
                }:
                    issues.append(
                        ValidationIssue(
                            code="reflection_lesson_shape_invalid",
                            message=f"{path} shape is invalid",
                            paths=(path,),
                            allowed_repairs=("replace", "remove"),
                        )
                    )
                    continue
                lesson_id = str(raw.get("lesson_id", ""))
                refs = {
                    str(item)
                    for key in (
                        "support_refs",
                        "counterevidence_refs",
                        "qualifies_refs",
                        "challenges_refs",
                    )
                    for item in raw.get(key, ())
                }
                if (
                    lesson_id not in lesson_slots
                    or lesson_id in seen_lessons
                    or not str(raw.get("guidance", "")).strip()
                    or not str(raw.get("applicable_scope", "")).strip()
                    or not str(raw.get("limitations", "")).strip()
                    or not raw.get("support_refs")
                    or not refs <= resolvable
                ):
                    issues.append(
                        ValidationIssue(
                            code="reflection_lesson_invalid",
                            message=(
                                f"{path} must use one unique lesson slot, contain "
                                "guidance/scope/limitations, and cite only top-level "
                                "feedback refs, valid episode/lesson slots, or prior "
                                "lesson ids"
                            ),
                            paths=(path,),
                            item_id=(lesson_id or None),
                            item_id_field="lesson_id",
                            allowed_repairs=("replace", "remove"),
                        )
                    )
                    continue
                seen_lessons.add(lesson_id)
            if issues:
                raise StructuredValidationError(issues)
            return {
                "episode_reflections": [dict(item) for item in episodes],
                "lesson_additions": [dict(item) for item in lessons],
            }

        value, usage, request_refs = _complete_parsed_role_with_trace(
            self.caller,
            stage="signal_mining_reflect",
            system_prompt=(
                "Reflect on complete committed Slow feedback units. Preserve their "
                "specific measurement conditions, failure layers, counterevidence, "
                "and unresolved questions. Append only; never rewrite prior memory, "
                "invent refs, infer causal Signal credit, or turn technical failure "
                "into a research conclusion. Return JSON with exactly "
                "episode_reflections and lesson_additions. Each episode has exactly "
                "episode_ref, source_refs, reflection, unresolved_questions. Each "
                "lesson has exactly lesson_id, guidance, applicable_scope, "
                "support_refs, counterevidence_refs, limitations, qualifies_refs, "
                "challenges_refs. Use only runtime-provided slots and refs."
                " In episode source_refs, copy only the top-level feedback_ref "
                "field of a supplied feedback_units row. Ref-like strings nested "
                "inside a feedback unit are audit content and are not valid output "
                "citations."
                + _UNTRUSTED_DATA_INSTRUCTION
            ),
            payload=payload,
            parser=parse,
            allow_outcomes=True,
            anonymous_aliases=(),
            temperature=0.0,
            reject_output_aliases=self.identity_guard_aliases,
            max_output_tokens=5_000,
            enforce_scoped_correction=True,
            stable_correction_prefix=True,
        )
        return AgentStep(
            value,
            usage,
            metadata={
                "request_refs": request_refs,
                "canonicalized_nested_refs": dict(canonicalized_nested_refs),
            },
        )

    def propose_hypotheses(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningHypothesis, ...]]:
        """Run the sole production H1 v7 contract."""

        return self._propose_hypotheses_v3(payload)

    def _propose_hypotheses_v3(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningHypothesis, ...]]:
        """Parse the production H1 contract without prose/identifier matching."""

        projected_payload = deepcopy(dict(payload))
        projected_backlog = projected_payload.get("capability_backlog", {})
        ordered_need_refs: list[str] = []
        if isinstance(projected_backlog, Mapping):
            for collection, field_name in (
                (projected_backlog.get("signal_need_items", ()), "need_ref"),
                (projected_backlog.get("items", ()), "request_id"),
            ):
                for item in collection:
                    if not isinstance(item, Mapping) or not item.get(field_name):
                        continue
                    ref = str(item[field_name])
                    if ref not in ordered_need_refs:
                        ordered_need_refs.append(ref)
        alias_width = max(3, len(str(len(ordered_need_refs))))
        original_to_alias = {
            ref: f"need-{index:0{alias_width}d}"
            for index, ref in enumerate(ordered_need_refs, start=1)
        }
        alias_to_original = {
            alias: original for original, alias in original_to_alias.items()
        }
        reflection_action_refs = {
            str(item["need_ref"])
            for item in (
                projected_backlog.get("signal_need_items", ())
                if isinstance(projected_backlog, Mapping)
                else ()
            )
            if isinstance(item, Mapping)
            and item.get("kind") == "meta_reflection_action"
            and item.get("need_ref")
        }
        reflection_action_aliases = {
            original_to_alias[ref]
            for ref in reflection_action_refs
            if ref in original_to_alias
        }
        if isinstance(projected_backlog, Mapping):
            projected_backlog = dict(projected_backlog)
            for collection_name, field_name in (
                ("signal_need_items", "need_ref"),
                ("items", "request_id"),
            ):
                projected_rows: list[Any] = []
                for item in projected_backlog.get(collection_name, ()):
                    if isinstance(item, Mapping) and item.get(field_name):
                        projected_rows.append(
                            {
                                **dict(item),
                                field_name: original_to_alias[str(item[field_name])],
                            }
                        )
                    else:
                        projected_rows.append(item)
                if collection_name in projected_backlog:
                    projected_backlog[collection_name] = projected_rows
            projected_payload["capability_backlog"] = projected_backlog

        need_rows_by_alias: dict[str, Mapping[str, Any]] = {}
        if isinstance(projected_backlog, Mapping):
            for collection_name, field_name in (
                ("signal_need_items", "need_ref"),
                ("items", "request_id"),
            ):
                for item in projected_backlog.get(collection_name, ()):
                    if isinstance(item, Mapping) and item.get(field_name):
                        need_rows_by_alias[str(item[field_name])] = item
        stable_cards_by_ref = {
            str(item["signal_ref"]): item
            for item in projected_payload.get("stable_signal_cards", ())
            if isinstance(item, Mapping) and item.get("signal_ref")
        }

        def has_explicit_update_basis(need_ref: str, signal_ref: str) -> bool:
            row = need_rows_by_alias.get(need_ref, {})
            if row.get("signal_ref") == signal_ref:
                return True
            need = str(row.get("need", ""))
            normalized_need = (
                " " + re.sub(r"[^a-z0-9]+", " ", need.casefold()).strip() + " "
            )
            card = stable_cards_by_ref.get(signal_ref, {})
            phrases = card.get("routing_answer_need_phrases", ())
            return isinstance(phrases, list) and any(
                isinstance(phrase, str)
                and phrase.strip()
                and (
                    " "
                    + re.sub(r"[^a-z0-9]+", " ", phrase.casefold()).strip()
                    + " "
                )
                in normalized_need
                for phrase in phrases
            )

        limits = dict(projected_payload.get("limits", {}))
        limit = int(limits.get("hypothesis_limit", 3))
        lookback_days = int(limits.get("evidence_lookback_days", 365))
        slots = tuple(str(item) for item in projected_payload.get("hypothesis_slots", ()))
        if len(slots) != limit or len(set(slots)) != len(slots):
            raise ValidationError(
                "Signal Mining H1 v7 requires one unique runtime slot per hypothesis"
            )
        allowed_slots = set(slots)
        allowed_source_types = {
            str(item) for item in projected_payload.get("available_raw_source_types", ())
        }
        backlog = projected_payload.get("capability_backlog", {})
        allowed_need_refs: set[str] = set()
        if isinstance(backlog, Mapping):
            allowed_need_refs.update(
                str(item["need_ref"])
                for item in backlog.get("signal_need_items", ())
                if isinstance(item, Mapping) and item.get("need_ref")
            )
            allowed_need_refs.update(
                str(item["request_id"])
                for item in backlog.get("items", ())
                if isinstance(item, Mapping) and item.get("request_id")
            )
        allowed_signal_refs = {
            str(item["signal_ref"])
            for item in projected_payload.get("stable_signal_cards", ())
            if isinstance(item, Mapping) and item.get("signal_ref")
        }
        applicability_contract = projected_payload.get("h2_applicability_contract", {})
        expected_directions = {
            "higher_in_positive",
            "lower_in_positive",
            "more_frequent_in_positive",
            "less_frequent_in_positive",
            "different_between_groups",
        }
        value_kinds = {"boolean", "ordinal", "numeric", "categorical"}
        no_hypothesis_codes = {
            "no_new_measurable_gap",
            "insufficient_retrieval_basis",
            "prior_attempts_exhausted",
        }
        allowed_need_dispositions = {
            "new_measurement",
            "deferred_measurement",
            "update_existing",
            "repair_dependency",
            "already_covered",
            "not_testable",
            "fast_plan_action",
        }
        conclusion_metadata: dict[str, Any] = {}

        def string_array(
            value: Any, *, path: str, allow_empty: bool = False
        ) -> tuple[str, ...]:
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise ValidationError(f"{path} must be an array of non-empty strings")
            if not allow_empty and not value:
                raise ValidationError(f"{path} must not be empty")
            return tuple(value)

        def validate_need_refs(value: Any, *, path: str) -> tuple[str, ...]:
            refs = string_array(value, path=path, allow_empty=True)
            if len(set(refs)) != len(refs):
                raise ValidationError(f"{path} must be unique")
            unknown = sorted(set(refs) - allowed_need_refs)
            if unknown:
                raise ValidationError(
                    f"{path} contains unknown runtime need refs: " + ", ".join(unknown)
                )
            return refs

        def parse(value: Mapping[str, Any]) -> tuple[SignalMiningHypothesis, ...]:
            if set(value) != {
                "conclusion",
                "hypotheses",
                "no_hypothesis",
                "need_dispositions",
            }:
                raise ValidationError(
                    "Signal Mining H1 v7 requires conclusion, hypotheses, "
                    "no_hypothesis, and need_dispositions"
                )
            conclusion = value.get("conclusion")
            raw_items = value.get("hypotheses")
            if conclusion not in {"hypotheses", "no_testable_hypothesis"} or not isinstance(
                raw_items, list
            ):
                raise ValidationError("Signal Mining H1 v7 conclusion is invalid")
            raw_dispositions = value.get("need_dispositions")
            if not isinstance(raw_dispositions, list):
                raise ValidationError("need_dispositions must be an array")
            ledger_issues: list[ValidationIssue] = []
            raw_disposition_refs: list[str] = []
            new_measurement_refs_from_ledger: set[str] = set()
            for index, raw_disposition in enumerate(raw_dispositions):
                if not isinstance(raw_disposition, Mapping):
                    continue
                disposition_path = f"need_dispositions[{index}]"
                if set(raw_disposition) != {
                    "need_refs",
                    "disposition",
                    "signal_refs",
                    "rationale",
                }:
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_disposition_row_shape_invalid",
                            message=(
                                f"{disposition_path} must contain exactly need_refs, "
                                "disposition, signal_refs, and rationale; replace the "
                                "complete row and do not use singular signal_ref"
                            ),
                            paths=(disposition_path,),
                            allowed_repairs=("replace",),
                        )
                    )
                raw_refs = raw_disposition.get("need_refs")
                if not isinstance(raw_refs, list):
                    continue
                string_refs = [item for item in raw_refs if isinstance(item, str)]
                raw_disposition_refs.extend(string_refs)
                unknown = sorted(set(string_refs) - allowed_need_refs)
                if unknown:
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_unknown_need_refs",
                            message=(
                                f"need_dispositions[{index}].need_refs contains unknown "
                                "runtime aliases: " + ", ".join(unknown)
                            ),
                            paths=(f"need_dispositions[{index}].need_refs",),
                            source_refs=tuple(unknown),
                        )
                    )
                if len(set(string_refs)) != len(string_refs):
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_duplicate_need_refs_in_row",
                            message=(
                                f"need_dispositions[{index}].need_refs must be unique"
                            ),
                            paths=(f"need_dispositions[{index}].need_refs",),
                        )
                    )
                if raw_disposition.get("disposition") == "new_measurement":
                    new_measurement_refs_from_ledger.update(
                        ref for ref in string_refs if ref in allowed_need_refs
                    )
                reflection_refs = set(string_refs).intersection(
                    reflection_action_aliases
                )
                disposition = raw_disposition.get("disposition")
                raw_signal_refs = raw_disposition.get("signal_refs")
                signal_refs = (
                    [item for item in raw_signal_refs if isinstance(item, str)]
                    if isinstance(raw_signal_refs, list)
                    else []
                )
                signal_ref_shape_valid = (
                    len(signal_refs) == 1
                    if disposition in {"update_existing", "already_covered"}
                    else not signal_refs
                )
                if disposition in allowed_need_dispositions and not signal_ref_shape_valid:
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_disposition_signal_refs_invalid",
                            message=(
                                f"need_dispositions[{index}] disposition={disposition} "
                                "must cite exactly one stable Signal only for "
                                "update_existing/already_covered and otherwise must "
                                "use signal_refs=[]"
                            ),
                            paths=(f"need_dispositions[{index}].signal_refs",),
                        )
                    )
                unmatched_refs = {
                    ref
                    for ref in string_refs
                    if need_rows_by_alias.get(ref, {}).get("kind")
                    == "unmatched_signal_need"
                }
                if disposition == "already_covered" and unmatched_refs:
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_unmatched_need_cannot_be_already_covered",
                            message=(
                                f"{disposition_path} erases explicitly unmatched "
                                "Signal needs without action. Replace the row with "
                                "new_measurement, deferred_measurement, "
                                "update_existing with an explicit version-owned "
                                "answer-phrase basis, repair_dependency, or an "
                                "intrinsically justified not_testable disposition"
                            ),
                            paths=("need_dispositions",),
                            source_refs=tuple(sorted(unmatched_refs)),
                            allowed_repairs=("replace",),
                        )
                    )
                if (
                    disposition == "update_existing"
                    and len(signal_refs) == 1
                    and signal_refs[0] in allowed_signal_refs
                ):
                    unsupported_refs = tuple(
                        sorted(
                            ref
                            for ref in string_refs
                            if ref in allowed_need_refs
                            and not has_explicit_update_basis(ref, signal_refs[0])
                        )
                    )
                    if unsupported_refs:
                        ledger_issues.append(
                            ValidationIssue(
                                code="h1_update_existing_lacks_explicit_basis",
                                message=(
                                    f"{disposition_path} may update one stable Signal "
                                    "only when every grouped need independently "
                                    "carries that signal_ref or contains one of its "
                                    "version-owned routing_answer_need_phrases"
                                ),
                                paths=("need_dispositions",),
                                source_refs=unsupported_refs,
                                allowed_repairs=("replace",),
                                repair_context={
                                    "unsupported_need_refs": list(unsupported_refs),
                                    "cited_signal_ref": signal_refs[0],
                                },
                            )
                        )
                if reflection_refs and disposition == "already_covered":
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_reflection_action_ignored",
                            message=(
                                "meta-reflection action refs cannot be already_covered; "
                                "use new_measurement, update_existing, "
                                "repair_dependency, fast_plan_action, or an "
                                "intrinsically justified not_testable disposition"
                            ),
                            paths=(f"need_dispositions[{index}]",),
                            allowed_repairs=("replace",),
                        )
                        )
                if (
                    disposition == "fast_plan_action"
                    and set(string_refs) - reflection_action_aliases
                ):
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_fast_plan_action_scope_invalid",
                            message=(
                                "fast_plan_action may disposition only supplied "
                                "meta_reflection_action refs; ordinary Signal and "
                                "capability needs remain Slow obligations"
                            ),
                            paths=(f"need_dispositions[{index}]",),
                            allowed_repairs=("replace",),
                        )
                    )
            duplicated_refs = sorted(
                {
                    ref
                    for ref in raw_disposition_refs
                    if raw_disposition_refs.count(ref) > 1
                }
            )
            missing_refs = sorted(allowed_need_refs - set(raw_disposition_refs))
            if duplicated_refs or missing_refs:
                details = []
                if missing_refs:
                    details.append("missing " + ", ".join(missing_refs))
                if duplicated_refs:
                    details.append("duplicated " + ", ".join(duplicated_refs))
                ledger_issues.append(
                    ValidationIssue(
                        code="h1_need_ledger_coverage_invalid",
                        message=(
                            "need_dispositions must cover every runtime need alias "
                            "exactly once; " + "; ".join(details)
                        ),
                        paths=("need_dispositions",),
                    )
                )
            raw_no_hypothesis = value.get("no_hypothesis")
            if (
                conclusion == "no_testable_hypothesis"
                and isinstance(raw_no_hypothesis, Mapping)
                and isinstance(raw_no_hypothesis.get("need_refs"), list)
            ):
                no_hypothesis_refs = [
                    item
                    for item in raw_no_hypothesis["need_refs"]
                    if isinstance(item, str)
                ]
                unknown = sorted(set(no_hypothesis_refs) - allowed_need_refs)
                if unknown:
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_no_hypothesis_unknown_need_refs",
                            message=(
                                "no_hypothesis.need_refs contains unknown runtime "
                                "aliases: " + ", ".join(unknown)
                            ),
                            paths=("no_hypothesis",),
                            source_refs=tuple(unknown),
                        )
                    )
                if len(set(no_hypothesis_refs)) != len(no_hypothesis_refs):
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_no_hypothesis_duplicate_need_refs",
                            message="no_hypothesis.need_refs must be unique",
                            paths=("no_hypothesis",),
                        )
                    )
            if (
                conclusion == "no_testable_hypothesis"
                and new_measurement_refs_from_ledger
            ):
                ledger_issues.append(
                    ValidationIssue(
                        code="h1_new_measurement_conclusion_conflict",
                        message=(
                            "A no_testable_hypothesis conclusion cannot retain any "
                            "new_measurement disposition; either produce hypotheses "
                            "for those aliases or revise the dispositions and reason"
                        ),
                        paths=(
                            "conclusion",
                            "hypotheses",
                            "no_hypothesis",
                            "need_dispositions",
                        ),
                        path_policy="any",
                        dependent_paths=("no_hypothesis",),
                    )
                )
            if (
                conclusion == "no_testable_hypothesis"
                and isinstance(raw_no_hypothesis, Mapping)
                and isinstance(raw_no_hypothesis.get("rationale"), list)
                and any(
                    isinstance(reason, str)
                    and _H1_WITHHELD_CONTEXT_RATIONALE.search(reason)
                    for reason in raw_no_hypothesis["rationale"]
                )
            ):
                ledger_issues.append(
                    ValidationIssue(
                        code="h1_withheld_context_is_not_empty_reason",
                        message=(
                            "H1 intentionally withholds case labels and full case "
                            "evidence. Their absence cannot justify a no-hypothesis "
                            "result; give a measurement-level reason or propose a "
                            "hypothesis for H2/H3 testing."
                        ),
                        paths=(
                            "no_hypothesis.rationale",
                            "conclusion",
                            "hypotheses",
                            "need_dispositions",
                        ),
                        path_policy="any",
                        dependent_paths=("no_hypothesis",),
                    )
                )
            for index, raw_disposition in enumerate(raw_dispositions):
                if (
                    isinstance(raw_disposition, Mapping)
                    and raw_disposition.get("disposition") == "not_testable"
                    and isinstance(raw_disposition.get("rationale"), list)
                    and any(
                        isinstance(reason, str)
                        and _H1_WITHHELD_CONTEXT_RATIONALE.search(reason)
                        for reason in raw_disposition["rationale"]
                    )
                ):
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_not_testable_uses_withheld_context",
                            message=(
                                "not_testable cannot be justified by absent H1 case "
                                "labels, case evidence, group membership, or full "
                                "source excerpts. State an intrinsic measurement-level "
                                "reason or classify the need as new_measurement."
                            ),
                            paths=(
                                f"need_dispositions[{index}]",
                                "conclusion",
                                "hypotheses",
                                "no_hypothesis",
                            ),
                            path_policy="any",
                        )
                    )
            if conclusion == "hypotheses" and isinstance(raw_items, list):
                for index, raw_item in enumerate(raw_items):
                    if not isinstance(raw_item, Mapping):
                        continue
                    measurement = raw_item.get("measurement")
                    retrieval = raw_item.get("retrieval_intent")
                    falsifiers = raw_item.get("falsifiers")
                    semantic_values = [
                        *(
                            [str(item) for item in measurement.values()]
                            if isinstance(measurement, Mapping)
                            else []
                        ),
                        *(
                            [str(retrieval.get("query", ""))]
                            if isinstance(retrieval, Mapping)
                            else []
                        ),
                        *(
                            [
                                str(item.get(key, ""))
                                for item in falsifiers
                                if isinstance(item, Mapping)
                                for key in ("condition", "expected_observation")
                            ]
                            if isinstance(falsifiers, list)
                            else []
                        ),
                    ]
                    if any(
                        _H1_POST_CUTOFF_SOURCE.search(item)
                        for item in semantic_values
                    ):
                        proposal_ref = str(raw_item.get("proposal_ref", ""))
                        ledger_issues.append(
                            ValidationIssue(
                                code="h1_post_cutoff_source_invalid",
                                message=(
                                    f"hypotheses[{index}] explicitly requests facts "
                                    "after a point-in-time source series, cutoff, or "
                                    "prediction time. Define the measurement only over "
                                    "facts available at or before each prediction time"
                                ),
                                paths=(f"hypotheses[{index}]",),
                                item_id=(
                                    proposal_ref
                                    if proposal_ref in allowed_slots
                                    else None
                                ),
                                item_id_field="proposal_ref",
                                allowed_repairs=("replace", "remove"),
                            )
                        )
            if conclusion == "hypotheses" and isinstance(raw_items, list):
                hypothesis_need_refs = {
                    ref
                    for raw_item in raw_items
                    if isinstance(raw_item, Mapping)
                    and isinstance(raw_item.get("need_refs"), list)
                    for ref in raw_item["need_refs"]
                    if isinstance(ref, str) and ref in allowed_need_refs
                }
                if hypothesis_need_refs != new_measurement_refs_from_ledger:
                    ledger_only = sorted(
                        new_measurement_refs_from_ledger - hypothesis_need_refs
                    )
                    hypothesis_only = sorted(
                        hypothesis_need_refs - new_measurement_refs_from_ledger
                    )
                    ledger_issues.append(
                        ValidationIssue(
                            code="h1_hypothesis_need_refs_mismatch",
                            message=(
                                "new_measurement disposition aliases must exactly match "
                                "the union of hypothesis need_refs. Reclassify every "
                                "ledger-only ref outside the bounded portfolio, or "
                                "directly attach it to a hypothesis that measures it"
                            ),
                            paths=("hypotheses", "need_dispositions"),
                            path_policy="any",
                            repair_context={
                                "ledger_only_new_measurement_refs": ledger_only,
                                "hypothesis_only_need_refs": hypothesis_only,
                            },
                        )
                    )
            if ledger_issues:
                raise StructuredValidationError(ledger_issues)
            disposition_rows: list[dict[str, Any]] = []
            disposition_need_refs: list[str] = []
            for index, raw_disposition in enumerate(raw_dispositions):
                path = f"need_dispositions[{index}]"
                if not isinstance(raw_disposition, Mapping) or set(
                    raw_disposition
                ) != {"need_refs", "disposition", "signal_refs", "rationale"}:
                    raise ValidationError(f"{path} has unexpected fields")
                refs = validate_need_refs(
                    raw_disposition.get("need_refs"), path=f"{path}.need_refs"
                )
                if not refs:
                    raise ValidationError(f"{path}.need_refs must not be empty")
                disposition = str(raw_disposition.get("disposition", ""))
                if disposition not in allowed_need_dispositions:
                    raise ValidationError(f"{path}.disposition is invalid")
                signal_refs = string_array(
                    raw_disposition.get("signal_refs"),
                    path=f"{path}.signal_refs",
                    allow_empty=True,
                )
                if len(set(signal_refs)) != len(signal_refs):
                    raise ValidationError(f"{path}.signal_refs must be unique")
                unknown_signals = sorted(set(signal_refs) - allowed_signal_refs)
                if unknown_signals:
                    raise ValidationError(
                        f"{path}.signal_refs contains unknown stable refs: "
                        + ", ".join(unknown_signals)
                    )
                if disposition in {"update_existing", "already_covered"} and len(signal_refs) != 1:
                    raise ValidationError(
                        f"{path}.{disposition} requires exactly one stable signal_ref"
                    )
                if disposition in {
                    "new_measurement",
                    "deferred_measurement",
                    "repair_dependency",
                    "not_testable",
                    "fast_plan_action",
                } and signal_refs:
                    raise ValidationError(
                        f"{path}.{disposition} cannot cite an existing Signal"
                    )
                rationale = string_array(
                    raw_disposition.get("rationale"), path=f"{path}.rationale"
                )
                disposition_need_refs.extend(refs)
                disposition_rows.append(
                    {
                        "need_refs": list(refs),
                        "disposition": disposition,
                        "signal_refs": list(signal_refs),
                        "rationale": list(rationale),
                    }
                )
            if len(set(disposition_need_refs)) != len(disposition_need_refs) or set(
                disposition_need_refs
            ) != allowed_need_refs:
                raise ValidationError(
                    "need_dispositions must cover every runtime need_ref exactly once"
                )
            if conclusion == "no_testable_hypothesis":
                no_hypothesis = value.get("no_hypothesis")
                if raw_items or not isinstance(no_hypothesis, Mapping) or set(
                    no_hypothesis
                ) != {"reason_code", "rationale", "need_refs"}:
                    raise ValidationError(
                        "no_testable_hypothesis requires an empty portfolio and one "
                        "structured reason"
                    )
                reason_code = str(no_hypothesis.get("reason_code", ""))
                if reason_code not in no_hypothesis_codes:
                    raise ValidationError("Signal Mining H1 no-hypothesis code is invalid")
                rationale = string_array(
                    no_hypothesis.get("rationale"), path="no_hypothesis.rationale"
                )
                need_refs = validate_need_refs(
                    no_hypothesis.get("need_refs"), path="no_hypothesis.need_refs"
                )
                if any(
                    item["disposition"] == "new_measurement"
                    for item in disposition_rows
                ):
                    raise ValidationError(
                        "no_testable_hypothesis cannot disposition a need as "
                        "new_measurement"
                    )
                conclusion_metadata.clear()
                conclusion_metadata.update(
                    {
                        "conclusion": conclusion,
                        "reason_code": reason_code,
                        "rationale": list(rationale),
                        "need_refs": list(need_refs),
                        "need_dispositions": disposition_rows,
                    }
                )
                return ()
            if value.get("no_hypothesis") is not None:
                raise ValidationError(
                    "Signal Mining H1 hypothesis portfolio requires no_hypothesis=null"
                )
            if not raw_items or len(raw_items) > limit:
                raise ValidationError(
                    "Signal Mining H1 hypothesis portfolio must contain 1 through "
                    f"{limit} items"
                )
            parsed: list[SignalMiningHypothesis] = []
            issues: list[ValidationIssue] = []
            seen_slots: set[str] = set()
            for index, raw in enumerate(raw_items):
                item_path = f"hypotheses[{index}]"
                proposal_ref = (
                    str(raw.get("proposal_ref", ""))
                    if isinstance(raw, Mapping)
                    else ""
                )
                try:
                    if not isinstance(raw, Mapping) or set(raw) != {
                        "proposal_ref",
                        "measurement",
                        "applicability",
                        "expected_direction",
                        "retrieval_intent",
                        "falsifiers",
                        "need_refs",
                    }:
                        raise ValidationError("hypothesis has unexpected fields")
                    if proposal_ref not in allowed_slots or proposal_ref in seen_slots:
                        raise ValidationError(
                            "proposal_ref must be one unused runtime hypothesis slot"
                        )
                    measurement = raw.get("measurement")
                    if not isinstance(measurement, Mapping) or set(measurement) != {
                        "observable",
                        "value_kind",
                        "normalization",
                    }:
                        raise ValidationError(
                            "measurement requires observable, value_kind, and normalization"
                        )
                    normalized_measurement = {
                        key: str(measurement.get(key, "")).strip()
                        for key in ("observable", "value_kind", "normalization")
                    }
                    if any(not item for item in normalized_measurement.values()):
                        raise ValidationError("measurement fields must not be empty")
                    if normalized_measurement["value_kind"] not in value_kinds:
                        raise ValidationError("measurement value_kind is invalid")
                    raw_applicability = raw.get("applicability")
                    if not isinstance(raw_applicability, Mapping) or set(
                        raw_applicability
                    ) != {"rule", "values"}:
                        raise ValidationError(
                            "applicability requires structured rule and values"
                        )
                    applicability_rule = str(
                        raw_applicability.get("rule", "")
                    )
                    applicability_values = string_array(
                        raw_applicability.get("values"),
                        path=f"{item_path}.applicability.values",
                        allow_empty=True,
                    )
                    applicability = (
                        "all_ready_issuers"
                        if applicability_rule == "all_ready_issuers"
                        and not applicability_values
                        else f"{applicability_rule}:{'|'.join(applicability_values)}"
                    )
                    _h1_applicability_rule(
                        applicability,
                        contract=(
                            applicability_contract
                            if isinstance(applicability_contract, Mapping)
                            else {}
                        ),
                    )
                    expected_direction = str(raw.get("expected_direction", ""))
                    if expected_direction not in expected_directions:
                        raise ValidationError("expected_direction is invalid")
                    retrieval = raw.get("retrieval_intent")
                    if not isinstance(retrieval, Mapping) or set(retrieval) != {
                        "source_types",
                        "query",
                    }:
                        raise ValidationError(
                            "retrieval_intent requires source_types and query"
                        )
                    source_types = string_array(
                        retrieval.get("source_types"),
                        path=f"{item_path}.retrieval_intent.source_types",
                    )
                    if len(set(source_types)) != len(source_types):
                        raise ValidationError("retrieval source_types must be unique")
                    unsupported = sorted(set(source_types) - allowed_source_types)
                    if unsupported:
                        raise ValidationError(
                            "retrieval source_types are unavailable: "
                            + ", ".join(unsupported)
                        )
                    query = str(retrieval.get("query", "")).strip()
                    if not 1 <= len(query) <= 240:
                        raise ValidationError("retrieval query must be 1-240 characters")
                    raw_falsifiers = raw.get("falsifiers")
                    if not isinstance(raw_falsifiers, list) or not raw_falsifiers:
                        raise ValidationError("falsifiers must be a non-empty array")
                    falsifiers: tuple[str, ...] = tuple(
                        f"{str(item.get('condition', '')).strip()} => "
                        f"{str(item.get('expected_observation', '')).strip()}"
                        for item in raw_falsifiers
                        if isinstance(item, Mapping)
                        and set(item) == {"condition", "expected_observation"}
                        and str(item.get("condition", "")).strip()
                        and str(item.get("expected_observation", "")).strip()
                    )
                    if len(falsifiers) != len(raw_falsifiers):
                        raise ValidationError(
                            "each falsifier requires condition and expected_observation"
                        )
                    semantic_texts = (
                        *normalized_measurement.values(),
                        query,
                        *falsifiers,
                    )
                    if any(
                        _fixed_semantics_match(text) is not None
                        or _H1_ALTERNATE_TEST_OUTCOME.search(text) is not None
                        for text in semantic_texts
                    ):
                        raise ValidationError(
                            "measurement, retrieval, and falsifiers must remain "
                            "point-in-time and cannot redefine fixed outcome semantics"
                        )
                    need_refs = validate_need_refs(
                        raw.get("need_refs"), path=f"{item_path}.need_refs"
                    )
                    seen_slots.add(proposal_ref)
                    parsed.append(
                        SignalMiningHypothesis(
                            hypothesis_id=proposal_ref,
                            statement=normalized_measurement["observable"],
                            applicability=applicability,
                            expected_positive_pattern=(
                                "The runtime will test expected_direction="
                                f"{expected_direction} across the fixed Discovery "
                                "positive/control comparison."
                            ),
                            source_types=source_types,
                            query=query,
                            falsifiers=falsifiers,
                            lookback_days=lookback_days,
                            measurement=normalized_measurement,
                            expected_direction=expected_direction,
                        )
                    )
                except (TypeError, ValueError, ValidationError) as exc:
                    issues.append(
                        ValidationIssue(
                            code="h1_hypothesis_v3_invalid",
                            message=f"{item_path}: {exc}",
                            paths=(item_path,),
                            item_id=(proposal_ref if proposal_ref in allowed_slots else None),
                            item_id_field="proposal_ref",
                            allowed_repairs=("replace", "remove"),
                        )
                    )
            if issues:
                raise StructuredValidationError(issues)
            hypothesis_need_refs = {
                ref
                for raw in raw_items
                if isinstance(raw, Mapping)
                for ref in raw.get("need_refs", ())
            }
            new_measurement_refs = {
                ref
                for item in disposition_rows
                if item["disposition"] == "new_measurement"
                for ref in item["need_refs"]
            }
            if hypothesis_need_refs != new_measurement_refs:
                raise ValidationError(
                    "new_measurement dispositions must match hypothesis need_refs"
                )
            conclusion_metadata.clear()
            conclusion_metadata.update(
                {
                    "conclusion": "hypotheses",
                    "reason_code": None,
                    "rationale": [],
                    "need_refs": sorted(
                        {
                            ref
                            for raw in raw_items
                            if isinstance(raw, Mapping)
                            for ref in raw.get("need_refs", ())
                        }
                    ),
                    "need_dispositions": disposition_rows,
                    "hypothesis_need_refs": {
                        str(raw["proposal_ref"]): list(raw.get("need_refs", ()))
                        for raw in raw_items
                        if isinstance(raw, Mapping)
                    },
                }
            )
            return tuple(parsed)

        if self.identity_guard_aliases:
            _scan_payload(
                projected_payload,
                allow_outcomes=True,
                anonymous_aliases=self.identity_guard_aliases,
                identity_boundary="Signal Mining H1 v7 aggregate request",
            )
        system_prompt = (
            "Propose only reusable, point-in-time observable measurements. The "
            "runtime owns hypothesis identity, comparison groups, evidence window, "
            "case selection, and limits; copy proposal_ref and need_refs exactly. "
            "Give every supplied backlog need_ref exactly one disposition; a pure "
            "provider or dependency failure may be repair_dependency without forcing "
            "a hypothesis. Items with kind=meta_reflection_action are explicit "
            "outcome-aware lessons from earlier Fast evaluation. Route a reusable "
            "observable factor to new_measurement or update_existing, a missing "
            "source capability to repair_dependency, and an intrinsically "
            "untestable factor to not_testable. A reusable measurable gap outside "
            "the frozen hypothesis_limit must be deferred_measurement, not "
            "already_covered or not_testable. An unmatched_signal_need is still "
            "unresolved and cannot be already_covered. update_existing requires "
            "each grouped need to carry the cited signal_ref or literally contain "
            "one of that card's routing_answer_need_phrases. Use fast_plan_action only when the "
            "item changes retrieval, analysis, threshold calibration, magnitude, "
            "or another prediction policy rather than defining a reusable factor; "
            "the original reflection already flows through meta-memory to the next "
            "Fast proposer. fast_plan_action is invalid for ordinary backlog needs. "
            "Reflection does not force a fabricated measurement and cannot be "
            "dismissed as already_covered. Use the supplied canonical "
            "applicability contract and "
            "source types. A non-empty demand backlog is diagnostic demand, not proof "
            "that a new testable measurement exists. Return no_testable_hypothesis "
            "when the visible gaps, sources, or prior attempts do not support a new "
            "test. Do not infer an event from an outcome label, redefine the fixed "
            "groups, encode a future outcome in the measurement, or request facts "
            "after a source series, cutoff, or prediction time; every measurement "
            "uses only facts available at or before each prediction time. Existing Signal "
            "cards are an exclusion catalog. On correction, follow the supplied "
            "field paths. When an issue identifies one invalid proposal_ref, change "
            "or remove only that hypothesis and retain valid siblings byte-for-byte."
            " The candidate-case roster, its labels and fixed group membership, and "
            "full candidate source excerpts are intentionally absent at H1, while "
            "retrospective meta-memory is outcome-aware; do not use absent candidate "
            "inputs alone to reject a "
            "measurement definable from the backlog and source catalog. H2/H3 owns "
            "case feasibility and evidence testing. Group equivalent need "
            "dispositions compactly."
            + _UNTRUSTED_DATA_INSTRUCTION
            + _SIGNAL_MINING_HYPOTHESES_V3_OUTPUT
        )
        estimator = getattr(self.caller, "estimate_json_request_tokens", None)
        if self.request_token_budget is not None and callable(estimator):
            required = estimator(
                system_prompt=system_prompt,
                payload=projected_payload,
                allow_outcomes=True,
                anonymous_aliases=self.identity_guard_aliases,
                max_output_tokens=self.h1_max_output_tokens,
                temperature=self.creative_temperature,
            )
            if required > self.request_token_budget:
                raise CandidateExecutionRejected(
                    "signal_mining_hypotheses",
                    "complete H1 search context exceeds the frozen request-token "
                    f"budget: required={required}, limit={self.request_token_budget}",
                    AgentUsage(),
                    details={
                        "failure_kind": "role_request_too_large",
                        "required_request_bytes": required,
                        "request_budget_bytes": self.request_token_budget,
                    },
                )
        value, usage, request_refs = _complete_parsed_role_with_trace(
            self.caller,
            stage="signal_mining_hypotheses",
            system_prompt=system_prompt,
            payload=projected_payload,
            parser=parse,
            allow_outcomes=True,
            anonymous_aliases=self.identity_guard_aliases,
            reject_output_aliases=self.identity_guard_aliases,
            max_output_tokens=self.h1_max_output_tokens,
            temperature=self.creative_temperature,
            stable_correction_prefix=True,
            enforce_scoped_correction=True,
            final_validation_fallback=_h1_redundant_signal_ref_fallback,
        )
        restored_metadata = deepcopy(conclusion_metadata)
        if "need_refs" in restored_metadata:
            restored_metadata["need_refs"] = [
                alias_to_original.get(ref, ref)
                for ref in restored_metadata.get("need_refs", ())
            ]
        for disposition in restored_metadata.get("need_dispositions", ()):
            disposition["need_refs"] = [
                alias_to_original.get(ref, ref)
                for ref in disposition.get("need_refs", ())
            ]
        if isinstance(restored_metadata.get("hypothesis_need_refs"), Mapping):
            restored_metadata["hypothesis_need_refs"] = {
                key: [alias_to_original.get(ref, ref) for ref in refs]
                for key, refs in restored_metadata["hypothesis_need_refs"].items()
            }
        restored_metadata["need_ref_aliases"] = [
            {"alias": alias, "need_ref": original}
            for alias, original in alias_to_original.items()
        ]
        restored_metadata["request_refs"] = list(request_refs)
        return AgentStep(value, usage, metadata=restored_metadata)

    def rank_cases(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[Mapping[str, tuple[str, ...]]]:
        hypotheses = payload.get("hypotheses", ())
        case_briefs = payload.get("case_briefs", ())
        allowed_hypotheses = {
            str(item["hypothesis_id"])
            for item in hypotheses
            if isinstance(item, Mapping) and "hypothesis_id" in item
        }
        allowed_cases = {
            str(item["case_ref"])
            for item in case_briefs
            if isinstance(item, Mapping) and "case_ref" in item
        }
        briefs_by_ref = {
            str(item["case_ref"]): item
            for item in case_briefs
            if isinstance(item, Mapping) and "case_ref" in item
        }
        applicability_by_hypothesis: dict[str, str] = {}
        for item in hypotheses:
            if not isinstance(item, Mapping) or "hypothesis_id" not in item:
                continue
            applicability = str(item.get("applicability", ""))
            try:
                _h1_applicability_rule(applicability)
            except ValidationError:
                continue
            applicability_by_hypothesis[str(item["hypothesis_id"])] = applicability
        brief_strings_by_ref: dict[str, tuple[str, ...]] = {}

        def collect_strings(value: Any, *, key: str | None = None) -> list[str]:
            if isinstance(value, str):
                return [] if key == "case_ref" else [" ".join(value.split())]
            if isinstance(value, Mapping):
                return [
                    text
                    for child_key, child in value.items()
                    for text in collect_strings(child, key=str(child_key))
                ]
            if isinstance(value, (list, tuple)):
                return [
                    text
                    for child in value
                    for text in collect_strings(child, key=key)
                ]
            return []

        for item in case_briefs:
            if isinstance(item, Mapping) and "case_ref" in item:
                brief_strings_by_ref[str(item["case_ref"])] = tuple(
                    text for text in collect_strings(item) if text
                )
        rules = payload.get("rules", {})
        ranking_limit = int(
            rules.get("max_case_refs_per_hypothesis", len(allowed_cases))
            if isinstance(rules, Mapping)
            else len(allowed_cases)
        )
        if ranking_limit < 1:
            raise ValidationError("Signal Mining H2 ranking limit must be positive")

        def parse(value: Mapping[str, Any]) -> Mapping[str, tuple[str, ...]]:
            if set(value) != {"rankings"} or not isinstance(
                value.get("rankings"), list
            ):
                raise ValidationError("Signal Mining H2 requires a rankings array")
            rankings: dict[str, tuple[str, ...]] = {}
            semantic_issues: dict[str, list[str]] = {
                "evidence_bounds": [],
                "reason_bounds": [],
                "self_disqualifying_reason": [],
                "inferential_reason": [],
                "nonliteral_evidence": [],
                "applicability_rule_mismatch": [],
                "empty_despite_visible_match": [],
            }

            def record_issue(kind: str, hypothesis_id: str, case_ref: str) -> None:
                ref = f"{hypothesis_id}/{case_ref}"
                if ref not in semantic_issues[kind]:
                    semantic_issues[kind].append(ref)

            for raw in value["rankings"]:
                if not isinstance(raw, Mapping) or set(raw) != {
                    "hypothesis_id",
                    "cases",
                }:
                    raise ValidationError(
                        "each Signal Mining H2 ranking requires hypothesis_id and cases"
                    )
                hypothesis_id = str(raw["hypothesis_id"])
                raw_cases = raw["cases"]
                if not isinstance(raw_cases, list):
                    raise ValidationError("Signal Mining H2 cases must be an array")
                if len(raw_cases) > ranking_limit:
                    raise ValidationError(
                        "Signal Mining H2 ranking exceeds "
                        f"max_case_refs_per_hypothesis={ranking_limit}"
                    )
                refs: list[str] = []
                for ranked_case in raw_cases:
                    if not isinstance(ranked_case, Mapping) or set(ranked_case) != {
                        "case_ref",
                        "profile_evidence",
                        "applicability_reason",
                    }:
                        raise ValidationError(
                            "each Signal Mining H2 case requires case_ref, "
                            "profile_evidence, and applicability_reason"
                        )
                    case_ref = str(ranked_case["case_ref"])
                    evidence = " ".join(
                        str(ranked_case["profile_evidence"]).split()
                    )
                    reason = " ".join(
                        str(ranked_case["applicability_reason"]).split()
                    )
                    if not evidence or len(evidence) > 160:
                        record_issue("evidence_bounds", hypothesis_id, case_ref)
                    if not reason or len(reason) > 240:
                        record_issue("reason_bounds", hypothesis_id, case_ref)
                    if _h2_reason_disclaims_applicability(reason):
                        record_issue(
                            "self_disqualifying_reason", hypothesis_id, case_ref
                        )
                    if _H2_INFERENTIAL_REASON_PATTERN.search(reason) is not None:
                        record_issue("inferential_reason", hypothesis_id, case_ref)
                    visible_fields = brief_strings_by_ref.get(case_ref, ())
                    if evidence and len(evidence) <= 160 and not any(
                        evidence.casefold() in field.casefold()
                        for field in visible_fields
                    ):
                        record_issue("nonliteral_evidence", hypothesis_id, case_ref)
                    applicability = applicability_by_hypothesis.get(hypothesis_id)
                    brief = briefs_by_ref.get(case_ref)
                    if (
                        applicability is not None
                        and brief is not None
                        and not _h2_applicability_matches(applicability, brief)
                    ):
                        record_issue(
                            "applicability_rule_mismatch", hypothesis_id, case_ref
                        )
                    refs.append(case_ref)
                if len(set(refs)) != len(refs):
                    raise ValidationError("Signal Mining H2 case refs must be unique")
                if hypothesis_id in rankings:
                    raise ValidationError("Signal Mining H2 repeated a hypothesis")
                rankings[hypothesis_id] = tuple(refs)
            if set(rankings) != allowed_hypotheses:
                raise ValidationError("Signal Mining H2 must rank every supplied hypothesis")
            for hypothesis_id, applicability in applicability_by_hypothesis.items():
                if rankings.get(hypothesis_id):
                    continue
                if any(
                    _h2_applicability_matches(applicability, brief)
                    for brief in briefs_by_ref.values()
                ):
                    semantic_issues["empty_despite_visible_match"].append(
                        hypothesis_id
                    )
            unknown = sorted(
                {case_ref for refs in rankings.values() for case_ref in refs}
                - allowed_cases
            )
            if unknown:
                raise ValidationError(
                    "Signal Mining H2 used unknown case refs: " + ", ".join(unknown)
                )
            issue_messages: list[str] = []
            if semantic_issues["evidence_bounds"]:
                issue_messages.append(
                    "Signal Mining H2 profile_evidence must be 1-160 characters for: "
                    + ", ".join(semantic_issues["evidence_bounds"])
                )
            if semantic_issues["reason_bounds"]:
                issue_messages.append(
                    "Signal Mining H2 applicability_reason must be 1-240 characters for: "
                    + ", ".join(semantic_issues["reason_bounds"])
                )
            if semantic_issues["self_disqualifying_reason"]:
                issue_messages.append(
                    "Signal Mining H2 applicability_reason must state positive visible "
                    "support and cannot disclaim applicability for: "
                    + ", ".join(semantic_issues["self_disqualifying_reason"])
                )
            if semantic_issues["inferential_reason"]:
                issue_messages.append(
                    "Signal Mining H2 applicability_reason must not infer missing profile "
                    "facts for: " + ", ".join(semantic_issues["inferential_reason"])
                )
            if semantic_issues["nonliteral_evidence"]:
                issue_messages.append(
                    "Signal Mining H2 profile_evidence must be an exact contiguous span "
                    "from the selected case brief for: "
                    + ", ".join(semantic_issues["nonliteral_evidence"])
                )
            if semantic_issues["applicability_rule_mismatch"]:
                issue_messages.append(
                    "Signal Mining H2 selected case must satisfy the canonical visible "
                    "applicability rule for: "
                    + ", ".join(semantic_issues["applicability_rule_mismatch"])
                )
            if semantic_issues["empty_despite_visible_match"]:
                issue_messages.append(
                    "Signal Mining H2 cannot return an empty ranking when supplied "
                    "briefs satisfy the canonical visible applicability rule for: "
                    + ", ".join(semantic_issues["empty_despite_visible_match"])
                )
            if issue_messages:
                raise ValidationError("; ".join(issue_messages))
            return rankings

        value, usage, request_refs = _complete_parsed_role_with_trace(
            self.caller,
            stage="signal_mining_case_ranking",
            system_prompt=(
                "Rank the anonymous company briefs by applicability to each hypothesis. "
                "Outcomes and identities are hidden. Use only supplied opaque refs and "
                "rank all hypotheses in this single call. Return only materially "
                "applicable cases, most applicable first; omit irrelevant cases, do "
                "not pad by copying the full pool, and use an empty cases array when "
                "none apply. applicability is a canonical single-field rule produced "
                "from this exact brief pool. all_ready_issuers matches every supplied "
                "brief; *_values rules match the named visible field; and "
                "business_description_topics matches those literal normalized topics. "
                "Do not return empty when at least one supplied brief satisfies the rule, "
                "and never select a brief that does not satisfy it. Every included case "
                "must quote one short exact contiguous "
                "span of 1-160 characters from its supplied anonymous brief as "
                "profile_evidence and give an applicability_reason of 1-240 characters "
                "that states positive visible support for the exact hypothesis "
                "applicability. If the reason would say evidence is missing, unavailable, "
                "generic, insufficient, speculative, or unconfirmed, omit that case; "
                "never infer missing profile facts. Reasons using suggests, indicates, "
                "aligns, likely, typically, may, might, or similar inferential language "
                "are invalid; omit those cases. Do not quote a company name, ticker, "
                "or brand in profile_evidence. Respect "
                "rules.max_case_refs_per_hypothesis."
                + _UNTRUSTED_DATA_INSTRUCTION
                + _SIGNAL_MINING_RANKING_OUTPUT
            ),
            payload=payload,
            parser=parse,
            allow_outcomes=False,
            anonymous_aliases=(),
            reject_output_aliases=self.identity_guard_aliases,
            max_output_tokens=2_000,
            stable_correction_prefix=True,
            echo_invalid_output_on_correction=False,
        )
        return AgentStep(value, usage, metadata={"request_refs": request_refs})

    def contrast(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningDecision, ...]]:
        comparisons = tuple(
            item for item in payload.get("comparisons", ()) if isinstance(item, Mapping)
        )
        allowed = {
            str(item["hypothesis"]["hypothesis_id"])
            for item in comparisons
            if isinstance(item, Mapping)
            and isinstance(item.get("hypothesis"), Mapping)
            and "hypothesis_id" in item["hypothesis"]
        }
        inconclusive_only: set[str] = set()
        for item in comparisons:
            if not isinstance(item, Mapping) or not isinstance(
                item.get("hypothesis"), Mapping
            ):
                continue
            hypothesis_id = str(item["hypothesis"].get("hypothesis_id", ""))
            packets = tuple(
                packet
                for packet in item.get("evidence_packets", ())
                if isinstance(packet, Mapping)
            )
            if not hypothesis_id or not packets:
                continue
            matched_labels = {
                str(packet.get("label", ""))
                for packet in packets
                if packet.get("query_match_status") == "matched"
            }
            if not {"positive", "control"}.issubset(matched_labels):
                inconclusive_only.add(hypothesis_id)
        return self._decisions(
            stage="signal_mining_contrast",
            payload=payload,
            allowed_hypothesis_ids=allowed,
            inconclusive_only_ids=inconclusive_only,
            prompt=(
                "Contrast the supplied exact point-in-time positive and control evidence. "
                "Support only a repeated observable difference, refine an underspecified "
                "idea, reject a visibly contradicted one, or return inconclusive when the "
                "visible material is still semantically insufficient. A supported draft "
                "must be a complete new Signal with executable fixtures. Return exactly "
                "one decision for every comparison. The controller has preflighted "
                "deterministic query coverage, but use inconclusive for any residual "
                "source insufficiency; use refine only for an evidence-grounded semantic "
                "change and rejected only for visible contradiction. A packet marked "
                "unmatched_comparator_context is real point-in-time source context, but "
                "query non-match is not proof that the feature or event is absent; "
                "without direct positive or counter evidence it supports only an "
                "inconclusive decision. For each decision, use only the evidence_packets "
                "nested under that decision's own comparison; never count or describe "
                "packets belonging to a sibling hypothesis."
            ),
            temperature=0.0,
        )

    def extract_exploration(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningSignature, ...]]:
        packets = tuple(
            item
            for item in payload.get("cases", ())
            if isinstance(item, Mapping)
        )
        allowed = {
            str(item["case_ref"])
            for item in packets
            if isinstance(item, Mapping) and "case_ref" in item
        }
        allowed_order = tuple(
            str(item["case_ref"])
            for item in packets
            if isinstance(item, Mapping) and "case_ref" in item
        )
        packet_by_ref = {
            str(item["case_ref"]): item
            for item in packets
            if isinstance(item, Mapping) and "case_ref" in item
        }

        def parse(value: Mapping[str, Any]) -> tuple[SignalMiningSignature, ...]:
            if set(value) != {"signatures"} or not isinstance(
                value.get("signatures"), list
            ):
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="e1_portfolio_shape_invalid",
                            message="Signal Mining E1 requires a signatures array",
                            paths=("signatures",),
                        )
                    ]
                )
            raw_items = value["signatures"]
            issues: list[ValidationIssue] = []
            parsed_by_ref: dict[str, SignalMiningSignature] = {}
            raw_ref_counts: dict[str, int] = {}
            for raw in raw_items:
                if isinstance(raw, Mapping) and isinstance(raw.get("case_ref"), str):
                    case_ref = str(raw["case_ref"])
                    raw_ref_counts[case_ref] = raw_ref_counts.get(case_ref, 0) + 1
            for index, raw in enumerate(raw_items):
                item_path = f"signatures[{index}]"
                if not isinstance(raw, Mapping):
                    issues.append(
                        ValidationIssue(
                            code="e1_signature_shape_invalid",
                            message="E1 signature must be an object",
                            paths=(item_path,),
                            allowed_repairs=("replace", "remove"),
                        )
                    )
                    continue
                raw_ref = raw.get("case_ref")
                case_ref = str(raw_ref) if isinstance(raw_ref, str) else None
                if case_ref is None or case_ref not in allowed:
                    issues.append(
                        ValidationIssue(
                            code="e1_case_ref_invalid",
                            message=(
                                "Signal Mining E1 case_ref must be copied from the "
                                "supplied cases"
                            ),
                            paths=(f"{item_path}.case_ref",),
                            allowed_repairs=("replace", "remove"),
                        )
                    )
                    continue
                if raw_ref_counts[case_ref] > 1:
                    issues.append(
                        ValidationIssue(
                            code="e1_case_ref_duplicate",
                            message=(
                                "Signal Mining E1 must not duplicate supplied "
                                f"case_ref {case_ref}"
                            ),
                            paths=(item_path,),
                            allowed_repairs=("replace", "remove"),
                            source_refs=(case_ref,),
                        )
                    )
                    continue
                try:
                    item = SignalMiningSignature.from_dict(raw)
                    validate_signal_mining_signatures(
                        (item,), (packet_by_ref[case_ref],)
                    )
                except ValidationError as exc:
                    issues.append(
                        ValidationIssue(
                            code="e1_signature_invalid",
                            message=str(exc),
                            paths=(item_path,),
                            item_id=case_ref,
                            item_id_field="case_ref",
                            allowed_repairs=("replace",),
                            source_refs=(case_ref,),
                        )
                    )
                    continue
                parsed_by_ref[case_ref] = item
            missing_refs = sorted(allowed - set(raw_ref_counts))
            if missing_refs:
                issues.append(
                    ValidationIssue(
                        code="e1_case_refs_missing",
                        message=(
                            "Signal Mining E1 must return one signature for every "
                            f"case_ref; missing={missing_refs}"
                        ),
                        paths=("signatures",),
                        allowed_repairs=("replace",),
                        source_refs=tuple(missing_refs),
                    )
                )
            if issues:
                raise StructuredValidationError(issues)
            return tuple(parsed_by_ref[case_ref] for case_ref in allowed_order)

        quarantined: dict[str, list[str]] = {}

        def quarantine_invalid_observations(
            failed: Mapping[str, Any], _error: ValidationError,
        ) -> tuple[dict[str, Any], dict[str, tuple[str, ...]]] | None:
            """Keep only independently grounded observations after bounded repair."""

            rows = failed.get("signatures")
            if not isinstance(rows, list):
                return None
            repaired = []
            removed = []
            for index, row in enumerate(rows):
                if (
                    not isinstance(row, Mapping)
                    or not isinstance(row.get("case_ref"), str)
                    or row["case_ref"] not in packet_by_ref
                ):
                    return None
                case_ref = str(row["case_ref"])
                observations = row.get("observations")
                gaps = row.get("evidence_gaps")
                if not isinstance(observations, list) or not isinstance(gaps, list):
                    return None
                kept = []
                reasons = []
                for offset, raw_observation in enumerate(observations):
                    try:
                        if not isinstance(raw_observation, Mapping):
                            raise ValidationError("Mining observation must be an object")
                        observation = SignalMiningObservation.from_dict(raw_observation)
                        validate_signal_mining_signatures(
                            (SignalMiningSignature(case_ref, (observation,)),),
                            (packet_by_ref[case_ref],),
                        )
                    except (KeyError, TypeError, ValueError, ValidationError) as exc:
                        reasons.append(str(exc))
                        removed.append(f"signatures[{index}].observations[{offset}]")
                    else:
                        kept.append(raw_observation)
                if reasons:
                    quarantined.setdefault(case_ref, []).extend(reasons)
                    gaps = [*gaps, "Some extracted observations failed validation; "
                            "this does not establish absent source data or conditions."]
                repaired.append({**row, "observations": kept, "evidence_gaps": gaps})
            if not removed:
                return None
            return {**failed, "signatures": repaired}, {
                "removed_paths": tuple(removed), "source_substitution_paths": (),
            }

        value, usage, request_refs = _complete_parsed_role_with_trace(
            self.caller,
            stage="signal_mining_exploration_extract",
            system_prompt=(
                "Describe only recurring, executable observations in the anonymous "
                "point-in-time evidence. Ground every observation in its own supplied "
                "literal; the literal is authoritative when a summary overstates it. "
                "Labels are hidden; do not predict or infer them."
                + _SIGNAL_MINING_SIGNATURES_OUTPUT
            ),
            payload=payload,
            parser=parse,
            allow_outcomes=False,
            anonymous_aliases=(),
            reject_output_aliases=self.identity_guard_aliases,
            stable_correction_prefix=True,
            enforce_scoped_correction=True,
            final_validation_fallback=quarantine_invalid_observations,
        )
        return AgentStep(
            value,
            usage,
            metadata={
                "quarantined_observations": quarantined,
                "request_refs": request_refs,
            },
        )

    def discover_exploration(
        self, payload: Mapping[str, Any]
    ) -> AgentStep[tuple[SignalMiningDecision, ...]]:
        return self._decisions(
            stage="signal_mining_exploration_discover",
            payload=payload,
            allowed_hypothesis_ids=None,
            inconclusive_only_ids=set(),
            prompt=(
                "The signatures were frozen while outcomes were hidden; the supplied "
                "positive/control labels are now visible and must be compared against "
                "those unchanged signatures. Do not claim the labels remain hidden, "
                "unavailable, or uncomparable. "
                "Each deterministic summary contains only source-owned context. "
                "Treat each exact_span as authoritative; ignore any stronger or "
                "different claim inferred from the summary. "
                "Do not infer issuer-profile differences such as sector, industry, "
                "business model, market-cap class, geography, or listing venue unless "
                "that attribute is literally present in the supplied signatures. "
                "Each decision is a portfolio-level recurring pattern, not one decision "
                "per case. Propose a reusable new Signal only for a repeated observable "
                "difference. If the cases only support individual rejections or no "
                "recurring pattern, return decisions=[] and the structured no_candidate "
                "reason covering every supplied case_ref."
            ),
            temperature=self.creative_temperature,
        )

    def _decisions(
        self,
        *,
        stage: str,
        payload: Mapping[str, Any],
        allowed_hypothesis_ids: set[str] | None,
        inconclusive_only_ids: set[str],
        prompt: str,
        temperature: float,
    ) -> AgentStep[tuple[SignalMiningDecision, ...]]:
        exploration = stage == "signal_mining_exploration_discover"
        rules = payload.get("rules", {})
        allowed_dispositions = {
            str(item)
            for item in (
                rules.get(
                    "decisions",
                    ("supported", "refine", "rejected", "inconclusive"),
                )
                if isinstance(rules, Mapping)
                else ("supported", "refine", "rejected", "inconclusive")
            )
        }
        comparison_refs: dict[str, tuple[str, ...]] = {
            str(item["hypothesis"]["hypothesis_id"]): tuple(
                str(packet["packet_ref"])
                for packet in item.get("evidence_packets", ())
                if isinstance(packet, Mapping) and packet.get("packet_ref")
            )
            for item in payload.get("comparisons", ())
            if isinstance(item, Mapping)
            and isinstance(item.get("hypothesis"), Mapping)
            and item["hypothesis"].get("hypothesis_id")
        }
        packet_labels = {
            str(packet["packet_ref"]): str(packet.get("label", ""))
            for comparison in payload.get("comparisons", ())
            if isinstance(comparison, Mapping)
            for packet in comparison.get("evidence_packets", ())
            if isinstance(packet, Mapping) and packet.get("packet_ref")
        }
        exploration_labels = {
            str(item["case_ref"]): str(item.get("label", ""))
            for item in payload.get("signatures", ())
            if isinstance(item, Mapping) and item.get("case_ref")
        }
        exploration_evidence_limited = bool(
            rules.get("evidence_limited", False)
            if isinstance(rules, Mapping)
            else False
        )
        decision_metadata: dict[str, Any] = {}
        decision_slots = tuple(
            str(item) for item in payload.get("decision_slots", ()) if str(item)
        )

        def sample_basis(
            item: SignalMiningDecision,
        ) -> Mapping[str, tuple[str, ...]] | None:
            if item.hypothesis_id in comparison_refs:
                refs = comparison_refs[item.hypothesis_id]
                labels = packet_labels
            else:
                refs = tuple(exploration_labels)
                labels = exploration_labels
            basis = {
                "positive_refs": tuple(ref for ref in refs if labels.get(ref) == "positive"),
                "control_refs": tuple(ref for ref in refs if labels.get(ref) == "control"),
            }
            if not basis["positive_refs"] or not basis["control_refs"]:
                if item.disposition == "inconclusive":
                    return None
                raise ValidationError(
                    "Signal Mining association requires positive and control sample refs"
                )
            return basis

        def parse(value: Mapping[str, Any]) -> tuple[SignalMiningDecision, ...]:
            expected_fields = (
                {"decisions", "no_candidate"} if exploration else {"decisions"}
            )
            if set(value) != expected_fields or not isinstance(
                value.get("decisions"), list
            ):
                raise ValidationError(f"{stage} requires a decisions array")
            raw_decisions = value["decisions"]
            if exploration and raw_decisions and all(
                isinstance(item, Mapping)
                and item.get("case_ref") in exploration_labels
                and item.get("candidate") is None
                and item.get("hypothesis_id") in {None, ""}
                and item.get("disposition", item.get("decision"))
                in {"rejected", "inconclusive"}
                for item in raw_decisions
            ):
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="e2_per_case_rows_not_portfolio_decisions",
                            message=(
                                "These are per-case rejection rows, not recurring "
                                "cross-case decisions. Replace decisions with [] and "
                                "replace no_candidate with reason_code, non-empty "
                                "rationale, and every supplied case_ref in order."
                            ),
                            paths=("decisions", "no_candidate"),
                        )
                    ]
                )
            if exploration:
                parsed_items: list[SignalMiningDecision] = []
                shape_issues: list[ValidationIssue] = []
                for index, raw_item in enumerate(raw_decisions):
                    path = f"decisions[{index}]"
                    if not isinstance(raw_item, Mapping) or set(raw_item) != {
                        "hypothesis_id", "disposition", "rationale", "contrast", "candidate"
                    }:
                        shape_issues.append(
                            ValidationIssue(
                                code="e2_decision_shape_invalid",
                                message=(
                                    f"{path} requires exactly hypothesis_id, disposition, "
                                    "rationale, contrast, and candidate"
                                ),
                                paths=(path,),
                                allowed_repairs=("replace", "remove"),
                            )
                        )
                        continue
                    slot = str(raw_item.get("hypothesis_id", ""))
                    contrast = raw_item.get("contrast")
                    if (
                        slot not in decision_slots
                        or raw_item.get("disposition") != "supported"
                        or not isinstance(contrast, Mapping)
                        or set(contrast) != {
                            "positive_case_refs",
                            "control_case_refs",
                            "observable_difference",
                        }
                    ):
                        shape_issues.append(
                            ValidationIssue(
                                code="e2_decision_contract_invalid",
                                message=(
                                    f"{path} must use one supplied decision slot, "
                                    "disposition=supported, and the exact contrast fields"
                                ),
                                paths=(path,),
                                item_id=(slot or None),
                                item_id_field="hypothesis_id",
                                allowed_repairs=("replace", "remove"),
                            )
                        )
                        continue
                    positive_refs = contrast.get("positive_case_refs")
                    control_refs = contrast.get("control_case_refs")
                    difference = contrast.get("observable_difference")
                    valid_positive = {
                        ref for ref, label in exploration_labels.items() if label == "positive"
                    }
                    valid_control = {
                        ref for ref, label in exploration_labels.items() if label == "control"
                    }
                    refs_valid = all(
                        isinstance(refs, list)
                        and bool(refs)
                        and len(refs) == len(set(refs))
                        and all(isinstance(ref, str) and ref in allowed for ref in refs)
                        for refs, allowed in (
                            (positive_refs, valid_positive),
                            (control_refs, valid_control),
                        )
                    )
                    candidate = raw_item.get("candidate")
                    rationale = raw_item.get("rationale")
                    if (
                        not refs_valid
                        or not isinstance(difference, str)
                        or not difference.strip()
                        or not isinstance(rationale, list)
                        or not rationale
                        or any(not isinstance(reason, str) or not reason.strip() for reason in rationale)
                        or not isinstance(candidate, Mapping)
                        or set(candidate) != {"spec", "skill", "tests"}
                    ):
                        shape_issues.append(
                            ValidationIssue(
                                code="e2_contrast_or_candidate_invalid",
                                message=(
                                    f"{path} requires non-empty label-correct contrast refs, "
                                    "one observable difference, rationale, and a complete "
                                    "spec/skill/tests candidate"
                                ),
                                paths=(path,),
                                item_id=slot,
                                item_id_field="hypothesis_id",
                                allowed_repairs=("replace", "remove"),
                            )
                        )
                        continue
                    label_assignment_indexes = (
                        _e2_free_text_label_assignment_indexes(
                            rationale, payload.get("signatures", ())
                        )
                    )
                    if label_assignment_indexes:
                        shape_issues.append(
                            ValidationIssue(
                                code="e2_free_text_label_assignment_forbidden",
                                message=(
                                    f"{path}.rationale must not restate case-to-label "
                                    "mappings in free text. Keep the comparison claim "
                                    "generic and rely on the validated contrast refs."
                                ),
                                paths=(f"{path}.rationale",),
                                item_id=slot,
                                item_id_field="hypothesis_id",
                                allowed_repairs=("replace", "remove"),
                            )
                        )
                        continue
                    unsupported_rationale_claims = (
                        _e2_profile_claims_without_literal_support(
                            rationale, payload.get("signatures", ())
                        )
                    )
                    unsupported_difference_claims = (
                        _e2_profile_claims_without_literal_support(
                            (difference,), payload.get("signatures", ())
                        )
                    )
                    unsupported_profile_claims = tuple(
                        dict.fromkeys(
                            (
                                *unsupported_rationale_claims,
                                *unsupported_difference_claims,
                            )
                        )
                    )
                    if unsupported_profile_claims:
                        shape_issues.append(
                            ValidationIssue(
                                code="e2_unsupported_profile_claim",
                                message=(
                                    f"{path} claims unsupplied issuer-profile attributes: "
                                    + ", ".join(unsupported_profile_claims)
                                    + ". Remove the claim or ground it in a supplied "
                                    "literal signature."
                                ),
                                paths=tuple(
                                    candidate_path
                                    for claims, candidate_path in (
                                        (
                                            unsupported_rationale_claims,
                                            f"{path}.rationale",
                                        ),
                                        (
                                            unsupported_difference_claims,
                                            f"{path}.contrast.observable_difference",
                                        ),
                                    )
                                    if claims
                                ),
                                item_id=slot,
                                item_id_field="hypothesis_id",
                                allowed_repairs=("replace", "remove"),
                            )
                        )
                        continue
                    uncited_gap_indexes = _e2_uncited_source_gap_claim_indexes(
                        rationale, payload.get("signatures", ())
                    )
                    if uncited_gap_indexes:
                        shape_issues.append(
                            ValidationIssue(
                                code="e2_source_gap_claim_ungrounded",
                                message=(
                                    f"{path}.rationale contains a specific source-gap "
                                    "claim that is not a canonical [case_ref] plus "
                                    "verbatim evidence_gaps citation. Remove the claim "
                                    "or copy exactly one supplied gap per rationale item."
                                ),
                                paths=(f"{path}.rationale",),
                                item_id=slot,
                                item_id_field="hypothesis_id",
                                allowed_repairs=("replace", "remove"),
                            )
                        )
                        continue
                    parsed_items.append(
                        SignalMiningDecision(
                            hypothesis_id=slot,
                            disposition="supported",
                            rationale=tuple(str(reason) for reason in rationale),
                            candidate=dict(candidate),
                            sample_basis={
                                "positive_refs": tuple(positive_refs),
                                "control_refs": tuple(control_refs),
                            },
                        )
                    )
                if shape_issues:
                    raise StructuredValidationError(shape_issues)
                items = tuple(parsed_items)
            else:
                items = tuple(
                    SignalMiningDecision.from_dict(item)
                    if isinstance(item, Mapping)
                    else (_raise_mining_shape("Mining decision must be an object"))
                    for item in value["decisions"]
                )
            if exploration:
                no_candidate = value.get("no_candidate")
                if items and no_candidate is not None:
                    raise ValidationError(
                        "Exploration E2 non-empty decisions require no_candidate=null"
                    )
                if not items:
                    if not isinstance(no_candidate, Mapping) or set(no_candidate) != {
                        "reason_code",
                        "rationale",
                        "considered_case_refs",
                    }:
                        raise ValidationError(
                            "Exploration E2 empty decisions require structured no_candidate"
                        )
                    reason_code = str(no_candidate.get("reason_code", ""))
                    if reason_code not in {
                        "no_measurable_pattern",
                        "insufficient_evidence",
                        "already_covered",
                    }:
                        raise ValidationError(
                            "Exploration E2 no_candidate reason_code is invalid"
                        )
                    if (
                        exploration_evidence_limited
                        and reason_code == "no_measurable_pattern"
                    ):
                        raise StructuredValidationError(
                            [
                                ValidationIssue(
                                    code="e2_limited_evidence_overclaims_no_pattern",
                                    message=(
                                        "The controller marked this comparison evidence "
                                        "as limited. An empty portfolio must use "
                                        "insufficient_evidence, not no_measurable_pattern."
                                    ),
                                    paths=("no_candidate.reason_code",),
                                    allowed_repairs=("replace",),
                                )
                            ]
                        )
                    rationale = no_candidate.get("rationale")
                    considered = no_candidate.get("considered_case_refs")
                    if not isinstance(rationale, list) or not rationale or any(
                        not isinstance(item, str) or not item.strip()
                        for item in rationale
                    ):
                        raise ValidationError(
                            "Exploration E2 no_candidate rationale is invalid"
                        )
                    if (
                        all(label in {"positive", "control"} for label in exploration_labels.values())
                        and any(
                            re.search(r"\bunlabel(?:ed|led)\b", item, re.IGNORECASE)
                            or _E2_VISIBLE_LABEL_DENIAL.search(item)
                            for item in rationale
                        )
                    ):
                        raise StructuredValidationError(
                            [
                                ValidationIssue(
                                    code="e2_no_candidate_label_inventory_mismatch",
                                    message=(
                                        "Every selected E2 signature has a positive or "
                                        "control label visible in this request; the "
                                        "no_candidate rationale must not claim labels "
                                        "are absent, hidden, unavailable, or uncomparable."
                                    ),
                                    paths=("no_candidate.rationale",),
                                )
                            ]
                        )
                    label_assignment_indexes = (
                        _e2_free_text_label_assignment_indexes(
                            rationale, payload.get("signatures", ())
                        )
                    )
                    if label_assignment_indexes:
                        raise StructuredValidationError(
                            [
                                ValidationIssue(
                                    code="e2_free_text_label_assignment_forbidden",
                                    message=(
                                        "Exploration E2 no_candidate rationale must "
                                        "not restate case-to-label mappings in free "
                                        "text. Keep comparison claims generic; runtime "
                                        "records the exact groups separately."
                                    ),
                                    paths=("no_candidate.rationale",),
                                    allowed_repairs=("replace", "remove"),
                                )
                            ]
                        )
                    unsupported_profile_claims = (
                        _e2_profile_claims_without_literal_support(
                            rationale, payload.get("signatures", ())
                        )
                    )
                    if unsupported_profile_claims:
                        raise StructuredValidationError(
                            [
                                ValidationIssue(
                                    code="e2_unsupported_profile_claim",
                                    message=(
                                        "Exploration E2 no_candidate rationale claims "
                                        "issuer-profile attributes absent from every "
                                        "supplied literal signature: "
                                        + ", ".join(unsupported_profile_claims)
                                        + ". Remove the claim or ground it in supplied "
                                        "literal evidence."
                                    ),
                                    paths=("no_candidate.rationale",),
                                    allowed_repairs=("replace",),
                                )
                            ]
                        )
                    uncited_gap_indexes = _e2_uncited_source_gap_claim_indexes(
                        rationale, payload.get("signatures", ())
                    )
                    if uncited_gap_indexes:
                        raise StructuredValidationError(
                            [
                                ValidationIssue(
                                    code="e2_source_gap_claim_ungrounded",
                                    message=(
                                        "Exploration E2 no_candidate rationale "
                                        "contains a specific source-gap claim that "
                                        "is not a canonical [case_ref] plus verbatim "
                                        "evidence_gaps citation. Remove the claim or "
                                        "copy exactly one supplied gap per rationale "
                                        "item."
                                    ),
                                    paths=("no_candidate.rationale",),
                                    allowed_repairs=("replace", "remove"),
                                )
                            ]
                        )
                    expected_refs = tuple(exploration_labels)
                    if not isinstance(considered, list) or tuple(considered) != expected_refs:
                        raise ValidationError(
                            "Exploration E2 considered_case_refs must match the actual "
                            "selected grounded signatures"
                        )
                    decision_metadata.clear()
                    decision_metadata["no_candidate"] = {
                        "reason_code": reason_code,
                        "rationale": list(rationale),
                        "considered_case_refs": list(considered),
                        "positive_case_refs": [
                            ref
                            for ref, label in exploration_labels.items()
                            if label == "positive"
                        ],
                        "control_case_refs": [
                            ref
                            for ref, label in exploration_labels.items()
                            if label == "control"
                        ],
                    }
                else:
                    decision_metadata.clear()
                    decision_metadata["no_candidate"] = None
            invalid_unmatched = sorted(
                item.hypothesis_id
                for item in items
                if item.hypothesis_id in inconclusive_only_ids
                and item.disposition != "inconclusive"
            )
            if invalid_unmatched:
                raise ValidationError(
                    "Signal Mining decisions without query-matched positive and "
                    "control evidence must be inconclusive: "
                    + ", ".join(invalid_unmatched)
                )
            ids = [item.hypothesis_id for item in items]
            if len(set(ids)) != len(ids):
                raise ValidationError("Signal Mining decisions must use unique ids")
            if allowed_hypothesis_ids is not None and set(ids) != allowed_hypothesis_ids:
                raise ValidationError(
                    "Signal Mining decisions must cover every supplied comparison"
                )
            unsupported = sorted(
                {item.disposition for item in items} - allowed_dispositions
            )
            if unsupported:
                raise ValidationError(
                    "Signal Mining used unsupported dispositions: "
                    + ", ".join(unsupported)
                )
            for item in items:
                if item.disposition in {"refine", "rejected"} and any(
                    _MINING_EVIDENCE_ABSENCE.search(reason)
                    for reason in item.rationale
                ):
                    raise ValidationError(
                        "Signal Mining evidence absence must use inconclusive, not "
                        + item.disposition
                        + ": "
                        + item.hypothesis_id
                    )
            return tuple(
                item if exploration else replace(item, sample_basis=sample_basis(item))
                for item in items
            )

        value, usage, request_refs = _complete_parsed_role_with_trace(
            self.caller,
            stage=stage,
            system_prompt=prompt + (
                _SIGNAL_MINING_EXPLORATION_DECISIONS_OUTPUT
                if exploration
                else _SIGNAL_MINING_DECISIONS_OUTPUT
            ),
            payload=payload,
            parser=parse,
            allow_outcomes=True,
            anonymous_aliases=(),
            reject_output_aliases=self.identity_guard_aliases,
            max_output_tokens=(8_000 if stage == "signal_mining_contrast" else 4_000),
            temperature=temperature,
            stable_correction_prefix=exploration,
            enforce_scoped_correction=exploration,
            correction_guidance=(
                "For E2, decisions are cross-case portfolio patterns. Per-case "
                "rejections must become decisions=[] with structured no_candidate. "
                "A supported pattern must preserve its candidate intent while fixing "
                "the exact decision row, contrast refs, and spec/skill/tests contract. "
                "When rules.evidence_limited is true, an empty result must use "
                "reason_code=insufficient_evidence."
                if exploration
                else ""
            ),
        )
        return AgentStep(
            value,
            usage,
            metadata={**decision_metadata, "request_refs": request_refs},
        )


def _raise_mining_shape(message: str) -> Any:
    raise ValidationError(message)


@dataclass(frozen=True)
class _SignalProjectionLineage:
    document: RawInfoDocument
    projection_text: str
    raw_offset_runs: tuple[tuple[int, int, int, int], ...]
    normalized_start: int
    normalized_end: int
    normalized_source_length: int


def _slice_projection_offset_runs(
    runs: Iterable[tuple[int, int, int, int]],
    start: int,
    end: int,
    *,
    rebase: int,
) -> tuple[tuple[int, int, int, int], ...]:
    """Clip normalized-to-raw lineage without widening one-to-one runs."""

    clipped: list[tuple[int, int, int, int]] = []
    for run_start, run_end, raw_start, raw_end in runs:
        intersection_start = max(run_start, start)
        intersection_end = min(run_end, end)
        if intersection_start >= intersection_end:
            continue
        if run_end - run_start == raw_end - raw_start:
            clipped_raw_start = raw_start + intersection_start - run_start
            clipped_raw_end = raw_start + intersection_end - run_start
        else:
            # One normalized character may represent an entity, removed markup,
            # or collapsed whitespace. Its complete raw range is indivisible.
            clipped_raw_start = raw_start
            clipped_raw_end = raw_end
        clipped.append(
            (
                intersection_start - rebase,
                intersection_end - rebase,
                clipped_raw_start,
                clipped_raw_end,
            )
        )
    return tuple(clipped)


def _shared_llm_signal_projection(
    inputs: tuple[LLMSignalBatchInput, ...],
) -> tuple[list[dict[str, Any]], dict[str, _SignalProjectionLineage]]:
    """Build one deduplicated readable projection for up to two soft Signals."""

    documents_by_identity: dict[tuple[str, str], RawInfoDocument] = {}
    for item in inputs:
        for document in item.documents:
            documents_by_identity[(document.document_id, document.content_hash)] = document

    candidates: list[
        tuple[
            tuple[Any, ...],
            RawInfoDocument,
            str,
            tuple[tuple[int, int, int, int], ...],
            int,
            int,
        ]
    ] = []
    step = LLM_SIGNAL_CONTEXT_CHUNK_CHARS - LLM_SIGNAL_CONTEXT_CHUNK_OVERLAP
    for document in documents_by_identity.values():
        normalized, runs = _normalized_projection_text(
            document.content,
            strip_market_metadata=document.source_type.casefold()
            in {"market_data", "historical_price", "price_daily", "prices"},
        )
        start = 0
        while start < len(normalized):
            end = min(start + LLM_SIGNAL_CONTEXT_CHUNK_CHARS, len(normalized))
            rank = (-document.available_at.timestamp(), document.document_id, start)
            candidates.append((rank, document, normalized, runs, start, end))
            if end == len(normalized):
                break
            start += step

    payload: list[dict[str, Any]] = []
    lineage: dict[str, _SignalProjectionLineage] = {}
    used = 0
    queues = []
    for item in sorted(inputs, key=lambda item: item.spec.ref):
        terms = {
            token.casefold() for token in re.findall(
                r"[A-Za-z0-9]+",
                item.spec.retrieval_policy.query + " " + " ".join(
                    item.spec.parameters.get("result_required_evidence_phrases", ())
                ),
            ) if len(token) >= 3 and token.casefold() not in _LLM_SIGNAL_QUERY_STOP_WORDS
        }
        eligible = {d.document_id for d in item.documents}

        def rank_candidate(candidate):
            """Rank an eligible chunk using only version-owned search intent."""

            base_rank, _document, normalized, _runs, start, end = candidate
            tokens = re.findall(r"[A-Za-z0-9]+", normalized[start:end].casefold())
            return (
                -len(terms.intersection(tokens)),
                -sum(min(tokens.count(term), 3) for term in terms),
                *base_rank,
            )

        queues.append(sorted(
            (candidate for candidate in candidates if candidate[1].document_id in eligible),
            key=rank_candidate,
        ))
    ordered = []
    selected = set()
    visited_documents = set()
    ordered_chars = 0
    while any(queues) and ordered_chars < MAX_LLM_SIGNAL_CONTEXT_CHARS:
        for queue in queues:
            queue[:] = [
                c for c in queue
                if (c[1].document_id, c[4]) not in selected
                and c[5] - c[4] <= MAX_LLM_SIGNAL_CONTEXT_CHARS - ordered_chars
            ]
            if not queue:
                continue
            index = next(
                (i for i, candidate in enumerate(queue)
                 if candidate[1].document_id not in visited_documents),
                0,
            )
            candidate = queue.pop(index)
            ordered.append(candidate)
            ordered_chars += candidate[5] - candidate[4]
            selected.add((candidate[1].document_id, candidate[4]))
            visited_documents.add(candidate[1].document_id)
    for _rank, document, normalized, runs, start, end in ordered:
        text_value = normalized[start:end]
        if not text_value or used + len(text_value) > MAX_LLM_SIGNAL_CONTEXT_CHARS:
            continue
        projection_id = "projection_" + hashlib.sha256(
            json.dumps(
                [document.document_id, document.content_hash, start, end, text_value],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:24]
        clipped_runs = _slice_projection_offset_runs(
            runs,
            start,
            end,
            rebase=start,
        )
        payload.append(
            {
                "projection_id": projection_id,
                "document_id": document.document_id,
                "content_hash": document.content_hash,
                "source_type": document.source_type,
                "published_at": document.published_at.isoformat(),
                "available_at": document.available_at.isoformat(),
                "exact_text": text_value,
            }
        )
        lineage[projection_id] = _SignalProjectionLineage(
            document=document,
            projection_text=text_value,
            raw_offset_runs=clipped_runs,
            normalized_start=start,
            normalized_end=end,
            normalized_source_length=len(normalized),
        )
        used += len(text_value)
    return payload, lineage


def _bounded_projection_interior_candidate(
    projection: _SignalProjectionLineage,
    *,
    anchor_normalized_offset: int,
    maximum_characters: int = 800,
) -> str | None:
    """Return one complete sentence containing the rejected source boundary."""

    text_value = projection.projection_text
    anchor = anchor_normalized_offset - projection.normalized_start
    if anchor <= 0 or anchor >= len(text_value):
        return None
    sentence_end = re.compile(r'[.!?](?:["\')\]]*)(?=\s|$)')
    lower = 0
    if projection.normalized_start > 0:
        first_end = sentence_end.search(text_value)
        if first_end is None:
            return None
        lower = first_end.end()
        while lower < len(text_value) and text_value[lower].isspace():
            lower += 1

    terminal_ends = [
        match.end()
        for match in sentence_end.finditer(text_value, lower)
        if not (
            projection.normalized_end < projection.normalized_source_length
            and match.end() == len(text_value)
        )
    ]
    if not terminal_ends:
        return None
    candidates: list[str] = []
    sentence_start = lower
    for sentence_end_offset in terminal_ends:
        raw_candidate = text_value[sentence_start:sentence_end_offset]
        leading = len(raw_candidate) - len(raw_candidate.lstrip())
        trailing = len(raw_candidate.rstrip())
        candidate_start = sentence_start + leading
        candidate_end = sentence_start + trailing
        candidate = text_value[candidate_start:candidate_end]
        if (
            candidate
            and candidate_start < anchor < candidate_end
            and len(candidate) <= maximum_characters
            and text_value.count(candidate) == 1
        ):
            candidates.append(candidate)
        sentence_start = sentence_end_offset
        while sentence_start < len(text_value) and text_value[sentence_start].isspace():
            sentence_start += 1
    if len(set(candidates)) != 1:
        return None
    return candidates[0]


def _map_projected_signal_evidence(
    value: Mapping[str, Any],
    lineage: Mapping[str, _SignalProjectionLineage],
    *,
    eligible_projection_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Map unique projected quotes back to canonical original Raw Info spans."""

    eligible_ids = (
        frozenset(lineage)
        if eligible_projection_ids is None
        else frozenset(eligible_projection_ids)
    )
    unknown_ids = eligible_ids - set(lineage)
    if unknown_ids:
        raise ValidationError(
            "Signal eligible_projection_ids contain unknown projections: "
            f"{sorted(unknown_ids)}"
        )
    eligible_lineage = {
        projection_id: projection
        for projection_id, projection in lineage.items()
        if projection_id in eligible_ids
    }
    normalized = json.loads(json.dumps(value))
    evidence = normalized.get("evidence")
    if not isinstance(evidence, Mapping):
        return normalized
    for group in ("supporting", "counter"):
        entries = evidence.get(group, ())
        if not isinstance(entries, list):
            continue
        mapped_entries: list[dict[str, Any]] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                mapped_entries.append(dict(entry) if isinstance(entry, Mapping) else {})
                continue
            if "document_id" in entry and "exact_span" in entry:
                mapped_entries.append(dict(entry))
                continue
            projection_id = entry.get("projection_id")
            exact_text = entry.get("exact_text")
            if not isinstance(projection_id, str) or not isinstance(exact_text, str):
                raise ValidationError("Signal evidence requires projection_id and exact_text")
            if projection_id in lineage and projection_id not in eligible_ids:
                raise ValidationError(
                    f"Signal {group} evidence[{index}] cites projection "
                    f"{projection_id!r} outside this Signal's "
                    f"eligible_projection_ids={sorted(eligible_ids)}"
                )
            projection = eligible_lineage.get(projection_id)
            resolved_projection_id = projection_id
            if not exact_text:
                raise ValidationError(
                    f"Signal {group} evidence[{index}] exact_text must be non-empty"
                )
            if projection is None or projection.projection_text.count(exact_text) != 1:
                matches = [
                    (candidate_id, candidate)
                    for candidate_id, candidate in eligible_lineage.items()
                    if candidate.projection_text.count(exact_text) == 1
                ]
                occurrence_count = sum(
                    candidate.projection_text.count(exact_text)
                    for candidate in eligible_lineage.values()
                )
                if len(matches) != 1 or occurrence_count != 1:
                    supplied_occurrences = (
                        projection.projection_text.count(exact_text)
                        if projection is not None
                        else 0
                    )
                    raise ValidationError(
                        f"Signal {group} evidence[{index}] exact_text does not map "
                        f"uniquely: supplied_projection_id={projection_id!r}, "
                        f"supplied_occurrences={supplied_occurrences}, "
                        f"visible_occurrences={occurrence_count}, "
                        f"matching_projection_ids="
                        f"{sorted(candidate_id for candidate_id, _ in matches)}. "
                        "Copy one case- and punctuation-exact literal from an eligible "
                        "projection or return unavailable"
                    )
                resolved_projection_id, projection = matches[0]
            projection_start = projection.projection_text.index(exact_text)
            projection_end = projection_start + len(exact_text)
            touched_edges: list[str] = []
            if (
                projection_start == 0
                and projection.normalized_start > 0
            ):
                touched_edges.append("start")
            if (
                projection_end == len(projection.projection_text)
                and projection.normalized_end < projection.normalized_source_length
            ):
                touched_edges.append("end")
            if touched_edges:
                overlapping = {
                    candidate_id: candidate
                    for candidate_id, candidate in eligible_lineage.items()
                    if candidate_id != resolved_projection_id
                    and candidate.document.document_id
                    == projection.document.document_id
                    and candidate.document.content_hash
                    == projection.document.content_hash
                    and (
                        (
                            "start" in touched_edges
                            and candidate.normalized_start
                            < projection.normalized_start
                            < candidate.normalized_end
                        )
                        or (
                            "end" in touched_edges
                            and candidate.normalized_start
                            < projection.normalized_end
                            < candidate.normalized_end
                        )
                    )
                }
                overlapping_projection_ids = sorted(overlapping)
                interior_candidates: dict[str, str] = {}
                for candidate_id, candidate in sorted(overlapping.items()):
                    anchored = {
                        interior
                        for edge in touched_edges
                        if (
                            interior := _bounded_projection_interior_candidate(
                                candidate,
                                anchor_normalized_offset=(
                                    projection.normalized_start
                                    if edge == "start"
                                    else projection.normalized_end
                                ),
                            )
                        )
                    }
                    if len(anchored) != 1:
                        continue
                    interior = next(iter(anchored))
                    if (
                        sum(
                            visible.projection_text.count(interior)
                            for visible in eligible_lineage.values()
                        )
                        == 1
                    ):
                        interior_candidates[candidate_id] = interior
                raise ValidationError(
                    f"Signal {group} evidence[{index}] on projection "
                    f"{resolved_projection_id!r} touches internal projection "
                    f"edge={touched_edges}; overlapping_projection_ids="
                    f"{overlapping_projection_ids}; "
                    "overlapping_projection_interior_candidates="
                    f"{json.dumps(interior_candidates, ensure_ascii=False)}. Copy "
                    "one listed byte-exact candidate, another complete literal from "
                    "an overlapping projection, or return unavailable"
                )
            overlaps = _slice_projection_offset_runs(
                projection.raw_offset_runs,
                projection_start,
                projection_end,
                rebase=projection_start,
            )
            if not overlaps:
                raise ValidationError("Signal projection evidence has no raw mapping")
            raw_start = min(item[2] for item in overlaps)
            raw_end = max(item[3] for item in overlaps)
            raw_span = projection.document.content[raw_start:raw_end]
            if not raw_span:
                raise ValidationError("Signal projection mapped to an empty raw span")
            projected_raw_span, _raw_span_runs = _normalized_projection_text(
                raw_span,
                strip_market_metadata=projection.document.source_type.casefold()
                in {"market_data", "historical_price", "price_daily", "prices"},
            )
            if projected_raw_span != exact_text:
                raise ValidationError(
                    f"Signal {group} evidence[{index}] raw mapping did not round-trip "
                    "to exact_text; choose another complete literal or return unavailable"
                )
            mapped_entries.append(
                {
                    "document_id": projection.document.document_id,
                    "exact_span": raw_span,
                    "timestamp": projection.document.available_at.isoformat(),
                }
            )
        evidence[group] = mapped_entries
    normalized["evidence"] = evidence
    return normalized


_LLM_SIGNAL_BATCH_SYSTEM_PROMPT = (
    "Apply each versioned extraction skill independently to the one shared "
    "bounded point-in-time source_projection. Each evidence item inside a nested "
    "result must use projection_id and exact_text copied from one visible "
    "projection; runtime maps it to the original raw span. Each Signal may cite "
    "only projection ids listed in its own eligible_projection_ids, even though "
    "peer Signal projections are visible in the shared batch. Do not cite text "
    "that starts or ends at an internal projection edge; use the overlapping "
    "projection containing the complete clause. Edge validation feedback may give "
    "bounded byte-exact overlapping_projection_interior_candidates; copy one "
    "exactly, choose another complete visible literal, or return unavailable. "
    "Never infer omitted source text "
    "is absent. Return unavailable with no evidence when visible text is "
    "insufficient. If optional validation_feedback is present, this is the only "
    "correction attempt: apply each required_action exactly. The rejected row "
    "remains in the saved initial response and is intentionally not duplicated "
    "here. When no literal citation supports the corrected "
    "conclusion, set state.value and status.coverage to unavailable and keep both "
    "evidence arrays empty."
    + _UNTRUSTED_DATA_INSTRUCTION
    + _SIGNAL_BATCH_RESULT_OUTPUT
)


class StructuredLLMSignalRunner:
    """No-label extraction-skill runner for one Signal and its exact documents."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller
        self.request_token_budget: int | None = None

    def set_request_token_budget(self, value: int) -> None:
        self.request_token_budget = int(value)

    @staticmethod
    def _batch_payload(
        inputs: tuple[LLMSignalBatchInput, ...],
        documents: list[dict[str, Any]],
        lineage: Mapping[str, _SignalProjectionLineage],
        as_of: datetime,
        *,
        budget_trimmed: bool,
    ) -> dict[str, Any]:
        projection_ids_by_ref: dict[str, tuple[str, ...]] = {}
        for item in inputs:
            document_identities = {
                (document.document_id, document.content_hash)
                for document in item.documents
            }
            projection_ids_by_ref[item.spec.ref] = tuple(
                projection_id
                for projection_id, projection in lineage.items()
                if (
                    projection.document.document_id,
                    projection.document.content_hash,
                )
                in document_identities
            )
        return {
            "batch_signal_refs": sorted(item.spec.ref for item in inputs),
            "signals": [
                {
                    "signal_ref": item.spec.ref,
                    "signal_spec": item.spec.to_dict(),
                    "skill": item.skill,
                    "eligible_projection_ids": list(
                        projection_ids_by_ref[item.spec.ref]
                    ),
                }
                for item in inputs
            ],
            "as_of": as_of.isoformat(),
            "source_projection": documents,
            "context_contract": {
                "kind": "bounded_normalized_raw_info_projection",
                "max_source_characters": MAX_LLM_SIGNAL_CONTEXT_CHARS,
                "visible_source_characters": sum(
                    len(item["exact_text"]) for item in documents
                ),
                "budget_trimmed": budget_trimmed,
                "complete_documents_retained_locally": True,
                "omitted_text_may_contain_additional_evidence": True,
                "citation_fields": ["projection_id", "exact_text"],
            },
        }

    def _fit_projection_to_budget(
        self,
        inputs: tuple[LLMSignalBatchInput, ...],
        documents: list[dict[str, Any]],
        lineage: Mapping[str, _SignalProjectionLineage],
        as_of: datetime,
        *,
        request_token_budget: int | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, _SignalProjectionLineage], bool]:
        estimator = getattr(self.caller, "estimate_json_request_tokens", None)
        budget = (
            self.request_token_budget
            if request_token_budget is None
            else request_token_budget
        )
        if budget is None or not callable(estimator):
            return documents, dict(lineage), False

        def payload_for(
            selected_documents: list[dict[str, Any]],
            *,
            trimmed: bool,
        ) -> tuple[dict[str, Any], dict[str, _SignalProjectionLineage]]:
            selected_ids = {
                str(document["projection_id"]) for document in selected_documents
            }
            selected_lineage = {
                projection_id: projection
                for projection_id, projection in lineage.items()
                if projection_id in selected_ids
            }
            payload = self._batch_payload(
                inputs,
                selected_documents,
                selected_lineage,
                as_of,
                budget_trimmed=trimmed,
            )
            return payload, selected_lineage

        full_payload, full_lineage = payload_for(documents, trimmed=False)
        full_reservation = estimator(
            system_prompt=_LLM_SIGNAL_BATCH_SYSTEM_PROMPT,
            payload=full_payload,
            allow_outcomes=False,
            max_output_tokens=4_000,
        )
        if full_reservation <= budget:
            return documents, full_lineage, False

        essential_ids: set[str] = set()
        for item in inputs:
            identities = {
                (document.document_id, document.content_hash)
                for document in item.documents
            }
            for projection_id, projection in lineage.items():
                if (
                    projection.document.document_id,
                    projection.document.content_hash,
                ) in identities:
                    essential_ids.add(projection_id)
                    break
        selected = [
            document
            for document in documents
            if str(document["projection_id"]) in essential_ids
        ]
        minimum_payload, minimum_lineage = payload_for(selected, trimmed=True)
        minimum_reservation = estimator(
            system_prompt=_LLM_SIGNAL_BATCH_SYSTEM_PROMPT,
            payload=minimum_payload,
            allow_outcomes=False,
            max_output_tokens=4_000,
        )
        if minimum_reservation > budget:
            return selected, minimum_lineage, True

        selected_ids = {
            str(document["projection_id"]) for document in selected
        }
        projection_order = {
            str(document["projection_id"]): index
            for index, document in enumerate(documents)
        }
        for document in documents:
            projection_id = str(document["projection_id"])
            if projection_id in selected_ids:
                continue
            trial = [*selected, document]
            trial.sort(
                key=lambda item: projection_order[str(item["projection_id"])]
            )
            trial_payload, _trial_lineage = payload_for(trial, trimmed=True)
            reservation = estimator(
                system_prompt=_LLM_SIGNAL_BATCH_SYSTEM_PROMPT,
                payload=trial_payload,
                allow_outcomes=False,
                max_output_tokens=4_000,
            )
            if reservation <= budget:
                selected = trial
                selected_ids.add(projection_id)
        _payload, selected_lineage = payload_for(selected, trimmed=True)
        return selected, selected_lineage, True

    def execute(
        self,
        spec: SignalSpec,
        documents: tuple[RawInfoDocument, ...],
        skill: str,
        as_of: datetime,
    ) -> tuple[SignalResult, AgentUsage]:
        results, usage = self.execute_many(
            (LLMSignalBatchInput(spec, documents, skill),), as_of
        )
        return results[spec.ref], usage

    def execute_many(
        self,
        inputs: tuple[LLMSignalBatchInput, ...],
        as_of: datetime,
    ) -> tuple[Mapping[str, SignalResult], AgentUsage]:
        if not inputs or len(inputs) > 2:
            raise ValidationError("LLM Signal batch requires one or two inputs")
        if len({item.spec.ref for item in inputs}) != len(inputs):
            raise ValidationError("LLM Signal batch refs must be unique")
        usage = AgentUsage()
        pending = {item.spec.ref: item for item in inputs}
        accepted: dict[str, SignalResult] = {}
        validation_feedback: list[dict[str, Any]] = []
        last_errors: dict[str, str] = {}
        failure_statuses: dict[str, SignalExecutionStatus] = {}

        for attempt in range(2):
            attempt_inputs = tuple(pending.values())
            documents, lineage = _shared_llm_signal_projection(attempt_inputs)
            remaining_budget = (
                self.request_token_budget - usage.tokens
                if self.request_token_budget is not None
                else None
            )
            documents, lineage, budget_trimmed = self._fit_projection_to_budget(
                attempt_inputs,
                documents,
                lineage,
                as_of,
                request_token_budget=remaining_budget,
            )
            payload = self._batch_payload(
                attempt_inputs,
                documents,
                lineage,
                as_of,
                budget_trimmed=budget_trimmed,
            )
            projection_ids_by_ref = {
                str(item["signal_ref"]): tuple(item["eligible_projection_ids"])
                for item in payload["signals"]
            }
            if validation_feedback:
                pending_refs = set(pending)
                payload["validation_feedback"] = [
                    item
                    for item in validation_feedback
                    if item.get("signal_ref") in pending_refs
                ]
            try:
                value, step_usage = _complete_json_with_invalid_value(
                    self.caller,
                    stage=(
                        "llm_signal_batch_execute"
                        if attempt == 0
                        else "llm_signal_batch_execute_correction"
                    ),
                    system_prompt=_LLM_SIGNAL_BATCH_SYSTEM_PROMPT,
                    payload=payload,
                    allow_outcomes=False,
                    max_output_tokens=4_000,
                    max_request_tokens=(
                        self.request_token_budget - usage.tokens
                        if self.request_token_budget is not None
                        else None
                    ),
                )
            except RuntimeBudgetExceeded as exc:
                if attempt == 0:
                    raise RuntimeBudgetExceeded(
                        str(exc), usage=usage + exc.usage
                    ) from exc
                usage = usage + exc.usage
                for signal_ref in pending:
                    failure_statuses[signal_ref] = (
                        SignalExecutionStatus.BUDGET_BLOCKED
                    )
                    last_errors[signal_ref] = (
                        "correction request was not sent because its exact "
                        f"reservation exceeded the remaining budget: {exc}"
                    )
                break
            usage = usage + step_usage
            rows = value.get("results")
            row_by_ref: dict[str, Mapping[str, Any]] = {}
            duplicate_refs: set[str] = set()
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, Mapping) or not isinstance(
                        row.get("signal_ref"), str
                    ) or not isinstance(row.get("result"), Mapping):
                        continue
                    returned_ref = str(row["signal_ref"])
                    if returned_ref in row_by_ref:
                        duplicate_refs.add(returned_ref)
                        continue
                    row_by_ref[returned_ref] = dict(row["result"])
            elif len(pending) == 1 and {
                "signal_id",
                "version",
                "state",
                "interpretation",
                "evidence",
                "status",
            }.issubset(value):
                row_by_ref[next(iter(pending))] = value
            validation_feedback = []
            for signal_ref, item in tuple(pending.items()):
                raw_result = row_by_ref.get(signal_ref)
                try:
                    if signal_ref in duplicate_refs:
                        raise ValidationError(
                            "batch output duplicated requested signal_ref"
                        )
                    if raw_result is None:
                        raise ValidationError("batch output omitted requested signal_ref")
                    if "execution" in raw_result:
                        raise ValidationError(
                            "Signal execution status is runtime-owned and must be omitted"
                        )
                    normalized = _normalize_signal_result_output(raw_result)
                    normalized = _canonicalize_unique_case_only_spans(
                        normalized, item.documents
                    )
                    normalized = _map_projected_signal_evidence(
                        normalized,
                        lineage,
                        eligible_projection_ids=projection_ids_by_ref[signal_ref],
                    )
                    result = _parse_role_output(
                        "llm_signal_batch_execute", normalized, SignalResult.from_dict
                    )
                    validate_signal_result(
                        item.spec, result, item.documents, as_of=as_of
                    )
                except ValidationError as exc:
                    validation_error = str(exc)
                    failure_statuses[signal_ref] = (
                        SignalExecutionStatus.VALIDATION_FAILED
                    )
                    if "identity does not match SignalSpec" in validation_error:
                        validation_error += (
                            "; returned result.signal_id="
                            f"{raw_result.get('signal_id')!r}, result.version="
                            f"{raw_result.get('version')!r}; expected result.signal_id="
                            f"{item.spec.signal_id!r}, result.version={item.spec.version}"
                        )
                    last_errors[signal_ref] = validation_error
                    validation_feedback.append(
                        {
                            "signal_ref": signal_ref,
                            "returned_signal_refs": sorted(row_by_ref),
                            "expected_result_identity": {
                                "signal_id": item.spec.signal_id,
                                "version": item.spec.version,
                            },
                            "validation_error": validation_error,
                            "required_action": (
                                f"Return outer signal_ref exactly {signal_ref!r}; set nested "
                                f"result.signal_id exactly {item.spec.signal_id!r} without "
                                f"a version suffix and result.version exactly {item.spec.version}. "
                                "Ground the corrected result in the smallest set of unique "
                                "quotes required by that Signal's skill, using only its "
                                "unchanged eligible_projection_ids list. Comparisons may use "
                                "multiple current/prior or supporting/counter quotes. Return "
                                "unavailable with empty evidence when visible literals are "
                                "insufficient."
                            ),
                        }
                    )
                    continue
                if (
                    attempt == 0
                    and result.value is SignalValue.UNAVAILABLE
                    and item.spec.retrieval_policy.comparison_requirement is not None
                ):
                    supplement, _supplement_lineage = _shared_llm_signal_projection(
                        (item,)
                    )
                    current_ids = set(projection_ids_by_ref[signal_ref])
                    added_ids = {
                        str(projection["projection_id"])
                        for projection in supplement
                    } - current_ids
                    if added_ids:
                        failure_statuses[signal_ref] = (
                            SignalExecutionStatus.VALIDATION_FAILED
                        )
                        last_errors[signal_ref] = (
                            "visible shared projection omitted additional comparison "
                            "windows available to this Signal"
                        )
                        validation_feedback.append(
                            {
                                "signal_ref": signal_ref,
                                "validation_error": last_errors[signal_ref],
                                "required_action": (
                                    "Re-evaluate only this Signal against the expanded "
                                    "bounded projection. Return unavailable with empty "
                                    "evidence if the required comparison is still absent."
                                ),
                            }
                        )
                        continue
                accepted[signal_ref] = result
                del pending[signal_ref]
            if not pending:
                break

        for signal_ref, item in pending.items():
            status = failure_statuses.get(
                signal_ref, SignalExecutionStatus.VALIDATION_FAILED
            )
            accepted[signal_ref] = signal_execution_failure_result(
                item.spec,
                status=status,
                error_code=(
                    "signal_execution_budget_blocked"
                    if status is SignalExecutionStatus.BUDGET_BLOCKED
                    else "signal_output_validation_exhausted"
                ),
                error_message=last_errors.get(signal_ref, "missing batch result"),
            )
        return accepted, usage


def _canonicalize_unique_case_only_spans(
    value: Mapping[str, Any],
    documents: tuple[RawInfoDocument, ...],
) -> dict[str, Any]:
    """Copy unique case-only citation matches from their exact source document."""

    normalized = json.loads(json.dumps(value))
    evidence = normalized.get("evidence")
    if not isinstance(evidence, Mapping):
        return normalized
    documents_by_id = {item.document_id: item for item in documents}
    for group in ("supporting", "counter"):
        entries = evidence.get(group, ())
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            document = documents_by_id.get(str(entry.get("document_id", "")))
            span = str(entry.get("exact_span", ""))
            if document is None or not span or span in document.content:
                continue
            lowered_content = document.content.lower()
            lowered_span = span.lower()
            if lowered_content.count(lowered_span) != 1:
                continue
            start = lowered_content.index(lowered_span)
            entry["exact_span"] = document.content[start : start + len(span)]
    return normalized
