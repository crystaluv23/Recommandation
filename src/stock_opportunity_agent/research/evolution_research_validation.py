"""Research-state and routing validation for evolution roles."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping
from stock_opportunity_agent.data.resolution import (
    MAX_BASIC_INFO_REQUESTS,
    MAX_DOCUMENTS_PER_REQUEST,
)
from stock_opportunity_agent.models import (
    StructuredValidationError,
    ValidationError,
    ValidationIssue,
)
from stock_opportunity_agent.research.scheme_evolution import (
    ResearchDecision,
    ResearchState,
    ResearchEvidenceRef,
    SignalSelectionDecision,
    _normalized_projection_text,
)
from stock_opportunity_agent.research.evolution_core import _is_forbidden_basic_info_field
from stock_opportunity_agent.signal_library import (
    SignalBatchResult,
    SignalCoverage,
    SignalResult,
    SignalValue,
    signal_result_model_view,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _CLAIM_QUANTITY,
    _RESEARCH_STATE_ARRAY_LIMITS,
    _RESEARCH_STATE_JSON_BYTE_LIMIT,
    _RESEARCH_STATE_TOTAL_ITEM_LIMIT,
    _missing_claim_quantity_details,
    _missing_claim_quantity_groups,
    _normalized_claim_quantities,
    _normalized_claim_quantity_groups,
    _research_state_json_size,
)


def _normalize_information_plan_output(
    value: Mapping[str, Any],
    *,
    plan_id: str,
    parent_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Normalize the observed semantic B/H_* provider shape at the role boundary."""

    if "basic_info_policy" in value:
        normalized = dict(value)
    elif isinstance(value.get("B"), Mapping) and all(
        isinstance(value.get(key), str)
        for key in ("H_init", "H_reflect", "H_analyse")
    ):
        normalized = {
            "basic_info_policy": dict(value["B"]),
            "initial_research_skill": value["H_init"],
            "reflection_skill": value["H_reflect"],
            "analysis_prompt": value["H_analyse"],
        }
    else:
        h_init_value = value.get("H_init")
        h_reflect_value = value.get("H_reflect")
        h_analyse_value = value.get("H_analyse", value.get("H_analyze"))
        if not all(
            isinstance(item, Mapping)
            for item in (h_init_value, h_reflect_value, h_analyse_value)
        ):
            field_types = ", ".join(
                f"{key}={type(item).__name__}"
                for key, item in (
                    ("H_init", h_init_value),
                    ("H_reflect", h_reflect_value),
                    ("H_analyse", h_analyse_value),
                )
            )
            raise ValidationError(
                "information_plan_propose returned incompatible semantic fields: "
                + field_types
            )
        h_init = dict(h_init_value)
        h_reflect = dict(h_reflect_value)
        h_analyse = dict(h_analyse_value)
        policy = h_init.get("basic_info_policy")
        if not isinstance(policy, Mapping):
            basic = value.get("B", {})
            if isinstance(basic, Mapping):
                policy = (
                    dict(basic)
                    if "fields" in basic or "requests" in basic
                    else {"fields": [str(key) for key in basic]}
                )
        normalized = {
            "basic_info_policy": policy,
            "initial_research_skill": h_init.get("initial_research_skill"),
            "reflection_skill": h_reflect.get("reflection_skill"),
            "analysis_prompt": h_analyse.get("analysis_prompt"),
        }
    normalized["plan_id"] = plan_id
    normalized["parent_ids"] = list(parent_ids)
    required_strings = (
        "initial_research_skill",
        "reflection_skill",
        "analysis_prompt",
    )
    if any(
        not isinstance(normalized.get(key), str) or not normalized[key].strip()
        for key in required_strings
    ):
        raise ValidationError(
            "information_plan_propose returned missing or non-string Plan fields"
        )
    if not isinstance(normalized.get("basic_info_policy"), Mapping):
        raise ValidationError(
            "information_plan_propose returned invalid basic_info_policy"
        )
    policy = dict(normalized["basic_info_policy"])
    requests = policy.get("requests")
    if isinstance(requests, list):
        normalized_requests: list[Any] = []
        for request in requests:
            if not isinstance(request, Mapping):
                normalized_requests.append(request)
                continue
            normalized_request = dict(request)
            if (
                isinstance(normalized_request.get("query"), str)
                and not normalized_request["query"].strip()
            ):
                normalized_request.pop("query")
            normalized_requests.append(normalized_request)
        policy["requests"] = normalized_requests
        normalized["basic_info_policy"] = policy
    return normalized


def _validate_raw_information_plan_request_fields(
    value: Mapping[str, Any],
) -> None:
    """Validate the live canonical Plan shape with exact correction coordinates."""

    issues: list[ValidationIssue] = []

    def issue(path: str, message: str, repairs: tuple[str, ...] = ("replace",), *, invalid_container: bool = False) -> None:
        issues.append(ValidationIssue(
            code="plan_output_shape_invalid", message=message,
            paths=(path,), allowed_repairs=repairs,
            repair_context={"invalid_container_paths": [path]} if invalid_container else {},
        ))

    required = {"B", "H_init", "H_reflect", "H_analyse"}
    for name in sorted(required - set(value)):
        issue(name, f"information_plan_propose is missing {name}", ("add",))
    for name in sorted(set(value) - required):
        issue(name, f"information_plan_propose has unexpected field {name}", ("remove",), invalid_container=True)
    for name in ("H_init", "H_reflect", "H_analyse"):
        if name in value and (not isinstance(value[name], str) or not value[name].strip()):
            issue(name, f"information_plan_propose {name} must be a nonempty string", invalid_container=True)
    basic = value.get("B")
    if "B" in value and not isinstance(basic, Mapping):
        issue("B", "information_plan_propose B must be an object", invalid_container=True)
    elif isinstance(basic, Mapping):
        if "requests" not in basic:
            issue("B.requests", "B requires a requests array", ("add",))
        for name in sorted(set(basic) - {"requests"}):
            issue(f"B.{name}", f"B has unexpected field {name}", ("remove",), invalid_container=True)
        requests = basic.get("requests")
        if "requests" in basic and not isinstance(requests, list):
            issue("B.requests", "B.requests must be an array")
        elif isinstance(requests, list):
            if not requests:
                issue("B.requests", "basic info policy requires requests", ("add",))
            if len(requests) > MAX_BASIC_INFO_REQUESTS:
                issue("B.requests", "basic info policy cannot exceed 8 requests", ("remove",))
            required_fields = {"request_id", "description", "source_types", "max_documents"}
            optional_fields = {"lookback_days", "query"}
            seen_ids: set[str] = set()
            for index, request in enumerate(requests):
                prefix = f"B.requests[{index}]"
                if not isinstance(request, Mapping):
                    issue(prefix, f"{prefix} must be a request object", ("replace", "remove"), invalid_container=True)
                    continue
                for name in sorted(required_fields - set(request)):
                    issue(f"{prefix}.{name}", f"{prefix} is missing {name}", ("add",))
                for name in sorted(set(request) - required_fields - optional_fields):
                    issue(f"{prefix}.{name}", f"{prefix} has unexpected field {name}", ("remove",), invalid_container=True)
                for name in ("request_id", "description", "query"):
                    if name in request and (not isinstance(request[name], str) or (name != "query" and not request[name].strip())):
                        issue(f"{prefix}.{name}", f"{prefix}.{name} must be omitted or a non-empty string" if name == "query" else f"{prefix}.{name} must be nonempty text", ("replace", "remove") if name == "query" else ("replace",), invalid_container=True)
                    elif isinstance(request.get(name), str) and _is_forbidden_basic_info_field(request[name]):
                        issues.append(ValidationIssue(
                            code="plan_outcome_data_forbidden",
                            message=f"basic info policy cannot request outcome data: {prefix}.{name}",
                            paths=(f"{prefix}.{name}",),
                            allowed_repairs=("replace", "remove") if name == "query" else ("replace",),
                        ))
                request_id = request.get("request_id")
                if isinstance(request_id, str):
                    if request_id in seen_ids:
                        issue(f"{prefix}.request_id", "basic info policy request ids must be unique")
                    seen_ids.add(request_id)
                sources = request.get("source_types")
                if "source_types" in request and not isinstance(sources, list):
                    issue(f"{prefix}.source_types", "raw info request requires source_types array")
                elif isinstance(sources, list):
                    if not sources:
                        issue(f"{prefix}.source_types", "raw info request requires source_types", ("add",))
                    seen_sources: set[str] = set()
                    for source_index, source in enumerate(sources):
                        path = f"{prefix}.source_types[{source_index}]"
                        if not isinstance(source, str) or not source.strip():
                            issue(path, "raw info request source_types must be nonempty text", invalid_container=True)
                        elif source in seen_sources:
                            issue(path, "raw info request source_types must be unique", ("replace", "remove"))
                        elif _is_forbidden_basic_info_field(source):
                            issues.append(ValidationIssue(
                                code="plan_outcome_data_forbidden",
                                message=f"basic info policy cannot request outcome data: {path}",
                                paths=(path,), allowed_repairs=("replace", "remove"),
                            ))
                        else:
                            seen_sources.add(source)
                for name in ("max_documents", "lookback_days"):
                    if name in request and (type(request[name]) is not int or request[name] < 1 or (name == "max_documents" and request[name] > MAX_DOCUMENTS_PER_REQUEST)):
                        issue(f"{prefix}.{name}", "raw info max_documents must be between 1 and 10" if name == "max_documents" else "raw info lookback_days must be a positive integer", invalid_container=True)
    if issues:
        raise StructuredValidationError(issues)


def _normalize_signal_result_output(value: Mapping[str, Any]) -> dict[str, Any]:
    """Conservatively align DeepSeek's unavailable state and coverage fields."""

    normalized = dict(value)
    state_value = normalized.get("state")
    status_value = normalized.get("status")
    if isinstance(state_value, Mapping) and isinstance(status_value, Mapping):
        state = dict(state_value)
        status = dict(status_value)
        if state.get("value") == "unavailable":
            status["coverage"] = "unavailable"
            normalized["state"] = state
            normalized["status"] = status
    return normalized


def _research_state_capacity(state: ResearchState) -> dict[str, Any]:
    """Expose exact remaining compact-state capacity without repeating evidence."""

    value = state.to_dict()
    field_capacity: dict[str, dict[str, int]] = {}
    current_total = 0
    for field_name, default_limit in _RESEARCH_STATE_ARRAY_LIMITS.items():
        items = value.get(field_name, ())
        current_count = len(items) if isinstance(items, list) else 0
        effective_limit = max(default_limit, current_count)
        current_total += current_count
        field_capacity[field_name] = {
            "current_count": current_count,
            "effective_maximum_count": effective_limit,
            "new_item_capacity": max(0, effective_limit - current_count),
        }
    effective_total_limit = max(_RESEARCH_STATE_TOTAL_ITEM_LIMIT, current_total)
    current_size = _research_state_json_size(value)
    effective_size_limit = max(_RESEARCH_STATE_JSON_BYTE_LIMIT, current_size)
    return {
        "advisory": True,
        "fields": field_capacity,
        "combined": {
            "current_count": current_total,
            "effective_maximum_count": effective_total_limit,
            "new_item_capacity": max(0, effective_total_limit - current_total),
        },
        "canonical_json_bytes": {
            "current_count": current_size,
            "effective_maximum_count": effective_size_limit,
            "new_item_capacity": max(0, effective_size_limit - current_size),
        },
    }


_ANSWER_SIGNATURE_ALIASES = {
    "boost": "raise",
    "boosted": "raise",
    "cut": "lower",
    "decrease": "lower",
    "decreased": "lower",
    "downgrade": "lower",
    "downgraded": "lower",
    "downward": "lower",
    "increase": "raise",
    "increased": "raise",
    "latest": "recent",
    "lift": "raise",
    "lifted": "raise",
    "lowered": "lower",
    "raised": "raise",
    "recently": "recent",
    "reduce": "lower",
    "reduced": "lower",
    "revision": "revise",
    "revised": "revise",
    "upgrade": "raise",
    "upgraded": "raise",
    "upward": "raise",
}


_ANSWER_SIGNATURE_STOP_WORDS = frozenset(
    "a about an and any are as at be been being by company did do does for from "
    "had has have in is it of on or that the their there this to was were what "
    "when where which who with".split()
)


_ANSWER_RESIDUAL_SCOPE_MARKERS = frozenset({"additional", "beyond", "other"})


def _singularize_topic_token(token: str) -> str:
    """Apply the conservative singularization shared by topic matchers."""

    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if (
        len(token) > 4
        and token.endswith("s")
        and not token.endswith(("is", "ss", "us"))
    ):
        return token[:-1]
    return token


def _answer_signature_tokens(value: str) -> tuple[str, ...]:
    """Return ordered conservative concepts for visible-answer matching."""

    tokens: list[str] = []
    for raw in re.findall(r"[a-z0-9]+", value.casefold()):
        if raw in _ANSWER_SIGNATURE_STOP_WORDS:
            continue
        token = _singularize_topic_token(raw)
        token = _ANSWER_SIGNATURE_ALIASES.get(token, token)
        if token == "revise":
            lowered = value.casefold()
            if "upward" in lowered:
                token = "raise"
            elif "downward" in lowered:
                token = "lower"
        tokens.append(token)
    return tuple(tokens)


def _basic_projection_rows(
    basic_info: Mapping[str, Any],
) -> list[tuple[str, str]]:
    """Return the visible Basic projection id/text pairs in payload order."""

    rows: list[tuple[str, str]] = []
    requests = basic_info.get("requests", ())
    if not isinstance(requests, (list, tuple)):
        return rows
    for request in requests:
        if not isinstance(request, Mapping):
            continue
        projections = request.get("projections", ())
        if not isinstance(projections, (list, tuple)):
            continue
        for projection in projections:
            if not isinstance(projection, Mapping):
                continue
            projection_id = projection.get("projection_id")
            exact_text = projection.get("exact_text")
            if isinstance(projection_id, str) and isinstance(exact_text, str):
                rows.append((projection_id, exact_text))
    return rows


