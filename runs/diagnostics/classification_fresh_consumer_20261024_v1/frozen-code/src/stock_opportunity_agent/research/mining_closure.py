"""Controlled candidate closed loop for the label-aware mining controller.

Builds eight fixed scenario fixtures (single fact, multi-period, ratio,
cross-document, narrative event, insufficient evidence, technical failure,
no-pattern) over synthetic issuer-disjoint dev/check cohorts, executes the
mining controller with zero model calls, and drives at least one candidate
through the complete local loop ``discovery -> candidate -> fixture ->
holdout simulation -> promotion decision``. The loop proves the candidate
path is structurally reachable before any live shadow cycle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    EvolutionCase,
    GroundTruth,
)
from stock_opportunity_agent.research.mining_agent_tools import (
    fetch_case_evidence,
    project_facts_from_documents,
    _unique_latest_fact,
    _unique_period_pair,
)

SCENARIOS = (
    "single_fact",
    "multi_period",
    "ratio",
    "cross_document",
    "narrative_event",
    "insufficient_evidence",
    "technical_failure",
    "no_pattern",
)

_CUTOFF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _facts_json(concept: str, records: Sequence[Mapping[str, Any]]) -> str:
    import json

    return json.dumps(
        {
            "facts": {
                "us-gaap": {
                    concept: {
                        "label": concept,
                        "units": {"USD": [dict(row) for row in records]},
                    }
                }
            }
        }
    )


def _growth_records(latest: int, prior: int) -> tuple[Mapping[str, Any], ...]:
    return (
        {"end": "2025-12-31", "val": latest, "filed": "2026-01-01"},
        {"end": "2024-12-31", "val": prior, "filed": "2025-01-01"},
    )


def _case(name: str, multiple: float) -> EvolutionCase:
    return EvolutionCase(
        company_id=f"closure-{name}",
        prediction_time=_CUTOFF,
        basic_info={"company_name": f"Closure {name}", "ticker": name.upper()},
        ground_truth=GroundTruth(multiple),
        case_id=f"closure:{name}",
    )


def _doc(doc_id: str, company: str, source_type: str, content: str) -> RawInfoDocument:
    return RawInfoDocument.create(
        document_id=doc_id,
        company_id=company,
        source_type=source_type,
        published_at=_CUTOFF,
        available_at=_CUTOFF,
        content=content,
    )


@dataclass(frozen=True)
class Scenario:
    """One fixed controlled scenario with issuer-disjoint dev/check cohorts."""

    name: str
    store: RawInfoStore
    dev_cases: tuple[EvolutionCase, ...]
    check_cases: tuple[EvolutionCase, ...]
    actions: tuple[Any, ...]
    manifest: Mapping[str, Any]
    signal_catalog: tuple[Mapping[str, Any], ...]
    execution: Mapping[str, Any]
    expected_terminal: str
    expected_decision: str | None


def _manifest_for(concepts: Sequence[str]) -> dict[str, Any]:
    return {
        "schema_version": "h1-measurable-evidence-manifest-v1",
        "cohort_case_count": 4,
        "structured_financial_concepts": [
            {
                "taxonomy": "us-gaap",
                "concept": concept,
                "source_display_name": concept,
                "unit": "USD",
                "case_count": 4,
                "cases_with_comparable_records": 4,
            }
            for concept in concepts
        ],
        "pre_cutoff_price_series_cases": 0,
        "narrative_source_families": [
            {"source_type": "8-k", "case_count": 2}
        ],
        "coverage_note": "controlled fixture",
    }


def _cohort(
    kind: str,
    *,
    positive_content: str,
    control_content: str,
    source_type: str,
    doc_prefix: str,
) -> tuple[tuple[EvolutionCase, ...], tuple[RawInfoDocument, ...]]:
    cases = tuple(
        _case(f"{kind}-pos-{index}", 4.0) for index in range(2)
    ) + tuple(_case(f"{kind}-ctl-{index}", 1.1) for index in range(2))
    documents = []
    for index, case in enumerate(cases):
        content = (
            positive_content if case.ground_truth.is_surge else control_content
        )
        documents.append(
            _doc(
                f"{doc_prefix}-{index}",
                case.company_id,
                source_type,
                content,
            )
        )
    return cases, tuple(documents)


def _candidate_action(
    observable: str,
    normalization: str,
    *,
    forced_evidence_refs: Sequence[str] | None = None,
) -> Callable:
    def action(view: Mapping[str, Any]) -> dict[str, Any]:
        if forced_evidence_refs is not None:
            evidence = list(forced_evidence_refs)
        else:
            known = sorted(
                [*view["known_fact_refs"], *view.get("known_event_refs", ())]
            )
            evidence = known[:2] if known else ["fact-missing"]
        candidate: dict[str, Any] = {
            "measurement": {
                "observable": observable,
                "value_kind": "numeric",
                "normalization": normalization,
            },
            "falsifiers": [
                {
                    "condition": "Positives do not exceed controls.",
                    "expected_observation": "Median positive <= control.",
                }
            ],
            "evidence_refs": evidence,
        }
        return {
            "action": "propose_candidate",
            "rationale": ["Controlled fixture candidate."],
            "candidate": candidate,
        }

    return action


def _fetch_action(case_refs: Sequence[str], families: Sequence[str]) -> dict[str, Any]:
    return {
        "action": "fetch_evidence",
        "rationale": ["Controlled fixture fetch."],
        "case_refs": list(case_refs),
        "source_families": list(families),
        "max_documents": 4,
    }


def _dev_refs(scenario_dev_cases) -> list[str]:
    return [case.case_id for case in scenario_dev_cases]


def _scenario_single_fact() -> Scenario:
    cases, documents = _cohort(
        "sf",
        positive_content=_facts_json(
            "CashAndCashEquivalentsAtCarryingValue", _growth_records(2000, 1000)
        ),
        control_content=_facts_json(
            "CashAndCashEquivalentsAtCarryingValue", _growth_records(400, 300)
        ),
        source_type="company_facts",
        doc_prefix="sf",
    )
    check_cases, check_documents = _cohort(
        "sfc",
        positive_content=_facts_json(
            "CashAndCashEquivalentsAtCarryingValue", _growth_records(2500, 1200)
        ),
        control_content=_facts_json(
            "CashAndCashEquivalentsAtCarryingValue", _growth_records(350, 280)
        ),
        source_type="company_facts",
        doc_prefix="sfc",
    )
    refs = _dev_refs(cases)
    return Scenario(
        name="single_fact",
        store=RawInfoStore(documents=documents + check_documents),
        dev_cases=cases,
        check_cases=check_cases,
        actions=(
            _fetch_action(refs, ["financial"]),
            _candidate_action(
                "cash_balance_at_least_threshold",
                "latest CashAndCashEquivalentsAtCarryingValue USD value >= 1000",
            ),
        ),
        manifest=_manifest_for(["CashAndCashEquivalentsAtCarryingValue"]),
        signal_catalog=(),
        execution={
            "kind": "concept_latest_at_least",
            "concept": "CashAndCashEquivalentsAtCarryingValue",
            "threshold": 1000.0,
        },
        expected_terminal="candidate",
        expected_decision="promote",
    )


def _scenario_multi_period() -> Scenario:
    cases, documents = _cohort(
        "mp",
        positive_content=_facts_json(
            "Revenues", _growth_records(5000, 3000)
        ),
        control_content=_facts_json(
            "Revenues", _growth_records(900, 1500)
        ),
        source_type="company_facts",
        doc_prefix="mp",
    )
    check_cases, check_documents = _cohort(
        "mpc",
        positive_content=_facts_json(
            "Revenues", _growth_records(6000, 3100)
        ),
        control_content=_facts_json(
            "Revenues", _growth_records(2600, 2400)
        ),
        source_type="company_facts",
        doc_prefix="mpc",
    )
    refs = _dev_refs(cases)
    return Scenario(
        name="multi_period",
        store=RawInfoStore(documents=documents + check_documents),
        dev_cases=cases,
        check_cases=check_cases,
        actions=(
            _fetch_action(refs, ["financial"]),
            _candidate_action(
                "revenue_growth_latest_over_prior",
                "latest Revenues over comparable prior Revenues growth",
            ),
        ),
        manifest=_manifest_for(["Revenues"]),
        signal_catalog=(),
        execution={
            "kind": "concept_growth",
            "concept": "Revenues",
        },
        expected_terminal="candidate",
        expected_decision="reject",
    )


def _scenario_ratio() -> Scenario:
    cases, documents = _cohort(
        "rt",
        positive_content=_facts_json(
            "NetIncomeLoss", _growth_records(2400, 1000)
        ),
        control_content=_facts_json(
            "NetIncomeLoss", _growth_records(400, 500)
        ),
        source_type="company_facts",
        doc_prefix="rt",
    )
    check_cases, check_documents = _cohort(
        "rtc",
        positive_content=_facts_json(
            "NetIncomeLoss", _growth_records(3000, 1200)
        ),
        control_content=_facts_json(
            "NetIncomeLoss", _growth_records(360, 520)
        ),
        source_type="company_facts",
        doc_prefix="rtc",
    )
    refs = _dev_refs(cases)
    return Scenario(
        name="ratio",
        store=RawInfoStore(documents=documents + check_documents),
        dev_cases=cases,
        check_cases=check_cases,
        actions=(
            _fetch_action(refs, ["financial"]),
            _candidate_action(
                "net_income_ratio_at_least",
                "latest NetIncomeLoss over comparable prior >= 1.8",
            ),
        ),
        manifest=_manifest_for(["NetIncomeLoss"]),
        signal_catalog=(),
        execution={
            "kind": "concept_ratio_at_least",
            "concept": "NetIncomeLoss",
            "threshold": 1.8,
        },
        expected_terminal="candidate",
        expected_decision="promote",
    )


def _scenario_cross_document() -> Scenario:
    import json as _json

    def combined(cash: int, revenue: int) -> tuple[str, str]:
        cash_doc = _facts_json(
            "CashAndCashEquivalentsAtCarryingValue",
            _growth_records(cash, cash // 2),
        )
        revenue_doc = _json.dumps(
            {
                "facts": {
                    "us-gaap": {
                        "Revenues": {
                            "label": "Revenues",
                            "units": {
                                "USD": [
                                    {
                                        "end": "2025-12-31",
                                        "val": revenue,
                                        "filed": "2026-01-01",
                                    },
                                    {
                                        "end": "2024-12-31",
                                        "val": revenue,
                                        "filed": "2025-01-01",
                                    },
                                ]
                            },
                        }
                    }
                }
            }
        )
        return cash_doc, revenue_doc

    cases = tuple(
        _case(f"cd-pos-{index}", 4.0) for index in range(2)
    ) + tuple(_case(f"cd-ctl-{index}", 1.1) for index in range(2))
    documents = []
    for index, case in enumerate(cases):
        cash_value, revenue_value = (
            (2000, 5000) if case.ground_truth.is_surge else (300, 900)
        )
        cash_doc, revenue_doc = combined(cash_value, revenue_value)
        documents.append(
            _doc(f"cd-cash-{index}", case.company_id, "company_facts", cash_doc)
        )
        documents.append(
            _doc(
                f"cd-rev-{index}",
                case.company_id,
                "financial_statements",
                revenue_doc,
            )
        )
    check_cases = tuple(
        _case(f"cdc-pos-{index}", 4.0) for index in range(2)
    ) + tuple(_case(f"cdc-ctl-{index}", 1.1) for index in range(2))
    check_documents = []
    for index, case in enumerate(check_cases):
        cash_value, revenue_value = (
            (2100, 5200) if case.ground_truth.is_surge else (280, 800)
        )
        cash_doc, revenue_doc = combined(cash_value, revenue_value)
        check_documents.append(
            _doc(f"cdc-cash-{index}", case.company_id, "company_facts", cash_doc)
        )
        check_documents.append(
            _doc(
                f"cdc-rev-{index}",
                case.company_id,
                "financial_statements",
                revenue_doc,
            )
        )
    refs = _dev_refs(cases)
    return Scenario(
        name="cross_document",
        store=RawInfoStore(documents=documents + check_documents),
        dev_cases=cases,
        check_cases=check_cases,
        actions=(
            _fetch_action(refs, ["financial"]),
            _candidate_action(
                "cash_and_revenue_joint_level",
                "cash >= 1000 in one document and revenues >= 3000 in another",
            ),
        ),
        manifest=_manifest_for(
            ["CashAndCashEquivalentsAtCarryingValue", "Revenues"]
        ),
        signal_catalog=(),
        execution={
            "kind": "cross_document_concepts",
            "concepts": (
                "CashAndCashEquivalentsAtCarryingValue",
                "Revenues",
            ),
            "thresholds": (1000.0, 3000.0),
        },
        expected_terminal="candidate",
        expected_decision="promote",
    )


def _scenario_narrative_event() -> Scenario:
    cases, documents = _cohort(
        "nv",
        positive_content=(
            "The registrant announced a material commercial agreement with "
            "a strategic customer covering 2026 supply."
        ),
        control_content=(
            "The registrant filed this routine report to satisfy periodic "
            "reporting obligations."
        ),
        source_type="8-k",
        doc_prefix="nv",
    )
    check_cases, check_documents = _cohort(
        "nvc",
        positive_content=(
            "The registrant announced a material commercial agreement with "
            "a strategic customer covering 2026 supply."
        ),
        control_content=(
            "The registrant filed this routine report to satisfy periodic "
            "reporting obligations."
        ),
        source_type="8-k",
        doc_prefix="nvc",
    )
    refs = _dev_refs(cases)

    def action(view: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "action": "propose_candidate",
            "rationale": ["Narrative event fixture."],
            "candidate": {
                "measurement": {
                    "observable": "material_agreement_event",
                    "value_kind": "boolean",
                    "normalization": "8-K excerpt contains material agreement",
                },
                "falsifiers": [
                    {
                        "condition": "Controls show the same phrase.",
                        "expected_observation": "Phrase in both groups.",
                    }
                ],
                "evidence_refs": sorted(view.get("known_event_refs", ()))[:2]
                or ["event-missing"],
            },
        }

    def read_narrative(view: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "action": "read_span",
            "rationale": ["Read one raw narrative event before comparison."],
            "event_ref": sorted(view.get("known_event_refs", ()))[0],
            "offset": 0,
            "length": 600,
        }

    return Scenario(
        name="narrative_event",
        store=RawInfoStore(documents=documents + check_documents),
        dev_cases=cases,
        check_cases=check_cases,
        actions=(
            _fetch_action(refs, ["filing"]),
            read_narrative,
            action,
        ),
        manifest=_manifest_for([]),
        signal_catalog=(),
        execution={
            "kind": "narrative_contains_phrase",
            "phrase": "material commercial agreement",
        },
        expected_terminal="candidate",
        expected_decision="promote",
    )


def _scenario_insufficient_evidence() -> Scenario:
    cases = tuple(_case(f"ie-{index}", 4.0 if index < 2 else 1.1) for index in range(4))
    unrelated = _doc(
        "ie-unrelated",
        "closure-other-company",
        "company_facts",
        _facts_json("Revenues", _growth_records(1, 1)),
    )
    refs = _dev_refs(cases)
    return Scenario(
        name="insufficient_evidence",
        store=RawInfoStore(documents=(unrelated,)),
        dev_cases=cases,
        check_cases=(),
        actions=(
            _fetch_action(refs, ["financial"]),
            {
                "action": "record_deferred",
                "rationale": ["No in-window documents for this cohort."],
            },
        ),
        manifest=_manifest_for(["Revenues"]),
        signal_catalog=(),
        execution={"kind": "concept_latest_at_least", "concept": "Revenues", "threshold": 1.0},
        expected_terminal="evidence_unavailable",
        expected_decision=None,
    )


def _scenario_technical_failure() -> Scenario:
    cases, documents = _cohort(
        "tf",
        positive_content=_facts_json(
            "CashAndCashEquivalentsAtCarryingValue", _growth_records(2000, 1000)
        ),
        control_content=_facts_json(
            "CashAndCashEquivalentsAtCarryingValue", _growth_records(400, 300)
        ),
        source_type="company_facts",
        doc_prefix="tf",
    )
    refs = _dev_refs(cases)
    return Scenario(
        name="technical_failure",
        store=RawInfoStore(documents=documents),
        dev_cases=cases,
        check_cases=(),
        actions=(
            _fetch_action(refs, ["financial"]),
            _candidate_action("broken", "n", forced_evidence_refs=["fact-missing"]),
            _candidate_action("broken", "n", forced_evidence_refs=["fact-missing"]),
            _candidate_action("broken", "n", forced_evidence_refs=["fact-missing"]),
            _candidate_action("broken", "n", forced_evidence_refs=["fact-missing"]),
        ),
        manifest=_manifest_for(["CashAndCashEquivalentsAtCarryingValue"]),
        signal_catalog=(),
        execution={
            "kind": "concept_latest_at_least",
            "concept": "CashAndCashEquivalentsAtCarryingValue",
            "threshold": 1000.0,
        },
        expected_terminal="technical_failure",
        expected_decision=None,
    )


def _scenario_no_pattern() -> Scenario:
    same = _facts_json(
        "CashAndCashEquivalentsAtCarryingValue", _growth_records(1000, 1000)
    )
    cases, documents = _cohort(
        "np",
        positive_content=same,
        control_content=same,
        source_type="company_facts",
        doc_prefix="np",
    )
    refs = _dev_refs(cases)
    return Scenario(
        name="no_pattern",
        store=RawInfoStore(documents=documents),
        dev_cases=cases,
        check_cases=(),
        actions=(
            _fetch_action(refs, ["financial"]),
            {
                "action": "record_no_pattern",
                "rationale": ["Identical values across both groups."],
                "coverage": {"explored_families": ["company_facts"]},
            },
        ),
        manifest=_manifest_for(["CashAndCashEquivalentsAtCarryingValue"]),
        signal_catalog=(),
        execution={
            "kind": "concept_latest_at_least",
            "concept": "CashAndCashEquivalentsAtCarryingValue",
            "threshold": 1500.0,
        },
        expected_terminal="no_pattern_with_coverage",
        expected_decision=None,
    )


_BUILDERS: dict[str, Callable[[], Scenario]] = {
    "single_fact": _scenario_single_fact,
    "multi_period": _scenario_multi_period,
    "ratio": _scenario_ratio,
    "cross_document": _scenario_cross_document,
    "narrative_event": _scenario_narrative_event,
    "insufficient_evidence": _scenario_insufficient_evidence,
    "technical_failure": _scenario_technical_failure,
    "no_pattern": _scenario_no_pattern,
}


def build_scenario(name: str) -> Scenario:
    """Return one fixed controlled scenario by name."""

    try:
        return _BUILDERS[name]()
    except KeyError as exc:
        raise ValidationError(f"unknown controlled scenario: {name}") from exc


class _ScriptedModel:
    def __init__(self, actions: Sequence[Any]) -> None:
        self._actions = list(actions)
        self.views: list[dict[str, Any]] = []

    def next_action(self, view: Mapping[str, Any]) -> dict[str, Any]:
        self.views.append(dict(view))
        if not self._actions:
            raise AssertionError("scripted model exhausted")
        item = self._actions.pop(0)
        return item(view) if callable(item) else item


def execute_measurement(
    execution: Mapping[str, Any],
    store: RawInfoStore,
    case: EvolutionCase,
    *,
    case_ref: str = "",
) -> dict[str, Any]:
    """Execute one frozen measurement on a case's point-in-time documents."""

    ref = case_ref or case.case_id
    documents = tuple(
        document
        for document in store.documents
        if document.company_id == case.company_id
        and document.available_at <= case.prediction_time
    )
    facts = {}
    for fact in project_facts_from_documents(documents, case_ref=ref):
        facts.setdefault(fact.concept, []).append(fact)
    kind = str(execution.get("kind", ""))

    selected_latest = {concept: _unique_latest_fact(rows) for concept, rows in facts.items()}
    selected_pairs = {concept: _unique_period_pair(rows) for concept, rows in facts.items()}

    def latest(concept: str) -> float | None:
        fact = selected_latest.get(concept)
        if fact is None:
            return None
        try:
            value = float(fact.value)
            return value if math.isfinite(value) else None
        except (ValueError, OverflowError):
            return None

    def comparable(concept: str) -> float | None:
        pair = selected_pairs.get(concept)
        if pair is None:
            return None
        try:
            value = float(pair[1].value)
            return value if math.isfinite(value) else None
        except (ValueError, OverflowError):
            return None

    if kind == "concept_latest_at_least":
        value = latest(str(execution["concept"]))
        if value is None:
            return {"available": False, "positive_evidence": False}
        return {
            "available": True,
            "positive_evidence": value >= float(execution["threshold"]),
            "value": value,
        }
    if kind == "concept_growth":
        value = latest(str(execution["concept"]))
        prior = comparable(str(execution["concept"]))
        if value is None or prior is None:
            return {"available": False, "positive_evidence": False}
        return {"available": True, "positive_evidence": value > prior, "value": value}
    if kind == "concept_ratio_at_least":
        value = latest(str(execution["concept"]))
        prior = comparable(str(execution["concept"]))
        if value is None or prior in (None, 0.0):
            return {"available": False, "positive_evidence": False}
        ratio = value / prior
        if not math.isfinite(ratio):
            return {"available": False, "positive_evidence": False}
        return {
            "available": True,
            "positive_evidence": ratio >= float(execution["threshold"]),
            "value": ratio,
        }
    if kind == "cross_document_concepts":
        concepts = tuple(str(item) for item in execution["concepts"])
        thresholds = tuple(float(item) for item in execution["thresholds"])
        values = []
        for concept, threshold in zip(concepts, thresholds):
            value = latest(concept)
            if value is None:
                return {"available": False, "positive_evidence": False}
            if value < threshold:
                return {"available": True, "positive_evidence": False}
            values.append(value)
        documents_by_concept = {
            concept: selected_latest[concept].document_ref
            for concept in concepts
            if selected_latest.get(concept) is not None
        }
        refs = [documents_by_concept.get(concept) for concept in concepts]
        joint = all(item is not None for item in refs) and len(set(refs)) == len(refs)
        return {"available": True, "positive_evidence": joint, "value": values}
    if kind == "narrative_contains_phrase":
        result = fetch_case_evidence(
            store,
            case,
            source_families=("filing",),
            query=None,
            max_documents=4,
            case_ref=ref,
        )
        phrase = str(execution["phrase"]).casefold()
        for event in result.narrative_events:
            if phrase in event.excerpt.casefold():
                return {"available": True, "positive_evidence": True}
        if result.narrative_events:
            return {"available": True, "positive_evidence": False}
        return {"available": False, "positive_evidence": False}
    raise ValidationError(f"unknown measurement kind: {kind}")


