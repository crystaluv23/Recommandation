"""Sourced, bounded retrospective views over caller-approved anonymous records."""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.memory.knowledge import empty_performance, source_signal_refs
from stock_opportunity_agent.research.cross_round_reflection import validate_prediction_comparison
from stock_opportunity_agent.signal_library import validate_signal_classification_contract


_ROLES = frozenset({"proposer", "plan_critic", "round_reflector", "slow_reflection", "signal_mining", "signal_update"})
_FORBIDDEN = frozenset({"raw_info", "basic_info_bundle", "final_context", "final_state", "initial_state", "company_id", "case_id", "identity_aliases", "trajectories"})
_CATEGORIES = {
    "case": frozenset({"decision_drivers", "why_prediction_failed", "misleading_signals", "ignored_evidence", "missing_information", "plan_issues"}),
    "plan": frozenset({"successful_patterns", "failed_patterns", "repeated_failure_modes", "misleading_signals", "missing_information_needs", "next_explorations"}),
    "round": frozenset({"successful_patterns", "failed_patterns", "false_positive_patterns", "false_negative_patterns", "useful_signals", "suspicious_signals", "missing_capabilities", "search_implications"}),
    "cross_round": frozenset({"prediction_changes", "comparison_analysis", "technical_diagnostics"}),
}
_OUTCOME_CATEGORIES = frozenset({"successful_patterns", "failed_patterns", "why_prediction_failed", "decision_drivers", "false_positive_patterns", "false_negative_patterns"})
_FACT_FIELDS = ("candidate_judgment_feedback", "magnitude_feedback", "jev_decision_feedback", "technical_exclusion")

# These are evaluation assertions, not numbers appearing in company evidence.
# Keeping the grammar bounded avoids treating a forecast or a class label as
# a measured statistic. Exact source membership still does not verify prose.
_STATISTIC_NAMES = {
    "binary_f1": r"binary[_ ]f1",
    "binary_precision": r"(?:binary[_ ])?precision",
    "binary_recall": r"(?:binary[_ ])?recall",
    "magnitude_macro_f1": r"magnitude[_ ]macro[_ ]f1",
    "conditional_accuracy_on_tp": r"conditional[_ ]accuracy(?:[_ ]on[_ ](?:tp|true positives))?",
    "underestimate_count": r"underestimate[_ ]count",
    "overestimate_count": r"overestimate[_ ]count",
    "missed_surge_count": r"missed[_ ]surge[_ ]count",
    "technical_completion_rate": r"technical[_ ]completion[_ ]rate",
    "research_completed_case_count": r"research[_ ]completed[_ ]case[_ ]count",
    "scored_case_count": r"scored[_ ]case[_ ]count",
    "technical_exclusion_count": r"technical[_ ]exclusion[_ ]count",
    "predicted_positive_count": r"predicted[_ ]positive[_ ]count",
    "predicted_2-3x": r"predicted[_ ]2-3x",
    "predicted_3-10x": r"predicted[_ ]3-10x",
    "predicted_10x+": r"predicted[_ ]10x\+",
    "true_positive": r"true[_ ]positive(?:[_ ]count)?",
    "true_negative": r"true[_ ]negative(?:[_ ]count)?",
    "false_positive": r"false[_ ]positive(?:[_ ]count)?",
    "false_negative": r"false[_ ]negative(?:[_ ]count)?",
}
_STATISTIC_NUMBER = r"[-+]?\d+(?:\.\d+)?%?"
_STATISTIC_PATTERNS = tuple(
    (key, re.compile(r"\b" + name + r"\s*(?:=|:|of\b|is\b|was\b)\s*(" + _STATISTIC_NUMBER + r")", re.I))
    for key, name in _STATISTIC_NAMES.items()
) + tuple(
    (key, re.compile(r"\b(" + _STATISTIC_NUMBER + r")\s+" + name + r"\b", re.I))
    for key, name in (
        ("underestimate_count", "underestimates"),
        ("overestimate_count", "overestimates"),
        ("false_positive", "false positives"),
        ("false_negative", "false negatives"),
        ("predicted_positive_count", "(?:positive predictions|predicted positives)"),
    )
)
_FULL_COMPLETION = re.compile(r"\b(?:full|complete|100%)(?:\s+technical|\s+research)[ -]completion\b", re.I)
_ROUND_POOLING = re.compile(
    r"\b(?:combined|pooled|aggregate(?:d)?)\s+(?:magnitude_diagnostics|diagnostics|statistics|counts|results|evaluation)\s+(?:for|across|of)\s+(?:the\s+)?(?:round|(?:both|two|all)\s+(?:child\s+)?plans)\b|"
    r"\b(?:round[- ]wide|pooled[- ]round)\s+(?:diagnostics|statistics|counts|results)\b", re.I,
)
_MULTI_PLAN = re.compile(r"\b(?:both|two|all|across(?:\s+the)?(?:\s+newly sampled)?(?:\s+child)?)\s+(?:child\s+)?plans\b", re.I)


def _numeric_leaves(value: Mapping[str, Any], prefix: str = "") -> dict[str, float | int]:
    result = {}
    for key, item in value.items():
        path = prefix + str(key)
        if isinstance(item, Mapping):
            result.update(_numeric_leaves(item, path + "."))
        elif type(item) in (int, float) and math.isfinite(item):
            result[path] = item
    return result


def _statistic_assertions(text: str) -> list[tuple[str, str, int]]:
    return [(key, match.group(1), match.start()) for key, pattern in _STATISTIC_PATTERNS for match in pattern.finditer(text)]


def _has_statistics(text: str) -> bool:
    return bool(_statistic_assertions(text) or _completion_claims(text))


def _completion_claims(text: str) -> list[Any]:
    return [match for match in _FULL_COMPLETION.finditer(text) if not re.search(
        r"\b(?:not|without|failed to|target|aim for)\b[^.;]{0,35}$",
        text[max(0, match.start() - 50):match.start()], re.I,
    )]


def _rounded_statistic_matches(token: str, expected: float | int) -> bool:
    scaled = float(token.rstrip("%")) / (100 if token.endswith("%") else 1)
    decimal_places = len(token.rstrip("%").partition(".")[2])
    tolerance = 0.5 * 10 ** (-decimal_places) / (100 if token.endswith("%") else 1)
    # Integer counts are exact; displayed rates may be rounded.
    if type(expected) is int or ("." not in token and not token.endswith("%")):
        return scaled == expected
    return abs(scaled - expected) <= tolerance + 1e-12

# Ingestion gate: an authored action item may not advise consulting
# information that only exists after the prediction boundary. The scan is
# deliberately narrow and lexical — sources_checked proves provenance, never
# point-in-time executability.
_PIT_INEXECUTABLE_ACTION = re.compile(
    r"(?:post[- ]prediction[- ]time|after\s+the\s+prediction\s+time|"
    r"post[- ]outcome|after\s+outcome\s+reveal|"
    r"(?:realized|subsequent)\s+price\s+action)",
    re.IGNORECASE,
)