def _matching_answer_excerpt(
    text_value: str,
    matched_terms: Iterable[str],
    *,
    max_chars: int = 480,
) -> str:
    """Return a bounded literal window around the first matched answer term."""

    start = 0
    lowered = text_value.casefold()
    offsets = [
        lowered.find(term)
        for term in matched_terms
        if term and lowered.find(term) >= 0
    ]
    if offsets:
        start = max(0, min(offsets) - max_chars // 4)
    end = min(len(text_value), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    return text_value[start:end]


def _raw_initialize_need_issues(
    value: Mapping[str, Any],
    basic_info: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Find only high-confidence already-answered H_init needs."""

    raw_needs = value.get("next_information_needs")
    raw_resolved = value.get("resolved_questions")
    if not isinstance(raw_needs, list):
        return []
    resolved = (
        [item for item in raw_resolved if isinstance(item, str)]
        if isinstance(raw_resolved, list)
        else []
    )
    projection_rows = _basic_projection_rows(basic_info)
    projection_tokens = [
        _answer_signature_tokens(text_value)
        for _projection_id, text_value in projection_rows
    ]
    corpus_frequency: dict[str, int] = {}
    for tokens in projection_tokens:
        for token in set(tokens):
            corpus_frequency[token] = corpus_frequency.get(token, 0) + 1
    corpus_cutoff = max(3, math.ceil(len(projection_rows) * 0.6))
    case_common = {
        token for token, count in corpus_frequency.items() if count >= corpus_cutoff
    }
    bigram_frequency: dict[tuple[str, str], int] = {}
    for tokens in projection_tokens:
        for bigram in {
            tokens[index : index + 2] for index in range(len(tokens) - 1)
        }:
            bigram_frequency[bigram] = bigram_frequency.get(bigram, 0) + 1
    distinctive_bigram_cutoff = max(2, math.ceil(len(projection_rows) * 0.25))
    issues: list[ValidationIssue] = []
    for need_index, need in enumerate(raw_needs):
        if not isinstance(need, str):
            continue
        need_tokens = tuple(
            token
            for token in _answer_signature_tokens(need)
            if token not in case_common
        )
        need_terms = frozenset(need_tokens)
        if len(need_terms) >= 4:
            for (projection_id, projection_text), candidate_tokens in zip(
                projection_rows,
                projection_tokens,
                strict=True,
            ):
                candidate_terms = frozenset(candidate_tokens)
                if (
                    need_terms & _ANSWER_RESIDUAL_SCOPE_MARKERS
                ) - candidate_terms:
                    continue
                matched = need_terms & candidate_terms
                coverage = len(matched) / len(need_terms)
                need_bigrams = {
                    need_tokens[index : index + 2]
                    for index in range(len(need_tokens) - 1)
                }
                candidate_bigrams = {
                    candidate_tokens[index : index + 2]
                    for index in range(len(candidate_tokens) - 1)
                }
                shared_bigrams = sorted(
                    (
                        bigram
                        for bigram in need_bigrams & candidate_bigrams
                        if bigram_frequency.get(bigram, 0)
                        <= distinctive_bigram_cutoff
                    ),
                    key=lambda bigram: (bigram_frequency.get(bigram, 0), bigram),
                )
                if coverage < 0.85 or not shared_bigrams:
                    continue
                excerpt = _matching_answer_excerpt(projection_text, matched)
                issues.append(
                    ValidationIssue(
                        code="visible_answer_need_retained",
                        message=(
                            "research_controller_initialize returned an information "
                            "need already answered by visible Basic Info, "
                            f"invalid_field='next_information_needs[{need_index}]', "
                            f"next_information_needs[{need_index}]={need!r}, "
                            f"matching_projection_id={projection_id!r}, "
                            f"matched_terms={sorted(matched)}, "
                            f"need_term_coverage={coverage:.6f}, "
                            f"shared_phrase={' '.join(shared_bigrams[0])!r}, "
                            f"visible_excerpt={excerpt!r}. Remove this answered need "
                            "or replace it with only genuinely unresolved facets"
                        ),
                        paths=(f"next_information_needs[{need_index}]",),
                        allowed_repairs=("replace", "remove"),
                        dependent_paths=("decision",) if len(raw_needs) == 1 else (),
                    )
                )
                break

        for resolved_index, resolved_question in enumerate(resolved):
            shared = _shared_resolved_need_phrase(need, resolved_question)
            if shared is None:
                continue
            issues.append(ValidationIssue(
                code="resolved_answer_need_retained",
                message=("research_controller_initialize contradicted its own resolved "
                "question with a retained information need, "
                f"invalid_field='next_information_needs[{need_index}]', "
                f"next_information_needs[{need_index}]={need!r}, "
                f"matching_resolved_question_index={resolved_index}, "
                f"matching_resolved_question={resolved_question!r}, "
                f"shared_content_phrase={shared!r}. Remove the "
                "answered need or narrow it to unresolved facets"),
                paths=(f"next_information_needs[{need_index}]",),
                allowed_repairs=("replace", "remove"),
                dependent_paths=("decision",) if len(raw_needs) == 1 else (),
            ))
            break
    return issues


_RUNTIME_EVALUATION_BASELINE_INPUT = re.compile(
    r"(?:\bbaseline\b.{0,48}\b(?:date|price)\b|"
    r"\b(?:date|price)\b.{0,48}\bbaseline\b)",
    re.IGNORECASE,
)


_RUNTIME_EVALUATION_DEFINITION_INPUT = re.compile(
    r"(?:\b(?:terms?|definition)\s+of\s+(?:the\s+)?(?:fixed\s+)?"
    r"(?:six[- ]month\s+)?(?:evaluation\s+)?outcome\b|"
    r"\b(?:six[- ]month\s+)?(?:evaluation|doubling)\s+outcome(?:'s)?"
    r"\s+(?:terms?|definition)\b)",
    re.IGNORECASE,
)


_RUNTIME_EVALUATION_CURRENT_PRICE_INPUT = re.compile(
    r"(?:\b(?:current|prediction[- ]time)\b.{0,48}\b(?:adjusted close(?: price)?|"
    r"closing price|share price|stock price)\b|"
    r"\b(?:adjusted close(?: price)?|closing price|share price|stock price)\b"
    r".{0,48}\b(?:current|prediction[- ]time)\b)",
    re.IGNORECASE,
)


_RUNTIME_EVALUATION_SCALAR_PRICE_LOOKUP = re.compile(
    r"\b(?:what|which)\s+(?:exact\s+)?(?:is|was|were)\b.{0,64}"
    r"\b(?:adjusted close(?: price)?|closing price|share price|stock price)\b|"
    r"\b(?:exact|value|level)\b.{0,32}"
    r"\b(?:adjusted close(?: price)?|closing price|share price|stock price)\b",
    re.IGNORECASE,
)


_RUNTIME_ANCHOR_BASELINE_WORD = re.compile(r"\bbaseline\b", re.IGNORECASE)


_RUNTIME_ANCHOR_DATE_OR_PRICE_WORD = re.compile(
    r"\b(?:date|price)\b", re.IGNORECASE
)


_RUNTIME_ANCHOR_PRICE_NOUN_WORD = re.compile(
    r"\b(?:adjusted close(?: price)?|closing price|share price|stock price)\b",
    re.IGNORECASE,
)


# Bare "with" is excluded: dative requests ("provide me with the baseline
# date") use it to introduce the requested object, so it is ambiguous rather
# than reference evidence. Reference "with" is licensed only as an explicit
# phrase in _RUNTIME_ANCHOR_REFERENCE_PHRASES ("compared with",
# "with respect to").
_RUNTIME_ANCHOR_REFERENCE_PREPOSITIONS = frozenset(
    "from against versus vs using above below beyond near than".split()
)


_RUNTIME_ANCHOR_REFERENCE_PHRASES = frozenset(
    "relative_to compared_to compared_with measured_from offset_from "
    "with_respect_to in_relation_to".split()
)


_RUNTIME_ANCHOR_CURRENT_WORD = re.compile(
    r"\b(?:current|prediction[- ]time)\b", re.IGNORECASE
)


_RUNTIME_ANCHOR_OUTCOME_NOUNS = frozenset(
    "2x double doubled doubles doubling reprice reprices repriced repricing".split()
)


_RUNTIME_ANCHOR_NP_INTERNAL_TOKENS = frozenset(
    "a an the its their this that these those and or as at me us you it "
    "exact current present latest fixed supplied given provided runtime "
    "evaluation prediction time six month adjusted close closing share "
    "stock date dates price prices baseline baselines company issuer "
    "outcome doubling term terms definition s".split()
)


# Temporal-boundary prepositions introduce the anchor as the deadline of a
# disclosure window ("disclosed by the prediction time"), not the requested
# object. They license reference use only when the next external governor is
# an evidence-availability participle, so request operators ("what was the
# share price by the prediction time") still fail closed.
_RUNTIME_ANCHOR_TEMPORAL_BOUNDARY_PREPOSITIONS = frozenset(
    "by before through prior".split()
)


_RUNTIME_ANCHOR_EVIDENCE_AVAILABILITY_WORDS = frozenset(
    "disclosed reported filed announced published available released "
    "provided furnished communicated posted stated said guided "
    "submitted listed recorded "
    # Bare verb forms: issuer-evidence questions ask "did the issuer
    # disclose/publish ... by the prediction time", and the temporal-boundary
    # scan meets the verb, not the participle.
    "disclose publish report file announce provide state submit "
    "record communicate furnish".split()
)


def _anchor_occurrence_reference_use(text: str, anchor_start: int) -> bool:
    """Return whether one anchor mention is clearly used as a supplied reference.

    Classification fails closed. Scanning left from the anchor over
    noun-phrase-internal tokens, the first external word must belong to a
    closed set of reference constructs: a reference preposition or phrase
    ("from the supplied baseline", "compared with the supplied baseline"),
    "of" headed by a fixed-outcome noun ("a doubling of the adjusted
    share price"), or a temporal-boundary preposition ("by", "before",
    "through", "prior to") whose own next external governor is an
    evidence-availability participle ("guidance disclosed by the
    prediction time"), because there the anchor bounds a disclosure
    window instead of naming the requested object. Bare "with" is not
    one of the prepositions: in a dative request ("provide me with the
    baseline date") it introduces the requested object, so the scan
    reaches the request verb and fails closed. Request operators,
    unrecognized governors ("the value of the baseline price", "obtain
    the baseline date"), inverted or passive restatements ("The baseline
    price is what?"), and mentions with no governor at all are not
    reference use, so unknown wording keeps the rejection instead of
    granting permission.
    """

    left = text[:anchor_start].casefold()
    for phrase in _RUNTIME_ANCHOR_REFERENCE_PHRASES:
        left = left.replace(phrase.replace("_", " "), phrase)
    words = re.findall(r"[a-z0-9_']+", left)
    while words:
        word = words.pop()
        if word.endswith("'s"):
            word = word[: -2]
        if (
            word in _RUNTIME_ANCHOR_REFERENCE_PREPOSITIONS
            or word in _RUNTIME_ANCHOR_REFERENCE_PHRASES
        ):
            return True
        if word in _RUNTIME_ANCHOR_TEMPORAL_BOUNDARY_PREPOSITIONS:
            while words:
                boundary_word = words.pop()
                if boundary_word.endswith("'s"):
                    boundary_word = boundary_word[: -2]
                if boundary_word == "to":
                    continue
                if boundary_word not in _RUNTIME_ANCHOR_NP_INTERNAL_TOKENS:
                    return (
                        boundary_word
                        in _RUNTIME_ANCHOR_EVIDENCE_AVAILABILITY_WORDS
                    )
            return False
        if word == "of":
            head = words[-1] if words else ""
            if head.endswith("'s"):
                head = head[: -2]
            return head in _RUNTIME_ANCHOR_OUTCOME_NOUNS
        if word not in _RUNTIME_ANCHOR_NP_INTERNAL_TOKENS:
            return False
    return False


def _runtime_evaluation_input_requested(
    item: str,
    prediction_date_texts: set[str],
) -> bool:
    """Return whether one question fails the closed reference-use test.

    The proximity patterns above nominate candidate anchors; every nominated
    occurrence must then be clearly identified as anchor-as-reference use
    (``_anchor_occurrence_reference_use``) or the question rejects. An
    issuer-evidence question that uses a supplied anchor ("a doubling of
    the adjusted share price from the supplied baseline") passes while a
    direct baseline, date, current-price, definition, or scalar price
    lookup — including unfamiliar request wording — still rejects.
    Underscore-separated spellings are normalized before matching, like the
    temporal checks. Nomination enumerates every anchor-word occurrence
    inside each proximity span, not only the first: a greedy span can
    cover repeated mentions across clauses, and an early reference mention
    never hides a later direct lookup of the same anchor. For the
    current-price trigger the classified anchor is the
    "current"/"prediction-time" word itself, because the paired price
    noun usually belongs to the fixed outcome phrase ("move the adjusted
    share price above the current market level").
    """

    normalized = item.replace("_", " ")
    anchor_positions: list[int] = []
    for match in _RUNTIME_EVALUATION_BASELINE_INPUT.finditer(normalized):
        for word_pattern in (
            _RUNTIME_ANCHOR_BASELINE_WORD,
            _RUNTIME_ANCHOR_DATE_OR_PRICE_WORD,
        ):
            for word in word_pattern.finditer(match.group(0)):
                anchor_positions.append(match.start() + word.start())
    scalar_enabled = prediction_date_texts and any(
        text in normalized for text in prediction_date_texts
    )
    for pattern in (
        _RUNTIME_EVALUATION_CURRENT_PRICE_INPUT,
        _RUNTIME_EVALUATION_DEFINITION_INPUT,
        _RUNTIME_EVALUATION_SCALAR_PRICE_LOOKUP if scalar_enabled else None,
    ):
        if pattern is None:
            continue
        for match in pattern.finditer(normalized):
            if pattern is _RUNTIME_EVALUATION_DEFINITION_INPUT:
                anchor_positions.append(match.start())
                continue
            if pattern is _RUNTIME_EVALUATION_CURRENT_PRICE_INPUT:
                current_words = list(
                    _RUNTIME_ANCHOR_CURRENT_WORD.finditer(match.group(0))
                )
                if current_words:
                    anchor_positions.extend(
                        match.start() + word.start() for word in current_words
                    )
                    continue
            for noun in _RUNTIME_ANCHOR_PRICE_NOUN_WORD.finditer(match.group(0)):
                anchor_positions.append(match.start() + noun.start())
    return any(
        not _anchor_occurrence_reference_use(normalized, position)
        for position in anchor_positions
    )


_FUTURE_OPERATING_EVENT = re.compile(
    r"\b(?:commerciali[sz](?:e|ed|ation)|complet(?:e|ed|ion)|commenc(?:e|ed|ement)|"
    r"launch(?:ed|ing)?|open(?:ed|ing)?|operat(?:e|ed|ing|ion|ional)|"
    r"produc(?:e|ed|ing|tion))\b",
    re.IGNORECASE,
)


_FIXED_PRICE_OUTCOME = re.compile(
    r"\b(?:2x|doubl(?:e|ed|es|ing)|re[- ]?pric(?:e|ed|ing)|share price|stock price)\b",
    re.IGNORECASE,
)


_EXPECTATION_TRANSMISSION = re.compile(
    r"\b(?:approval|bookings?|construction progress|de[- ]?risk(?:ed|ing)?|"
    r"expectation|financing|forecast|guidance|market recognition|milestone|"
    r"pre[- ]opening|pric(?:e|es|ed|ing)[ -]+in|progress toward)\b",
    re.IGNORECASE,
)


_EXPLICIT_CALENDAR_DATE = re.compile(
    r"\b(?P<date>(?:(?P<month>January|February|March|April|May|June|July|"
    r"August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|"
    r"Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)\s+"
    r"(?:(?P<day>\d{1,2})(?:st|nd|rd|th)?[,]?\s+)?(?P<year>20\d{2})|"
    r"(?P<iso>20\d{2}-\d{2}-\d{2})))\b",
    re.IGNORECASE,
)


_FUTURE_SOURCE_CONTENT_INTENT = re.compile(
    r"\b(?:contents?|results?|metrics?|figures?|numbers?|actuals?|guidance|"
    r"outlook|forecast|findings?|outcomes?|performance|revenue|sales|profit|"
    r"margins?|cash[ -]+flow|users?|subscribers?|updates?|milestones?|"
    r"announcements?|approvals?|partnerships?|agreements?)\b|"
    r"\b(?:what|which|how[ -]+much|how[ -]+many)\b.{0,120}"
    r"\b(?:did|does|will|would)\b.{0,80}"
    r"\b(?:provide|show|reveal|contain|report|state|say)\b|"
    r"\b(?:summarize|analyse|analyze)\b.{0,80}\b(?:report|release|filing)\b",
    re.IGNORECASE,
)


_EXPLICIT_AS_OF_BOUND = re.compile(
    r"\b(?:by|as\s+of|through|before|prior\s+to)\s+"
    r"(?P<date>(?:(?P<month>January|February|March|April|May|June|July|"
    r"August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|"
    r"Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)\s+"
    r"(?:(?P<day>\d{1,2})(?:st|nd|rd|th)?[,]?\s+)?(?P<year>20\d{2})|"
    r"(?P<iso>20\d{2}-\d{2}-\d{2})))\b",
    re.IGNORECASE,
)


_SYMBOLIC_AS_OF_BOUND = re.compile(
    r"\b(?:by|as\s+of|through|before|prior\s+to)\s+(?:the\s+)?"
    r"(?:prediction|cutoff|as[- ]of)\s+(?:date|time)\b",
    re.IGNORECASE,
)


_OPEN_ENDED_DATE_WINDOW = re.compile(
    r"\b(?P<operator>after|since|following|subsequent\s+to)\s+"
    r"(?P<date>(?:(?P<month>January|February|March|April|May|June|July|"
    r"August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|"
    r"Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)\s+"
    r"(?:(?P<day>\d{1,2})(?:st|nd|rd|th)?[,]?\s+)?(?P<year>20\d{2})|"
    r"(?P<iso>20\d{2}-\d{2}-\d{2})))\b",
    re.IGNORECASE,
)


_EXPLICIT_QUARTER = re.compile(
    r"\b(?P<quarter>Q[1-4]|first|second|third|fourth)\s+(?:quarter\s+)?"
    r"(?P<year>20\d{2})\b|"
    r"\b(?P<year_first>20\d{2})\s+(?P<quarter_after>Q[1-4]|first|second|"
    r"third|fourth)\s+quarter\b",
    re.IGNORECASE,
)


_RELATIVE_FUTURE_SCOPE = re.compile(
    r"\b(?:post[- ]cutoff|after\s+(?:the\s+)?(?:prediction|cutoff|as[- ]of)\s+"
    r"(?:date|time)|(?:next|following|subsequent)\s+"
    r"(?:month|quarter|half|year|reporting\s+period))\b",
    re.IGNORECASE,
)


_QUESTION_FACT_REQUEST = re.compile(
    r"^\s*(?:what|which|when|where|who|did|does|do|has|have|had|is|are|was|"
    r"were|how\s+(?:many|much)|summari[sz]e|identify|list|report|provide)\b",
    re.IGNORECASE,
)


_HYPOTHETICAL_FUTURE_ANALYSIS = re.compile(
    r"^\s*(?:how|what)\s+(?:could|might|would)\b|"
    r"^\s*(?:could|might|would)\b",
    re.IGNORECASE,
)


_FUTURE_EXPECTATION_OR_SCHEDULE = re.compile(
    r"\b(?:timing|dates?|schedules?|timelines?|milestones?|expected|anticipated|"
    r"projected|projections?|planned|"
    r"upcoming|future|releases?|reports?|guidance|outlook|forecasts?|"
    r"targets?|goals?|openings?|could|might|would|commentary|"
    r"construction\s+plans?)\b",
    re.IGNORECASE,
)


_FUTURE_REALIZED_RESULT = re.compile(
    r"\b(?:results?|actuals?|realized|realised)\b|"
    r"\bhow\s+(?:many|much)\b",
    re.IGNORECASE,
)


def _calendar_match_date(match: re.Match[str], *, month_end: bool) -> date | None:
    """Parse one explicit calendar match without inventing a missing day."""

    iso = match.group("iso")
    if iso is not None:
        try:
            return date.fromisoformat(iso)
        except ValueError:
            return None
    month = str(match.group("month")).casefold().rstrip(".")[:3]
    month_number = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }[month]
    year = int(str(match.group("year")))
    raw_day = match.group("day")
    if raw_day is None:
        if not month_end:
            return date(year, month_number, 1)
        next_month = date(
            year + (month_number == 12),
            1 if month_number == 12 else month_number + 1,
            1,
        )
        return date.fromordinal(next_month.toordinal() - 1)
    try:
        return date(year, month_number, int(raw_day))
    except ValueError:
        return None


def _has_prediction_bounded_as_of_clause(
    text: str,
    prediction_date: date,
) -> bool:
    """Return whether an explicit as-of clause caps facts at the blind cutoff."""

    if _SYMBOLIC_AS_OF_BOUND.search(text):
        return True
    for match in _EXPLICIT_AS_OF_BOUND.finditer(text):
        referenced = _calendar_match_date(match, month_end=True)
        if referenced is not None and referenced <= prediction_date:
            return True
    return False


def _quarter_match_end(match: re.Match[str]) -> date:
    """Return the inclusive calendar-quarter end represented by one match."""

    raw_quarter = str(match.group("quarter") or match.group("quarter_after"))
    quarter = {
        "q1": 1,
        "first": 1,
        "q2": 2,
        "second": 2,
        "q3": 3,
        "third": 3,
        "q4": 4,
        "fourth": 4,
    }[raw_quarter.casefold()]
    year = int(str(match.group("year") or match.group("year_first")))
    month = quarter * 3
    if month == 12:
        return date(year, 12, 31)
    next_month = date(year, month + 1, 1)
    return date.fromordinal(next_month.toordinal() - 1)


def _future_source_date_refs(
    text: str,
    prediction_date: date,
    *,
    field_name: str,
) -> list[str]:
    """Return future or cutoff-open date scopes for requested realized facts."""

    text = text.replace("_", " ")
    fact_request = bool(
        _FUTURE_SOURCE_CONTENT_INTENT.search(text)
        or _QUESTION_FACT_REQUEST.search(text)
    )
    if not fact_request:
        return []
    if (
        field_name == "open_questions"
        and _HYPOTHETICAL_FUTURE_ANALYSIS.search(text)
        and not _FUTURE_SOURCE_CONTENT_INTENT.search(text)
    ):
        return []
    future: list[str] = []
    covered_year_offsets: set[int] = set()
    for match in _EXPLICIT_CALENDAR_DATE.finditer(text):
        referenced = _calendar_match_date(match, month_end=False)
        year_start = match.start("year") if match.group("year") else match.start("iso")
        covered_year_offsets.add(year_start)
        if referenced is not None and referenced > prediction_date and match.group(
            "date"
        ) not in future:
            future.append(match.group("date"))
    for match in _EXPLICIT_QUARTER.finditer(text):
        year_group = "year" if match.group("year") else "year_first"
        covered_year_offsets.add(match.start(year_group))
        if _quarter_match_end(match) > prediction_date:
            quarter_ref = match.group(0)
            if quarter_ref not in future:
                future.append(quarter_ref)
    for match in re.finditer(r"\b20\d{2}\b", text):
        if match.start() in covered_year_offsets:
            continue
        if int(match.group(0)) > prediction_date.year and match.group(0) not in future:
            future.append(match.group(0))
    for match in _OPEN_ENDED_DATE_WINDOW.finditer(text):
        referenced = _calendar_match_date(match, month_end=True)
        if referenced is None or referenced < prediction_date:
            continue
        open_scope = f"{match.group('operator')} {match.group('date')}"
        if open_scope not in future:
            future.append(open_scope)
    relative = _RELATIVE_FUTURE_SCOPE.search(text)
    if relative is not None and relative.group(0) not in future:
        future.append(relative.group(0))
    if not future:
        return []
    if (
        _has_prediction_bounded_as_of_clause(text, prediction_date)
        and _FUTURE_EXPECTATION_OR_SCHEDULE.search(text)
        and not _FUTURE_REALIZED_RESULT.search(text)
    ):
        return []
    return future


def _raw_future_information_issues(
    value: Mapping[str, Any],
    evaluation_context: Mapping[str, Any] | None,
) -> list[ValidationIssue]:
    """Return typed issues for questions that require post-cutoff facts."""

    if not isinstance(evaluation_context, Mapping):
        return []
    try:
        prediction_date = datetime.fromisoformat(
            str(evaluation_context.get("prediction_time")).replace("Z", "+00:00")
        ).date()
    except ValueError:
        return []
    issues: list[ValidationIssue] = []
    for field_name in ("open_questions", "next_information_needs"):
        raw_items = value.get(field_name)
        if not isinstance(raw_items, list):
            continue
        for index, item in enumerate(raw_items):
            if not isinstance(item, str):
                continue
            future_refs = _future_source_date_refs(
                item,
                prediction_date,
                field_name=field_name,
            )
            if not future_refs:
                continue
            path = f"{field_name}[{index}]"
            issues.append(
                ValidationIssue(
                    code="future_information_unavailable",
                    message=(
                        "research_controller requested source contents or realized "
                        "facts beyond prediction_time, "
                        f"invalid_field={path!r}, {path}={item!r}, "
                        "future_source_date_refs="
                        f"{json.dumps(future_refs, separators=(',', ':'))}, "
                        f"prediction_time={prediction_date.isoformat()!r}. Remove "
                        "this item or restate it to request only evidence already "
                        "available by prediction_time. A cutoff-bounded as-of "
                        "question about a disclosed future schedule, expectation, "
                        "or milestone is allowed, but later contents, results, "
                        "announcements, or updates are not"
                    ),
                    paths=(path,),
                    allowed_repairs=("replace", "remove"),
                    repair_context={
                        "prediction_time": prediction_date.isoformat(),
                        "future_source_date_refs": future_refs,
                        "required_temporal_boundary": "available_by_prediction_time",
                    },
                )
            )
    return issues


def _raw_research_evaluation_boundary_issues(
    value: Mapping[str, Any],
    evaluation_context: Mapping[str, Any] | None = None,
) -> list[ValidationIssue]:
    """Reject research state that requests runtime-owned or future facts."""

    issues: list[ValidationIssue] = []
    prediction_date: date | None = None
    if isinstance(evaluation_context, Mapping):
        raw_prediction_time = evaluation_context.get("prediction_time")
        try:
            prediction_date = datetime.fromisoformat(
                str(raw_prediction_time).replace("Z", "+00:00")
            ).date()
        except ValueError:
            pass
    prediction_date_texts = (
        {
            prediction_date.isoformat(),
            f"{prediction_date.strftime('%B')} {prediction_date.day}, "
            f"{prediction_date.year}",
        }
        if prediction_date is not None
        else set()
    )
    for field_name in ("open_questions", "next_information_needs"):
        raw_items = value.get(field_name)
        if not isinstance(raw_items, list):
            continue
        for index, item in enumerate(raw_items):
            if not isinstance(item, str):
                continue
            runtime_owned = _runtime_evaluation_input_requested(
                item,
                prediction_date_texts,
            )
            if not runtime_owned:
                continue
            path = f"{field_name}[{index}]"
            issues.append(
                ValidationIssue(
                    code="runtime_evaluation_input_requested",
                    message=(
                        "research_controller_initialize asked for a runtime-owned "
                        "evaluation input rather than issuer evidence, "
                        f"invalid_field={path!r}, {path}={item!r}. Remove this "
                        "item; do not answer, source, or rewrite the fixed "
                        "baseline/definition"
                    ),
                    paths=(path,),
                    allowed_repairs=("remove",),
                    dependent_paths=("decision",) if (
                        field_name == "next_information_needs" and len(raw_items) == 1
                    ) else (),
                    repair_context={"dependency_allowed_repairs": {"decision": ["replace"]}},
                )
            )
    if not isinstance(evaluation_context, Mapping):
        return issues
    raw_horizon_end = evaluation_context.get("horizon_end")
    try:
        horizon_end = date.fromisoformat(str(raw_horizon_end))
    except ValueError:
        return issues
    raw_hypotheses = value.get("hypotheses")
    if not isinstance(raw_hypotheses, list):
        return issues
    for index, item in enumerate(raw_hypotheses):
        if not isinstance(item, str):
            continue
        future_years = sorted(
            {
                int(year)
                for year in re.findall(r"\b20\d{2}\b", item)
                if int(year) > horizon_end.year
            }
        )
        if not future_years or not (
            _FUTURE_OPERATING_EVENT.search(item)
            and _FIXED_PRICE_OUTCOME.search(item)
        ):
            continue
        if _EXPECTATION_TRANSMISSION.search(item):
            continue
        path = f"hypotheses[{index}]"
        issues.append(ValidationIssue(
            code="outside_horizon_event_causality",
            message=("research_controller_initialize directly conditioned the fixed "
            "six-month price outcome on an operating event outside the horizon, "
            f"invalid_field={path!r}, {path}={item!r}, "
            f"future_event_years={future_years}, horizon_end={horizon_end.isoformat()!r}. "
            "Reframe the hypothesis around within-horizon expectation evidence or "
            "a de-risking milestone. Do not assume the later event has occurred"),
            paths=(path,), allowed_repairs=("replace", "remove"),
        ))
    return issues


def _raw_research_state_compaction_issues(
    value: Mapping[str, Any],
    *,
    previous_state: ResearchState | None = None,
    initialize: bool = False,
    basic_info: Mapping[str, Any] | None = None,
    evaluation_context: Mapping[str, Any] | None = None,
) -> list[ValidationIssue]:
    """Validate research questions independently of advisory summary targets."""

    issues: list[ValidationIssue] = []
    if initialize:
        issues.extend(_raw_initialize_need_issues(value, basic_info or {}))
    if initialize or evaluation_context is not None:
        issues.extend(
            _raw_research_evaluation_boundary_issues(
                value,
                evaluation_context,
            )
        )
    return issues


def _prediction_date_from_context(
    evaluation_context: Mapping[str, Any] | None,
) -> date | None:
    """Return the runtime-owned blind cutoff date when supplied."""

    if not isinstance(evaluation_context, Mapping):
        return None
    try:
        return datetime.fromisoformat(
            str(evaluation_context.get("prediction_time")).replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None


def _need_as_of_bound_clause(
    need: str,
    prediction_date: date | None = None,
) -> tuple[str, date] | None:
    """Return one explicit as-of clause bounding an information need.

    Without a prediction date the earliest explicit bound wins, so routing can
    anchor a residual to the tightest scope its target need declares. With a
    prediction date the latest bound at or before that date wins, so a restored
    residual keeps the widest legitimate inherited scope.
    """

    best: tuple[str, date] | None = None
    for match in _EXPLICIT_AS_OF_BOUND.finditer(need):
        referenced = _calendar_match_date(match, month_end=True)
        if referenced is None:
            continue
        if prediction_date is not None and referenced > prediction_date:
            continue
        if best is None or (
            referenced < best[1] if prediction_date is None else referenced >= best[1]
        ):
            best = (match.group(0), referenced)
    return best


_INHERITABLE_EXPECTATION_CONTEXT = re.compile(
    r"\b(?:guidance|outlook|forecasts?|targets?|goals?|schedules?|timelines?"
    r"|milestones?|dates?|timing|releases?|reports?|openings?|commentary"
    r"|construction\s+plans?|projections?)\b",
    re.IGNORECASE,
)


def _bounded_residual_need(
    residual_need: str | None,
    prior_need: str,
    prediction_date: date | None,
) -> str | None:
    """Return the exact residual representation the temporal guard accepts.

    A literal residual that already respects the prediction-time boundary is
    returned unchanged. A residual that dropped the parent need's cutoff is
    returned with the inherited as-of clause restored; when the parent need is
    itself accepted by the same prediction-time guard (not merely a keyword
    plus a cutoff clause), a clause-only restore that still flags additionally
    inherits the parent's noun-form expectation/schedule marker as explicit
    parent-owned framing, because the as-of bounded allowance requires both
    the cutoff clause and that framing. Returns None only when no bounded
    restatement of the literal residual exists, in which case callers must
    not demand the literal as an exact replacement.
    """

    if not isinstance(residual_need, str) or not residual_need.strip():
        return None
    if prediction_date is None:
        return residual_need
    if not _future_source_date_refs(
        residual_need, prediction_date, field_name="next_information_needs"
    ):
        return residual_need
    bound = _need_as_of_bound_clause(prior_need, prediction_date)
    clause = bound[0] if bound is not None else None
    if clause is None:
        symbolic = _SYMBOLIC_AS_OF_BOUND.search(prior_need)
        clause = symbolic.group(0) if symbolic is not None else None
    if clause is None:
        return None
    stripped = residual_need.rstrip()
    if not stripped:
        return None
    terminator = stripped[-1] if stripped[-1] in ".?!" else ""
    base = stripped[:-1] if terminator else stripped
    restored = f"{base}, {clause}{terminator or '.'}"
    if not _future_source_date_refs(
        restored, prediction_date, field_name="next_information_needs"
    ):
        return restored
    if _future_source_date_refs(
        prior_need, prediction_date, field_name="next_information_needs"
    ):
        return None
    expectation = _INHERITABLE_EXPECTATION_CONTEXT.search(prior_need)
    if expectation is None:
        return None
    inherited = (
        f"{base}, {clause}, within the parent need's "
        f"{expectation.group(0)}{terminator or '.'}"
    )
    if _future_source_date_refs(
        inherited, prediction_date, field_name="next_information_needs"
    ):
        return None
    return inherited


def _reject_unrepresentable_partial_selections(
    selections: tuple[SignalSelectionDecision, ...],
    information_needs: tuple[str, ...],
    evaluation_context: Mapping[str, Any] | None,
) -> None:
    """Fail closed on a legacy partial residual no bounded prompt can carry.

    A partial-answer residual that requests realized facts beyond the runtime
    prediction boundary cannot appear in a reflection prompt without either
    demanding a literal the temporal guard must reject or licensing deletion of
    unresolved demand. Reject such routing state before any prompt exists.
    Without a runtime evaluation context there is no boundary to enforce, so
    the check is a no-op there.
    """

    prediction_date = _prediction_date_from_context(evaluation_context)
    if prediction_date is None:
        return
    for selection in selections:
        if (
            selection.reason_code != "answer_need"
            or selection.answer_scope != "partial"
            or len(selection.target_need_indices) != 1
            or not 0 <= selection.target_need_indices[0] < len(information_needs)
        ):
            continue
        target_need = information_needs[selection.target_need_indices[0]]
        if (
            _bounded_residual_need(
                selection.residual_need, target_need, prediction_date,
            )
            is None
        ):
            raise ValidationError(
                "reflection received a legacy partial-answer selection whose "
                f"residual_need={selection.residual_need!r} for signal_ref="
                f"{selection.signal_ref!r} cannot be represented within the "
                f"prediction-time boundary {prediction_date.isoformat()} of "
                f"targeted need {target_need!r}. Reject or re-run routing so "
                "the residual requests only facts available by "
                "prediction_time; runtime will not delete the unresolved "
                "demand or fabricate a cutoff for realized future facts"
            )


def _restore_inherited_need_cutoffs(
    value: dict[str, Any], previous_state: ResearchState | None,
    evaluation_context: Mapping[str, Any] | None,
) -> None:
    """Bound one literal residual that dropped its inherited cutoff."""

    if previous_state is None or not isinstance(evaluation_context, Mapping):
        return
    cutoff = _prediction_date_from_context(evaluation_context)
    if cutoff is None:
        return

    def words(text: str) -> str:
        return " " + " ".join(
            token for token in re.findall(r"[a-z0-9]+", text.casefold())
            if token != "any"
        ) + " "

    for field in ("open_questions", "next_information_needs"):
        items = value.get(field)
        if not isinstance(items, list):
            continue
        restored = list(items)
        for index, item in enumerate(items):
            if not isinstance(item, str) or not _future_source_date_refs(
                item, cutoff, field_name=field
            ):
                continue
            if _FUTURE_REALIZED_RESULT.search(item):
                continue
            topic = re.sub(
                r"\s+(?:remain(?:s)?|is|are)\s+unresolved[.?!]?\s*$", "", item,
                flags=re.IGNORECASE,
            )
            matches = [
                need for need in getattr(previous_state, field)
                if _has_prediction_bounded_as_of_clause(need, cutoff)
                and not _future_source_date_refs(need, cutoff, field_name=field)
                and words(topic).strip() and words(topic) in words(need)
            ]
            if len(matches) == 1:
                bounded = _bounded_residual_need(item, matches[0], cutoff)
                restored[index] = (
                    bounded if bounded is not None else matches[0]
                )
        value[field] = restored


def _raw_research_state_shape_issues(value: Mapping[str, Any]) -> list[ValidationIssue]:
    """Give malformed role fields exact repair scope before domain construction."""

    collections = (
        "hypotheses", "current_beliefs", "supporting_evidence", "contradictions",
        "resolved_questions", "open_questions", "next_information_needs",
    )
    issues: list[ValidationIssue] = []
    for field in (*collections, "decision"):
        if field not in value:
            issues.append(ValidationIssue(
                code="research_state_field_missing", message=f"ResearchState is missing field {field}",
                paths=(field,), allowed_repairs=("add",),
            ))
        elif field == "decision":
            if value[field] not in ("continue", "finalize"):
                issues.append(ValidationIssue(
                    code="research_state_decision_invalid",
                    message="ResearchState decision must be continue or finalize",
                    paths=(field,), allowed_repairs=("replace",),
                    repair_context={"invalid_container_paths": [field]},
                ))
        elif not isinstance(value[field], list):
            issues.append(ValidationIssue(
                code="research_state_collection_invalid", message=f"ResearchState {field} must be an array",
                paths=(field,), allowed_repairs=("replace",),
            ))
        elif field != "supporting_evidence":
            for index, item in enumerate(value[field]):
                if not isinstance(item, str) or not item.strip():
                    issues.append(ValidationIssue(
                        code="research_state_text_invalid",
                        message=f"ResearchState {field}[{index}] must be nonempty text",
                        paths=(f"{field}[{index}]",), allowed_repairs=("replace", "remove"),
                        repair_context={"invalid_container_paths": [f"{field}[{index}]"]},
                        dependent_paths=("decision",) if field == "next_information_needs" else (),
                    ))
    if value.get("decision") == "continue" and value.get("next_information_needs") == []:
        issues.append(ValidationIssue(
            code="continuing_research_needs_missing",
            message="continuing research requires next information needs; finalize or add one unresolved issuer need",
            paths=("decision", "next_information_needs"), path_policy="any",
            allowed_repairs=("replace", "add"),
        ))
    return issues


_ANCHOR_STATE_TEXT_FIELDS = (
    "current_beliefs",
    "contradictions",
    "resolved_questions",
    "open_questions",
)


def _anchor_restatement_issues(
    normalized: Mapping[str, Any],
    evaluation_context: Mapping[str, Any] | None,
) -> list[ValidationIssue]:
    """Reject numeric restatements of the runtime evaluation anchor.

    The anchor block is deterministic computation: a research state that
    mentions a baseline or threshold price with a different number — or
    derives a doubling threshold from the wrong base — carries an arithmetic
    error into the decision input. The same pattern family as the predictor
    check runs here, before prediction, on every authored state text field.
    """

    if not isinstance(evaluation_context, Mapping):
        return []
    anchor = evaluation_context.get("evaluation_anchor")
    if not isinstance(anchor, Mapping) or anchor.get("status") != "available":
        return []
    expected = anchor.get("mean_adjusted_close")
    if isinstance(expected, bool) or not isinstance(expected, (int, float)):
        return []
    from stock_opportunity_agent.research.evolution_output_validation import (
        _PREDICTOR_BASELINE_MULTIPLE_PREFIX,
        _PREDICTOR_CURRENT_PRICE,
    )

    issues: list[ValidationIssue] = []
    rows: list[tuple[str, str]] = []
    for field_name in _ANCHOR_STATE_TEXT_FIELDS:
        values = normalized.get(field_name)
        if isinstance(values, list):
            rows.extend(
                (f"{field_name}[{index}]", str(text))
                for index, text in enumerate(values)
                if isinstance(text, str)
            )
    evidence = normalized.get("supporting_evidence")
    if isinstance(evidence, list):
        for index, item in enumerate(evidence):
            if isinstance(item, Mapping) and isinstance(item.get("claim"), str):
                rows.append(
                    (f"supporting_evidence[{index}].claim", str(item["claim"]))
                )
    for path, text in rows:
        for match in _PREDICTOR_CURRENT_PRICE.finditer(text):
            returned = float(match.group(1))
            if math.isclose(
                returned, float(expected), rel_tol=0.01, abs_tol=0.05
            ):
                continue
            prefix = text[max(0, match.start() - 32) : match.start()]
            multiple_match = _PREDICTOR_BASELINE_MULTIPLE_PREFIX.search(prefix)
            if multiple_match is not None:
                multiple = (
                    float(multiple_match.group("numeric"))
                    if multiple_match.group("numeric") is not None
                    else 2.0
                )
                derived_threshold = multiple * float(expected)
                if math.isclose(
                    returned, derived_threshold, rel_tol=0.01, abs_tol=0.1
                ):
                    continue
                issues.append(
                    ValidationIssue(
                        code="research_state_anchor_arithmetic_invalid",
                        message=(
                            f"{path} gives {returned:g} for a {multiple:g}x "
                            "baseline threshold, but the runtime evaluation "
                            f"anchor implies {derived_threshold:g}"
                        ),
                        paths=(path,),
                        source_refs=("evaluation_anchor",),
                        allowed_repairs=("replace", "remove"),
                        repair_context={
                            "anchor_derived_threshold": derived_threshold,
                        },
                    )
                )
                continue
            issues.append(
                ValidationIssue(
                    code="research_state_anchor_value_invalid",
                    message=(
                        f"{path} labels {returned:g} as the current or "
                        "prediction-time baseline price, but the runtime "
                        "evaluation anchor mean is "
                        f"{float(expected):g}"
                    ),
                    paths=(path,),
                    source_refs=("evaluation_anchor",),
                    allowed_repairs=("replace", "remove"),
                    repair_context={"anchor_mean": float(expected)},
                )
            )
    return issues


def _normalize_research_state_output(
    value: Mapping[str, Any],
    *,
    previous_state: ResearchState | None = None,
    initialize: bool = False,
    basic_info: Mapping[str, Any] | None = None,
    evaluation_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate tagged-ref shapes and drop only allowed legacy Signal fields."""

    normalized = dict(value)
    shape_issues = _raw_research_state_shape_issues(normalized)
    if shape_issues:
        raise StructuredValidationError(shape_issues)
    anchor_issues = _anchor_restatement_issues(normalized, evaluation_context)
    _restore_inherited_need_cutoffs(normalized, previous_state, evaluation_context)
    future_information_issues = _raw_future_information_issues(
        normalized,
        evaluation_context,
    )
    if future_information_issues or anchor_issues:
        # A temporal rejection still surfaces every other independently
        # decidable raw issue when the evidence shape allows, so one
        # correction round can carry all actionable obligations. The
        # temporal issues stay first and nothing here accepts a future fact.
        evidence_for_aggregation = normalized.get("supporting_evidence")
        if isinstance(evidence_for_aggregation, list) and all(
            isinstance(item, Mapping) for item in evidence_for_aggregation
        ):
            future_information_issues.extend(
                _raw_basic_claim_quantity_issues(normalized)
            )
            future_information_issues.extend(
                _raw_quantitative_assertion_link_issues(normalized)
            )
            future_information_issues.extend(
                _raw_basic_literal_identity_issues(normalized, previous_state)
            )
        future_information_issues.extend(anchor_issues)
        raise StructuredValidationError(future_information_issues)
    evidence = normalized.get("supporting_evidence")
    issues = _raw_research_state_compaction_issues(
        normalized,
        previous_state=previous_state,
        initialize=initialize,
        basic_info=basic_info,
        evaluation_context=evaluation_context,
    )
    structured_preissues = list(issues)
    issues = []
    if not isinstance(evidence, list):
        if structured_preissues:
            raise StructuredValidationError(structured_preissues)
        return normalized
    basic_fields = {"kind", "claim", "projection_id", "exact_text"}
    signal_fields = {
        "kind",
        "claim",
        "signal_ref",
        "evidence_group",
        "evidence_index",
    }
    allowed_signal_legacy_fields = {"projection_id", "exact_text"}
    normalized_evidence: list[Any] = []
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            issues.append(ValidationIssue(
                code="evidence_shape_invalid",
                message=f"supporting_evidence[{index}] must be one tagged-ref JSON object",
                paths=(f"supporting_evidence[{index}]",), allowed_repairs=("replace", "remove"),
                repair_context={"invalid_container_paths": [f"supporting_evidence[{index}]"]},
            ))
            continue
        fields = set(item)
        kind = item.get("kind")
        if kind == "basic_info":
            missing = sorted(basic_fields - fields)
            unexpected = sorted(fields - basic_fields)
            non_string = sorted(
                name
                for name in basic_fields & fields
                if not isinstance(item.get(name), str)
            )
            if missing or unexpected or non_string:
                issues.append(ValidationIssue(
                    code="evidence_shape_invalid",
                    message=(f"supporting_evidence[{index}] basic_info shape is invalid: "
                    f"missing_fields={missing}, unexpected_fields={unexpected}, "
                    f"non_string_fields={non_string}, expected_fields="
                    f"{sorted(basic_fields)}. Copy projection_id and exact_text "
                    "byte-for-byte from one indexed "
                    "research_state.supporting_evidence Basic ref, restate only "
                    "claim, or remove this evidence item"),
                    paths=(f"supporting_evidence[{index}]",), allowed_repairs=("replace", "remove"),
                ))
            else:
                for name in ("projection_id", "exact_text"):
                    if not item[name].strip():
                        issues.append(ValidationIssue(
                            code="evidence_fields_invalid",
                            message=f"supporting_evidence[{index}].{name} must be nonempty text",
                            paths=(f"supporting_evidence[{index}].{name}",),
                            allowed_repairs=("replace", "remove"),
                            repair_context={"authorized_member_removals": [f"supporting_evidence[{index}]"]},
                        ))
                normalized_evidence.append(dict(item))
            continue
        if kind == "signal":
            missing = sorted(signal_fields - fields)
            unexpected = sorted(
                fields - signal_fields - allowed_signal_legacy_fields
            )
            non_string = sorted(
                name
                for name in {"kind", "claim", "signal_ref", "evidence_group"}
                & fields
                if not isinstance(item.get(name), str)
            )
            if missing or unexpected or non_string:
                issues.append(ValidationIssue(
                    code="evidence_shape_invalid",
                    message=(f"supporting_evidence[{index}] signal shape is invalid: "
                    f"missing_fields={missing}, unexpected_fields={unexpected}, "
                    f"non_string_fields={non_string}, expected_fields="
                    f"{sorted(signal_fields)}. Use one exact tuple from "
                    "signal_evidence_ref_catalog or remove this evidence item"),
                    paths=(f"supporting_evidence[{index}]",), allowed_repairs=("replace", "remove"),
                ))
            else:
                shaped = {key: item[key] for key in signal_fields}
                invalid_fields = [
                    name for name, valid in (
                        ("signal_ref", bool(shaped["signal_ref"].strip())),
                        ("evidence_group", shaped["evidence_group"] in {"supporting", "counter"}),
                        ("evidence_index", type(shaped["evidence_index"]) is int and shaped["evidence_index"] >= 0),
                    ) if not valid
                ]
                if invalid_fields:
                    issues.append(ValidationIssue(
                        code="evidence_fields_invalid",
                        message=f"supporting_evidence[{index}] signal evidence reference fields are invalid: {invalid_fields}",
                        paths=tuple(f"supporting_evidence[{index}].{name}" for name in invalid_fields),
                        allowed_repairs=("replace", "remove"),
                        repair_context={"authorized_member_removals": [f"supporting_evidence[{index}]"]},
                    ))
                normalized_evidence.append(shaped)
            continue
        kind_only = fields | {"kind"} in (basic_fields, signal_fields)
        issues.append(ValidationIssue(
            code="evidence_kind_invalid",
            message=(f"supporting_evidence[{index}] has unknown kind {kind!r}, "
                     "expected 'basic_info' or 'signal'"),
            paths=(f"supporting_evidence[{index}]" + (".kind" if kind_only else ""),),
            allowed_repairs=("add", "remove") if kind_only and "kind" not in fields else ("replace", "remove"),
            repair_context={"authorized_member_removals": [f"supporting_evidence[{index}]"]},
        ))
    issues.extend(_raw_research_evidence_claim_length_issues(normalized))
    if issues:
        raise StructuredValidationError([*issues, *structured_preissues])
    typed_issues = list(structured_preissues)
    typed_issues.extend(_raw_basic_claim_quantity_issues(normalized))
    typed_issues.extend(_raw_quantitative_assertion_link_issues(normalized))
    typed_issues.extend(_raw_basic_literal_identity_issues(normalized, previous_state))
    if typed_issues:
        raise StructuredValidationError(typed_issues)
    normalized["supporting_evidence"] = normalized_evidence
    return normalized


def _raw_research_evidence_claim_length_issues(
    value: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Identify empty claims and their linked assertions before construction."""

    evidence = value.get("supporting_evidence")
    if not isinstance(evidence, list):
        return []
    issues: list[ValidationIssue] = []
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            continue
        claim = item.get("claim")
        if not isinstance(claim, str) or claim.strip():
            continue
        linked = [
            f"{field_name}[{assertion_index}]"
            for field_name in ("current_beliefs", "contradictions")
            if isinstance(value.get(field_name), list)
            for assertion_index, assertion in enumerate(value[field_name])
            if assertion == claim
        ]
        linked_instruction = (
            f". linked_assertions={linked} must copy the corrected claim "
            "byte-for-byte or be removed"
            if linked
            else ""
        )
        issues.append(ValidationIssue(
            code="evidence_claim_empty",
            message=(f"supporting_evidence[{index}].claim length={len(claim)} "
            "must be nonempty text. Supply a grounded claim while retaining "
            "its provenance, or remove this evidence item"
            + linked_instruction),
            paths=(f"supporting_evidence[{index}].claim",),
            dependent_paths=tuple(linked), allowed_repairs=("replace", "remove"),
            repair_context={"authorized_member_removals": [f"supporting_evidence[{index}]"]},
        ))
    return issues


def _basic_quantity_elsewhere_hints(
    missing_literals: list[str],
    evidence_items: list[tuple[int, str, str]],
) -> tuple[dict[str, list[str]], bool]:
    """Point at other evidence items that contain a missing quantity literal.

    Scans only the model's own output items (deterministic, no external
    context). Returns the hint map and whether every missing literal was
    located somewhere in the output at all.
    """

    hints: dict[str, list[str]] = {}
    located: set[str] = set()
    for literal in missing_literals:
        locations: list[str] = []
        normalized = _normalized_claim_quantities(literal)
        for index, exact_text, claim_preview in evidence_items:
            if normalized & _normalized_claim_quantities(exact_text):
                locations.append(
                    f"evidence_item[{index}] ({claim_preview[:60]}...)"
                )
                located.add(literal)
        if locations:
            hints[literal] = locations
    return hints, len(missing_literals) > 0 and located == set(missing_literals)


def _raw_basic_claim_quantity_issues(
    value: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Preflight decidable Basic quantity errors before tagged refs exist."""

    evidence = value.get("supporting_evidence")
    if not isinstance(evidence, list):
        return []
    grouped: dict[str, list[tuple[int, str]]] = {}
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping) or "signal_ref" in item:
            continue
        claim = item.get("claim")
        exact_text = item.get("exact_text")
        projection_id = item.get("projection_id")
        if not all(isinstance(value, str) for value in (claim, exact_text, projection_id)):
            continue
        grouped.setdefault(str(claim), []).append((index, str(exact_text)))
    issues: list[ValidationIssue] = []
    for claim, items in grouped.items():
        cited_quantities: set[str] = set()
        for _index, exact_text in items:
            cited_quantities.update(_normalized_claim_quantities(exact_text))
        missing = _missing_claim_quantity_groups(claim, cited_quantities)
        if missing:
            missing_groups_with_literals = [
                (
                    "|".join(sorted(group, key=lambda value: (len(value), value))),
                    match.group(0).rstrip(","),
                )
                for match, group in zip(
                    _CLAIM_QUANTITY.finditer(claim),
                    _normalized_claim_quantity_groups(claim),
                    strict=True,
                )
                if group.isdisjoint(cited_quantities)
            ]
            missing_literals = [
                literal for _group, literal in missing_groups_with_literals
            ]
            elsewhere_hints, all_located = _basic_quantity_elsewhere_hints(
                missing_literals,
                [
                    (
                        item_index,
                        str(item.get("exact_text", "")),
                        str(item.get("claim", "")),
                    )
                    for item_index, item in enumerate(evidence)
                    if isinstance(item, Mapping)
                ],
            )
            elsewhere_instruction = (
                " The missing literals already appear in your own other "
                "evidence items at "
                + json.dumps(elsewhere_hints, separators=(",", ":"))
                + ": cite those ref tuples under the same claim or split the "
                "claim, copying the literal byte-for-byte without rounding or "
                "conversion"
                if elsewhere_hints
                else (
                    " The missing literals appear in NO supplied Basic "
                    "exact_text: computing, estimating, or converting them is "
                    "invalid - narrow the claim to the cited literals or "
                    "remove the quantity"
                )
            )
            evidence_paths = [
                f"supporting_evidence[{index}].claim" for index, _text in items
            ]
            linked = [
                f"{field_name}[{index}]"
                for field_name in ("current_beliefs", "contradictions")
                if isinstance(value.get(field_name), list)
                for index, item in enumerate(value[field_name])
                if item == claim and _normalized_claim_quantity_groups(str(item))
            ]
            issues.append(
                ValidationIssue(
                    code="claim_quantity_not_supported",
                    message=(
                        f"supporting_evidence[{items[0][0]}] claim contains numeric "
                        "quantities absent from all Basic exact_text refs with the "
                        "same claim, missing_quantity_groups="
                        f"{json.dumps(missing, separators=(',', ':'))}, "
                        "missing_quantity_literals="
                        f"{json.dumps(missing_literals, separators=(',', ':'))}, "
                        "same_claim_evidence_paths="
                        f"{json.dumps(evidence_paths, separators=(',', ':'))}. "
                        "Change or remove every listed evidence claim "
                        "together, and retained refs must share one identical "
                        "corrected claim. Add one exact literal ref for every "
                        "quantity, split the multi-span claim across refs with the "
                        "same claim, or narrow the claim"
                        + (
                            f". linked_assertions={linked} must copy the corrected "
                            "claim byte-for-byte"
                            if linked
                            else ""
                        )
                        + elsewhere_instruction
                    ),
                    paths=tuple(dict.fromkeys(evidence_paths)),
                    allowed_repairs=("replace", "remove", "add"),
                    dependent_paths=tuple(linked),
                    repair_context={
                        "missing_quantity_groups": missing,
                        "missing_quantity_literals": missing_literals,
                        "same_claim_evidence_paths": evidence_paths,
                        "permitted_append_paths": ["supporting_evidence"],
                        **(
                            {"quantity_elsewhere_hints": elsewhere_hints}
                            if elsewhere_hints
                            else {"quantity_elsewhere": "absent_from_all_basic_refs"}
                        ),
                    },
                )
            )
    return issues


def _raw_quantitative_assertion_link_issues(
    value: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Aggregate decidable assertion-link errors into the first correction."""

    evidence = value.get("supporting_evidence")
    accepted_claims = (
        {
            str(item["claim"])
            for item in evidence
            if isinstance(item, Mapping) and isinstance(item.get("claim"), str)
        }
        if isinstance(evidence, list)
        else set()
    )
    invalid_paths: list[str] = []
    for field_name in ("current_beliefs", "contradictions"):
        assertions = value.get(field_name)
        if not isinstance(assertions, list):
            continue
        for index, item in enumerate(assertions):
            if (
                not isinstance(item, str)
                or not _normalized_claim_quantity_groups(item)
                or item in accepted_claims
            ):
                continue
            invalid_paths.append(f"{field_name}[{index}]")
    if not invalid_paths:
        return []
    return [
        ValidationIssue(
            code="assertion_without_support",
            message=(
                "quantitative ResearchState assertions must each copy one "
                "supporting_evidence claim byte-for-byte, invalid_fields="
                f"{invalid_paths}. For every named path, "
                "replace it with one exact accepted claim, attach literals to that "
                "same exact claim, or remove unsupported "
                "numeric detail. Numbers from unrelated claims do not count"
            ),
            paths=tuple(invalid_paths),
            allowed_repairs=("replace", "remove"),
            repair_context={"invalid_fields": invalid_paths},
        )
    ]


def _raw_basic_literal_identity_issues(
    value: Mapping[str, Any],
    previous_state: ResearchState | None,
) -> list[ValidationIssue]:
    """Surface Basic literal identity defects with the other raw issues.

    The tagged-ref construction guard stays the final boundary; this raw
    check makes a mutated or invented Basic literal correctable in the same
    initial feedback as quantity and assertion defects instead of surfacing
    as a plain construction error after the correction budget is gone.
    """

    if previous_state is None:
        return []
    prior_literals: dict[str, set[str]] = {}
    for item in previous_state.supporting_evidence:
        if isinstance(item, ResearchEvidenceRef) and item.kind == "basic_info":
            prior_literals.setdefault(str(item.projection_id), set()).add(
                str(item.exact_text)
            )
    evidence = value.get("supporting_evidence")
    if not isinstance(evidence, list):
        return []
    issues: list[ValidationIssue] = []
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping) or item.get("kind") != "basic_info":
            continue
        projection_id = item.get("projection_id")
        exact_text = item.get("exact_text")
        if not all(isinstance(entry, str) for entry in (projection_id, exact_text)):
            continue
        literals = prior_literals.get(projection_id)
        if literals is None:
            issues.append(
                ValidationIssue(
                    code="basic_ref_not_in_prior_state",
                    message=(
                        f"supporting_evidence[{index}] cites Basic Info "
                        f"projection {projection_id!r} that is absent from the "
                        "prior research state; reflect cannot introduce a new "
                        "Basic Info ref. Remove this evidence item; inventing or "
                        "substituting another ref is not authorized"
                    ),
                    paths=(f"supporting_evidence[{index}]",),
                    allowed_repairs=("remove",),
                    repair_context={"projection_id": projection_id},
                )
            )
            continue
        if exact_text in literals:
            continue
        if len(literals) == 1:
            prior_text = next(iter(literals))
            issues.append(
                ValidationIssue(
                    code="basic_literal_identity_mismatch",
                    message=(
                        f"supporting_evidence[{index}].exact_text for projection "
                        f"{projection_id!r} differs from the single prior exact "
                        f"literal (returned {len(exact_text)} characters, prior "
                        f"{len(prior_text)} characters). Restore the prior "
                        "exact_text byte-for-byte; no other edit to this ref is "
                        "authorized"
                    ),
                    paths=(f"supporting_evidence[{index}].exact_text",),
                    allowed_repairs=("replace",),
                    repair_context={
                        "projection_id": projection_id,
                        "prior_exact_text": prior_text,
                    },
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    code="basic_literal_identity_ambiguous",
                    message=(
                        f"supporting_evidence[{index}].exact_text for projection "
                        f"{projection_id!r} matches none of the multiple distinct "
                        "prior exact literals recorded for that projection; "
                        "substitution would be ambiguous. Remove this evidence "
                        "item"
                    ),
                    paths=(f"supporting_evidence[{index}]",),
                    allowed_repairs=("remove",),
                    repair_context={"projection_id": projection_id},
                )
            )
    return issues


def _basic_projection_texts(basic_info: Mapping[str, Any]) -> dict[str, str]:
    projections: dict[str, str] = {}
    for request in basic_info.get("requests", ()):
        if not isinstance(request, Mapping):
            continue
        for item in request.get("projections", ()):
            if not isinstance(item, Mapping):
                continue
            projection_id = item.get("projection_id")
            exact_text = item.get("exact_text")
            if isinstance(projection_id, str) and isinstance(exact_text, str):
                projections[projection_id] = exact_text
    return projections


def _research_evidence_key(item: ResearchEvidenceRef) -> str:
    if item.kind == "basic_info":
        value = {
            "kind": item.kind,
            "projection_id": item.projection_id,
            "exact_text": item.exact_text,
        }
    else:
        value = {
            "kind": item.kind,
            "signal_ref": item.signal_ref,
            "evidence_group": item.evidence_group,
            "evidence_index": item.evidence_index,
        }
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _signal_evidence_ref_catalog(batch: SignalBatchResult) -> list[dict[str, Any]]:
    """Expose the exact Signal evidence tuples visible to one reflect call."""

    return [
        {
            "signal_ref": result.ref,
            "supporting_evidence_indices": list(
                range(len(result.supporting_evidence))
            )
            if _signal_result_has_adoptable_evidence(result)
            else [],
            "counter_evidence_indices": list(range(len(result.counter_evidence)))
            if _signal_result_has_adoptable_evidence(result)
            else [],
        }
        for result in batch.results
    ]


MAX_REFLECT_SIGNAL_EVIDENCE_CHARS = 1_200


MAX_REFLECT_SIGNAL_BATCH_EVIDENCE_CHARS = 8_000


_COMPACT_EVIDENCE_OMISSION = " ...[bounded evidence text omitted]... "


def _compact_signal_evidence_text(text_value: str, *, max_chars: int) -> str:
    """Return readable evidence text without exposing the canonical raw span."""

    if max_chars <= 0:
        return ""
    normalized, _runs = _normalized_projection_text(
        text_value,
        strip_market_metadata=True,
    )
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= len(_COMPACT_EVIDENCE_OMISSION):
        return normalized[:max_chars]
    available = max_chars - len(_COMPACT_EVIDENCE_OMISSION)
    head = (available * 2) // 3
    tail = available - head
    return (
        normalized[:head]
        + _COMPACT_EVIDENCE_OMISSION
        + normalized[-tail:]
    )


def _signal_batch_model_view(batch: SignalBatchResult) -> list[dict[str, Any]]:
    """Project canonical Signal results into one compact H_reflect-only view."""

    remaining = MAX_REFLECT_SIGNAL_BATCH_EVIDENCE_CHARS
    rows: list[dict[str, Any]] = []
    for result in batch.results:
        model_result = signal_result_model_view(result)
        use_canonical_interpretation = (
            _signal_result_has_adoptable_evidence(result)
            and result.signal_id in _CANONICAL_NUMERIC_DETERMINISTIC_SIGNALS
            and result.interpretation.startswith(result.signal_id + "=")
        )
        evidence_view: dict[str, list[dict[str, Any]]] = {
            "supporting": [],
            "counter": [],
        }
        for group, evidence_items in (
            ("supporting", result.supporting_evidence),
            ("counter", result.counter_evidence),
        ):
            for index, evidence in enumerate(evidence_items):
                evidence_row = {
                    "evidence_index": index,
                    "available_at": evidence.timestamp.isoformat(),
                }
                if not use_canonical_interpretation:
                    text_limit = min(MAX_REFLECT_SIGNAL_EVIDENCE_CHARS, remaining)
                    compact_text = _compact_signal_evidence_text(
                        evidence.exact_span,
                        max_chars=text_limit,
                    )
                    remaining -= len(compact_text)
                    evidence_row["model_evidence_text"] = compact_text
                evidence_view[group].append(evidence_row)
        row = {
            "signal_ref": result.ref,
            "signal_id": result.signal_id,
            "version": result.version,
            "state": {
                "value": result.value.value,
                "confidence": result.confidence,
            },
            "evidence": evidence_view,
            "status": {"coverage": result.coverage.value},
        }
        if use_canonical_interpretation:
            row["exact_claim_if_adopted"] = result.interpretation
        else:
            row["interpretation"] = model_result["interpretation"]
        rows.append(row)
    return rows


def _signal_result_has_adoptable_evidence(result: SignalResult) -> bool:
    """Return whether H_reflect may cite one current result as evidence."""

    return (
        result.value is not SignalValue.UNAVAILABLE
        and result.coverage is not SignalCoverage.UNAVAILABLE
        and bool(result.supporting_evidence or result.counter_evidence)
    )


def _reflection_selection_intents(
    selections: tuple[SignalSelectionDecision, ...],
    *,
    information_needs: tuple[str, ...] = (),
    evaluation_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Project persisted routing decisions into the fields reflection still needs."""

    prediction_date = _prediction_date_from_context(evaluation_context)
    rows: list[dict[str, Any]] = []
    for item in selections:
        row = {
            "signal_ref": item.signal_ref,
            "reason_code": item.reason_code,
            "selection_reason": item.selection_reason,
            "target_need_indices": list(item.target_need_indices),
        }
        if item.answer_scope is not None:
            row["answer_scope"] = item.answer_scope
            if item.answer_scope == "partial":
                prior_need = (
                    information_needs[item.target_need_indices[0]]
                    if len(item.target_need_indices) == 1
                    and 0 <= item.target_need_indices[0] < len(information_needs)
                    else ""
                )
                bounded = (
                    _bounded_residual_need(
                        item.residual_need, prior_need, prediction_date,
                    )
                    if prior_need
                    else item.residual_need
                )
                if bounded is not None:
                    row["residual_need"] = bounded
            else:
                row["residual_need"] = item.residual_need
        rows.append(row)
    return rows


def _reflection_need_transition_contract(
    state: ResearchState,
    selections: tuple[SignalSelectionDecision, ...],
    batch: SignalBatchResult,
    *,
    evaluation_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind each prior need to deterministic routing and result-availability facts."""

    prediction_date = _prediction_date_from_context(evaluation_context)
    _reject_unrepresentable_partial_selections(
        selections, state.next_information_needs, evaluation_context,
    )
    results = {result.ref: result for result in batch.results}
    rules: list[dict[str, Any]] = []
    for index, need in enumerate(state.next_information_needs):
        available_answer_refs: list[str] = []
        available_answer_actions: list[dict[str, Any]] = []
        unavailable_answer_refs: list[str] = []
        contextual_refs: list[str] = []
        for selection in selections:
            if index not in selection.target_need_indices:
                continue
            if selection.reason_code != "answer_need":
                if selection.signal_ref not in contextual_refs:
                    contextual_refs.append(selection.signal_ref)
                continue
            result = results.get(selection.signal_ref)
            adoptable = (
                result is not None and _signal_result_has_adoptable_evidence(result)
            )
            destination = (
                available_answer_refs if adoptable else unavailable_answer_refs
            )
            if selection.signal_ref not in destination:
                destination.append(selection.signal_ref)
            if adoptable:
                action = {
                    "signal_ref": selection.signal_ref,
                    "answer_scope": selection.answer_scope,
                }
                if selection.answer_scope == "partial":
                    bounded = _bounded_residual_need(
                        selection.residual_need, need, prediction_date,
                    )
                    if bounded is not None:
                        action["residual_need"] = bounded
                else:
                    action["residual_need"] = selection.residual_need
                available_answer_actions.append(action)
        if not available_answer_actions:
            required_transition = "preserve_exactly"
        elif available_answer_actions[0]["answer_scope"] == "full":
            required_transition = (
                "if evidence from this available full answer is adopted, "
                "remove_exact_need; otherwise preserve_exactly"
            )
        elif (
            available_answer_actions[0]["answer_scope"] == "partial"
            and not isinstance(
                available_answer_actions[0].get("residual_need"), str
            )
        ):
            required_transition = "preserve_exactly"
        elif available_answer_actions[0]["answer_scope"] == "partial":
            required_transition = (
                "if evidence from this available partial answer is adopted, "
                "replace_with_exact_residual_need; otherwise preserve_exactly"
            )
        else:
            required_transition = (
                "if evidence from an available_answer_signal_ref is adopted, "
                "remove_or_genuinely_narrow; otherwise preserve_exactly"
            )
        rules.append(
            {
                "need_index": index,
                "need": need,
                "available_answer_signal_refs": available_answer_refs,
                "available_answer_actions": available_answer_actions,
                "unavailable_answer_signal_refs": unavailable_answer_refs,
                "context_only_signal_refs": contextual_refs,
                "required_transition": required_transition,
            }
        )
    return {
        "need_rules": rules,
        "legacy_unindexed_answer_signal_refs": [
            item.signal_ref
            for item in selections
            if item.reason_code == "answer_need" and not item.target_need_indices
        ],
    }


_CANONICAL_NUMERIC_DETERMINISTIC_SIGNALS = frozenset(
    {
        "cash_reserves",
        "gross_margin_change",
        "max_drawdown_1y",
        "negative_word_count",
        "net_share_retirement_yoy",
        "operating_cash_flow_margin",
        "price_momentum_126d",
        "revenue_acceleration",
        "revenue_growth_yoy",
    }
)


MAX_BASIC_LITERAL_CORRECTION_WINDOW_CHARS = 800


def _closest_basic_literal_correction_window(
    invalid_text: str,
    projection_text: str,
) -> str | None:
    """Expose one bounded exact source window for a strongly overlapping bad quote."""

    if not invalid_text or not projection_text:
        return None
    match = SequenceMatcher(
        None,
        invalid_text,
        projection_text,
        autojunk=False,
    ).find_longest_match()
    if match.size < 32 or match.size / len(invalid_text) < 0.5:
        return None
    remaining = MAX_BASIC_LITERAL_CORRECTION_WINDOW_CHARS - match.size
    before = min(match.b, max(0, remaining // 2))
    after = min(
        len(projection_text) - match.b - match.size,
        max(0, remaining - before),
    )
    before = min(match.b, max(0, remaining - after))
    return projection_text[
        match.b - before : match.b + match.size + after
    ]


def _linked_quantitative_assertion_paths(
    state: ResearchState,
    claim: str,
) -> list[str]:
    """Name state assertions that must track a corrected evidence claim."""

    return [
        f"{field_name}[{index}]"
        for field_name in ("current_beliefs", "contradictions")
        for index, item in enumerate(getattr(state, field_name))
        if item == claim and _normalized_claim_quantity_groups(item)
    ]


def _validate_basic_claim_quantities(
    refs: tuple[ResearchEvidenceRef, ...],
    state: ResearchState,
) -> list[ValidationIssue]:
    """Require each Basic claim's quantities across its cited literal group."""

    grouped: dict[str, list[tuple[int, str]]] = {}
    for index, item in enumerate(refs):
        if item.kind == "basic_info":
            grouped.setdefault(item.claim, []).append((index, str(item.exact_text)))
    issues: list[ValidationIssue] = []
    for claim, items in grouped.items():
        cited_quantities: set[str] = set()
        for _index, exact_text in items:
            cited_quantities.update(_normalized_claim_quantities(exact_text))
        missing, missing_literals = _missing_claim_quantity_details(
            claim, cited_quantities
        )
        if missing:
            index = items[0][0]
            evidence_paths = [
                f"supporting_evidence[{item_index}].claim"
                for item_index, _text in items
            ]
            linked = _linked_quantitative_assertion_paths(state, claim)
            elsewhere_hints, _all_located = _basic_quantity_elsewhere_hints(
                missing_literals,
                [
                    (item_index, str(ref.exact_text), str(ref.claim))
                    for item_index, ref in enumerate(refs)
                    if ref.kind == "basic_info"
                ],
            )
            elsewhere_instruction = (
                " The missing literals already appear in your other cited "
                "Basic refs at "
                + json.dumps(elsewhere_hints, separators=(",", ":"))
                + ": add those ref tuples under the same claim, copying the "
                "literal byte-for-byte without rounding or conversion"
                if elsewhere_hints
                else (
                    " The missing literals appear in NO supplied Basic "
                    "exact_text: computing, estimating, or converting them is "
                    "invalid - narrow the claim to the cited literals or "
                    "remove the quantity"
                )
            )
            issues.append(
                ValidationIssue(
                    code="claim_quantity_not_supported",
                    message=(
                        f"supporting_evidence[{index}] claim contains numeric "
                        "quantities absent from all Basic exact_text refs with the "
                        "same claim. Change or remove every listed evidence claim "
                        "together. Add one exact literal ref for every quantity, "
                        "split the multi-span claim across refs with the same claim, "
                        "or narrow the claim"
                        + elsewhere_instruction
                    ),
                    paths=tuple(evidence_paths),
                    allowed_repairs=("replace", "remove", "add"),
                    dependent_paths=tuple(linked),
                    repair_context={
                        "missing_quantity_groups": missing,
                        "missing_quantity_literals": missing_literals,
                        "same_claim_evidence_paths": evidence_paths,
                        "permitted_append_paths": ["supporting_evidence"],
                        **(
                            {"quantity_elsewhere_hints": elsewhere_hints}
                            if elsewhere_hints
                            else {
                                "quantity_elsewhere": "absent_from_all_basic_refs"
                            }
                        ),
                    },
                )
            )
    return issues


def _signal_quantity_location_hints(
    missing: list[str],
    cited_signal_refs: tuple[str, ...],
    available: Mapping[str, list[tuple[str, int, str]]] | None,
) -> dict[str, list[str]]:
    """Name same-Signal evidence locations that contain a missing quantity."""

    hints: dict[str, list[str]] = {}
    for group in missing:
        alternatives = set(group.split("|"))
        locations: list[str] = []
        for ref in cited_signal_refs:
            for group_name, evidence_index, span in (available or {}).get(ref, ()):
                if alternatives & _normalized_claim_quantities(span):
                    locations.append(f"{group_name}[{evidence_index}]")
        if locations:
            hints[group] = locations
    return hints


def _validate_signal_claim_quantities(
    grouped: Mapping[str, list[tuple[int, str]]],
    state: ResearchState,
    available: Mapping[str, list[tuple[str, int, str]]] | None = None,
) -> list[ValidationIssue]:
    """Require each new Signal claim's quantities in its cited evidence items."""

    issues: list[ValidationIssue] = []
    for claim, items in grouped.items():
        cited_quantities: set[str] = set()
        for _index, exact_text in items:
            cited_quantities.update(_normalized_claim_quantities(exact_text))
        missing, missing_literals = _missing_claim_quantity_details(
            claim, cited_quantities
        )
        if missing:
            index = items[0][0]
            evidence_paths = [
                f"supporting_evidence[{item_index}].claim"
                for item_index, _text in items
            ]
            linked = _linked_quantitative_assertion_paths(state, claim)
            cited_signal_refs = tuple(
                dict.fromkeys(
                    str(ref.signal_ref)
                    for ref in state.supporting_evidence
                    if isinstance(ref, ResearchEvidenceRef)
                    and ref.kind == "signal"
                    and ref.claim == claim
                )
            )
            location_hints = _signal_quantity_location_hints(
                missing, cited_signal_refs, available
            )
            provenance_dependency_paths = (
                [
                    f"supporting_evidence[{ref_index}].{field_name}"
                    for ref_index, ref in enumerate(state.supporting_evidence)
                    if isinstance(ref, ResearchEvidenceRef)
                    and ref.kind == "signal"
                    and ref.claim == claim
                    and ref.signal_ref in cited_signal_refs
                    for field_name in ("evidence_group", "evidence_index")
                ]
                if location_hints
                else []
            )
            hint_instruction = (
                " Missing quantities occur in same-Signal evidence "
                f"locations {json.dumps(location_hints, separators=(',', ':'))}: "
                "add the exact evidence ref tuple for one such location with "
                "the same claim, or move an existing same-claim ref by changing "
                "only its permitted evidence_group/evidence_index coordinates, "
                "or narrow the claim to the cited literals"
                if location_hints
                else ""
            )
            issues.append(
                ValidationIssue(
                    code="claim_quantity_not_supported",
                    message=(
                        f"supporting_evidence[{index}] claim contains numeric "
                        "quantities absent from all referenced Signal evidence items "
                        "with the same claim, missing_quantity_groups="
                        f"{json.dumps(missing, separators=(',', ':'))}, "
                        "missing_quantity_literals="
                        f"{json.dumps(missing_literals, separators=(',', ':'))}, "
                        "same_claim_evidence_paths="
                        f"{json.dumps(list(dict.fromkeys(evidence_paths)), separators=(',', ':'))}. "
                        "Change or remove every listed evidence "
                        "claim together. Copy the exact canonical numeric form from "
                        "a deterministic Signal interpretation, cite every required "
                        "Signal evidence item with the same claim, or narrow the "
                        "claim. Do not round or convert the supplied values"
                        + hint_instruction
                    ),
                    paths=tuple(dict.fromkeys(evidence_paths)),
                    allowed_repairs=("replace", "remove", "add"),
                    dependent_paths=tuple(
                        dict.fromkeys((*linked, *provenance_dependency_paths))
                    ),
                    source_refs=cited_signal_refs,
                    repair_context={
                        "missing_quantity_groups": missing,
                        "missing_quantity_literals": missing_literals,
                        "same_claim_evidence_paths": evidence_paths,
                        "permitted_append_paths": ["supporting_evidence"],
                        **(
                            {
                                "permitted_evidence_ref_paths": (
                                    provenance_dependency_paths
                                )
                            }
                            if provenance_dependency_paths
                            else {}
                        ),
                        **(
                            {"quantity_location_hints": location_hints}
                            if location_hints
                            else {}
                        ),
                    },
                )
            )
    return issues


def _validate_assertive_state_claim_links(
    state: ResearchState,
    refs: tuple[ResearchEvidenceRef, ...],
) -> list[ValidationIssue]:
    """Bind every quantitative state assertion to one exact evidence claim."""

    accepted_claims = {item.claim for item in refs}
    invalid_paths: list[str] = []
    for field_name in ("current_beliefs", "contradictions"):
        for index, item in enumerate(getattr(state, field_name)):
            if not _normalized_claim_quantity_groups(item):
                continue
            if item in accepted_claims:
                continue
            invalid_paths.append(f"{field_name}[{index}]")
    if not invalid_paths:
        return []
    return [
        ValidationIssue(
            code="assertion_without_support",
            message=(
                "quantitative ResearchState assertions must copy one accepted "
                "supporting_evidence claim byte-for-byte, invalid_fields="
                f"{invalid_paths}. Attach every literal "
                "needed by that exact claim, or remove the unsupported numeric "
                "detail. Numbers from unrelated claims do not count"
            ),
            paths=tuple(invalid_paths),
            allowed_repairs=("replace", "remove"),
            repair_context={"invalid_fields": invalid_paths},
        )
    ]


def _validate_research_state_refs(
    state: ResearchState,
    *,
    phase: str,
    basic_info: Mapping[str, Any] | None = None,
    previous_state: ResearchState | None = None,
    batch: SignalBatchResult | None = None,
    selections: tuple[SignalSelectionDecision, ...] = (),
    must_finalize: bool = False,
    evaluation_context: Mapping[str, Any] | None = None,
) -> ResearchState:
    """Enforce the v6 visible-evidence transition contract locally."""

    legacy_issues = [ValidationIssue(
        code="evidence_shape_invalid", message="active v6 ResearchState evidence must use tagged refs",
        paths=(f"supporting_evidence[{index}]",), allowed_repairs=("replace", "remove"),
    ) for index, item in enumerate(state.supporting_evidence) if not isinstance(item, ResearchEvidenceRef)]
    if legacy_issues:
        raise StructuredValidationError(legacy_issues)
    refs = tuple(
        item
        for item in state.supporting_evidence
        if isinstance(item, ResearchEvidenceRef)
    )
    normalized_refs = list(refs)
    previous = {
        _research_evidence_key(item)
        for item in (previous_state.supporting_evidence if previous_state else ())
        if isinstance(item, ResearchEvidenceRef)
    }
    previous_refs = {
        _research_evidence_key(item): item
        for item in (previous_state.supporting_evidence if previous_state else ())
        if isinstance(item, ResearchEvidenceRef)
    }
    projection_texts = _basic_projection_texts(basic_info or {})
    results = {item.ref: item for item in (batch.results if batch else ())}
    signal_claim_literals: dict[str, list[tuple[int, str]]] = {}
    signal_available_spans: dict[str, list[tuple[str, int, str]]] = {
        ref: [
            (group_name, evidence_index, evidence.exact_span)
            for group_name, evidence_items in (
                ("supporting", result.supporting_evidence),
                ("counter", result.counter_evidence),
            )
            for evidence_index, evidence in enumerate(evidence_items)
        ]
        for ref, result in results.items()
    }
    structured_issues: list[ValidationIssue] = []

    def reference_issue(
        index: int, item: ResearchEvidenceRef, code: str, message: str,
        *, fields: tuple[str, ...] = (), repairs: tuple[str, ...] = ("replace", "remove"),
    ) -> None:
        path = f"supporting_evidence[{index}]"
        linked = tuple(
            f"{field}[{position}]" for field in ("current_beliefs", "contradictions")
            for position, assertion in enumerate(getattr(state, field)) if assertion == item.claim
        )
        structured_issues.append(ValidationIssue(
            code=code, message=message,
            paths=tuple(f"{path}.{field}" for field in fields) if fields else (path,),
            path_policy="any" if len(fields) > 1 else "all",
            allowed_repairs=repairs, dependent_paths=linked,
            repair_context={"authorized_member_removals": [path]},
        ))

    for index, item in enumerate(refs):
        key = _research_evidence_key(item)
        if phase == "finalize":
            if key not in previous:
                reference_issue(index, item, "new_finalization_evidence", "finalize cannot introduce a new evidence ref", repairs=("remove",))
            continue
        if item.kind == "basic_info":
            if phase == "reflect":
                if key not in previous:
                    reference_issue(index, item, "new_reflection_basic_evidence", "reflect cannot introduce a new Basic Info ref", repairs=("remove",))
                continue
            projection = projection_texts.get(str(item.projection_id))
            exact_text = str(item.exact_text)
            if projection is not None and projection.count(exact_text) == 1:
                continue
            matches = [
                projection_id
                for projection_id, candidate in projection_texts.items()
                if candidate.count(exact_text) == 1
            ]
            occurrence_count = sum(
                candidate.count(exact_text) for candidate in projection_texts.values()
            )
            if len(matches) == 1 and occurrence_count == 1:
                normalized_refs[index] = ResearchEvidenceRef(
                    kind="basic_info",
                    claim=item.claim,
                    projection_id=matches[0],
                    exact_text=exact_text,
                )
                continue
            dependent_paths = tuple(
                f"{field_name}[{assertion_index}]"
                for field_name in ("current_beliefs", "contradictions")
                for assertion_index, assertion in enumerate(
                    getattr(state, field_name)
                )
                if assertion == item.claim
            )
            if projection is None:
                structured_issues.append(
                    ValidationIssue(
                        code="basic_literal_not_grounded",
                        message=(
                            f"supporting_evidence[{index}] cited unknown Basic Info "
                            f"projection {item.projection_id!r}. Use the single "
                            "projection containing the exact contiguous literal or "
                            "remove this evidence item"
                        ),
                        paths=(f"supporting_evidence[{index}]",),
                        allowed_repairs=("replace", "remove"),
                        dependent_paths=dependent_paths,
                        source_refs=tuple(matches),
                        repair_context={
                            "returned_projection_id": item.projection_id,
                            "matching_projection_ids": matches,
                            "occurrence_count": occurrence_count,
                        },
                    )
                )
                continue
            closest_window = _closest_basic_literal_correction_window(
                exact_text,
                projection,
            )
            closest_instruction = (
                f"; invalid_exact_text={exact_text!r}; "
                f"occurrences_in_named_projection={projection.count(exact_text)}; "
                f"closest_visible_projection_window={closest_window!r}"
                if closest_window is not None
                else (
                    f"; invalid_exact_text={exact_text!r}; "
                    f"occurrences_in_named_projection={projection.count(exact_text)}"
                )
            )
            structured_issues.append(
                ValidationIssue(
                    code="basic_literal_not_grounded",
                    message=(
                        f"supporting_evidence[{index}] basic_info exact_text is not "
                        "one contiguous literal substring unique to projection "
                        f"{item.projection_id!r}{closest_instruction}. Copy one "
                        "byte-for-byte span without ellipses, JSON-field reordering, "
                        "non-contiguous joins, or paraphrase, or remove this "
                        "evidence item"
                    ),
                    paths=(f"supporting_evidence[{index}]",),
                    allowed_repairs=("replace", "remove"),
                    dependent_paths=dependent_paths,
                    source_refs=tuple(matches),
                    repair_context={
                        "returned_projection_id": item.projection_id,
                        "matching_projection_ids": matches,
                        "occurrences_in_named_projection": projection.count(
                            exact_text
                        ),
                        "closest_visible_projection_window": closest_window,
                    },
                )
            )
            continue
        if key in previous:
            prior = previous_refs[key]
            if item.claim != prior.claim:
                reference_issue(index, item, "retained_signal_claim_changed",
                    f"supporting_evidence[{index}] retained Signal claim changed from "
                    f"{prior.claim!r} to {item.claim!r}. Copy the prior claim "
                    "byte-for-byte or remove this evidence item; its backing Signal "
                    "batch is no longer visible", fields=("claim",),
                )
            continue
        result = results.get(str(item.signal_ref))
        if result is None:
            signal_id_matches = [
                candidate
                for candidate in results.values()
                if candidate.signal_id == str(item.signal_ref)
            ]
            if len(signal_id_matches) == 1:
                result = signal_id_matches[0]
                normalized_refs[index] = ResearchEvidenceRef(
                    kind="signal",
                    claim=item.claim,
                    signal_ref=result.ref,
                    evidence_group=item.evidence_group,
                    evidence_index=item.evidence_index,
                )
            else:
                reference_issue(index, item, "signal_reference_unknown",
                    f"supporting_evidence[{index}] cited Signal "
                    f"{item.signal_ref!r} outside the current batch; use one exact "
                    "signal_ref supplied by signal_batch",
                    fields=("signal_ref", "evidence_group", "evidence_index"),
                )
                continue
        if not _signal_result_has_adoptable_evidence(result):
            reference_issue(index, item, "signal_result_unavailable",
                f"supporting_evidence[{index}] cited unavailable Signal result "
                f"signal_ref={result.ref!r}. Unavailable is a coverage diagnostic, "
                "not adoptable evidence; remove this evidence item", repairs=("remove",),
            )
            continue
        evidence = (
            result.supporting_evidence
            if item.evidence_group == "supporting"
            else result.counter_evidence
        )
        if int(item.evidence_index or 0) >= len(evidence):
            valid_indices = list(range(len(evidence)))
            reference_issue(index, item, "signal_evidence_coordinate_invalid",
                f"supporting_evidence[{index}] cited unavailable Signal evidence "
                f"signal_ref={result.ref!r}, evidence_group={item.evidence_group!r}, "
                f"evidence_index={item.evidence_index!r}; valid_evidence_indices="
                f"{valid_indices} for that signal_ref and group. Use one exact tuple "
                "from signal_evidence_ref_catalog or remove this evidence item",
                fields=("signal_ref", "evidence_group", "evidence_index"),
            )
            continue
        claim_literals = signal_claim_literals.setdefault(item.claim, [])
        claim_literals.append(
            (index, evidence[int(item.evidence_index or 0)].exact_span)
        )
        if (
            result.signal_id in _CANONICAL_NUMERIC_DETERMINISTIC_SIGNALS
            and result.interpretation.startswith(result.signal_id + "=")
        ):
            claim_literals.append((index, result.interpretation))
    structured_issues.extend(
        _validate_basic_claim_quantities(tuple(normalized_refs), state)
    )
    structured_issues.extend(
        _validate_signal_claim_quantities(
            signal_claim_literals, state, signal_available_spans
        )
    )
    structured_issues.extend(
        _validate_assertive_state_claim_links(state, tuple(normalized_refs))
    )
    validation_errors: list[ValidationIssue] = []
    legacy_cross_field_duplicates = (
        set(previous_state.open_questions)
        & set(previous_state.next_information_needs)
        if previous_state is not None
        else set()
    )
    for index, item in enumerate(state.open_questions):
        if (
            item not in state.next_information_needs
            or item in legacy_cross_field_duplicates
        ):
            continue
        need_index = state.next_information_needs.index(item)
        path = f"open_questions[{index}]"
        structured_issues.append(
            ValidationIssue(
                code="open_question_duplicates_need",
                message=(
                    f"{path} duplicates one next information need byte-for-byte, "
                    f"matching_next_need_index={need_index}, invalid_field={path!r}. "
                    "Remove the duplicate open question; next_information_needs owns "
                    "the actionable retrieval item"
                ),
                paths=(path,),
                allowed_repairs=("remove",),
            )
        )
    adopted_new_signal_evidence = any(
        item.kind == "signal"
        and _research_evidence_key(item) not in previous
        and str(item.signal_ref) in results
        for item in normalized_refs
    )
    adopted_new_signal_refs = {
        str(item.signal_ref)
        for item in normalized_refs
        if item.kind == "signal"
        and _research_evidence_key(item) not in previous
        and str(item.signal_ref) in results
    }
    available_current_signal_refs = (
        {
            result.ref
            for result in batch.results
            if _signal_result_has_adoptable_evidence(result)
        }
        if batch is not None
        else set()
    )
    targeted_answer_need_errors = _targeted_answer_need_transition_errors(
        previous_state,
        state,
        selections,
        adopted_new_signal_refs,
        available_current_signal_refs,
        evaluation_context=evaluation_context,
    )
    cosmetic_needs = _cosmetically_retained_information_needs(
        previous_state.next_information_needs if previous_state else (),
        state.next_information_needs,
    )
    stale_resolved_needs = _stale_resolved_information_needs(
        previous_state,
        state,
    )
    unavailable_state_errors = _unavailable_signal_state_errors(
        previous_state,
        state,
        batch,
    )
    if phase == "reflect" and unavailable_state_errors:
        for error in unavailable_state_errors:
            validation_errors.append(ValidationIssue(
                code="unavailable_signal_treated_as_finding",
                message=("research_controller_reflect treated an unavailable Signal as a finding: "
                         f"{error}. Unavailable is coverage-only; remove the "
                         "new belief/resolution and keep the topic open if it still matters"),
                paths=tuple(f"{error['field']}[{index}]" for index, text in enumerate(getattr(state, error["field"])) if text == error["text"]),
                allowed_repairs=("remove",),
            ))
    terminal_unavailable_only = (
        phase == "reflect"
        and must_finalize
        and previous_state is not None
        and batch is not None
        and bool(batch.results)
        and all(
            result.value is SignalValue.UNAVAILABLE
            or result.coverage is SignalCoverage.UNAVAILABLE
            for result in batch.results
        )
    )
    if terminal_unavailable_only and previous_state is not None:
        previous_content = previous_state.to_dict()
        reflected_content = state.to_dict()
        previous_content.pop("decision")
        reflected_content.pop("decision")
        if reflected_content != previous_content:
            validation_errors.append(ValidationIssue(
                code="terminal_unavailable_state_changed", retryability="terminal",
                paths=("decision",),
                message=("research_controller_reflect received an all-unavailable terminal "
                "batch. Preserve every prior ResearchState field and item "
                "byte-for-byte and change only decision from 'continue' to "
                "'finalize'; unavailable coverage cannot justify any other update"),
            ))
    if (
        phase == "reflect"
        and must_finalize
        and state.decision is not ResearchDecision.FINALIZE
    ):
        validation_errors.append(ValidationIssue(
            code="terminal_decision_required", paths=("decision",),
            message=("research_controller_reflect reached the last executable evidence "
            "batch but returned decision='continue'. Return decision='finalize' "
            "from the accepted evidence; preserve unresolved uncertainty in "
            "open_questions or next_information_needs rather than inventing a "
            "resolution"),
        ))
    if phase == "reflect" and adopted_new_signal_evidence:
        for error in targeted_answer_need_errors:
            structured_issues.append(
                _need_transition_validation_issue(error, state)
            )
    if (
        phase == "reflect"
        and previous_state is not None
        and state.decision is ResearchDecision.CONTINUE
        and adopted_new_signal_evidence
    ):
        if cosmetic_needs:
            validation_errors.append(ValidationIssue(
                code="cosmetic_need_update",
                paths=tuple(dict.fromkeys(f"next_information_needs[{index}]" for error in cosmetic_needs for index, need in enumerate(state.next_information_needs) if need == error["current_need"])),
                allowed_repairs=("replace", "remove"),
                dependent_paths=("decision",) if len(state.next_information_needs) == 1 else (),
                message=("research_controller_reflect adopted new current-batch Signal evidence "
                "but cosmetically changed prior next_information_needs: "
                f"{cosmetic_needs}. Keep an unanswered need byte-for-byte, or narrow/"
                "replace the answered portion. Do not append a qualifier to the old "
                "need"),
            ))
        if stale_resolved_needs:
            for stale_need in [
                need
                for resolved_question in state.resolved_questions
                if previous_state is None
                or resolved_question not in previous_state.resolved_questions
                for need in state.next_information_needs
                if _shared_resolved_need_phrase(need, resolved_question) is not None
            ]:
                structured_issues.append(
                    ValidationIssue(
                        code="stale_resolved_need_retained",
                        message=(
                            "research_controller_reflect newly resolved a question "
                            "but retained an exact matching next_information_need: "
                            f"{[stale_need]}. Remove or narrow the answered need, or "
                            "remove the unsupported resolved question"
                        ),
                        paths=(
                            (
                                "next_information_needs["
                                f"{state.next_information_needs.index(stale_need)}]"
                            ),
                        ),
                        allowed_repairs=("replace", "remove"),
                    )
                )
        legacy_answer_need_refs = {
            item.signal_ref
            for item in selections
            if item.reason_code == "answer_need" and not item.target_need_indices
            and item.signal_ref in available_current_signal_refs
        }
        if (
            adopted_new_signal_refs.intersection(legacy_answer_need_refs)
            and len(state.next_information_needs)
            == len(previous_state.next_information_needs)
            and set(state.next_information_needs)
            == set(previous_state.next_information_needs)
        ):
            retained_indexed_items = [
                {
                    "path": f"next_information_needs[{index}]",
                    "value": need,
                }
                for index, need in enumerate(previous_state.next_information_needs)
            ]
            validation_errors.append(ValidationIssue(
                code="answered_need_without_progress",
                paths=tuple(row["path"] for row in retained_indexed_items), path_policy="any",
                allowed_repairs=("replace", "remove"),
                dependent_paths=("decision",) if len(state.next_information_needs) == 1 else (),
                message=("research_controller_reflect adopted evidence from an available "
                "Signal selected with reason_code='answer_need' but retained the "
                "exact same set of prior next_information_needs; "
                "invalid_field='next_information_needs'; "
                f"retained_indexed_items={retained_indexed_items}. Change the field "
                "by removing or genuinely narrowing at least one listed item that "
                "the supplied selection intent and accepted evidence actually "
                "answered. Preserve every unanswered listed item byte-for-byte; "
                "runtime will not choose the need or fabricate a resolution"),
            ))
    if structured_issues or validation_errors:
        raise StructuredValidationError([*validation_errors, *structured_issues])
    if tuple(normalized_refs) == refs:
        return state
    value = state.to_dict()
    value["supporting_evidence"] = [item.to_dict() for item in normalized_refs]
    return ResearchState.from_dict(value)


def _normalized_need_tokens(value: str) -> frozenset[str]:
    """Return stable word tokens for the narrow cosmetic-progress boundary."""

    return frozenset(re.findall(r"[a-z0-9]+", value.casefold()))


_NEED_RESIDUAL_GENERIC_TOKENS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "company",
        "cover",
        "covered",
        "covering",
        "covers",
        "current",
        "direct",
        "directly",
        "did",
        "disclose",
        "disclosed",
        "discloses",
        "disclosure",
        "do",
        "does",
        "figure",
        "figures",
        "fiscal",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "in",
        "is",
        "key",
        "latest",
        "of",
        "on",
        "or",
        "provide",
        "provided",
        "provides",
        "report",
        "reported",
        "reporting",
        "remain",
        "remaining",
        "s",
        "specific",
        "such",
        "the",
        "there",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    }
)


def _normalized_need_content_tokens(value: str) -> frozenset[str]:
    """Return lightly singularized topic tokens for residual-target grounding."""

    normalized: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", value.casefold()):
        if token in _NEED_RESIDUAL_GENERIC_TOKENS:
            continue
        normalized.add(_singularize_topic_token(token))
    return frozenset(normalized)


_ROUTING_COMPOUND_FACET_BOUNDARY = re.compile(
    r"(?:;\s*|,\s+(?:and|or)\s+)", re.IGNORECASE
)


def _routing_residual_facet_candidates(
    target_need: str,
    answer_need_phrases: Iterable[str],
) -> tuple[str, ...]:
    """Return literal unresolved clauses for one unambiguous direct-answer split."""

    clauses = tuple(
        clause.strip().strip(" ,;.?")[:300]
        for clause in _ROUTING_COMPOUND_FACET_BOUNDARY.split(target_need)
        if clause.strip().strip(" ,;.?")
    )
    if len(clauses) < 2:
        return ()
    normalized_phrases = tuple(
        " " + re.sub(r"[^a-z0-9]+", " ", phrase.casefold()).strip() + " "
        for phrase in answer_need_phrases
        if re.sub(r"[^a-z0-9]+", " ", phrase.casefold()).strip()
    )
    if not normalized_phrases:
        return ()
    matched_indices = {
        index
        for index, clause in enumerate(clauses)
        if any(
            phrase
            in " " + re.sub(r"[^a-z0-9]+", " ", clause.casefold()).strip() + " "
            for phrase in normalized_phrases
        )
    }
    if len(matched_indices) != 1:
        return ()
    return tuple(
        clause for index, clause in enumerate(clauses) if index not in matched_indices
    )


def _coordinated_residual_facet_terms(
    target_need: str,
    residual_need: str,
) -> tuple[str, ...]:
    """Return retained values paired with a removed alternative in the target."""

    target_content = _normalized_need_content_tokens(target_need)
    residual_content = _normalized_need_content_tokens(residual_need)
    answered_content = target_content - residual_content
    if not answered_content:
        return ()

    raw_tokens = re.findall(r"[a-z0-9]+", target_need.casefold())

    def normalized_at(index: int) -> str | None:
        token = raw_tokens[index]
        if token in _NEED_RESIDUAL_GENERIC_TOKENS:
            return None
        if len(token) > 4 and token.endswith("ies"):
            return token[:-3] + "y"
        if (
            len(token) > 4
            and token.endswith("s")
            and not token.endswith(("is", "ss", "us"))
        ):
            return token[:-1]
        return token

    retained: list[str] = []
    for conjunction_index, token in enumerate(raw_tokens):
        if token not in {"and", "or", "versus", "vs"}:
            continue
        left = next(
            (
                normalized
                for index in range(conjunction_index - 1, -1, -1)
                if (normalized := normalized_at(index)) is not None
            ),
            None,
        )
        right = next(
            (
                normalized
                for index in range(conjunction_index + 1, len(raw_tokens))
                if (normalized := normalized_at(index)) is not None
            ),
            None,
        )
        if not (
            left is not None
            and right is not None
            and _TEMPORAL_TOPIC_TOKEN.fullmatch(left)
            and _TEMPORAL_TOPIC_TOKEN.fullmatch(right)
        ):
            continue
        if left in answered_content and right in residual_content:
            retained.append(str(right))
        elif right in answered_content and left in residual_content:
            retained.append(str(left))
    return tuple(dict.fromkeys(retained))


def _shared_distinctive_phrase(
    left: str,
    right: str,
    *,
    minimum_words: int = 3,
) -> str | None:
    """Return one shared ordered or reordered topic, ignoring routing filler."""

    def words(value: str) -> tuple[str, ...]:
        normalized: list[str] = []
        for token in re.findall(r"[a-z0-9]+", value.casefold()):
            if token in _NEED_RESIDUAL_GENERIC_TOKENS:
                continue
            normalized.append(_singularize_topic_token(token))
        return tuple(normalized)

    left_words = words(left)
    right_words = words(right)
    left_topic_words = tuple(
        token
        for token in left_words
        if not token.isdigit() and not _TEMPORAL_TOPIC_TOKEN.fullmatch(token)
    )
    right_topic_words = tuple(
        token
        for token in right_words
        if not token.isdigit() and not _TEMPORAL_TOPIC_TOKEN.fullmatch(token)
    )
    right_ngrams = {
        right_topic_words[start : start + size]
        for size in range(minimum_words, len(right_topic_words) + 1)
        for start in range(len(right_topic_words) - size + 1)
    }
    for size in range(len(left_topic_words), minimum_words - 1, -1):
        for start in range(len(left_topic_words) - size + 1):
            phrase = left_topic_words[start : start + size]
            if phrase in right_ngrams:
                return " ".join(phrase)
    right_word_set = set(right_topic_words)
    reordered_overlap: list[str] = []
    for token in left_topic_words:
        if token in reordered_overlap or token not in right_word_set:
            continue
        reordered_overlap.append(token)
    if len(reordered_overlap) >= minimum_words:
        return " ".join(reordered_overlap)
    temporal_overlap = [
        token
        for token in left_words
        if token in right_words
        and (token.isdigit() or _TEMPORAL_TOPIC_TOKEN.fullmatch(token))
    ]
    if len(reordered_overlap) >= 2 and temporal_overlap:
        return " ".join(dict.fromkeys((*reordered_overlap, *temporal_overlap)))
    return None


def _need_transition_validation_issue(
    error: Mapping[str, Any],
    state: ResearchState,
) -> ValidationIssue:
    """Build the need-transition issue with returned-path-first coordinates.

    The returned invalid row — not the prior-state slot that sourced the
    transition rule — is the correction target whenever the offending
    occurrence still exists in the returned state, so every user-visible
    coordinate names the returned index first and the prior index stays
    explicitly labeled. The occurrence-aware transition validator supplies
    that returned_path; global text membership is never used here because a
    retained untargeted duplicate must not be mistaken for the target row.
    """

    returned_path = error.get("returned_path")
    return ValidationIssue(
        code="research_need_transition_invalid",
        message=(
            "research_controller_reflect violated the supplied need transition "
            f"contract: {error}. Preserve every untargeted prior need exactly"
        ),
        paths=(returned_path or str(error["prior_state_path"]),),
        allowed_repairs=("replace", "remove", "add"),
        repair_context={
            "write_scope_complete": (
                error["required_action"] == "replace_with_exact_residual"
                and returned_path is not None
            ),
            "returned_path": returned_path,
            "prior_state_path": str(error["prior_state_path"]),
            "prior_need": error["value"],
            "required_action": error["required_action"],
            "required_need": error.get("required_need"),
            "required_need_occurrences": error.get("required_need_occurrences"),
            "returned_need": error.get("returned_need", error["value"]),
        },
    )


def _targeted_answer_need_transition_errors(
    previous: ResearchState | None,
    current: ResearchState,
    selections: tuple[SignalSelectionDecision, ...],
    adopted_signal_refs: set[str],
    available_signal_refs: set[str],
    *,
    evaluation_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Bind adopted answer evidence to its preselected need occurrence.

    Validation is occurrence- and multiplicity-aware: every untargeted prior
    occurrence must be preserved byte-for-byte, each targeted occurrence must
    carry its bounded residual (partial answer) or be removed (full answer),
    a retained untargeted duplicate never satisfies a targeted occurrence's
    obligation, and one returned occurrence never satisfies two prior
    occurrences. Matching is by exact-text counts, never by global text
    membership, so deduplicating prior needs or deleting unselected copies
    cannot satisfy the guard.
    """

    if previous is None:
        return []
    if not adopted_signal_refs or not selections:
        return []
    if any(
        selection.reason_code == "answer_need"
        and selection.signal_ref in adopted_signal_refs
        and selection.signal_ref in available_signal_refs
        and not selection.target_need_indices
        for selection in selections
    ):
        return []
    prediction_date = _prediction_date_from_context(evaluation_context)
    target_selections: dict[int, list[SignalSelectionDecision]] = {}
    for selection in selections:
        if (
            selection.reason_code != "answer_need"
            or selection.signal_ref not in adopted_signal_refs
            or selection.signal_ref not in available_signal_refs
            or not selection.target_need_indices
        ):
            continue
        # A selection binds every named target occurrence, matching the
        # per-index rules the transition contract already publishes.
        for target_index in selection.target_need_indices:
            target_selections.setdefault(target_index, []).append(selection)
    prior_needs = previous.next_information_needs
    current_needs = list(current.next_information_needs)
    obligations: list[dict[str, Any]] = []
    for index, need in enumerate(prior_needs):
        if index not in target_selections:
            obligations.append({"kind": "preserve", "need": need})
            continue
        targeted = target_selections[index]
        signal_refs = [item.signal_ref for item in targeted]
        scoped = targeted[0] if len(targeted) == 1 else None
        if scoped is not None and scoped.answer_scope == "partial":
            required_residual = _bounded_residual_need(
                scoped.residual_need, need, prediction_date,
            )
            if required_residual is None:
                # An unrepresentable residual cannot authorize removing the
                # unresolved need, so this occurrence must stay preserved.
                obligations.append(
                    {
                        "kind": "preserve",
                        "need": need,
                        "signal_refs": signal_refs,
                        "unrepresentable": True,
                    }
                )
            else:
                obligations.append(
                    {
                        "kind": "replace",
                        "need": need,
                        "residual": required_residual,
                        "signal_refs": signal_refs,
                    }
                )
            continue
        obligations.append(
            {"kind": "remove", "need": need, "signal_refs": signal_refs}
        )
    required_counts: dict[str, int] = {}
    for obligation in obligations:
        if obligation["kind"] == "remove":
            # A removed targeted occurrence requires no returned text.
            continue
        required_text = (
            obligation["residual"]
            if obligation["kind"] == "replace"
            else obligation["need"]
        )
        required_counts[required_text] = required_counts.get(required_text, 0) + 1
    positions: dict[str, list[int]] = {}
    for index, item in enumerate(current_needs):
        positions.setdefault(item, []).append(index)
    shortfall = {
        text: required - len(positions.get(text, ()))
        for text, required in required_counts.items()
        if len(positions.get(text, ())) < required
    }
    surplus_positions = {
        text: positions[text][required_counts.get(text, 0):]
        for text in positions
        if len(positions[text]) > required_counts.get(text, 0)
    }
    errors: list[dict[str, Any]] = []
    for index, obligation in enumerate(obligations):
        if obligation["kind"] != "preserve":
            continue
        need = obligation["need"]
        if shortfall.get(need, 0) <= 0:
            continue
        shortfall[need] -= 1
        error = {
            "prior_state_path": f"next_information_needs[{index}]",
            "value": need,
            "issue": "untargeted need changed or was removed",
            "required_action": "restore_exactly",
            "required_need": need,
            "required_need_occurrences": required_counts.get(need, 1),
        }
        if obligation.get("unrepresentable"):
            error.update(
                {
                    "signal_refs": obligation["signal_refs"],
                    "issue": (
                        "partial-answer residual is unrepresentable at "
                        "the prediction-time boundary and cannot "
                        "authorize removing the unresolved need"
                    ),
                }
            )
        errors.append(error)
    for index, obligation in enumerate(obligations):
        if obligation["kind"] == "preserve":
            continue
        need = obligation["need"]
        prior_state_path = f"next_information_needs[{index}]"
        signal_refs = obligation["signal_refs"]
        surplus = surplus_positions.get(need, [])
        if surplus:
            errors.append(
                {
                    "returned_path": f"next_information_needs[{surplus[0]}]",
                    "prior_state_path": prior_state_path,
                    "value": need,
                    "signal_refs": signal_refs,
                    "issue": (
                        "partial-answer target remained byte-for-byte"
                        if obligation["kind"] == "replace"
                        else "targeted need remained byte-for-byte"
                    ),
                    "required_action": (
                        "replace_with_exact_residual"
                        if obligation["kind"] == "replace"
                        else "remove_exact_target"
                    ),
                    **(
                        {
                            "required_need": obligation["residual"],
                            "required_residual_need": obligation["residual"],
                        }
                        if obligation["kind"] == "replace"
                        else {}
                    ),
                }
            )
            del surplus[0]
            continue
        if obligation["kind"] == "replace":
            residual = obligation["residual"]
            if shortfall.get(residual, 0) > 0:
                shortfall[residual] -= 1
                errors.append(
                    {
                        "prior_state_path": prior_state_path,
                        "value": need,
                        "signal_refs": signal_refs,
                        "issue": "partial-answer target omitted its exact residual",
                        "required_action": "replace_with_exact_residual",
                        "required_need": residual,
                        "required_residual_need": residual,
                        "required_need_occurrences": required_counts.get(
                            residual, 1
                        ),
                    }
                )
            continue
        prior_tokens = _normalized_need_tokens(need)
        cosmetic = next(
            (
                candidate
                for candidate in current_needs
                if candidate != need
                and prior_tokens
                and len(
                    prior_tokens & _normalized_need_tokens(candidate)
                )
                / len(prior_tokens)
                >= 0.9
            ),
            None,
        )
        if cosmetic is not None:
            errors.append(
                {
                    "returned_path": (
                        "next_information_needs["
                        f"{current_needs.index(cosmetic)}]"
                    ),
                    "prior_state_path": prior_state_path,
                    "value": need,
                    "signal_refs": signal_refs,
                    "issue": "targeted need changed only cosmetically",
                    "required_action": "remove_or_genuinely_narrow",
                    "returned_need": cosmetic,
                }
            )
    return errors


def _cosmetically_retained_information_needs(
    previous: tuple[str, ...],
    current: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Identify changed old needs hidden inside an equal-or-larger need list."""

    if not previous or len(current) < len(previous):
        return []
    retained: list[dict[str, Any]] = []
    for prior_need in previous:
        if prior_need in current:
            continue
        prior_tokens = _normalized_need_tokens(prior_need)
        if not prior_tokens:
            continue
        for current_need in current:
            overlap = len(prior_tokens & _normalized_need_tokens(current_need))
            coverage = overlap / len(prior_tokens)
            if coverage >= 0.9:
                retained.append(
                    {
                        "prior_need": prior_need,
                        "current_need": current_need,
                        "prior_token_coverage": round(coverage, 6),
                    }
                )
                break
    return retained


_NEED_FUNCTION_WORDS = frozenset(
    "a an and are as at be been being by companies company could current did do "
    "does for from has have how if in is issuer issuers it latest of on or recent "
    "s that the their this to was were what when which who why will with would".split()
)


_TEMPORAL_TOPIC_TOKEN = re.compile(
    r"^(?:q[1-4]|(?:19|20)\d{2}|quarter|quarters|quarterly|year|years|annual|"
    r"month|months|monthly|week|weeks|weekly|day|days|daily)$"
)


def _need_content_tokens(value: str) -> tuple[str, ...]:
    """Return ordered content tokens for the narrow resolved-need check."""

    return tuple(
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if token not in _NEED_FUNCTION_WORDS
    )


def _titlecase_phrase_occurs(
    value: str,
    phrase: tuple[str, ...],
    *,
    require_all_words: bool = False,
) -> bool:
    """Return whether a phrase begins with a title-cased source entity word."""

    words = tuple(
        word
        for word in re.findall(r"[A-Za-z0-9]+", value)
        if word.casefold() != "s"
    )
    normalized = tuple(word.casefold() for word in words)
    for index in range(len(words) - len(phrase) + 1):
        if normalized[index : index + len(phrase)] != phrase:
            continue
        phrase_words = words[index : index + len(phrase)]
        if require_all_words and all(
            word[:1].isupper() for word in phrase_words
        ):
            return True
        if not require_all_words and words[index][:1].isupper():
            return True
    return False


def _shared_resolved_need_phrase(left: str, right: str) -> str | None:
    """Return one directly decidable shared topic, excluding issuer-name bigrams."""

    left_tokens = _need_content_tokens(left)
    right_tokens = _need_content_tokens(right)
    left_terms = frozenset(left_tokens)
    right_terms = frozenset(right_tokens)
    if not left_terms:
        return None
    if (left_terms & _ANSWER_RESIDUAL_SCOPE_MARKERS) - right_terms:
        return None
    if len(left_terms & right_terms) / len(left_terms) < 0.75:
        return None
    for size in (3, 2):
        if len(left_tokens) < size or len(right_tokens) < size:
            continue
        left_phrases = {
            left_tokens[index : index + size]
            for index in range(len(left_tokens) - size + 1)
        }
        right_phrases = {
            right_tokens[index : index + size]
            for index in range(len(right_tokens) - size + 1)
        }
        for phrase in sorted(left_phrases & right_phrases):
            if all(_TEMPORAL_TOPIC_TOKEN.fullmatch(token) for token in phrase):
                continue
            if size == 2 and _titlecase_phrase_occurs(
                left, phrase
            ) and _titlecase_phrase_occurs(right, phrase):
                continue
            if size >= 3 and _titlecase_phrase_occurs(
                left,
                phrase,
                require_all_words=True,
            ) and _titlecase_phrase_occurs(
                right,
                phrase,
                require_all_words=True,
            ):
                continue
            return " ".join(phrase)
    return None


def _stale_resolved_information_needs(
    previous: ResearchState | None,
    current: ResearchState,
) -> list[dict[str, Any]]:
    """Find exact retained needs contradicted by a newly resolved same-topic question."""

    if previous is None:
        return []
    newly_resolved = tuple(
        item
        for item in current.resolved_questions
        if item not in previous.resolved_questions
    )
    if not newly_resolved:
        return []
    retained = set(previous.next_information_needs) & set(
        current.next_information_needs
    )
    stale: list[dict[str, Any]] = []
    for need in previous.next_information_needs:
        if need not in retained:
            continue
        for resolved in newly_resolved:
            matching_phrase = _shared_resolved_need_phrase(need, resolved)
            if matching_phrase is None:
                continue
            stale.append(
                {
                    "retained_need": need,
                    "newly_resolved_question": resolved,
                    "matching_content_phrase": matching_phrase,
                }
            )
            break
    return stale


_UNAVAILABLE_BELIEF_MARKERS = frozenset(
    "absence absent insufficient lack lacks missing no none not undisclosed unknown "
    "unavailable without zero".split()
)


def _unavailable_signal_state_errors(
    previous: ResearchState | None,
    current: ResearchState,
    batch: SignalBatchResult | None,
) -> list[dict[str, str]]:
    """Reject belief/resolution claims derived from unavailable Signal topics."""

    if previous is None or batch is None:
        return []
    new_beliefs = tuple(
        item for item in current.current_beliefs if item not in previous.current_beliefs
    )
    newly_resolved = tuple(
        item
        for item in current.resolved_questions
        if item not in previous.resolved_questions
    )
    errors: list[dict[str, str]] = []
    for result in batch.results:
        if not (
            result.value is SignalValue.UNAVAILABLE
            or result.coverage is SignalCoverage.UNAVAILABLE
        ):
            continue
        topic_tokens = frozenset(
            re.findall(r"[a-z0-9]+", result.signal_id.casefold())
        )
        if not topic_tokens:
            continue
        for item in newly_resolved:
            tokens = frozenset(re.findall(r"[a-z0-9]+", item.casefold()))
            if topic_tokens.issubset(tokens):
                errors.append(
                    {
                        "field": "resolved_questions",
                        "signal_ref": result.ref,
                        "text": item,
                    }
                )
        for item in new_beliefs:
            tokens = frozenset(re.findall(r"[a-z0-9]+", item.casefold()))
            if topic_tokens.issubset(tokens) and (
                tokens & _UNAVAILABLE_BELIEF_MARKERS
            ):
                errors.append(
                    {
                        "field": "current_beliefs",
                        "signal_ref": result.ref,
                        "text": item,
                    }
                )
    return errors
