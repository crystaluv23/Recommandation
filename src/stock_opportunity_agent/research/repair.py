"""Generalized mechanical repair ladder for structured model output.

Real run records (V143 corrections, live validation journals) show a large
share of correction friction comes from defects whose correct fix is
uniquely determined by validator state: outcome claims citing resolvable
refs that were not re-listed in ``source_refs``, open questions repeating a
need byte-for-byte, empty rows in text arrays, and JSON truncated at the
output ceiling. Spending the only LLM correction round on such defects —
or losing whole rows when the model fails to apply them — discards real
content for mechanical reasons.

The ladder here is deliberately conservative:

- L0 repairs raw text (truncation completion, fence stripping, trailing
  commas) and only produces a *candidate*; the caller still parses and
  fully validates it.
- L2 repairs reorganize information the model already provided (register a
  cited ref, drop an exact duplicate, drop an empty row, split a straddling
  item into its two single-axis forms per the audit prescription). They
  never invent values or choose between alternatives.
- Every repair is a typed ``RepairOp`` recorded in a repair log; the
  repaired object is accepted only when it passes the caller's complete,
  unchanged validator (``parse`` here), so the validator — not the repair —
  remains the arbiter.

Anything ambiguous (which field a non-text object should collapse to,
semantic category choices without a fixed counterpart, missing content)
stays with the LLM correction frontier.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from stock_opportunity_agent.models import ValidationError

L0_JSON = "L0_json_text"
L2_MECHANICAL = "L2_mechanical"

# Issue codes whose unique fixes are copy-literal or whole-row removal;
# deterministic fallbacks may be promoted ahead of the LLM round only for
# these. Semantic classes keep the post-correction position.
MECHANICAL_FALLBACK_CODES = frozenset(
    {
        "assertion_without_support",
        "claim_quantity_not_supported",
        "evidence_claim_empty",
        "signal_update_diff_metadata_invalid",
    }
)

def is_mechanical_issue(issue: Any) -> bool:
    """Recognize only typed unique fallback authority, including mixed failures."""
    if issue.code in MECHANICAL_FALLBACK_CODES:
        return True
    if issue.code == "research_need_transition_invalid":
        return issue.repair_context.get("required_action") in {
            "restore_exactly", "replace_with_exact_residual", "remove_exact_target",
        }
    if issue.code == "stale_resolved_need_retained":
        return issue.repair_context.get("mechanical_action") == "remove_unsupported_resolution"
    if issue.code == "routing_answer_conflict":
        return issue.repair_context.get("mechanical_action") == "context_only_selection"
    if issue.code == "basic_literal_not_grounded":
        return issue.repair_context.get("mechanical_action") == "remove_runtime_control_citation"
    if issue.code == "source_json_literal_not_exact":
        return issue.repair_context.get("mechanical_action") == "restore_source_json_literal"
    return False


def unique_json_source_literal(text: str, sources: Any) -> str | None:
    """Return one complete, strictly equivalent original from an owning scope.

    Example: ``unique_json_source_literal('{"b":2,"a":1}', ['{"a":1,"b":2}'])``.
    Owners supply only visible originals from the same case/document. Distinct
    byte originals with equal structures are ambiguous; identical repeats are not.
    """

    def keys(pairs: list[tuple[str, Any]], *, repeated_identical: bool) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                if not repeated_identical or json.dumps(result[key], sort_keys=True, allow_nan=False) != json.dumps(value, sort_keys=True, allow_nan=False):
                    raise ValueError("ambiguous duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON number: {value}")

    def canonical(value: str, *, repeated_identical: bool = False) -> str | None:
        try:
            decoded = json.loads(value, object_pairs_hook=lambda pairs: keys(pairs, repeated_identical=repeated_identical),
                                 parse_constant=reject_constant)
            if not isinstance(decoded, (dict, list)):
                return None
            return json.dumps(decoded, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError, OverflowError, RecursionError):
            return None

    expected = canonical(text, repeated_identical=True)
    if expected is None:
        return None
    matches = {source for source in sources
               if isinstance(source, str) and canonical(source) == expected}
    return next(iter(matches)) if len(matches) == 1 else None


_SUCCESS_COUNTERPART = {
    "why_prediction_failed": "decision_drivers",
    "failed_patterns": "successful_patterns",
    "false_positive_patterns": "successful_patterns",
    "false_negative_patterns": "successful_patterns",
}
_FAILURE_COUNTERPART = {
    "successful_patterns": "failed_patterns",
    "decision_drivers": "why_prediction_failed",
}
def _derive_text_array_fields() -> tuple[str, ...]:
    """Derive the research-state text-array fields from the owning model.

    Single source of truth: adding a ``tuple[str, ...]`` field to
    ``ResearchState`` extends the repairs automatically instead of
    drifting a copied list here.
    """

    import dataclasses
    import inspect
    import typing

    from stock_opportunity_agent.research.evolution_core import ResearchState

    module = inspect.getmodule(ResearchState)
    scope = vars(module)
    fields = []
    for field in dataclasses.fields(ResearchState):
        annotation = field.type
        if isinstance(annotation, str):
            try:
                annotation = eval(annotation, scope)  # noqa: S307
            except Exception:
                continue
        args = typing.get_args(annotation)
        if (
            typing.get_origin(annotation) is tuple
            and len(args) == 2
            and args[0] is str
            and args[1] is Ellipsis
        ):
            fields.append(field.name)
    return tuple(fields)


_TEXT_ARRAY_FIELDS = _derive_text_array_fields()


@dataclass(frozen=True)
class RepairOp:
    """One typed mechanical repair, auditable and replayable."""

    level: str
    action: str
    path: str
    before: Any = None
    after: Any = None


def strip_json_fences(text: str) -> str:
    """Remove markdown code fences around a JSON payload."""

    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def complete_truncated_json(text: str) -> tuple[str, list[RepairOp]] | None:
    """Deterministically close a JSON object truncated at the output ceiling.

    Applicable only when the text starts a JSON object/array and the final
    character is not a closing bracket — the signature of an output-budget
    cut. Open strings are closed, dangling commas or colons are dropped,
    and the open bracket stack is closed in order. The result is a
    *candidate*: the caller must still parse and fully validate it.
    """

    candidate = strip_json_fences(text)
    if not candidate or candidate[0] not in "{[":
        return None
    if candidate.rstrip().endswith(("}", "]")):
        return None
    stack: list[str] = []
    in_string = False
    escaped = False
    for character in candidate:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "{[":
            stack.append(character)
        elif character in "}]":
            if stack:
                stack.pop()
    if in_string:
        candidate += '"'
    while candidate and candidate[-1] in ",:":
        candidate = candidate[:-1]
    closers = {"{": "}", "[": "]"}
    while stack:
        candidate += closers[stack.pop()]
    ops = [
        RepairOp(
            level=L0_JSON,
            action="complete_truncated_json",
            path="$",
            before=len(text),
            after=len(candidate),
        )
    ]
    return candidate, ops


def _repairable_reflection_package(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("reflection_items"), list)
    )


def claim_refs_into_source_refs(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], list[RepairOp]]:
    """Register claim-cited resolvable refs into the item's source_refs.

    The rejection "outcome claim must cite a supporting source" fires when
    the model cites a lower-level item in a claim but forgets to re-list it
    in source_refs. The repair is unique: union the claim refs in. It is
    applied blindly here; acceptance still requires the full validator.
    """

    ops: list[RepairOp] = []
    items = []
    for index, raw in enumerate(value.get("reflection_items", ())):
        if not isinstance(raw, Mapping) or "outcome_claims" not in raw:
            items.append(raw)
            continue
        claims = raw.get("outcome_claims")
        source_refs = raw.get("source_refs")
        if not isinstance(claims, list) or not isinstance(source_refs, list):
            items.append(raw)
            continue
        claim_refs = {
            claim.get("source_ref")
            for claim in claims
            if isinstance(claim, Mapping)
            and isinstance(claim.get("source_ref"), str)
        }
        missing = claim_refs - set(source_refs)
        if not missing:
            items.append(raw)
            continue
        repaired = dict(raw)
        repaired["source_refs"] = list(source_refs) + sorted(missing)
        ops.append(
            RepairOp(
                level=L2_MECHANICAL,
                action="claim_refs_into_source_refs",
                path=f"reflection_items[{index}].source_refs",
                before=list(source_refs),
                after=repaired["source_refs"],
            )
        )
        items.append(repaired)
    result = dict(value)
    result["reflection_items"] = items
    return result, ops


def split_mixed_axis_items(
    value: Mapping[str, Any],
    level_categories: frozenset[str] | set[str] | None = None,
) -> tuple[dict[str, Any], list[RepairOp]]:
    """Split items whose claims straddle success and failure axes.

    A success/failure-category item may carry claims of only one
    correctness sign. When the model authored one straddling item (binary
    correct, magnitude wrong — the audit's recurring mixed outcome), the
    fixed repair is to split it into its two single-axis forms: claims are
    distributed by sign, brief/detail/scope are retained on both sides, and
    each side takes its level's fixed counterpart category. Nothing is
    invented; the split is unique.
    """

    ops: list[RepairOp] = []
    items: list[Any] = []
    for index, raw in enumerate(value.get("reflection_items", ())):
        if not isinstance(raw, Mapping):
            items.append(raw)
            continue
        category = raw.get("category")
        claims = raw.get("outcome_claims")
        if not isinstance(claims, list) or not claims:
            items.append(raw)
            continue
        correct_flags = [
            isinstance(claim, Mapping) and claim.get("correct") is True
            for claim in claims
        ]
        if all(correct_flags) or not any(correct_flags):
            items.append(raw)
            continue
        if category in _SUCCESS_COUNTERPART:
            keep_sign, split_category = False, _SUCCESS_COUNTERPART[category]
        elif category in _FAILURE_COUNTERPART:
            keep_sign, split_category = True, _FAILURE_COUNTERPART[category]
        else:
            items.append(raw)
            continue
        if (
            level_categories is not None
            and split_category not in level_categories
        ):
            # The counterpart category does not exist at this level; the
            # full validator would reject the split, so leave the row for
            # the next rung instead of producing a known-invalid shape.
            items.append(raw)
            continue
        kept_claims = [
            claim
            for claim, flag in zip(claims, correct_flags)
            if flag == keep_sign
        ]
        moved_claims = [
            claim
            for claim, flag in zip(claims, correct_flags)
            if flag != keep_sign
        ]
        kept = dict(raw)
        kept["outcome_claims"] = kept_claims
        moved = dict(raw)
        moved["category"] = split_category
        moved["outcome_claims"] = moved_claims
        items.append(kept)
        items.append(moved)
        ops.append(
            RepairOp(
                level=L2_MECHANICAL,
                action="split_mixed_axis_item",
                path=f"reflection_items[{index}]",
                before={"category": category, "claims": len(claims)},
                after={
                    "kept": {"category": category, "claims": len(kept_claims)},
                    "split": {
                        "category": split_category,
                        "claims": len(moved_claims),
                    },
                },
            )
        )
    result = dict(value)
    result["reflection_items"] = items
    return result, ops


def scope_narrow_to_support(
    value: Mapping[str, Any],
    resolver: Callable[[str], Mapping[str, Any] | None],
) -> tuple[dict[str, Any], list[RepairOp]]:
    """Narrow a reflection item's declared scope to its supporting closure.

    When an item cites lower-level sources but declares a broader
    case/Plan scope than those sources cover, the unique mechanical repair
    is to narrow the declared scope to the closure of its resolvable
    citations (supporting sources and claim citations). No citation is
    invented and no claim text changes; the validator re-adjudicates.
    """

    ops: list[RepairOp] = []
    items = []
    for index, raw in enumerate(value.get("reflection_items", ())):
        if not isinstance(raw, Mapping):
            items.append(raw)
            continue
        refs = set(raw.get("source_refs") or ())
        for claim in raw.get("outcome_claims") or ():
            if isinstance(claim, Mapping) and isinstance(
                claim.get("source_ref"), str
            ):
                refs.add(claim["source_ref"])
        covered_cases: set[str] = set()
        covered_plans: set[str] = set()
        for ref in sorted(refs):
            row = resolver(ref)
            if not isinstance(row, Mapping):
                continue
            covered_cases.update(row.get("case_refs") or ())
            covered_plans.update(row.get("plan_refs") or ())
        scope = raw.get("scope")
        if not isinstance(scope, Mapping):
            items.append(raw)
            continue
        # Union semantics: the declared scope becomes exactly what the
        # item's citations cover. Declared-but-uncited entries are dropped
        # and covered-but-undeclared entries are added — the model cited
        # the sources, so their closure is the scope it can claim.
        case_refs = sorted(covered_cases)
        plan_refs = sorted(covered_plans)
        if case_refs == list(scope.get("case_refs") or ()) and plan_refs == list(
            scope.get("plan_refs") or ()
        ):
            items.append(raw)
            continue
        repaired = dict(raw)
        repaired["scope"] = {
            **scope,
            "case_refs": case_refs,
            "plan_refs": plan_refs,
        }
        ops.append(
            RepairOp(
                level=L2_MECHANICAL,
                action="scope_narrow_to_support",
                path=f"reflection_items[{index}].scope",
                before={
                    "case_refs": list(scope.get("case_refs") or ()),
                    "plan_refs": list(scope.get("plan_refs") or ()),
                },
                after={"case_refs": case_refs, "plan_refs": plan_refs},
            )
        )
        items.append(repaired)
    result = dict(value)
    result["reflection_items"] = items
    return result, ops


def _repairable_research_state(value: Any) -> bool:
    return isinstance(value, Mapping) and "next_information_needs" in value


def drop_duplicate_open_questions(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], list[RepairOp]]:
    """Remove open questions that repeat a need byte-for-byte.

    The contract forbids repeating an exact next_information_needs string
    in open_questions; the unique repair is removal of the duplicate row.
    """

    ops: list[RepairOp] = []
    needs = {
        row.strip()
        for row in (value.get("next_information_needs") or ())
        if isinstance(row, str)
    }
    questions = value.get("open_questions")
    if not isinstance(questions, list) or not questions:
        return dict(value), ops
    kept: list[Any] = []
    for index, row in enumerate(questions):
        if isinstance(row, str) and row.strip() in needs:
            ops.append(
                RepairOp(
                    level=L2_MECHANICAL,
                    action="drop_duplicate_open_question",
                    path=f"open_questions[{index}]",
                    before=row,
                )
            )
            continue
        kept.append(row)
    result = dict(value)
    result["open_questions"] = kept
    return result, ops


def drop_empty_text_rows(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], list[RepairOp]]:
    """Remove empty-string rows from research-state text arrays."""

    ops: list[RepairOp] = []
    result = dict(value)
    for field_name in _TEXT_ARRAY_FIELDS:
        rows = value.get(field_name)
        if not isinstance(rows, list) or not rows:
            continue
        kept = []
        for index, row in enumerate(rows):
            if isinstance(row, str) and not row.strip():
                ops.append(
                    RepairOp(
                        level=L2_MECHANICAL,
                        action="drop_empty_text_row",
                        path=f"{field_name}[{index}]",
                        before="",
                    )
                )
                continue
            kept.append(row)
        if len(kept) != len(rows):
            result[field_name] = kept
    return result, ops


def flatten_text_array_objects(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], list[RepairOp]]:
    """Flatten evidence objects misplaced into research-state text arrays.

    A text-array row written as an evidence object has exactly one
    prose-bearing field by schema: ``claim`` when present, otherwise the
    sole string field. Flattening to that string is the unique
    non-inventive action; rows with several string candidates stay for
    the LLM correction.
    """

    ops: list[RepairOp] = []
    result = dict(value)
    for field_name in _TEXT_ARRAY_FIELDS:
        rows = value.get(field_name)
        if not isinstance(rows, list):
            continue
        flattened: list[Any] = []
        for index, row in enumerate(rows):
            replacement = row
            if isinstance(row, Mapping):
                claim = row.get("claim")
                if isinstance(claim, str) and claim.strip():
                    replacement = claim
                else:
                    strings = [
                        item
                        for item in row.values()
                        if isinstance(item, str) and item.strip()
                    ]
                    replacement = strings[0] if len(strings) == 1 else row
            if replacement is not row:
                ops.append(
                    RepairOp(
                        level=L2_MECHANICAL,
                        action="flatten_text_array_object",
                        path=f"{field_name}[{index}]",
                        before=dict(row),
                        after=replacement,
                    )
                )
            flattened.append(replacement)
        if any(item is not orig for item, orig in zip(flattened, rows)):
            result[field_name] = flattened
    return result, ops


# Open registry: (shape predicate, chain factory). New output schemas
# register a repair family here instead of editing the dispatcher; the
# frontier and salvage path both consult the same registry.
REPAIR_CHAIN_REGISTRY: list[
    tuple[
        Callable[[Any], bool],
        Callable[
            [Any, Callable[[str], Mapping[str, Any] | None] | None],
            list[Callable[[Mapping[str, Any]], tuple[dict[str, Any], list[RepairOp]]]],
        ],
    ]
] = []


def register_repair_chain(predicate, factory) -> None:
    """Register one repair family for a new output shape."""

    REPAIR_CHAIN_REGISTRY.append((predicate, factory))


def _reflection_chain(value, resolver, level_categories=None):
    chain: list[Any] = [claim_refs_into_source_refs]
    if resolver is not None:
        chain.append(lambda v: scope_narrow_to_support(v, resolver))
    chain.append(
        lambda v: split_mixed_axis_items(v, level_categories)
    )
    return chain


def _research_state_chain(value, resolver, level_categories=None):
    return [
        flatten_text_array_objects,
        drop_duplicate_open_questions,
        drop_empty_text_rows,
    ]


register_repair_chain(_repairable_reflection_package, _reflection_chain)
register_repair_chain(_repairable_research_state, _research_state_chain)


def mechanical_repairs_for(
    value: Any,
    resolver: Callable[[str], Mapping[str, Any] | None] | None = None,
    level_categories: frozenset[str] | set[str] | None = None,
) -> list[Callable[[Mapping[str, Any]], tuple[dict[str, Any], list[RepairOp]]]]:
    """Return the applicable L2 repair chain for one parsed output."""

    for predicate, factory in REPAIR_CHAIN_REGISTRY:
        if predicate(value):
            return factory(value, resolver, level_categories)
    return []


def mechanical_repair_candidate(
    value: Mapping[str, Any],
    resolver: Callable[[str], Mapping[str, Any] | None] | None = None,
    level_categories: frozenset[str] | set[str] | None = None,
) -> tuple[dict[str, Any], list[RepairOp]]:
    """Return a transformed candidate and operations without claiming validity.

    Consumers revalidate it and retain partial progress as a correction base.
    The original response remains untouched, including when no repair applies.
    """
    from copy import deepcopy

    current = deepcopy(dict(value))
    ops: list[RepairOp] = []
    for repair in mechanical_repairs_for(current, resolver, level_categories):
        current, repair_ops = repair(current)
        ops.extend(repair_ops)
    return dict(current), ops


def apply_mechanical_repairs(
    value: Mapping[str, Any],
    parse: Callable[[Mapping[str, Any]], Any],
    resolver: Callable[[str], Mapping[str, Any] | None] | None = None,
    level_categories: frozenset[str] | set[str] | None = None,
) -> tuple[Any, list[RepairOp]] | None:
    """Run the L2 chain and accept only a full-validator pass.

    Returns the parsed result plus the repair log when some repair changed
    the object and the complete unchanged validator accepts it; ``None``
    means no repair applied or the repaired object still fails.
    """

    current, ops = mechanical_repair_candidate(value, resolver, level_categories)
    if not ops:
        return None
    try:
        parsed = parse(current)
    except ValidationError:
        return None
    return parsed, ops
