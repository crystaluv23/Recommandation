"""Zero-call deterministic replay of mining hypotheses over frozen history.

Measures the information-arrival rate defined in the v2.1 action plan: for
each historical mining hypothesis, the declared measurement inputs are
enumerated (source families from its retrieval intent, structured concepts
named by its measurement text), and for each input the fraction of the frozen
dev cohort where the input is actually retrievable or deterministically
computable inside the point-in-time window is computed from the local Raw
Info oracle. No model or provider is called; every number is reproducible
from committed artifacts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research.evolution_core import (
    EvolutionCase,
    _evidence_source_family,
)
from stock_opportunity_agent.research.mining_agent_tools import (
    EvidenceFact,
    project_facts_from_documents,
)

_H1_STAGES = frozenset(
    {"signal_mining_hypotheses", "signal_mining_hypotheses_correction"}
)


def load_historical_hypotheses(
    workspace_root: str | Path,
) -> list[dict[str, Any]]:
    """Return the chronologically final accepted H1 hypotheses of a workspace.

    Requests are ordered through the committed trajectory, so the last cached
    hypotheses-stage response is the contract-accepted output; earlier
    superseded corrections are ignored.
    """

    root = Path(workspace_root)
    trajectory = root / "experiments" / "trajectory.jsonl"
    if not trajectory.is_file():
        return []
    ordered_hashes: list[str] = []
    for line in trajectory.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            event.get("event_type") == "external_call_completed"
            and str(event.get("stage", "")) in _H1_STAGES
        ):
            request_hash = str(event.get("request_hash", ""))
            if request_hash:
                ordered_hashes.append(request_hash)
    requests = {
        entry["request_hash"]: entry
        for entry in (
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((root / "requests").glob("*.json"))
        )
    }
    hypotheses: list[dict[str, Any]] = []
    for request_hash in ordered_hashes:
        response_path = root / "cache" / "responses" / f"{request_hash}.json"
        if not response_path.is_file():
            continue
        output = json.loads(response_path.read_text(encoding="utf-8")).get(
            "json_output", {}
        )
        rows = output.get("hypotheses", []) if isinstance(output, Mapping) else []
        if isinstance(rows, list) and rows:
            hypotheses = [dict(row) for row in rows if isinstance(row, Mapping)]
    return hypotheses


def _documents_by_company(
    store: RawInfoStore,
) -> dict[str, tuple[RawInfoDocument, ...]]:
    buckets: dict[str, list[RawInfoDocument]] = {}
    for document in store.documents:
        buckets.setdefault(document.company_id, []).append(document)
    return {key: tuple(value) for key, value in buckets.items()}


def _iter_view_strings(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for nested in value.values():
            yield from _iter_view_strings(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _iter_view_strings(nested)
    elif isinstance(value, str):
        yield value


def assert_view_masked(view: Mapping[str, Any], aliases: Sequence[str]) -> None:
    """Fail when any identity alias survives inside a model view."""

    for text in _iter_view_strings(view):
        for alias in aliases:
            if alias and re.search(
                r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])",
                text,
                flags=re.IGNORECASE if alias.isupper() else 0,
            ):
                raise AssertionError(
                    f"identity alias {alias!r} leaked into model view"
                )


def measure_arrival(
    store: RawInfoStore,
    cohort: Sequence[EvolutionCase],
    hypotheses: Sequence[Mapping[str, Any]],
    *,
    workspace_label: str = "",
) -> dict[str, Any]:
    """Measure per-hypothesis input arrival over the frozen cohort."""

    documents_by_company = _documents_by_company(store)
    facts_by_case: dict[str, dict[str, dict[str, EvidenceFact]]] = {}
    docs_by_case: dict[str, tuple[RawInfoDocument, ...]] = {}
    for case in cohort:
        documents = tuple(
            document
            for document in documents_by_company.get(case.company_id, ())
            if document.available_at <= case.prediction_time
        )
        docs_by_case[case.case_id] = documents
        concepts: dict[str, dict[str, EvidenceFact]] = {}
        for fact in project_facts_from_documents(documents, case_ref=case.case_id):
            concepts.setdefault(fact.concept, {})[fact.record_selection] = fact
        facts_by_case[case.case_id] = concepts
    concept_catalog = sorted(
        {
            (fact.concept, fact.source_display_name)
            for case_concepts in facts_by_case.values()
            for role_facts in case_concepts.values()
            for fact in role_facts.values()
        }
    )

    case_ids = [case.case_id for case in cohort]
    reports: list[dict[str, Any]] = []
    for hypothesis in hypotheses:
        measurement = dict(hypothesis.get("measurement", {}))
        text = " ".join(
            str(measurement.get(key, "")) for key in ("observable", "normalized", "normalization")
        ).casefold()
        retrieval = dict(hypothesis.get("retrieval_intent", {}))
        source_types = [
            str(item) for item in retrieval.get("source_types", ()) if item
        ]
        family_inputs = sorted({family for family in source_types})
        concept_inputs: list[str] = []
        for concept, label in concept_catalog:
            needles = [token for token in (concept, label) if token]
            if any(
                re.search(r"(?<![a-z0-9])" + re.escape(token.casefold()), text)
                for token in needles
                if len(token) >= 6
            ):
                concept_inputs.append(concept)
        family_rows = []
        for family in family_inputs:
            cases_with = sum(
                1
                for case_id in case_ids
                if any(
                    document.source_type.casefold() == family.casefold()
                    or _evidence_source_family(document.source_type) == family
                    for document in docs_by_case[case_id]
                )
            )
            family_rows.append(
                {
                    "family": family,
                    "cases_with_documents": cases_with,
                    "coverage": round(cases_with / len(case_ids), 4)
                    if case_ids
                    else 0.0,
                }
            )
        concept_rows = []
        for concept in concept_inputs:
            latest = comparable = 0
            for case_id in case_ids:
                roles = facts_by_case[case_id].get(concept, {})
                if "latest" in roles:
                    latest += 1
                if "latest" in roles and "comparable_prior" in roles:
                    comparable += 1
            concept_rows.append(
                {
                    "concept": concept,
                    "cases_with_latest": latest,
                    "cases_with_comparable_pair": comparable,
                    "pair_coverage": round(comparable / len(case_ids), 4)
                    if case_ids
                    else 0.0,
                }
            )
        coverages = [row["coverage"] for row in family_rows] + [
            row["pair_coverage"] for row in concept_rows
        ]
        reports.append(
            {
                "hypothesis_id": str(hypothesis.get("proposal_ref", "")),
                "observable": str(measurement.get("observable", "")),
                "source_types": source_types,
                "family_inputs": family_rows,
                "concept_inputs": concept_rows,
                "input_count": len(coverages),
                "mean_input_coverage": round(
                    sum(coverages) / len(coverages), 4
                )
                if coverages
                else None,
            }
        )
    return {
        "schema_version": "mining-arrival-replay-v1",
        "workspace": workspace_label,
        "cohort_case_count": len(case_ids),
        "concept_catalog_size": len(concept_catalog),
        "hypotheses": reports,
    }


def verify_replay_invariants(
    *,
    facts: Sequence[EvidenceFact],
    documents_by_content_hash: Mapping[str, RawInfoDocument],
    ledger_ids: Sequence[int],
    model_views: Sequence[Mapping[str, Any]],
    identity_aliases: Sequence[str],
) -> dict[str, Any]:
    """Check traceability, PIT, append-only ledger ids, and view masking."""

    traceability_failures: list[str] = []
    pit_failures: list[str] = []
    for fact in facts:
        document = documents_by_content_hash.get(fact.content_hash)
        if document is None:
            traceability_failures.append(f"{fact.fact_ref}: unknown content hash")
            continue
        if fact.exact_span not in document.content:
            traceability_failures.append(
                f"{fact.fact_ref}: span absent from cited document"
            )
        if document.available_at.isoformat() > fact.available_at:
            pit_failures.append(f"{fact.fact_ref}: fact predates document")
    append_only_ok = list(ledger_ids) == list(range(1, len(ledger_ids) + 1))
    masking_failures: list[str] = []
    for index, view in enumerate(model_views):
        try:
            assert_view_masked(view, identity_aliases)
        except AssertionError as exc:
            masking_failures.append(f"view[{index}]: {exc}")
    return {
        "evidence_traceability_failures": traceability_failures,
        "pit_failures": pit_failures,
        "ledger_append_only": append_only_ok,
        "identity_masking_failures": masking_failures,
        "all_passed": not traceability_failures
        and not pit_failures
        and append_only_ok
        and not masking_failures,
    }
