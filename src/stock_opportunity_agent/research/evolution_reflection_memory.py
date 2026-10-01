"""Sourced, bounded retrospective views over caller-approved anonymous records."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError


_ROLES = frozenset({"proposer", "plan_critic", "round_reflector", "slow_reflection", "signal_mining", "signal_update"})
_FORBIDDEN = frozenset({"raw_info", "basic_info_bundle", "final_context", "final_state", "initial_state", "company_id", "case_id", "identity_aliases", "trajectories"})
_CATEGORIES = {
    "case": frozenset({"decision_drivers", "why_prediction_failed", "misleading_signals", "ignored_evidence", "missing_information", "plan_issues"}),
    "plan": frozenset({"successful_patterns", "failed_patterns", "repeated_failure_modes", "misleading_signals", "missing_information_needs", "next_explorations"}),
    "round": frozenset({"successful_patterns", "failed_patterns", "false_positive_patterns", "false_negative_patterns", "useful_signals", "suspicious_signals", "missing_capabilities", "search_implications"}),
}
_OUTCOME_CATEGORIES = frozenset({"successful_patterns", "failed_patterns", "why_prediction_failed", "decision_drivers", "false_positive_patterns", "false_negative_patterns"})
_FACT_FIELDS = ("candidate_judgment_feedback", "magnitude_feedback", "jev_decision_feedback", "technical_exclusion")

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
    r"\b(?:guaranteed?|proven|certain)\s+(?:[\w-]+\s+){0,3}"
    r"(?:doubling|2x|price\s+outcome|share[- ]price\s+outcome)\b)",
    re.IGNORECASE,
)
_OPPORTUNITY_JUDGMENT = re.compile(
    r"\b(?:surge|doubling|2x|positive\s+judgment|candidate\s+judgment|"
    r"positive\s+opportunity)\b", re.IGNORECASE,
)


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

    def __init__(self, message: str, *, path: str, dependency_paths: tuple[str, ...] = (), invalid_container_paths: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.path = path
        self.dependency_paths = dependency_paths
        self.invalid_container_paths = invalid_container_paths


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

    def __init__(self) -> None:
        self._sources: dict[str, dict[str, Any]] = {}
        self._items: dict[str, ReflectionItem] = {}
        self._preferred: list[str] = []

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
                    self._create_items((authored,), level=level, owner_ref=item.owner_ref)
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
            if isinstance(reflection, Mapping):
                self._layer(reflection, level="case", owner_ref=case_ref, source_refs=(fact_ref, original_ref), case_refs=(case_ref,), plan_refs=plan_scope)
        return tuple(cases)

    @classmethod
    def from_case_rows(cls, rows: Iterable[Mapping[str, Any]], *, owner_ref: str) -> "ReflectionMemoryIndex":
        result = cls()
        result._cases(rows, owner_ref)
        return result

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
    def from_entries(cls, entries: Iterable[Mapping[str, Any]]) -> "ReflectionMemoryIndex":
        result = cls()
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

    def _catalog_row(self, source: Mapping[str, Any]) -> dict[str, Any]:
        value = {key: deepcopy(item) for key, item in source.items() if key != "content"}
        value["source_kind"] = (
            "item" if source["source_ref"] in self._items else
            "canonical_case_facts" if "source_identity" in source["content"] else
            "legacy_snippet" if {"category", "index", "text", "owner_ref"} <= set(source["content"]) else
            "original_" + source["level"]
        )
        packet = {"sources": [source], "requested_refs": [source["source_ref"]], "byte_count": 0}
        while packet["byte_count"] != _bytes(packet):
            packet["byte_count"] = _bytes(packet)
        value["read_bytes"] = packet["byte_count"]
        return value

    def catalog_view(self, *, max_bytes: int = 16_000) -> dict[str, Any]:
        """Bound a role's source directory, avoiding repeated legacy item scopes."""
        def priority(source: Mapping[str, Any]) -> int:
            if "source_identity" in source["content"]:
                return 0
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
                ) from exc
            except ValidationError as exc:
                raise ReflectionValidationError(str(exc), path=f"reflection_items[{index}]") from exc
        for item in result:
            self._item(item)
        return tuple(result)

    def _create_items(self, raw_items: Iterable[Mapping[str, Any]], *, level: str, owner_ref: str) -> tuple[ReflectionItem, ...]:
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
        ranks = {"case": 0, "plan": 1, "round": 2}
        for raw in raw_items:
            if not isinstance(raw, Mapping) or set(raw) != allowed:
                invalid("reflection item fields differ from the authored contract", "", container=True)
            value = deepcopy(dict(raw))
            for name in ("category", "kind", "brief", "detail"):
                if not isinstance(value[name], str) or not value[name].strip():
                    invalid(f"reflection item {name} must be nonempty text", name, container=True)
            if level not in _CATEGORIES or value["category"] not in _CATEGORIES[level]:
                invalid("reflection item level/category is invalid", "category")
            if value["kind"] not in {"fact", "hypothesis", "action"}:
                invalid("reflection item kind is invalid", "kind")
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
                if level not in ranks or (level != "case" and any(ranks[source["level"]] >= ranks[level] for source in sources)):
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
            if value["kind"] == "action":
                for field_name in ("brief", "detail"):
                    if violates_opportunity_proof_gate(value[field_name]):
                        invalid(
                            "action cannot require a quantified path or guaranteed "
                            "price outcome for a positive opportunity judgment; "
                            "propose optional supporting analysis instead",
                            field_name,
                        )
                _reject_pit_inexecutable_action(
                    value, invalid, ("brief", "detail")
                )
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
            trial["items"].append(self._items[ref].brief_dict())
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

    def directory(self, *, cursor: int = 0, max_bytes: int = 8_000, level: str | None = None) -> dict[str, Any]:
        """Page complete briefs under a full-envelope budget for deferred discovery."""
        if level is not None and (not isinstance(level, str) or level not in _CATEGORIES):
            raise ValidationError("reflection directory level is invalid")
        catalog = [item.brief_dict() for item in reversed(tuple(self._items.values())) if level is None or item.level == level]
        if type(cursor) is not int or not 0 <= cursor <= len(catalog):
            raise ValidationError("reflection directory cursor is invalid")
        result: dict[str, Any] = {"items": [], "total": len(catalog), "level": level, "next_cursor": cursor if cursor < len(catalog) else None, "oversized_refs": []}
        for position in range(cursor, len(catalog)):
            next_cursor = position + 1 if position + 1 < len(catalog) else None
            trial = {**result, "items": [*result["items"], catalog[position]], "next_cursor": next_cursor}
            if _bytes(trial) > max_bytes:
                if result["items"]:
                    break
                trial = {**result, "oversized_refs": [*result["oversized_refs"], catalog[position]["item_ref"]], "next_cursor": next_cursor}
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