_MANDATORY_PROOF_CONDITION = re.compile(
    r"\b(?:requires?|required|must\s+(?:have|provide|show|demonstrate)|"
    r"only\s+(?:if|when)|unless)\b[^.;]{0,320}?"
    r"(?:\b(?:quantified|numeric|numerical|quantitative)\s+"
    r"(?:[\w-]+\s+){0,5}(?:path|bridge|price\s+target)\b|"
    r"\bquantif(?:y|ies)\s+(?:a\s+)?(?:[\w-]+\s+){0,3}(?:path|bridge)\b|"
    r"\b(?:stated|explicit|concrete|demonstrated)\s+(?:[\w-]+\s+){0,4}"
    r"(?:path|bridge)\s+(?:from|to)\b[^.;]{0,100}\b(?:price|threshold|doubling|2x)\b|"
    r"\b(?:projection|forecast|price\s+target)\b[^.;]{0,100}"
    r"\b(?:tied|linked|connected)\s+to\b[^.;]{0,60}"
    r"\b(?:doubling|2x|share[- ]price|price\s+threshold)\b|"
    r"\b(?:guaranteed?|proven|certain)\s+(?:[\w-]+\s+){0,3}"
    r"(?:doubling|2x|price\s+outcome|share[- ]price\s+outcome)\b)",
    re.IGNORECASE,
)
_OPPORTUNITY_JUDGMENT = re.compile(
    r"\b(?:surge|doubling|2x|positive\s+judgment|candidate\s+judgment|"
    r"positive\s+opportunity)\b", re.IGNORECASE,
)
_ABSENT_PROOF_DOWNGRADE = re.compile(
    r"\b(?:if|when)\s+(?:no|without)\b[^.;]{0,160}\b(?:path|bridge)\b"
    r"(?P<link>[^.;]{0,100}?)\b(?:record|downgrade|classify|label)\s+"
    r"(?:(?:the|a|this)\s+)?(?:call|judgment|candidate)?\s*(?:as|to)?\s*"
    r"(?:non[- ]surge|unlikely|negative)\b", re.I,
)
_ABSENT_PROJECTION_CAP = re.compile(
    r"\b(?:if|when)\s+(?:no|without)\b[^.;]{0,60}"
    r"\b(?:forward\s+projection|price\s+(?:projection|forecast|target))\b"
    r"(?P<link>[^.;]{0,240}?)\bcap\s+(?:(?:the|a|this)\s+)?"
    r"(?:surge|positive|candidate)\s+judgment\b", re.I,
)
_FACT_WEIGHT_INFERENCE = re.compile(
    r"\b(?:under|over)[- ]?weight(?:ed|ing)\b|"
    r"\bdid\s+not\s+reflect\s+(?:the\s+)?weight\b", re.I,
)
_FACT_SUFFICIENCY_INFERENCE = re.compile(
    r"\b(?:evidence|signals?|reasons?|guidance|financing|momentum|catalysts?)\b"
    r"[^;.!?]{0,200}\b(?:was|were|is|are|proved)\s+(?:already\s+)?sufficient\s+"
    r"(?:to\s+)?(?:identify|explain|predict|support|cause|justify|establish)\b"
    r"[^;.!?]{0,80}\b(?:outcome|surge|judgment|prediction)\b", re.I,
)
_INFERENCE_NOT_ESTABLISHED = re.compile(
    r"\b(?:does|do|did)\s+not\s+(?:prove|show|establish|demonstrate)\b|"
    r"\b(?:cannot|can't|could\s+not)\s+(?:prove|show|establish|demonstrate)\b|"
    r"\b(?:not|never)\s+(?:established|proven)\b|"
    r"\b(?:unproven|unverified)\b", re.I,
)


def reflection_fact_inference_fields(item: Mapping[str, Any], *, detail_field: str = "detail") -> tuple[str, ...]:
    """Locate narrow explanatory claims misclassified as observable facts.

    Outcome correctness and provenance do not establish normative weighting or
    signal sufficiency. No economic interpretation is mechanically substituted.
    """

    if item.get("kind") != "fact":
        return ()
    invalid = []
    for field in ("brief", detail_field):
        text = item.get(field)
        if not isinstance(text, str):
            continue
        clauses = re.split(r"[;!?]|\.(?=\s|$)|\b(?:but|yet|however|although)\b", text, flags=re.I)
        if any(
            (_FACT_WEIGHT_INFERENCE.search(clause) or _FACT_SUFFICIENCY_INFERENCE.search(clause))
            and not _INFERENCE_NOT_ESTABLISHED.search(clause)
            for clause in clauses
        ):
            invalid.append(field)
    return tuple(invalid)


def violates_opportunity_proof_gate(text: str) -> bool:
    """Recognize affirmative mandatory-proof gates, not optional analysis.

    The narrow policy is shared by new action ingestion and Plan validation;
    it does not claim to decide arbitrary economic reasoning correctness.
    """

    for match in _MANDATORY_PROOF_CONDITION.finditer(text):
        prefix = text[max(0, match.start() - 40):match.start()]
        if re.search(r"\b(?:not|never|without)\s*$", prefix, re.IGNORECASE):
            continue
        # Ordinary quantified business analysis in a neighboring sentence is
        # not a condition on the fixed screening judgment.
        sentence_start = max(text.rfind(mark, 0, match.start()) for mark in ".!?") + 1
        endings = [text.find(mark, match.end()) for mark in ".!?"]
        sentence_end = min((end for end in endings if end >= 0), default=len(text))
        scope = text[sentence_start:sentence_end]
        if _OPPORTUNITY_JUDGMENT.search(scope):
            return True
    for match in _ABSENT_PROOF_DOWNGRADE.finditer(text):
        prefix = text[max(0, match.start() - 60):match.start()]
        link = match.group("link")
        # A business milestone path is not a mandatory share-price proof.
        if (re.match(r"\s+(?:to|towards?|for)\b", link, re.I)
                and not re.search(r"\b(?:price|threshold|doubling|2x)\b", link, re.I)):
            continue
        if re.search(r"\b(?:not|never)\s+(?:\w+\s+){0,5}['\"]?\s*$", prefix, re.I):
            continue
        if re.search(r"\b(?:not|never|may|might|consider|whether)\b", link, re.I):
            continue
        return True
    for match in _ABSENT_PROJECTION_CAP.finditer(text):
        prefix = text[max(0, match.start() - 60):match.start()]
        link = match.group("link")
        if not re.search(r"\bbinding\s+evidence\s+gap\b", link, re.I):
            continue
        if re.search(r"\b(?:not|never)\s+(?:\w+\s+){0,5}['\"]?\s*$", prefix, re.I):
            continue
        if re.search(r"\b(?:not|never|may|might|consider|whether)\b", link, re.I):
            continue
        return True
    return False


def _reject_pit_inexecutable_action(
    value: Mapping[str, Any],
    invalid: Any,
    fields: tuple[str, ...],
) -> None:
    for field_name in fields:
        text = value.get(field_name)
        if isinstance(text, str) and _PIT_INEXECUTABLE_ACTION.search(text):
            invalid(
                "action reflection advises consulting post-prediction-time "
                "information; research actions must be executable from "
                "facts available by the prediction boundary",
                field_name,
                ("kind",),
            )


class ReflectionValidationError(ValidationError):
    """A role adapter may translate this precise path into scoped correction."""

    def __init__(self, message: str, *, path: str, dependency_paths: tuple[str, ...] = (), invalid_container_paths: tuple[str, ...] = (), allowed_append_values: Mapping[str, Iterable[str]] | None = None) -> None:
        super().__init__(message)
        self.path = path
        self.dependency_paths = dependency_paths
        self.invalid_container_paths = invalid_container_paths
        self.allowed_append_values = {key: list(values) for key, values in (allowed_append_values or {}).items()}


def validate_source_snapshot(identity: Any, snapshot: Any) -> dict[str, Any]:
    """Validate runtime-owned anonymous facts retained with case reflection."""
    if not isinstance(identity, str) or not identity.strip() or not isinstance(snapshot, Mapping):
        raise ValidationError("reflection source identity and snapshot are both required")
    if set(snapshot) - {"source_identity", *_FACT_FIELDS} or snapshot.get("source_identity") != identity:
        raise ValidationError("reflection source snapshot has invalid identity or fields")
    result = deepcopy(dict(snapshot))
    _approved(result)
    return result


