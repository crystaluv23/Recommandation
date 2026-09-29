#!/usr/bin/env python3
"""Replay real reflection artifacts through the new contracts without networking.

The historical model responses remain immutable. New wire-format responses in
this replay are deterministic fixtures, not claims about a model's ability to
produce good patches or briefs. Run with ``PYTHONPATH=src python
scripts/replay_incremental_reflection_memory.py --output report.json``.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import socket
from typing import Any, Iterator, Mapping
from unittest.mock import patch

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.models import StructuredValidationError, ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs/cold_start/evolution"
V126 = RUNS_ROOT / "information-evolution-dual-self-evolution-20260920-v126"
V138 = RUNS_ROOT / "information-evolution-dual-self-evolution-20260922-v138"
V141 = RUNS_ROOT / "information-evolution-jev-dual-self-evolution-20260926-v141"
ROUTING_REQUEST = (
    "006613a63ddc8e2205f914113ee079ebc44be8b9a106be1c53edcae410eee511"
)
CITATION_REQUESTS = (
    "c5d612e8037dfb6b86c8b4368b3c541a8045be12345e7b1748d70d0b94888991",
    "8119a7cd98bc613f53f553b7de7bd90b2c8d5d5b2d31aa15788983ec75573d4b",
)
IMPORTED_META_REQUEST = (
    "0e93e5f5e03f91018387a80d2e4bf1295fc8b40059bce1d5dc1d890c4ec9c6dd"
)


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


class HistoricalSources:
    """Read JSON and prove every consumed historical file retained its bytes."""

    def __init__(self) -> None:
        self.hashes: dict[Path, str] = {}

    def read(self, path: Path) -> dict[str, Any]:
        raw = path.read_bytes()
        digest = sha256(raw).hexdigest()
        if path in self.hashes and self.hashes[path] != digest:
            raise AssertionError(f"historical source changed during replay: {path}")
        self.hashes[path] = digest
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise AssertionError(f"historical source is not an object: {path}")
        return value

    def verify(self) -> list[dict[str, Any]]:
        """Rehash all read files, failing if anything rewrote their contents."""

        rows = []
        for path, before in sorted(self.hashes.items()):
            after = sha256(path.read_bytes()).hexdigest()
            if before != after:
                raise AssertionError(f"historical source was rewritten: {path}")
            rows.append({
                "path": str(path.relative_to(PROJECT_ROOT)),
                "sha256_before": before,
                "sha256_after": after,
                "unchanged": True,
            })
        return rows


@contextmanager
def deny_network() -> Iterator[dict[str, int]]:
    """Block DNS and socket entry points, including accidental provider calls."""

    attempts = {"network_attempts": 0}

    def blocked(*_args: Any, **_kwargs: Any) -> None:
        attempts["network_attempts"] += 1
        raise AssertionError("network is forbidden during offline reflection replay")

    with (
        patch.object(socket, "getaddrinfo", side_effect=blocked),
        patch.object(socket, "create_connection", side_effect=blocked),
        patch.object(socket.socket, "connect", side_effect=blocked),
        patch.object(socket.socket, "connect_ex", side_effect=blocked),
        patch.object(socket.socket, "sendto", side_effect=blocked),
    ):
        yield attempts


def _payload(source: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(source["request"]["messages"][-1]["content"])


def _historical_contracts(sources: HistoricalSources) -> dict[str, Any]:
    routing = _payload(sources.read(V126 / "requests" / f"{ROUTING_REQUEST}.json"))
    routing_error = routing["validation_feedback"]["validation_error"]
    if "selection_reason" not in routing_error or "residual" not in routing_error:
        raise AssertionError("V126 selection/residual failure is no longer reproduced")
    citation_frontiers = []
    for request_hash in CITATION_REQUESTS:
        payload = _payload(sources.read(V138 / "requests" / f"{request_hash}.json"))
        response = sources.read(V138 / "cache/responses" / f"{request_hash}.json")
        feedback = payload["validation_feedback"]
        before = feedback["invalid_output"]
        after = response["json_output"]
        changed = [
            f"supporting_evidence[{index}].evidence_index"
            for index, (old, new) in enumerate(zip(
                before["supporting_evidence"], after["supporting_evidence"],
            ))
            if old.get("evidence_index") != new.get("evidence_index")
        ]
        if not changed or any(path in feedback["required_change_paths"] for path in changed):
            raise AssertionError("V138 historic authorization contradiction changed")
        citation_frontiers.append({
            "request_hash": request_hash,
            "historic_required_paths": feedback["required_change_paths"],
            "model_changed_reference_paths": changed,
            "historic_reference_changes_were_unauthorized": True,
        })
    return {
        "v126": {
            "request_hash": ROUTING_REQUEST,
            "selection_residual_contract_failure_present": True,
        },
        "v138": citation_frontiers,
    }


def _historical_reflection_audit(meta: Mapping[str, Any]) -> dict[str, Any]:
    plans = meta["plan_reflections"]
    case = plans[0]["original_case_reflections"][20]
    feedback = case["candidate_judgment_feedback"]
    false_success = plans[0]["vertical_plan_reflection"]["successful_patterns"][6]
    if not (
        case["case_index"] == 21
        and feedback["binary_correct"] is False
        and feedback["assessment"] == "severe_false_negative"
        and "Correct negative calls" in false_success
    ):
        raise AssertionError("V141 false-success source fixture changed")
    technical = [
        item["case_index"]
        for item in plans[1]["original_case_reflections"]
        if "technical_exclusion" in item
    ]
    if len(technical) != 5:
        raise AssertionError(f"expected five V141 c02 technical exclusions: {technical}")
    return {
        "plan_count": len(plans),
        "case_count": sum(len(item["original_case_reflections"]) for item in plans),
        "c02_technical_exclusion_indices": technical,
        "false_success": {
            "plan_id": plans[0]["plan"]["plan_id"],
            "case_index": 21,
            "canonical_binary_correct": False,
            "canonical_assessment": feedback["assessment"],
            "historic_critic_text": false_success,
        },
        "raw_meta_compact_utf8_bytes": _json_bytes(meta),
    }


def _expect_rejected(action: Any, label: str) -> str:
    try:
        action()
    except ValidationError as exc:
        return str(exc)
    raise AssertionError(f"unsafe replay input was accepted: {label}")


def _incremental_citation_replay(sources: HistoricalSources) -> dict[str, Any]:
    """Apply the recorded coordinate repair, then only its remaining obligation."""

    from stock_opportunity_agent.research.evolution_core import ResearchState
    from stock_opportunity_agent.research.evolution_output_validation import (
        _complete_parsed_role,
        _validation_obligations,
    )
    from stock_opportunity_agent.llm.agent import AgentUsage
    from stock_opportunity_agent.research.evolution_research_validation import (
        _validate_signal_claim_quantities,
    )
    from stock_opportunity_agent.research.evolution_state_patch import (
        apply_state_patch,
        state_patch_contract,
    )

    request_hash = CITATION_REQUESTS[0]
    payload = _payload(sources.read(V138 / "requests" / f"{request_hash}.json"))
    recorded = sources.read(V138 / "cache/responses" / f"{request_hash}.json")
    base = payload["validation_feedback"]["invalid_output"]
    original_hash = sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
    original_ref = base["supporting_evidence"][13]
    claim = original_ref["claim"]
    available = {}
    evidence_texts = {}
    for signal in payload["signal_batch"]:
        signal_ref = f"{signal['signal_id']}:v{signal['version']}"
        available[signal_ref] = []
        for group, rows in signal["evidence"].items():
            for row in rows:
                index, text = row["evidence_index"], row["model_evidence_text"]
                available[signal_ref].append((group, index, text))
                evidence_texts[(signal_ref, group, index)] = text

    def issues_for(value: Mapping[str, Any]):
        state = ResearchState.from_dict(value)
        cited = [
            (index, evidence_texts[(ref.signal_ref, ref.evidence_group, ref.evidence_index)])
            for index, ref in enumerate(state.supporting_evidence)
            if getattr(ref, "claim", None) == claim
        ]
        return _validate_signal_claim_quantities({claim: cited}, state, available)

    initial_issues = issues_for(base)
    if not initial_issues:
        raise AssertionError("recorded Ciena quantity failure was not reproduced")
    obligations = _validation_obligations(StructuredValidationError(initial_issues), base)
    contract = state_patch_contract(base, mode="correction", obligations=obligations["obligations"])
    first_patch = {
        "base_hash": contract["base_hash"],
        "operations": [{
            "op": "replace", "path": "supporting_evidence[13].evidence_index",
            "value": recorded["json_output"]["supporting_evidence"][13]["evidence_index"],
        }],
    }
    first = apply_state_patch(base, first_patch, contract=contract)
    remaining = issues_for(first)
    if not remaining or first["supporting_evidence"][13]["evidence_index"] != 1:
        raise AssertionError("recorded coordinate repair was lost or overaccepted")
    remaining_obligations = _validation_obligations(StructuredValidationError(remaining), first)
    next_contract = state_patch_contract(first, mode="correction", obligations=remaining_obligations["obligations"])
    second_patch = {
        "base_hash": next_contract["base_hash"],
        "operations": [{"op": "append", "path": "supporting_evidence", "value": original_ref}],
    }
    final = apply_state_patch(first, second_patch, contract=next_contract)
    if issues_for(final):
        raise AssertionError("second local repair did not satisfy the cited-quantity union")
    if any(final[key] != base[key] for key in base if key != "supporting_evidence"):
        raise AssertionError("citation correction altered an unrelated state field")
    if sha256(json.dumps(base, sort_keys=True).encode()).hexdigest() != original_hash:
        raise AssertionError("patch application mutated the original state snapshot")
    stale_error = _expect_rejected(
        lambda: apply_state_patch(first, first_patch, contract=next_contract), "stale patch",
    )
    unrelated_error = _expect_rejected(
        lambda: apply_state_patch(base, {
            "base_hash": contract["base_hash"],
            "operations": [{"op": "replace", "path": "decision", "value": "finalize"}],
        }, contract=contract), "unrelated decision edit",
    )
    whole_list_error = _expect_rejected(
        lambda: apply_state_patch(base, {
            "base_hash": contract["base_hash"],
            "operations": [{"op": "replace", "path": "supporting_evidence", "value": []}],
        }, contract=contract), "whole collection replacement",
    )

    class CitationCaller:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def complete_json(self, **kwargs: Any):
            self.calls.append(kwargs)
            call = kwargs["payload"]
            issued = call["output_patch_contract"]
            if len(self.calls) == 1:
                delta = {**first_patch, "base_hash": issued["base_hash"]}
            else:
                preserved = call["validation_feedback"]["invalid_output"]
                if preserved["supporting_evidence"][13]["evidence_index"] != 1:
                    raise AssertionError("production correction loop lost accepted partial progress")
                delta = {**second_patch, "base_hash": issued["base_hash"]}
            return delta, AgentUsage(llm_calls=1)

    def parse(value: Mapping[str, Any]):
        failures = issues_for(value)
        if failures:
            raise StructuredValidationError(failures)
        return ResearchState.from_dict(value)

    caller = CitationCaller()
    loop_result, _usage = _complete_parsed_role(
        caller,
        stage="research_controller_reflect",
        system_prompt="Replay the recorded Ciena citation failure under incremental output.",
        payload={"research_state": base},
        parser=parse,
        allow_outcomes=False,
        stable_correction_prefix=True,
        output_patch_base=base,
        patch_corrections=True,
        enforce_scoped_correction=True,
    )
    if loop_result.to_dict() != final or len(caller.calls) != 2:
        raise AssertionError("production parsed-role loop did not preserve the two local repairs")
    return {
        "request_hash": request_hash,
        "current_validator_authorizes_recorded_coordinate_repair": True,
        "first_patch_operations": 1,
        "remaining_quantity_obligation_after_coordinate_repair": True,
        "second_patch_operations": 1,
        "second_patch_only_adds_missing_same_claim_reference": True,
        "accepted_first_repair_preserved": final["supporting_evidence"][13]["evidence_index"] == 1,
        "unrelated_fields_preserved": True,
        "input_snapshot_unmodified": True,
        "full_state_output_utf8_bytes": _json_bytes(recorded["json_output"]),
        "first_delta_output_utf8_bytes": _json_bytes(first_patch),
        "second_delta_output_utf8_bytes": _json_bytes(second_patch),
        "production_correction_loop_calls": len(caller.calls),
        "production_correction_stages": [call["stage"] for call in caller.calls],
        "rejections": {
            "stale_snapshot": stale_error,
            "unrelated_edit": unrelated_error,
            "whole_collection_replacement": whole_list_error,
        },
        "validation_scope": "production patch authorization, typed state loading and exact recorded claim quantity union; not a full historical case rerun",
    }


def _memory_contract_replay(meta: Mapping[str, Any]) -> dict[str, Any]:
    """Verify indexed real originals, bounded briefs, canonical facts and reads."""

    from stock_opportunity_agent.research.evolution_reflection_memory import (
        ReflectionItem,
        ReflectionMemoryIndex,
    )

    index = ReflectionMemoryIndex.from_entries((meta,))
    catalog = index.source_catalog()
    original_case = meta["plan_reflections"][0]["original_case_reflections"][20]
    clinical_case = meta["plan_reflections"][1]["original_case_reflections"][20]
    selected: dict[str, dict[str, Any]] = {}
    for row in catalog:
        if row["level"] != "case" or row["source_ref"].startswith("reflection:"):
            continue
        read = index.read_refs((row["source_ref"],), role="proposer", max_bytes=32_000)
        source = read["sources"][0]
        if source["content"] == original_case:
            selected["false_negative"] = source
        if source["content"] == clinical_case:
            selected["clinical"] = source
        if source["canonical_outcomes"].get("technical_exclusion"):
            selected.setdefault("technical", source)
    if set(selected) != {"false_negative", "clinical", "technical"}:
        raise AssertionError("actual case originals are not addressable in the source index")

    source = selected["clinical"]
    clinical_text = clinical_case["self_reflection"]["missing_information"][0]
    authored = {
        "category": "missing_information_needs", "kind": "action",
        "brief": "For clinical-catalyst cases, verify the disclosed trial timetable, endpoints and enrollment status; retain missing details as uncertainty.",
        "detail": clinical_text,
        "scope": {"case_refs": source["case_refs"], "plan_refs": source["plan_refs"],
                  "conditions": "A clinical-catalyst interpretation depends on disclosed trial progress."},
        "limitations": ["Scripted offline brief fixture; neither causal attribution nor predictive gain is established."],
        "source_refs": [source["source_ref"]], "counter_refs": [], "outcome_claims": [],
    }
    created = index.create_items((authored,), level="plan", owner_ref=source["plan_refs"][0])[0]
    view = index.brief_view(max_bytes=12_000, max_items=4, preferred_refs=(created.item_ref,))
    if _json_bytes(view) > 12_000 or view["items"][0]["brief"] != authored["brief"]:
        raise AssertionError("brief selection truncated or dropped the preferred actionable brief")
    if any("detail" in item for item in view["items"]):
        raise AssertionError("brief view unexpectedly embeds complete item details")
    expanded = index.read_refs((created.item_ref,), role="proposer")
    if expanded["sources"][0]["content"] != created.to_dict():
        raise AssertionError("indexed experience read is not byte-content equivalent")
    case_read = index.read_refs((source["source_ref"],), role="proposer", max_bytes=32_000)
    if case_read["sources"][0]["content"] != clinical_case:
        raise AssertionError("indexed few-shot source differs from the persisted case")

    bad_source = selected["false_negative"]
    false_success = {
        **authored, "category": "successful_patterns", "kind": "fact",
        "brief": "This was a correct negative judgment.",
        "detail": meta["plan_reflections"][0]["vertical_plan_reflection"]["successful_patterns"][6],
        "scope": {"case_refs": bad_source["case_refs"], "plan_refs": bad_source["plan_refs"], "conditions": "Recorded case 21."},
        "source_refs": [bad_source["source_ref"]],
        "outcome_claims": [{"source_ref": bad_source["source_ref"], "axis": "binary", "correct": True}],
    }
    false_success_error = _expect_rejected(
        lambda: index.create_items((false_success,), level="plan", owner_ref="offline-plan"),
        "actual false negative relabeled success",
    )
    technical_source = selected["technical"]
    technical_success = {
        **false_success,
        "scope": {"case_refs": technical_source["case_refs"], "plan_refs": technical_source["plan_refs"], "conditions": "Technical abstention."},
        "source_refs": [technical_source["source_ref"]],
        "outcome_claims": [{"source_ref": technical_source["source_ref"], "axis": "binary", "correct": True}],
    }
    technical_error = _expect_rejected(
        lambda: index.create_items((technical_success,), level="plan", owner_ref="offline-plan"),
        "technical exclusion counted as research success",
    )
    rejections = {
        "actual_false_success": false_success_error,
        "technical_research_attribution": technical_error,
        "missing_reference": _expect_rejected(lambda: index.read_refs(("reflection_source:missing",), role="proposer"), "missing reference"),
        "filesystem_reference": _expect_rejected(lambda: index.read_refs(("../../private.json",), role="proposer"), "filesystem reference"),
        "blind_role_read": _expect_rejected(lambda: index.read_refs((source["source_ref"],), role="blind_predictor"), "blind role read"),
        "oversized_source_read": _expect_rejected(lambda: index.read_refs((source["source_ref"],), role="proposer", max_bytes=100), "oversized source read"),
        "stale_item_hash": _expect_rejected(lambda: ReflectionItem.from_dict({**created.to_dict(), "brief": "Silently rewritten brief."}), "tampered experience"),
    }

    page_refs = []
    cursor = 0
    pages = 0
    while cursor is not None:
        page = index.directory(cursor=cursor, max_bytes=8_000)
        if _json_bytes(page) > 8_000 or page["next_cursor"] == cursor:
            raise AssertionError("deferred source directory exceeds its bound or cannot advance")
        page_refs.extend(item["item_ref"] for item in page["items"])
        page_refs.extend(page["oversized_refs"])
        cursor = page["next_cursor"]
        pages += 1
    if set(page_refs) != {row["source_ref"] for row in index.source_catalog() if row["source_ref"].startswith("reflection:")}:
        raise AssertionError("bounded directory cannot recover every deferred experience handle")
    return {
        "source_count": len(index.source_catalog()),
        "case_originals_exactly_recoverable": True,
        "brief_to_item_to_original_case_verified": True,
        "authored_brief_is_scripted_fixture": True,
        "selected_brief_utf8_bytes": _json_bytes(view),
        "selected_brief_limit_bytes": 12_000,
        "brief_counts": view["counts"],
        "source_directory_pages": pages,
        "source_directory_page_limit_bytes": 8_000,
        "all_deferred_experiences_discoverable": True,
        "sources_checked_does_not_claim_verified_truth": created.evidence_status == "sources_checked",
        "rejections": rejections,
    }


def _production_proposer_replay(sources: HistoricalSources, meta: Mapping[str, Any]) -> dict[str, Any]:
    """Drive real proposer browsing and source disclosure with a local caller."""

    from stock_opportunity_agent.llm.agent import AgentUsage
    from stock_opportunity_agent.research.evolution_core import RoundMetaEntry
    from stock_opportunity_agent.research.evolution_plan_roles import LLMInformationPlanProposer

    recorded = _payload(sources.read(V141 / "requests" / f"{IMPORTED_META_REQUEST}.json"))
    imported = deepcopy(recorded["proposal_context"]["meta_info"])
    # The recorded request contains model-view diagnostics, while typed loading
    # accepts canonical stored fields. The same diagnostics are recomputed by
    # to_model_dict below; historical bytes and case/critic text are untouched.
    for entry in imported:
        for plan in entry["plan_reflections"]:
            plan.pop("technical_completion", None)
            plan.pop("jev_calibration_diagnostics", None)
    entries = tuple(RoundMetaEntry.from_dict(row) for row in [*imported, meta])
    source_entries = [entry.to_model_dict() for entry in entries]
    original_cases = [
        case for entry in source_entries for plan in entry["plan_reflections"]
        for case in plan["original_case_reflections"]
    ]
    parent = entries[-1].plan_reflections[-1].plan
    # Menu-era adaptation: the historical parent predates the constrained
    # Basic Info orientation menu, whose validator now rejects free-text
    # queries. This replay verifies reflection-memory protocol, so the
    # inexpressible query fields are dropped from the replayed policy.
    from dataclasses import replace as _dc_replace

    from stock_opportunity_agent.data.resolution import RawInfoRequest

    parent = _dc_replace(
        parent,
        basic_info_policy=type(parent.basic_info_policy)(
            requests=tuple(
                (
                    _dc_replace(request, query=None)
                    if getattr(request, "query", None)
                    else request
                )
                for request in parent.basic_info_policy.requests
            )
        ),
    )

    class BrowsingCaller:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []
            self.requested_refs: list[str] = []
            self.original_case: dict[str, Any] | None = None

        def complete_json(self, **kwargs: Any):
            self.calls.append(deepcopy(kwargs))
            context = kwargs["payload"]["proposal_context"]
            if len(self.calls) == 1:
                output = {"browse_memory": {"cursor": 0, "level": "case"}}
            elif len(self.calls) == 2:
                directory = context["memory_disclosures"][-1]
                item = next((item for item in directory["items"] if item["level"] == "case"), None)
                if item is None:
                    raise AssertionError("directory did not expose any actual case experience")
                self.requested_refs = [item["item_ref"], item["source_refs"][-1]]
                output = {"read_refs": self.requested_refs}
            elif len(self.calls) == 3:
                disclosure = context["memory_disclosures"][-1]
                if disclosure["requested_refs"] != self.requested_refs:
                    raise AssertionError("proposer disclosed a different reference set")
                self.original_case = disclosure["sources"][-1]["content"]
                if self.original_case not in original_cases:
                    raise AssertionError("production proposer did not receive an exact persisted case view")
                output = {
                    "B": parent.basic_info_policy.to_dict(),
                    "H_init": parent.initial_research_skill + " Preserve the applicability conditions and limitations of a retrieved lesson when forming information needs.",
                    "H_reflect": parent.reflection_skill,
                    "H_analyse": parent.analysis_prompt,
                }
            else:
                raise AssertionError("offline proposer fixture unexpectedly requested correction")
            return output, AgentUsage(llm_calls=1)

    caller = BrowsingCaller()
    proposed = LLMInformationPlanProposer(caller).propose(
        round_id=2, candidate_index=1, candidate_count=1,
        proposal_attempt=1, forbidden_plan_ids=(), parents=(parent,),
        meta_info=entries, prior="Apply sourced retrospective lessons without changing prediction semantics.",
    )
    if proposed.plan_id != "plan_r0002_c01" or caller.original_case is None:
        raise AssertionError("production proposer did not finish after local source disclosure")
    initial = caller.calls[0]["payload"]
    last = caller.calls[-1]["payload"]
    comparable_full = deepcopy(initial)
    comparable_full["proposal_context"]["meta_info"] = source_entries
    full_bytes = _json_bytes(comparable_full)
    first_bytes = _json_bytes(initial)
    last_bytes = _json_bytes(last)
    if not first_bytes < full_bytes or not last_bytes < full_bytes:
        raise AssertionError("progressive proposer request did not reduce full-history payload size")
    if initial["proposal_context"]["memory_disclosures"]:
        raise AssertionError("initial production request unexpectedly replayed full originals")
    return {
        "retained_round_ids": [entry.round_id for entry in entries],
        "retained_case_count": len(original_cases),
        "scripted_model_calls": len(caller.calls),
        "production_stages": [call["stage"] for call in caller.calls],
        "directory_then_exact_case_read_then_plan": True,
        "source_references_chosen_only_from_model_visible_directory": True,
        "original_case_exactly_matches_retained_model_view": True,
        "initial_brief_payload_utf8_bytes": first_bytes,
        "after_directory_and_case_read_payload_utf8_bytes": last_bytes,
        "same_payload_with_full_retained_meta_utf8_bytes": full_bytes,
        "initial_payload_reduction_fraction": 1 - first_bytes / full_bytes,
        "raw_payload_comparison_not_provider_token_usage": True,
        "returned_plan_id": proposed.plan_id,
    }


def _reflection_consumer_sizes(sources: HistoricalSources) -> dict[str, Any]:
    """Measure complete production critic/round inputs, including their catalogs."""

    from stock_opportunity_agent.llm.agent import AgentUsage
    from stock_opportunity_agent.research.evolution_core import (
        CaseReflectionEvidence,
        PlanRecord,
    )
    from stock_opportunity_agent.research.evolution_plan_roles import (
        LLMPlanCritic,
        LLMRoundReflector,
    )

    class SizingCaller:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []
            self.selected_ref: str | None = None
            self.case_original: dict[str, Any] | None = None

        def complete_json(self, **kwargs: Any):
            self.calls.append(deepcopy(kwargs))
            payload = kwargs["payload"]
            if len(self.calls) == 1:
                output = {"browse_memory": {"cursor": 0, "level": "case"}}
            elif len(self.calls) == 2:
                item = payload["memory_disclosures"][-1]["items"][0]
                self.selected_ref = item["item_ref"]
                output = {"read_refs": [self.selected_ref, item["source_refs"][-1]]}
            elif len(self.calls) == 3:
                self.case_original = payload["memory_disclosures"][-1]["sources"][-1]["content"]
                output = {"reflection_items": [], "selected_reflection_refs": [self.selected_ref]}
            else:
                raise AssertionError("reflection fixture unexpectedly requested a fourth call")
            return output, AgentUsage(llm_calls=1)

    records = tuple(
        PlanRecord.from_dict(sources.read(V141 / "plans" / plan_id / "record.json"))
        for plan_id in ("plan_r0001_c01", "plan_r0001_c02")
    )
    sizes = {}
    for record in records:
        caller = SizingCaller()
        result = LLMPlanCritic(caller).critique(
            plan=record.plan, trajectories=record.trajectories, metrics=record.metrics,
        )
        expected = [
            CaseReflectionEvidence.from_trajectory(row, case_index=position).to_model_dict()
            for position, row in enumerate(record.trajectories, 1)
        ]
        if caller.case_original not in expected or result.selected_reflection_refs != (caller.selected_ref,):
            raise AssertionError("production Plan critic did not select an exact lower-level case experience")
        payload = caller.calls[0]["payload"]
        sizes[record.plan_id] = {
            "stage": "plan_critic",
            "initial_payload_utf8_bytes": _json_bytes(payload),
            "after_disclosure_payload_utf8_bytes": _json_bytes(caller.calls[-1]["payload"]),
            "top_level_field_utf8_bytes": {key: _json_bytes(value) for key, value in payload.items()},
            "scripted_model_calls": len(caller.calls),
            "exact_lower_case_read_then_selected": True,
        }
    caller = SizingCaller()
    result = LLMRoundReflector(caller).reflect(
        round_id=1, records=records, prior="Offline transport sizing only.",
        parent_comparisons_by_plan_id={record.plan_id: () for record in records},
    )
    expected = [
        CaseReflectionEvidence.from_trajectory(row, case_index=position).to_model_dict()
        for record in records for position, row in enumerate(record.trajectories, 1)
    ]
    if caller.case_original not in expected or result.selected_reflection_refs != (caller.selected_ref,):
        raise AssertionError("production Round reflector did not select an exact lower-level case experience")
    payload = caller.calls[0]["payload"]
    sizes["round"] = {
        "stage": "round_reflect",
        "initial_payload_utf8_bytes": _json_bytes(payload),
        "after_disclosure_payload_utf8_bytes": _json_bytes(caller.calls[-1]["payload"]),
        "top_level_field_utf8_bytes": {key: _json_bytes(value) for key, value in payload.items()},
        "scripted_model_calls": len(caller.calls),
        "exact_lower_case_read_then_selected": True,
    }
    if any(row["initial_payload_utf8_bytes"] > 128_000 or row["after_disclosure_payload_utf8_bytes"] > 176_000 for row in sizes.values()):
        raise AssertionError("actual reflection payload exceeds the offline acceptance envelope")
    return sizes


def run_replay() -> dict[str, Any]:
    """Execute immutable-source audits and production contract replay offline."""

    sources = HistoricalSources()
    with deny_network() as network:
        historical_contracts = _historical_contracts(sources)
        meta = sources.read(V141 / "meta/round-0001.json")
        reflection_audit = _historical_reflection_audit(meta)
        incremental_replay = _incremental_citation_replay(sources)
        memory_replay = _memory_contract_replay(meta)
        proposer_replay = _production_proposer_replay(sources, meta)
        reflection_sizes = _reflection_consumer_sizes(sources)
        result = {
            "schema_version": "incremental-reflection-memory-offline-v1",
            "historical_contracts": historical_contracts,
            "historical_reflections": reflection_audit,
            "incremental_citation_repair": incremental_replay,
            "reflection_memory": memory_replay,
            "production_proposer": proposer_replay,
            "production_reflection_consumer_sizes": reflection_sizes,
            "network_attempts": network["network_attempts"],
            "external_model_calls": 0,
            "source_hashes": sources.verify(),
            "limitations": [
                "New-format patches and briefs are scripted fixtures; no new model output was generated.",
                "UTF-8 payload byte counts are not tokenizer counts or measured provider usage.",
                "Offline contract acceptance does not establish brief quality or research gain.",
            ],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is not None and args.output.resolve().is_relative_to(RUNS_ROOT.resolve()):
        parser.error("replay reports must not be written into immutable evolution run directories")
    result = run_replay()
    if args.output is not None:
        atomic_write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