def run_holdout(
    execution: Mapping[str, Any],
    store: RawInfoStore,
    cases: Sequence[EvolutionCase],
) -> dict[str, Any]:
    """Execute one frozen measurement over a cohort and aggregate honestly."""

    per_case = []
    available = correct = wrong = 0
    for case in cases:
        outcome = execute_measurement(execution, store, case)
        row = {"case_id": case.case_id, **outcome}
        if outcome["available"]:
            available += 1
            predicted_positive = bool(outcome["positive_evidence"])
            row["predicted_positive"] = predicted_positive
            if predicted_positive == case.ground_truth.is_surge:
                correct += 1
            else:
                wrong += 1
        per_case.append(row)
    return {
        "per_case": per_case,
        "case_count": len(cases),
        "available": available,
        "correct": correct,
        "wrong": wrong,
        "technical_failures": 0,
    }


def promotion_decision(
    aggregate: Mapping[str, Any],
    *,
    min_available: int = 3,
) -> dict[str, Any]:
    """Apply the absolute floor; promotion never lowers it for yield."""

    reasons: list[str] = []
    if int(aggregate.get("available", 0)) < min_available:
        reasons.append(
            f"insufficient availability: {aggregate.get('available', 0)} < {min_available}"
        )
    if int(aggregate.get("correct", 0)) <= int(aggregate.get("wrong", 0)):
        reasons.append(
            "no positive directional evidence over controls: "
            f"correct={aggregate.get('correct', 0)} wrong={aggregate.get('wrong', 0)}"
        )
    return {
        "decision": "reject" if reasons else "promote",
        "reasons": reasons,
    }