def _bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _ref(prefix: str, value: Any) -> str:
    return prefix + ":" + canonical_json_hash(value)


def _strings(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValidationError(f"reflection {name} must contain nonempty strings")
    if len(set(value)) != len(value):
        raise ValidationError(f"reflection {name} contains duplicate references or entries")
    return tuple(value)


def _approved(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in _FORBIDDEN:
                raise ValidationError(f"retrospective source contains forbidden context field: {key}")
            _approved(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _approved(child)


def validate_signal_classification_context(value: Any) -> tuple[dict[str, Any], ...]:
    """Validate saved round-owned declarations without inferring their meaning."""

    if not isinstance(value, (list, tuple)):
        raise ValidationError("Signal classification context must be an array")
    rows, seen = [], set()
    for row in value:
        if (not isinstance(row, Mapping)
                or set(row) != {"signal_round", "signal_ref", "contract"}
                or type(row["signal_round"]) is not int or row["signal_round"] < 1
                or not isinstance(row["signal_ref"], str)
                or re.fullmatch(r"[a-z0-9][a-z0-9_:-]*:v[1-9][0-9]*", row["signal_ref"]) is None):
            raise ValidationError("Signal classification context round/version is invalid")
        key = (row["signal_round"], row["signal_ref"])
        if key in seen:
            raise ValidationError("Signal classification context has duplicate round/version")
        seen.add(key)
        contract = validate_signal_classification_contract(row["contract"], signal_ref=row["signal_ref"])
        rows.append({"signal_round": key[0], "signal_ref": key[1], "contract": contract})
    return tuple(rows)


@dataclass(frozen=True)
class ReflectionItem:
    """One immutable authored learning item; checked sources do not prove truth."""

    item_ref: str
    level: str
    owner_ref: str
    category: str
    kind: str
    brief: str
    detail: str
    scope: Mapping[str, Any]
    limitations: tuple[str, ...]
    source_refs: tuple[str, ...]
    counter_refs: tuple[str, ...] = ()
    outcome_claims: tuple[Mapping[str, Any], ...] = ()
    evidence_status: str = "sources_checked"
    related_signal_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.level not in _CATEGORIES or self.category not in _CATEGORIES[self.level]:
            raise ValidationError("reflection item level/category is invalid")
        if self.kind not in {"fact", "hypothesis", "action"}:
            raise ValidationError("reflection item kind is invalid")
        if self.evidence_status not in {"sources_checked", "legacy_unreviewed"}:
            raise ValidationError("model reflection cannot claim verified truth")
        if not self.owner_ref or not self.brief.strip() or not self.detail.strip():
            raise ValidationError("reflection item requires owner, brief and detail")
        if set(self.scope) != {"case_refs", "plan_refs", "conditions"} or not isinstance(self.scope["conditions"], str):
            raise ValidationError("reflection item scope requires case_refs, plan_refs and conditions")
        scope = {
            "case_refs": list(_strings(self.scope["case_refs"], "scope.case_refs")),
            "plan_refs": list(_strings(self.scope["plan_refs"], "scope.plan_refs")),
            "conditions": self.scope["conditions"],
        }
        object.__setattr__(self, "scope", scope)
        for name in ("limitations", "source_refs", "counter_refs"):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        if not self.source_refs:
            raise ValidationError("reflection item requires supporting sources")
        object.__setattr__(self, "outcome_claims", tuple(deepcopy(dict(x)) for x in self.outcome_claims))
        related = _strings(self.related_signal_refs, "related_signal_refs")
        if len(related) > 12 or any(re.fullmatch(r"[a-z0-9_:-]+:v[1-9][0-9]*", ref) is None for ref in related):
            raise ValidationError("related_signal_refs must name bounded exact versions")
        object.__setattr__(self, "related_signal_refs", related)
        _approved(self._content())
        if self.item_ref != _ref("reflection", self._content()):
            raise ValidationError("reflection item content hash mismatch")

    def _content(self) -> dict[str, Any]:
        return {
            "level": self.level, "owner_ref": self.owner_ref,
            "category": self.category, "kind": self.kind,
            "brief": self.brief, "detail": self.detail,
            "scope": deepcopy(dict(self.scope)), "limitations": list(self.limitations),
            "source_refs": list(self.source_refs), "counter_refs": list(self.counter_refs),
            "outcome_claims": [deepcopy(dict(x)) for x in self.outcome_claims],
            "evidence_status": self.evidence_status,
            **({"related_signal_refs": list(self.related_signal_refs)} if self.related_signal_refs else {}),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"item_ref": self.item_ref, **self._content()}

    def brief_dict(self) -> dict[str, Any]:
        """Keep applicability, limitations and counterreferences beside the brief."""
        value = self.to_dict()
        value.pop("detail")
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReflectionItem":
        return cls(**dict(value))


def reflection_items_from_dict(value: Any) -> tuple[ReflectionItem, ...]:
    """Load additive archived items without interpreting legacy prose."""
    if not isinstance(value, (tuple, list)) or any(not isinstance(x, Mapping) for x in value):
        raise ValidationError("reflection_items must be objects")
    items = tuple(ReflectionItem.from_dict(x) for x in value)
    if len({x.item_ref for x in items}) != len(items):
        raise ValidationError("duplicate reflection item")
    return items


class ReflectionMemoryIndex:
    """Reference resolver with no filesystem, provider or blind-role access.

    Example: ``index.read_refs([ref], role="proposer", max_bytes=12000)``.
    Caller-owned role projections must already be anonymous and committed.
    """

    def __init__(self, *, performance_profiles: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self._sources: dict[str, dict[str, Any]] = {}
        self._items: dict[str, ReflectionItem] = {}
        self._preferred: list[str] = []
        self._performance_profiles = deepcopy(dict(performance_profiles or {}))
        _approved(self._performance_profiles)

    def _source(self, value: Mapping[str, Any], *, level: str, case_refs: Iterable[str] = (), plan_refs: Iterable[str] = (), canonical_outcomes: Mapping[str, Any] | None = None) -> str:
        content = deepcopy(dict(value))
        _approved(content)
        ref = _ref("reflection_source", {"level": level, "content": content})
        source = self._sources.get(ref)
        if source is None:
            source = {"source_ref": ref, "level": level, "content": content, "case_refs": [], "plan_refs": [], "canonical_outcomes": deepcopy(dict(canonical_outcomes or {}))}
            self._sources[ref] = source
        source["case_refs"] = sorted(set(source["case_refs"]) | set(case_refs))
        source["plan_refs"] = sorted(set(source["plan_refs"]) | set(plan_refs))
        return ref

    def _item(self, item: ReflectionItem) -> None:
        self._items[item.item_ref] = item
        self._sources[item.item_ref] = {
            "source_ref": item.item_ref, "level": item.level,
            "content": item.to_dict(), "case_refs": list(item.scope["case_refs"]),
            "plan_refs": list(item.scope["plan_refs"]), "canonical_outcomes": {},
            "legacy_unreviewed": item.evidence_status == "legacy_unreviewed",
        }

    def _layer(self, value: Mapping[str, Any], *, level: str, owner_ref: str, source_refs: tuple[str, ...], case_refs: tuple[str, ...], plan_refs: tuple[str, ...]) -> None:
        if "reflection_items" in value:
            for item in reflection_items_from_dict(value["reflection_items"]):
                if item.level != level:
                    raise ValidationError("stored reflection item is outside its containing level")
                if item.evidence_status == "sources_checked":
                    authored = item.to_dict()
                    for field in ("item_ref", "owner_ref", "level", "evidence_status"):
                        authored.pop(field)
                    # Immutable pre-contract items retain their original
                    # provenance checks; their new-view status is explicit.
                    self._create_items((authored,), level=level, owner_ref=item.owner_ref,
                                       check_statistics=False, check_inferences=False, check_proof_policy=False)
                self._item(item)
            selected = _strings(value.get("selected_reflection_refs", ()), "selected_reflection_refs")
            for ref in selected:
                if ref not in self._items:
                    raise ValidationError("selected reflection ref is absent from lower layers")
                if tuple(_CATEGORIES).index(self._items[ref].level) >= tuple(_CATEGORIES).index(level):
                    raise ValidationError("selected reflection ref must retain a lower-level item")
                self._preferred.append(ref)
            return
        for category in sorted(_CATEGORIES[level]):
            values = value.get(category, ())
            if not isinstance(values, (tuple, list)):
                continue
            for index, text in enumerate(values):
                if not isinstance(text, str) or not text.strip():
                    continue
                origin = self._source({"category": category, "index": index, "text": text, "owner_ref": owner_ref}, level=level, case_refs=case_refs, plan_refs=plan_refs)
                content = {
                    "level": level, "owner_ref": owner_ref, "category": category,
                    "kind": "action" if category in {"next_explorations", "search_implications", "plan_issues"} else "hypothesis",
                    "brief": text, "detail": text,
                    "scope": {"case_refs": list(case_refs), "plan_refs": list(plan_refs), "conditions": "Legacy original text; scope is its containing record, not verified support."},
                    "limitations": ["legacy_unreviewed: no authored brief or per-item source attribution"],
                    "source_refs": [origin, *source_refs], "counter_refs": [],
                    "outcome_claims": [], "evidence_status": "legacy_unreviewed",
                }
                self._item(ReflectionItem.from_dict({"item_ref": _ref("reflection", content), **content}))

    def _cases(self, rows: Iterable[Mapping[str, Any]], owner_ref: str) -> tuple[str, ...]:
        cases = []
        for position, raw in enumerate(rows, 1):
            row = deepcopy(dict(raw))
            classification_context = validate_signal_classification_context(row["signal_classification_context"]) if "signal_classification_context" in row else ()
            if "signal_classification_context" in row and row.get("technical_exclusion") is not None:
                raise ValidationError("technical exclusion cannot carry Signal classification context")
            reflection = row.get("self_reflection", {})
            identity = row.get("source_identity") or (reflection.get("source_identity") if isinstance(reflection, Mapping) else None)
            snapshot = reflection.get("source_snapshot") if isinstance(reflection, Mapping) else None
            if identity is not None:
                facts = validate_source_snapshot(identity, snapshot or {"source_identity": identity, **{key: row[key] for key in _FACT_FIELDS if row.get(key) is not None}})
                for key in _FACT_FIELDS:
                    if row.get(key) is not None and key in facts and row[key] != facts[key]:
                        raise ValidationError("saved reflection facts differ from canonical case feedback")
                case_ref = identity
            else:
                case_ref = _ref("reflection_case", {"owner": owner_ref, "case_index": row.get("case_index", position), "original": row})
                facts = {"source_identity": case_ref, **{key: row[key] for key in _FACT_FIELDS if row.get(key) is not None}}
            cases.append(case_ref)
            plan_scope = () if owner_ref == case_ref else (owner_ref,)
            technical = bool(facts.get("technical_exclusion"))
            feedback = facts.get("candidate_judgment_feedback", {})
            magnitude = facts.get("magnitude_feedback", {})
            outcomes = {
                "technical_exclusion": technical,
                "binary": feedback.get("binary_correct"),
                "magnitude": magnitude.get("magnitude_correct") if magnitude.get("magnitude_applicable") else None,
            }
            fact_ref = self._source(facts, level="case", case_refs=(case_ref,), plan_refs=plan_scope, canonical_outcomes=outcomes)
            original_ref = self._source(row, level="case", case_refs=(case_ref,), plan_refs=plan_scope, canonical_outcomes=outcomes)
            for declaration in classification_context:
                ref = self._source({"schema_version": "signal-classification-context-v1", **declaration},
                                   level="case", case_refs=(case_ref,), plan_refs=plan_scope)
                self._sources[ref].update(runtime_signal_classification=True,
                    signal_round=declaration["signal_round"], signal_ref=declaration["signal_ref"])
            if isinstance(reflection, Mapping):
                self._layer(reflection, level="case", owner_ref=case_ref, source_refs=(fact_ref, original_ref), case_refs=(case_ref,), plan_refs=plan_scope)
        return tuple(cases)

    @classmethod
    def from_case_rows(cls, rows: Iterable[Mapping[str, Any]], *, owner_ref: str) -> "ReflectionMemoryIndex":
        result = cls()
        result._cases(rows, owner_ref)
        return result

    def register_plan_statistics(self, values: Mapping[str, Any], *, plan_ref: str, plan_id: str) -> None:
        """Register existing runtime aggregates without recomputing scores.

        Critic and archive adapters supply their approved runtime projection.
        Sources bind exact case membership and expose only Plan attribution.
        """
        cases = sorted({ref for source in self._sources.values() if plan_ref in source["plan_refs"] for ref in source["case_refs"]})
        groups = {
            "metrics": (values.get("metrics", {}), "scored_cases", "combined"),
            "magnitude_diagnostics": (values.get("magnitude_diagnostics", {}), "research_completed", "combined"),
            "technical_completion": (values.get("technical_completion", {}), "scored_cases", "combined"),
        }
        evaluation = values.get("evaluation", {})
        for cohort, metrics in evaluation.get("metrics_by_cohort", {}).items():
            if cohort != "combined":
                groups["metrics_" + cohort] = (metrics, "scored_cases", cohort)
        for group, (raw, population, cohort) in groups.items():
            if not isinstance(raw, Mapping) or not raw:
                continue
            if group == "technical_completion":
                raw = {key: raw[key] for key in (
                    "scored_case_count", "research_completed_case_count",
                    "technical_exclusion_count", "technical_completion_rate",
                ) if key in raw}
            numbers = _numeric_leaves(raw)
            if not numbers:
                continue
            content = {
                "schema_version": "plan-statistics-v1", "plan_ref": plan_ref,
                "plan_id": plan_id, "group": group, "cohort": cohort,
                "population": population, "case_membership_hash": canonical_json_hash(cases),
                "case_count": len(cases), "values": numbers,
            }
            ref = self._source(content, level="plan", plan_refs=(plan_ref,))
            self._sources[ref]["runtime_statistics"] = True

    def _plans(self, rows: Iterable[Mapping[str, Any]], owner_ref: str) -> tuple[str, ...]:
        plans = []
        for position, raw in enumerate(rows):
            row = deepcopy(dict(raw))
            plan = row.get("plan", {})
            if "basic_info_policy" in plan:
                # Match InformationPlan.canonical_dict without introducing a
                # reverse dependency from this source resolver into core.
                canonical_plan = {
                    "basic_info": plan["basic_info_policy"].get("requests", []),
                    "initial_research": " ".join(plan["initial_research_skill"].split()),
                    "reflection": " ".join(plan["reflection_skill"].split()),
                    "analysis": " ".join(plan["analysis_prompt"].split()),
                }
            else:
                canonical_plan = {key: value for key, value in plan.items() if key not in {"plan_id", "round_id", "parent_ids"}}
            plan_ref = _ref("reflection_plan", canonical_plan or {"owner": owner_ref, "position": position})
            plans.append(plan_ref)
            cases = self._cases(row.get("original_case_reflections", ()), plan_ref)
            self.register_plan_statistics(row, plan_ref=plan_ref, plan_id=str(row.get("plan_id", "")))
            original_ref = self._source(row, level="plan", case_refs=cases, plan_refs=(plan_ref,))
            reflection = row.get("vertical_plan_reflection", row.get("reflection", {}))
            if isinstance(reflection, Mapping):
                self._layer(reflection, level="plan", owner_ref=plan_ref, source_refs=(original_ref,), case_refs=cases, plan_refs=(plan_ref,))
        return tuple(plans)

    @classmethod
    def from_plan_rows(cls, rows: Iterable[Mapping[str, Any]], *, owner_ref: str) -> "ReflectionMemoryIndex":
        result = cls()
        result._plans(rows, owner_ref)
        return result

    @classmethod
    def from_entries(cls, entries: Iterable[Mapping[str, Any]], *,
                     performance_profiles: Mapping[str, Mapping[str, Any]] | None = None) -> "ReflectionMemoryIndex":
        result = cls(performance_profiles=performance_profiles)
        for raw in entries:
            row = deepcopy(dict(raw))
            row.pop("round_id", None)
            owner_ref = _ref("reflection_round", row)
            plans = result._plans(row.get("plan_reflections", ()), owner_ref)
            cases = tuple(sorted({ref for source in result._sources.values() if set(source["plan_refs"]) & set(plans) for ref in source["case_refs"]}))
            original_ref = result._source(row, level="round", case_refs=cases, plan_refs=plans)
            horizontal = {
                **dict(row.get("plan_level", {})),
                "false_positive_patterns": row.get("prediction_errors", {}).get("false_positive", []),
                "false_negative_patterns": row.get("prediction_errors", {}).get("false_negative", []),
                "useful_signals": row.get("signal_observations", {}).get("useful", []),
                "suspicious_signals": row.get("signal_observations", {}).get("suspicious", []),
                "missing_capabilities": row.get("signal_observations", {}).get("missing_capabilities", []),
                "search_implications": row.get("search_implications", []),
            }
            for name in ("reflection_items", "selected_reflection_refs"):
                if name in row:
                    horizontal[name] = row[name]
            result._layer(horizontal, level="round", owner_ref=owner_ref, source_refs=(original_ref,), case_refs=cases, plan_refs=plans)
        return result

    def source_catalog(self) -> list[dict[str, Any]]:
        """Return opaque source handles, scope and runtime facts, without originals."""
        return [self._catalog_row(source) for source in self._sources.values()]

    def add_comparisons(self, comparisons: Iterable[Mapping[str, Any]], *, episodes: Iterable[Mapping[str, Any]] = (), source_aliases: Mapping[str, str] | None = None) -> None:
        """Add paired originals and completed comparison reflections to one index."""

        for raw in comparisons:
            pair = validate_prediction_comparison(raw)
            owner = pair["comparison_ref"]
            cases = (pair["case_key"],)
            plans = tuple(sorted({"reflection_plan:" + pair[side]["plan_hash"] for side in ("left", "right")}))
            sources = tuple(self._source(pair[side], level="case", case_refs=cases,
                                         plan_refs=plans) for side in ("left", "right"))
            self._sources[owner] = {"source_ref": owner, "level": "case", "content": pair,
                "case_refs": list(cases), "plan_refs": list(plans),
                "canonical_outcomes": {"technical_exclusion": not pair["research_attribution_allowed"]}}
            changes = ", ".join(pair["changed_outputs"]) or "technical execution"
            item = self.create_items([{
                "category": "prediction_changes" if pair["research_attribution_allowed"] else "technical_diagnostics",
                "kind": "fact", "brief": f"Same-case {changes} change; {pair['classification']}; cause unestablished.",
                "detail": json.dumps({"changed_outputs": pair["changed_outputs"],
                    "classification": pair["classification"], "cause_status": pair["cause_status"],
                    "left_prediction": {key: pair["left"]["prediction"].get(key) for key in ("is_surge", "magnitude", "candidate_judgment")},
                    "right_prediction": {key: pair["right"]["prediction"].get(key) for key in ("is_surge", "magnitude", "candidate_judgment")}},
                    ensure_ascii=False, sort_keys=True),
                "scope": {"case_refs": list(cases), "plan_refs": list(plans),
                          "conditions": "Same issuer, prediction time and outcome contract; retrospective comparison."},
                "limitations": pair["limitations"], "source_refs": list(sources),
                "counter_refs": [], "outcome_claims": [],
            }], level="cross_round", owner_ref=owner)[0]
            if not any(self._items[ref].level == "cross_round" for ref in self._preferred):
                self._preferred.append(item.item_ref)
        for alias, original in (source_aliases or {}).items():
            if original not in self._sources or not alias:
                raise ValidationError("comparison alias lacks its canonical paired source")
            self._sources[alias] = {**deepcopy(self._sources[original]), "source_ref": alias}
        for episode in episodes:
            if episode.get("reflection_layer") != "cross_round":
                continue
            refs = tuple(episode.get("source_refs", ()))
            if not refs or any(ref not in self._sources for ref in refs):
                raise ValidationError("cross-round episode lacks its complete paired sources")
            supporting = self._resolve(refs)
            self.create_items([{
                "category": "comparison_analysis", "kind": episode["kind"],
                "brief": episode["brief"], "detail": episode["reflection"],
                "scope": {"case_refs": sorted({ref for source in supporting for ref in source["case_refs"]}),
                          "plan_refs": sorted({ref for source in supporting for ref in source["plan_refs"]}),
                          "conditions": "Retrospective paired-case analysis; causal explanations remain unverified."},
                "limitations": ["Paired provenance is not causal verification.",
                                *episode.get("unresolved_questions", ())],
                "source_refs": list(refs), "counter_refs": [], "outcome_claims": [],
            }], level="cross_round", owner_ref=str(episode["episode_ref"]))

    def _catalog_row(self, source: Mapping[str, Any]) -> dict[str, Any]:
        value = {key: deepcopy(item) for key, item in source.items() if key != "content"}
        signals = sorted(source_signal_refs(source["content"]))
        if signals:
            value["signal_refs"] = signals[:12]
            value["signal_refs_omitted"] = max(0, len(signals) - 12)
        value["source_kind"] = (
            "runtime_plan_statistics" if source.get("runtime_statistics") else
            "runtime_signal_classification" if source.get("runtime_signal_classification") else
            "item" if source["source_ref"] in self._items else
            "canonical_case_facts" if "source_identity" in source["content"] else
            "legacy_snippet" if {"category", "index", "text", "owner_ref"} <= set(source["content"]) else
            "original_" + source["level"]
        )
        if source.get("runtime_statistics"):
            value["statistics"] = deepcopy(source["content"])
        if source["source_ref"] in self._items:
            status = self._statistics_status(self._items[source["source_ref"]])
            if status:
                value["statistics_status"] = status
            if reflection_fact_inference_fields(self._items[source["source_ref"]].to_dict()):
                value["inference_status"] = "legacy_inference_unchecked"
            if self._proof_policy_status(self._items[source["source_ref"]]):
                value["policy_status"] = "legacy_proof_policy_unchecked"
        packet = {"sources": [source], "requested_refs": [source["source_ref"]], "byte_count": 0}
        while packet["byte_count"] != _bytes(packet):
            packet["byte_count"] = _bytes(packet)
        value["read_bytes"] = packet["byte_count"]
        return value

    def catalog_view(self, *, max_bytes: int = 16_000) -> dict[str, Any]:
        """Bound a role's source directory, avoiding repeated legacy item scopes."""
        def priority(source: Mapping[str, Any]) -> int:
            if source.get("runtime_statistics"):
                return -1
            if "source_identity" in source["content"]:
                return 0
            if source.get("runtime_signal_classification"):
                return 1
            if source["source_ref"] in self._items:
                return 3 if source.get("legacy_unreviewed") else 1
            return 2

        ordered = sorted(self._sources.values(), key=priority)
        result: dict[str, Any] = {
            "sources": [], "counts": {"available": len(ordered), "included": 0, "deferred": len(ordered)},
        }
        for source in ordered:
            # Verbatim legacy entries already appear in the separate bounded
            # brief directory. Repeating their full container scope is wasteful.
            if source.get("legacy_unreviewed") or {"category", "index", "text", "owner_ref"} <= set(source["content"]):
                continue
            trial = deepcopy(result)
            trial["sources"].append(self._catalog_row(source))
            trial["counts"]["included"] += 1
            trial["counts"]["deferred"] -= 1
            if _bytes(trial) <= max_bytes:
                result = trial
        if _bytes(result) > max_bytes:
            raise ValidationError("reflection catalog budget cannot fit its manifest")
        return result

    def _resolve(self, refs: Iterable[str]) -> tuple[dict[str, Any], ...]:
        refs = _strings(tuple(refs), "references")
        if any(ref not in self._sources for ref in refs):
            raise ValidationError("reflection reference is not in the authorized catalog")
        return tuple(self._sources[ref] for ref in refs)

    def create_items(self, raw_items: Iterable[Mapping[str, Any]], *, level: str, owner_ref: str) -> tuple[ReflectionItem, ...]:
        """Validate explicit scope/outcomes and bind model-authored source-backed items."""
        if not isinstance(raw_items, (tuple, list)):
            raise ReflectionValidationError("reflection_items must be an array", path="reflection_items")
        result = []
        for index, raw in enumerate(raw_items):
            try:
                result.extend(self._create_items((raw,), level=level, owner_ref=owner_ref))
            except ReflectionValidationError as exc:
                prefix = f"reflection_items[{index}]"
                def prefixed(path: str) -> str:
                    return prefix + ("." + path if path else "")
                raise ReflectionValidationError(
                    str(exc), path=prefixed(exc.path),
                    dependency_paths=tuple(prefixed(path) for path in exc.dependency_paths),
                    invalid_container_paths=tuple(prefixed(path) for path in exc.invalid_container_paths),
                    allowed_append_values={prefixed(path): values for path, values in exc.allowed_append_values.items()},
                ) from exc
            except ValidationError as exc:
                raise ReflectionValidationError(str(exc), path=f"reflection_items[{index}]") from exc
        for item in result:
            self._item(item)
        return tuple(result)

    def _statistics_status(self, item: ReflectionItem) -> str | None:
        if item.level == "case" or not any(_has_statistics(text) or _ROUND_POOLING.search(text) for text in (item.brief, item.detail, item.scope["conditions"])):
            return None
        return "runtime_source_checked" if any(self._sources.get(ref, {}).get("runtime_statistics") for ref in item.source_refs) else "legacy_statistics_unchecked"

    def _brief(self, item: ReflectionItem) -> dict[str, Any]:
        value = item.brief_dict()
        # These are projections; originals and their content-addressed refs stay intact.
        value["usage_context"] = {
            "when_to_use": item.scope["conditions"] or None,
            "failure_conditions": list(item.limitations),
            "related_refs": list(item.related_signal_refs),
        }
        value["performance"] = deepcopy(self._performance_profiles.get(item.item_ref, empty_performance()))
        status = self._statistics_status(item)
        if status:
            value["statistics_status"] = status
        if reflection_fact_inference_fields(item.to_dict()):
            value["inference_status"] = "legacy_inference_unchecked"
        if self._proof_policy_status(item):
            value["policy_status"] = "legacy_proof_policy_unchecked"
        return value

    @staticmethod
    def _proof_policy_status(item: ReflectionItem) -> bool:
        """Identify legacy actions requiring review without changing their hash."""

        return item.kind == "action" and any(
            violates_opportunity_proof_gate(text) for text in (item.brief, item.detail)
        )

    def _validate_statistics(self, value: Mapping[str, Any], supporting: tuple[dict[str, Any], ...]) -> None:
        statistics = [source["content"] for source in supporting if source.get("runtime_statistics")]
        fields = (("brief", value["brief"]), ("detail", value["detail"]), ("scope.conditions", value["scope"]["conditions"]))
        statistical_paths = tuple(path for path, text in fields if _has_statistics(text) or _ROUND_POOLING.search(text))
        known_ids = {source["content"]["plan_id"] for source in self._sources.values() if source.get("runtime_statistics") and source["content"]["plan_id"]}
        allowed_sources = [source for source in self._sources.values() if source.get("runtime_statistics")]
        combined_text = " ".join(text for _, text in fields)
        named_owners = {plan_id for plan_id in known_ids if re.search(r"(?<![\w])" + re.escape(plan_id) + r"(?![\w])", combined_text)}
        if named_owners:
            allowed_sources = [source for source in allowed_sources if source["content"]["plan_id"] in named_owners]
        elif not _MULTI_PLAN.search(combined_text):
            allowed_sources = [source for source in allowed_sources if set(source["plan_refs"]) & set(value["scope"]["plan_refs"])]

        def statistical_invalid(message: str, path: str, dependencies: tuple[str, ...]) -> None:
            raise ReflectionValidationError(message, path=path, dependency_paths=dependencies, allowed_append_values={
                "source_refs": [source["source_ref"] for source in allowed_sources],
                "scope.plan_refs": sorted({ref for source in allowed_sources for ref in source["plan_refs"]}),
                "scope.case_refs": [],
            })

        def candidates_at(text: str, position: int) -> list[dict[str, Any]]:
            separators = list(re.finditer(r";|\.(?=\s+[A-Z])", text))
            left = max((mark.end() for mark in separators if mark.end() <= position), default=0)
            right = min((mark.start() for mark in separators if mark.start() > position), default=len(text))
            clause = text[left:right]
            owners = [plan_id for plan_id in known_ids if re.search(r"(?<![\w])" + re.escape(plan_id) + r"(?![\w])", clause)]
            cohort_names = re.findall(r"\b(anchor|random|combined)(?:[_ ]cohort)?\b", clause, re.I)
            cohort = cohort_names[0].lower() if len(set(name.lower() for name in cohort_names)) == 1 else "combined"
            return [source for source in statistics if source["cohort"] == cohort and (len(owners) != 1 or source["plan_id"] == owners[0])]

        for path, text in fields:
            if path not in statistical_paths:
                continue
            dependencies = ("source_refs", "scope.plan_refs", "scope.case_refs", "outcome_claims", *(other for other in statistical_paths if other != path))
            if not statistics:
                statistical_invalid("evaluation statistics require runtime_plan_statistics support, not a case or authored lesson source", path, dependencies)
            owners = {source["plan_ref"] for source in statistics}
            if not owners <= set(value["scope"]["plan_refs"]):
                statistical_invalid("statistical source owners must appear in the declared Plan scope", path, dependencies)
            mentioned = {plan_id for plan_id in known_ids if re.search(r"(?<![\w])" + re.escape(plan_id) + r"(?![\w])", text)}
            if not mentioned <= {source["plan_id"] for source in statistics} or (_MULTI_PLAN.search(text) and len(owners) < 2):
                statistical_invalid("multi-Plan statistics require each named Plan's runtime statistics source", path, dependencies)
            if _ROUND_POOLING.search(text) or (len(owners) > 1 and re.search(r"\bcombined diagnostics\b", text, re.I)):
                statistical_invalid("only per-Plan statistics exist; do not describe one Plan's combined cohort as pooled round statistics", path, dependencies)
            for complete in _completion_claims(text):
                completion = [source["values"] for source in candidates_at(text, complete.start()) if source["group"] == "technical_completion"]
                if not completion or any(row.get("technical_completion_rate") != 1 for row in completion):
                    statistical_invalid("full research/technical completion contradicts the cited runtime completion totals or lacks completion support", path, dependencies)
            for key, token, position in _statistic_assertions(text):
                candidates = candidates_at(text, position)
                paths = {key, "confusion." + key} if key in {"true_positive", "true_negative", "false_positive", "false_negative"} else {key}
                if key.startswith("predicted_") and key != "predicted_positive_count":
                    paths = {"prediction_distribution." + key}
                numbers = [(source["plan_ref"], number) for source in candidates for name, number in source["values"].items() if name in paths]
                matched = {owner for owner, number in numbers if _rounded_statistic_matches(token, number)}
                universal = _MULTI_PLAN.search(text) and len({source["plan_ref"] for source in candidates}) > 1
                expected_owners = {source["plan_ref"] for source in candidates}
                if not matched or (universal and not expected_owners <= matched):
                    statistical_invalid(f"{key}={token} is not supported by the cited runtime statistics; preserve its Plan/cohort/population instead of changing the scoring denominator", path, dependencies)

    def _create_items(self, raw_items: Iterable[Mapping[str, Any]], *, level: str, owner_ref: str,
                      check_statistics: bool = True, check_inferences: bool = True,
                      check_proof_policy: bool = True) -> tuple[ReflectionItem, ...]:
        """Validate authored content and issue paths at the owning rule boundary."""

        def invalid(message: str, path: str, dependencies: tuple[str, ...] = (), *, container: bool = False) -> None:
            raise ReflectionValidationError(
                message, path=path, dependency_paths=dependencies,
                invalid_container_paths=(path,) if container else (),
            )

        def strings(value: Any, path: str) -> tuple[str, ...]:
            try:
                return _strings(value, path)
            except ValidationError as exc:
                invalid(str(exc), path)

        def resolve(refs: Iterable[str], path: str, dependencies: tuple[str, ...] = ()) -> tuple[dict[str, Any], ...]:
            try:
                return self._resolve(refs)
            except ValidationError as exc:
                invalid(str(exc), path, dependencies)

        result = []
        allowed = {"category", "kind", "brief", "detail", "scope", "limitations", "source_refs", "counter_refs", "outcome_claims"}
        ranks = {level: rank for rank, level in enumerate(_CATEGORIES)}
        for raw in raw_items:
            if not isinstance(raw, Mapping) or not allowed <= set(raw) or set(raw) - allowed - {"related_signal_refs"}:
                invalid("reflection item fields differ from the authored contract", "", container=True)
            value = deepcopy(dict(raw))
            related = strings(value.get("related_signal_refs", ()), "related_signal_refs")
            for name in ("category", "kind", "brief", "detail"):
                if not isinstance(value[name], str) or not value[name].strip():
                    invalid(f"reflection item {name} must be nonempty text", name, container=True)
            if level not in _CATEGORIES or value["category"] not in _CATEGORIES[level]:
                invalid("reflection item level/category is invalid", "category")
            if value["kind"] not in {"fact", "hypothesis", "action"}:
                invalid("reflection item kind is invalid", "kind")
            if check_inferences:
                for field_name in reflection_fact_inference_fields(value):
                    invalid(
                        "fact cannot establish signal weighting or outcome sufficiency from "
                        "correctness; retain observable facts or author a testable hypothesis",
                        field_name, ("kind",),
                    )
            for name in ("limitations", "source_refs", "counter_refs"):
                strings(value[name], name)
            scope = value["scope"]
            if not isinstance(scope, Mapping) or set(scope) != {"case_refs", "plan_refs", "conditions"}:
                invalid("reflection scope is invalid", "scope", container=True)
            if not isinstance(scope["conditions"], str):
                invalid("reflection scope conditions must be text", "scope.conditions", container=True)
            for key in ("case_refs", "plan_refs"):
                strings(scope[key], "scope." + key)
            claims = value["outcome_claims"]
            if not isinstance(claims, (tuple, list)):
                invalid("reflection outcome_claims must be a list", "outcome_claims")
            for index, claim in enumerate(claims):
                path = f"outcome_claims[{index}]"
                if not isinstance(claim, Mapping) or set(claim) != {"source_ref", "axis", "correct"}:
                    invalid("reflection outcome claim is invalid", path, container=True)
                if not isinstance(claim["source_ref"], str) or not claim["source_ref"].strip():
                    invalid("reflection outcome source_ref must be nonempty text", path + ".source_ref", container=True)
                if not isinstance(claim["axis"], str) or claim["axis"] not in {"binary", "magnitude"}:
                    invalid("reflection outcome claim axis is invalid", path + ".axis", container=True)
                if type(claim["correct"]) is not bool:
                    invalid("reflection outcome claim correct must be boolean", path + ".correct", container=True)
            supporting = resolve(value["source_refs"], "source_refs", ("scope", "outcome_claims"))
            counters = resolve(value["counter_refs"], "counter_refs")
            if not supporting:
                invalid("reflection item requires supporting sources", "source_refs", ("scope", "outcome_claims"))
            for name, sources in (("source_refs", supporting), ("counter_refs", counters)):
                dependencies = ("scope", "outcome_claims") if name == "source_refs" else ()
                if level not in ranks or (level != "case" and any(ranks[source["level"]] >= ranks[level] and not (level == "plan" and source.get("runtime_statistics") and source["plan_refs"] == [owner_ref]) for source in sources)):
                    invalid("higher reflection requires lower-level sources", name, dependencies)
                if level == "case" and any(source["level"] != "case" for source in sources):
                    invalid("case reflection requires case sources", name, dependencies)
            for key in ("case_refs", "plan_refs"):
                covered = {ref for source in supporting for ref in source[key]}
                if not set(scope[key]) <= covered:
                    invalid("reflection claimed scope is not covered by its supporting sources", "scope." + key, ("source_refs", "outcome_claims"))
            if not scope["case_refs"] and not scope["plan_refs"]:
                invalid("reflection scope cannot be empty", "scope", ("source_refs", "outcome_claims"))
            if value["category"] in _OUTCOME_CATEGORIES and not claims:
                invalid("success/failure reflection requires canonical outcome claims", "outcome_claims", ("category",))
            outcome_cases: set[str] = set()
            outcome_plans: set[str] = set()
            for index, claim in enumerate(claims):
                path = f"outcome_claims[{index}]"
                source = resolve((claim["source_ref"],), path + ".source_ref", ("source_refs", "scope"))[0]
                if claim["source_ref"] not in value["source_refs"]:
                    invalid("outcome claim must cite a supporting source", path + ".source_ref", ("source_refs", "scope"))
                canonical = source["canonical_outcomes"]
                if canonical.get("technical_exclusion"):
                    invalid("technical exclusion cannot support research outcome attribution", path, ("category", "scope"))
                if canonical.get(claim["axis"]) is None or canonical[claim["axis"]] is not claim["correct"]:
                    invalid("reflection outcome claim contradicts canonical feedback", path, ("category",))
                if value["category"] in {"successful_patterns", "decision_drivers"} and not claim["correct"]:
                    invalid("successful reflection outcome claim is not correct", "category", ("outcome_claims",))
                if value["category"] in {"failed_patterns", "why_prediction_failed", "false_positive_patterns", "false_negative_patterns"} and claim["correct"]:
                    invalid("failed reflection outcome claim is correct", "category", ("outcome_claims",))
                outcome_cases.update(source["case_refs"])
                outcome_plans.update(source["plan_refs"])
            if value["category"] in _OUTCOME_CATEGORIES and not set(scope["case_refs"]) <= outcome_cases:
                invalid("outcome claims do not cover the declared case scope", "outcome_claims", ("scope.case_refs", "source_refs", "category"))
            if value["category"] in _OUTCOME_CATEGORIES and not set(scope["plan_refs"]) <= outcome_plans:
                invalid("outcome claims do not cover the declared Plan scope", "outcome_claims", ("scope.plan_refs", "source_refs", "category"))
            if level != "case" and (check_statistics or any(source.get("runtime_statistics") for source in supporting)):
                self._validate_statistics(value, supporting)
            if value["kind"] == "action":
                for field_name in ("brief", "detail"):
                    if check_proof_policy and violates_opportunity_proof_gate(value[field_name]):
                        invalid(
                            "action cannot require a quantified or stated price path, threshold-bound projection, or guaranteed "
                            "price outcome for a positive opportunity judgment; "
                            "propose optional supporting analysis instead",
                            field_name,
                        )
                _reject_pit_inexecutable_action(
                    value, invalid, ("brief", "detail")
                )
            if related:
                known_signals = source_signal_refs([source["content"] for source in supporting])
                if set(related) - known_signals:
                    invalid("related Signal version is absent from supporting sources", "related_signal_refs", ("source_refs",))
            else:
                value.pop("related_signal_refs", None)
            content = {**value, "level": level, "owner_ref": owner_ref, "evidence_status": "sources_checked"}
            item = ReflectionItem.from_dict({"item_ref": _ref("reflection", content), **content})
            result.append(item)
        return tuple(result)

    def citation_closure(self, ref: str) -> dict[str, Any] | None:
        """Return one ref's case/Plan closure for mechanical scope repair."""

        row = self._sources.get(ref)
        if row is not None:
            return {
                "case_refs": list(row["case_refs"]),
                "plan_refs": list(row["plan_refs"]),
            }
        item = self._items.get(ref)
        if item is not None:
            return {
                "case_refs": list(item.scope["case_refs"]),
                "plan_refs": list(item.scope["plan_refs"]),
            }
        return None

    def select_items(self, refs: Iterable[str]) -> tuple[ReflectionItem, ...]:
        """Select existing items without rewriting or upgrading legacy hypotheses."""
        refs = _strings(tuple(refs), "selected_reflection_refs")
        if any(ref not in self._items for ref in refs):
            raise ValidationError("selected reflection ref is not an existing item")
        return tuple(self._items[ref] for ref in refs)

    def brief_view(self, *, max_bytes: int = 48_000, max_items: int = 48, preferred_refs: Iterable[str] = ()) -> dict[str, Any]:
        """Select complete briefs; report all deferred refs without truncating prose."""
        if max_bytes < 1 or max_items < 1:
            raise ValidationError("reflection brief limits must be positive")
        preferred_refs = tuple(preferred_refs)
        preferred = preferred_refs + tuple(self._preferred)
        self.select_items(preferred_refs)
        levels: dict[str, list[str]] = {}
        for level in _CATEGORIES:
            ordered = [
                ref
                for ref in reversed(tuple(self._items))
                if self._items[ref].level == level
            ]
            # Authored structured items outrank unreviewed legacy strings —
            # which include technical diagnostics such as budget_skipped —
            # for the bounded brief slots. Legacy entries stay complete and
            # addressable by ref; only their slot priority drops.
            ordered.sort(
                key=lambda ref: (
                    self._items[ref].evidence_status == "legacy_unreviewed"
                )
            )
            levels[level] = ordered
        interleaved = [
            refs[position] for position in range(max(map(len, levels.values()), default=0))
            for refs in levels.values() if position < len(refs)
        ]
        ordered = list(dict.fromkeys((*preferred, *interleaved)))
        result: dict[str, Any] = {"items": [], "included_refs": [], "deferred_refs": list(ordered), "counts": {"available": len(ordered), "included": 0, "deferred": len(ordered)}, "directory": {"cursor": 0, "total": len(self._items), "levels": {level: len(refs) for level, refs in levels.items()}}}
        if _bytes(result) > max_bytes:
            # The full source directory remains separately addressable; its digest
            # represents the deferred inventory when even ref strings cannot fit.
            result["deferred_refs"] = []
            result["deferred_inventory_hash"] = canonical_json_hash(ordered)
            result["deferred_directory_omitted"] = True
        for ref in ordered:
            if len(result["items"]) >= max_items:
                break
            trial = deepcopy(result)
            trial["items"].append(self._brief(self._items[ref]))
            trial["included_refs"].append(ref)
            if ref in trial["deferred_refs"]:
                trial["deferred_refs"].remove(ref)
            trial["counts"]["included"] += 1
            trial["counts"]["deferred"] -= 1
            if _bytes(trial) <= max_bytes:
                result = trial
        if _bytes(result) > max_bytes:
            raise ValidationError("reflection brief budget cannot fit its manifest")
        return result

    def directory(self, *, cursor: int = 0, max_bytes: int = 8_000, level: str | None = None,
                  signal_ref: str | None = None) -> dict[str, Any]:
        """Page complete briefs and runtime source headers within one envelope."""
        if level is not None and (not isinstance(level, str) or level not in _CATEGORIES):
            raise ValidationError("reflection directory level is invalid")
        if signal_ref is not None and (not isinstance(signal_ref, str) or re.fullmatch(r"[a-z0-9_:-]+:v[1-9][0-9]*", signal_ref) is None):
            raise ValidationError("reflection Signal index requires an exact version")
        briefs = [self._brief(item) for item in reversed(tuple(self._items.values()))
                   if (level is None or item.level == level)
                   and (signal_ref is None or signal_ref in item.related_signal_refs)]
        sources = [self._catalog_row(source) for source in self._sources.values()
                   if source.get("runtime_signal_classification")
                   and (level is None or source["level"] == level)
                   and (signal_ref is None or source["signal_ref"] == signal_ref)]
        catalog = [("sources", row, row["source_ref"]) for row in sources]
        catalog.extend(("items", row, row["item_ref"]) for row in briefs)
        if type(cursor) is not int or not 0 <= cursor <= len(catalog):
            raise ValidationError("reflection directory cursor is invalid")
        result: dict[str, Any] = {"items": [], "total": len(catalog), "level": level, "next_cursor": cursor if cursor < len(catalog) else None, "oversized_refs": []}
        if sources:
            result["sources"] = []
        if signal_ref is not None:
            result["signal_ref"] = signal_ref
        for position in range(cursor, len(catalog)):
            collection, row, ref = catalog[position]
            next_cursor = position + 1 if position + 1 < len(catalog) else None
            trial = {**result, collection: [*result[collection], row], "next_cursor": next_cursor}
            if _bytes(trial) > max_bytes:
                if result["items"] or result.get("sources"):
                    break
                trial = {**result, "oversized_refs": [*result["oversized_refs"], ref], "next_cursor": next_cursor}
                if _bytes(trial) > max_bytes:
                    break
            result = trial
        if _bytes(result) > max_bytes:
            raise ValidationError("reflection directory budget cannot fit its manifest")
        if cursor < len(catalog) and result["next_cursor"] == cursor:
            raise ValidationError("reflection directory budget cannot fit an item or oversized reference")
        return result

    def read_refs(self, refs: Iterable[str], *, role: str, max_bytes: int = 16_000) -> dict[str, Any]:
        """Return exact registered units, rejecting unknown roles and oversized reads."""
        if role not in _ROLES:
            raise ValidationError("role is not authorized to read retrospective reflection")
        refs = _strings(tuple(refs), "read_refs")
        if not refs:
            raise ValidationError("reflection read requires at least one reference")
        sources = [deepcopy(source) for source in self._resolve(refs)]
        result = {"sources": sources, "requested_refs": list(refs)}
        if _bytes(result) > max_bytes:
            raise ValidationError("complete reflection sources exceed the read byte budget")
        result["byte_count"] = 0
        while result["byte_count"] != _bytes(result):
            result["byte_count"] = _bytes(result)
        if _bytes(result) > max_bytes:
            raise ValidationError("complete reflection sources exceed the read byte budget")
        return result