@dataclass
class ClosureResult:
    """The controlled closed loop's terminal outcome and decision."""

    scenario: str
    terminal_kind: str
    decision: str | None
    reasons: tuple[str, ...]
    dev_fixture: Mapping[str, Any] = field(default_factory=dict)
    holdout: Mapping[str, Any] = field(default_factory=dict)


def run_controlled_closure(name: str) -> ClosureResult:
    """Drive one scenario through discovery, candidate, fixture, and holdout."""

    from stock_opportunity_agent.research.mining_controller import (
        LabelAwareMiningController,
    )

    scenario = build_scenario(name)
    closure: dict[str, Any] = {}

    def sink(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
        dev_fixture = run_holdout(
            scenario.execution, scenario.store, scenario.dev_cases
        )
        if dev_fixture["available"] < 1:
            closure["decision"] = "reject"
            closure["reasons"] = ("fixture produced no available measurement",)
            closure["dev_fixture"] = dev_fixture
            closure["holdout"] = {}
            return {"status": "rejected"}
        holdout = run_holdout(
            scenario.execution, scenario.store, scenario.check_cases
        )
        decision = promotion_decision(holdout)
        closure["dev_fixture"] = dev_fixture
        closure["holdout"] = holdout
        closure["decision"] = decision["decision"]
        closure["reasons"] = tuple(decision["reasons"])
        return {
            "status": "validated" if decision["decision"] == "promote" else "rejected"
        }

    model = _ScriptedModel(scenario.actions)
    controller = LabelAwareMiningController(
        store=scenario.store,
        model=model,
        case_pairs=[
            (case.case_id, case) for case in scenario.dev_cases
        ],
        measurable_evidence_manifest=scenario.manifest,
        signal_catalog=scenario.signal_catalog,
        seed="discovery",
        validation_sink=sink if scenario.check_cases else None,
    )
    result = controller.run()
    if scenario.check_cases and not closure:
        raise ValidationError("closure sink never ran for a candidate scenario")
    return ClosureResult(
        scenario=name,
        terminal_kind=result.terminal_kind,
        decision=closure.get("decision"),
        reasons=tuple(closure.get("reasons", ())),
        dev_fixture=dict(closure.get("dev_fixture", {})),
        holdout=dict(closure.get("holdout", {})),
    )
