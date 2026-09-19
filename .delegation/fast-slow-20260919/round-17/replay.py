"""Round-17 exact replay of the V120 LifeTime reflection defect (no model calls).

Diagnosis (read-only): digest the c01 case5 rejection artifact and the
original V120 request/response files, confirm the literal mutation chain
(1718 -> 1704 -> 1697 characters) and the failure artifact's final plain
error.

Exact replay (production code only, ScriptedRoleCaller):
  1. Raw request95 through production LLMResearchController.reflect with the
     ORIGINAL prior state, evaluation context, skill, selection intents and
     signal batch: the initial correction feedback must carry BOTH the
     numeric assertion obligation AND the typed Basic literal identity
     obligation with the exact 1718-character prior literal as restoration
     candidate.
  2. The original output96 (belief retained, literal mutated further) plus an
     emulated identical cached correction must still advance the feedback,
     and the exhausted-budget deterministic fallback must restore the exact
     prior literal and remove only the authorized unsupported assertion.
  3. A compliant corrected fixture (restore exact literal + remove the
     unsupported assertion) is accepted through the production parser with
     unchanged siblings byte-preserved.
  4. Fail-closed fixtures: changed claim alongside the restored literal, a
     truly new Basic ref, ambiguous prior literals with a substitution
     attempt, and signal rows outside the identity check.

Exit code 0 only when every hard check passes.
"""

from __future__ import annotations

import difflib
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROUND17 = Path(__file__).resolve().parent
ROOT = ROUND17.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

RUN_DIR = (
    ROOT
    / "runs"
    / "cold_start"
    / "evolution"
    / "information-evolution-dual-self-evolution-20260920-v120"
)
REJECTION = ROUND17.parent / "v120" / "c01-case5-rejection.json"
FAILURE_ARTIFACT = (
    RUN_DIR
    / "experiments"
    / "trajectories"
    / "plan_r0001_c01"
    / "cik_0001869198:20250331.failure.json"
)
MUTATED_PID = "projection_cc9c7109afecaea135563db9"

from tests.evolution_runtime_test_support import ScriptedRoleCaller  # noqa: E402

from stock_opportunity_agent.models import (  # noqa: E402
    StructuredValidationError,
)
from stock_opportunity_agent.research.evolution_output_validation import (  # noqa: E402
    _complete_parsed_role,
)
from stock_opportunity_agent.research.evolution_plan_roles import (  # noqa: E402
    LLMResearchController,
)
from stock_opportunity_agent.research.evolution_research_validation import (  # noqa: E402
    _normalize_research_state_output,
    _raw_basic_literal_identity_issues,
    _validate_research_state_refs,
)
from stock_opportunity_agent.research.scheme_evolution import (  # noqa: E402
    CandidateExecutionRejected,
    ResearchState,
)
from stock_opportunity_agent.signal_library import (  # noqa: E402
    SignalBatchResult,
    SignalCoverage,
    SignalEvidence,
    SignalResult,
    SignalValue,
)


def heading(title: str) -> None:
    print(f"\n=== {title} ===")


def attempt_payload(attempt: dict) -> dict:
    payload = attempt.get("payload") or attempt.get("feedback") or {}
    return payload if isinstance(payload, dict) else {}


def literal_for(rows, projection_id: str) -> str | None:
    for row in rows or []:
        if isinstance(row, dict) and row.get("projection_id") == projection_id:
            return str(row.get("exact_text"))
    return None


def _ledger() -> dict[int, dict]:
    data = json.loads((RUN_DIR / "attempts.json").read_text(encoding="utf-8"))
    return {int(entry["attempt_id"]): entry for entry in data["attempts"]}


def original_parts(attempt_id: int) -> tuple[dict, dict]:
    entry = _ledger()[attempt_id]
    request = json.loads(
        (RUN_DIR / "requests" / f"{entry['request_hash']}.json").read_text(
            encoding="utf-8"
        )
    )
    payload: object = {}
    inner = request.get("request") if isinstance(request, dict) else request
    if isinstance(inner, dict):
        messages = inner.get("messages")
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, dict) or message.get("role") != "user":
                    continue
                try:
                    candidate = json.loads(message.get("content"))
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(candidate, dict):
                    payload = candidate
                    break
        elif isinstance(inner.get("payload"), dict):
            payload = inner["payload"]
    response_path = RUN_DIR / "cache" / "responses" / f"{entry['request_hash']}.json"
    output: object = json.loads(response_path.read_text(encoding="utf-8"))
    if isinstance(output, dict):
        for key in ("json_output", "output", "response", "parsed", "value"):
            if isinstance(output.get(key), (dict, list)):
                output = output[key]
                break
    return (
        payload if isinstance(payload, dict) else {},
        output if isinstance(output, dict) else {},
    )


def reconstruct_batch(model_rows: list[dict]) -> SignalBatchResult:
    """Rebuild one canonical SignalBatchResult from the stored model view."""

    results = []
    for row in model_rows:
        ref = str(row["signal_ref"])
        exact_claim = row.get("exact_claim_if_adopted")
        interpretation = (
            str(exact_claim)
            if exact_claim is not None
            else str(row.get("interpretation", {}).get("summary", "replay summary"))
        )
        evidence_groups: dict[str, tuple[SignalEvidence, ...]] = {}
        for group in ("supporting", "counter"):
            evidence_groups[group] = tuple(
                SignalEvidence(
                    document_id=f"replay:{ref}:{group}:{item['evidence_index']}",
                    exact_span=str(item.get("model_evidence_text") or interpretation),
                    timestamp=datetime.fromisoformat(str(item["available_at"])),
                )
                for item in row.get("evidence", {}).get(group, [])
            )
        results.append(
            SignalResult(
                signal_id=str(row["signal_id"]),
                version=int(row["version"]),
                value=SignalValue(str(row["state"]["value"])),
                confidence=float(row["state"]["confidence"]),
                interpretation=interpretation,
                supporting_evidence=evidence_groups["supporting"],
                counter_evidence=evidence_groups["counter"],
                coverage=SignalCoverage(str(row["status"]["coverage"])),
            )
        )
    return SignalBatchResult(results=tuple(results), signal_calls=len(results))


def reconstruct_selections(intents: list[dict]) -> tuple:
    views = []
    for intent in intents:
        views.append(
            SimpleNamespace(
                signal_ref=intent["signal_ref"],
                reason_code=intent["reason_code"],
                selection_reason=intent.get("selection_reason", ""),
                target_need_indices=list(intent.get("target_need_indices", ())),
                answer_scope=intent.get("answer_scope"),
                residual_need=intent.get("residual_need"),
            )
        )
    return tuple(views)


def diagnose(failures: list[str]) -> dict:
    heading("A. artifact diagnosis (read-only)")
    attempts = json.loads(REJECTION.read_text(encoding="utf-8"))
    print(f"attempts recorded: {[item.get('attempt_id') for item in attempts]}")
    for attempt in attempts:
        payload = attempt_payload(attempt)
        prior_rows = (payload.get("research_state") or {}).get("supporting_evidence")
        out_rows = (attempt.get("output") or {}).get("supporting_evidence")
        prior_literal = literal_for(prior_rows, MUTATED_PID)
        out_literal = literal_for(out_rows, MUTATED_PID)
        feedback = payload.get("validation_feedback")
        codes = [
            obligation.get("issue_code")
            for obligation in (feedback or {}).get("obligations", [])
        ]
        print(
            f"  attempt {attempt['attempt_id']} stage={attempt.get('stage')} "
            f"feedback_codes={codes} "
            f"prior_literal={len(prior_literal) if prior_literal else None} "
            f"output_literal={len(out_literal) if out_literal else None}"
        )
        if prior_literal and out_literal and prior_literal != out_literal:
            removed = [
                token
                for token in difflib.SequenceMatcher(
                    a=prior_literal, b=out_literal, autojunk=False
                ).get_opcodes()
                if token[0] in ("delete", "replace")
            ]
            deleted_text = "".join(prior_literal[tag[1]:tag[2]] for tag in removed)
            print(f"    deleted from prior literal: {deleted_text!r}")

    payload95, output95 = original_parts(95)
    _payload96, output96 = original_parts(96)
    prior_literal = literal_for(
        (payload95.get("research_state") or {}).get("supporting_evidence"), MUTATED_PID
    )
    out95_literal = literal_for(output95.get("supporting_evidence"), MUTATED_PID)
    out96_literal = literal_for(output96.get("supporting_evidence"), MUTATED_PID)
    print(
        f"original wire lengths: prior={len(prior_literal or '')} "
        f"out95={len(out95_literal or '')} out96={len(out96_literal or '')}"
    )
    if (
        len(prior_literal or "") != 1718
        or len(out95_literal or "") != 1704
        or len(out96_literal or "") != 1697
    ):
        failures.append("original wire files do not match the recorded lengths")

    if FAILURE_ARTIFACT.exists():
        blob = FAILURE_ARTIFACT.read_text(encoding="utf-8")
        print(
            "failure artifact records the hidden plain error: "
            f"{'reflect cannot introduce a new Basic Info ref' in blob}"
        )
    else:
        failures.append(f"failure artifact missing: {FAILURE_ARTIFACT.name}")

    return {
        "payload95": payload95,
        "output95": output95,
        "output96": output96,
        "prior_literal": prior_literal or "",
    }


def make_controller(caller, request_payload: dict) -> LLMResearchController:
    controller = LLMResearchController(caller)
    controller.evaluation_context = dict(request_payload["evaluation_context"])
    controller.set_reflection_runtime_context(
        selections=reconstruct_selections(
            request_payload["executed_selection_intents"]
        ),
        must_finalize=bool(request_payload["reflection_runtime"]["must_finalize"]),
        termination_trigger=None,
    )
    return controller


def reflect_plan(request_payload: dict) -> SimpleNamespace:
    return SimpleNamespace(reflection_skill=request_payload["reflection_skill"])


def evidence_row(value, index: int) -> dict:
    row = value.supporting_evidence[index]
    return row.to_dict() if hasattr(row, "to_dict") else dict(row)


def replay_chain(failures: list[str], context: dict) -> None:
    heading("B1. original raw95/96 chain through production reflect")
    payload95 = context["payload95"]
    output95 = context["output95"]
    output96 = context["output96"]
    prior_literal = context["prior_literal"]

    caller = ScriptedRoleCaller([output95, output96, output96])
    caller.max_structured_corrections = 2
    events: list[dict] = []
    caller.on_progress = events.append
    controller = make_controller(caller, payload95)
    step = controller.reflect(
        reflect_plan(payload95),
        ResearchState.from_dict(payload95["research_state"]),
        reconstruct_batch(payload95["signal_batch"]),
    )
    print(f"  llm_calls: {step.usage.llm_calls}")
    if step.usage.llm_calls != 3:
        failures.append(
            f"expected 3 llm_calls (raw + 2 corrections), got {step.usage.llm_calls}"
        )

    feedback = caller.calls[1]["payload"]["validation_feedback"]
    codes = sorted(item["issue_code"] for item in feedback["obligations"])
    print(f"  initial feedback codes: {codes}")
    if codes != [
        "assertion_without_support",
        "basic_literal_identity_mismatch",
    ]:
        failures.append(f"initial feedback does not expose both defects: {codes}")
    identity = next(
        (
            item
            for item in feedback["obligations"]
            if item["issue_code"] == "basic_literal_identity_mismatch"
        ),
        None,
    )
    if identity is None:
        failures.append("initial feedback lacks the identity obligation")
    else:
        print(
            f"  identity obligation paths={identity['must_change_paths']} "
            f"repairs={identity['allowed_repairs']} "
            f"prior_literal_chars={len(identity.get('prior_exact_text') or '')}"
        )
        if identity["must_change_paths"] != ["supporting_evidence[6].exact_text"]:
            failures.append("identity obligation targets the wrong path")
        if identity["allowed_repairs"] != ["replace"]:
            failures.append("identity obligation is not replace-only")
        if identity.get("prior_exact_text") != prior_literal:
            failures.append("identity obligation lacks the exact prior literal")
    assertion = next(
        (
            item
            for item in feedback["obligations"]
            if item["issue_code"] == "assertion_without_support"
        ),
        None,
    )
    if assertion is None or assertion["must_change_paths"] != ["current_beliefs[7]"]:
        failures.append("numeric assertion obligation missing or mispathed")

    request1 = json.dumps(caller.calls[1]["payload"], sort_keys=True)
    request2 = json.dumps(caller.calls[2]["payload"], sort_keys=True)
    if request1 == request2:
        print(
            "  correction-2 request repeated byte-for-byte (faithful cache-hit "
            "emulation, as recorded in the real run)"
        )
    else:
        print("  correction-2 request differs from correction-1 (advancing feedback)")
    feedback2 = caller.calls[2]["payload"]["validation_feedback"]
    codes2 = sorted(item["issue_code"] for item in feedback2["obligations"])
    print(f"  correction-2 feedback codes: {codes2}")
    if "basic_literal_identity_mismatch" not in codes2:
        failures.append(
            "correction-2 feedback lost the identity obligation (hidden defect "
            "regression)"
        )

    final = step.value
    final_rows = [
        evidence_row(final, index) for index in range(len(final.supporting_evidence))
    ]
    final_literal = literal_for(final_rows, MUTATED_PID)
    beliefs = [str(item) for item in final.current_beliefs]
    expected_beliefs = list(output96["current_beliefs"])
    removed_belief = expected_beliefs.pop(7)
    evicted_belief = expected_beliefs.pop(6)
    print(
        f"  final literal chars: {len(final_literal or '')} "
        f"(prior {len(prior_literal)}); final beliefs: {len(beliefs)}; "
        f"final evidence rows: {len(final_rows)}"
    )
    print(
        "  note: the reconstructed batch cannot ground the model's scaled "
        "liquidity wording, so the deterministic fallback also evicts that "
        f"signal row and its linked assertion ({evicted_belief[:60]!r}...) "
        "under the claim_quantity obligation's own remove authority"
    )
    if final_literal != prior_literal:
        failures.append("final Basic literal is not the exact prior literal")
    if beliefs != expected_beliefs:
        failures.append(
            "final beliefs are not output96 minus the authorized removals"
        )
    if removed_belief != "revenue_growth_yoy=0.182443":
        failures.append(f"fallback removed an unexpected belief: {removed_belief!r}")
    if len(final_rows) != 7:
        failures.append(f"final evidence has {len(final_rows)} rows, expected 7")
    else:
        for index in range(7):
            expected_row = dict(output96["supporting_evidence"][index])
            if index == 6:
                expected_row["exact_text"] = prior_literal
            if final_rows[index] != expected_row:
                failures.append(f"final evidence[{index}] differs from output96")
    for field in (
        "next_information_needs",
        "hypotheses",
        "resolved_questions",
        "open_questions",
        "contradictions",
    ):
        final_rows = [str(item) for item in getattr(final, field)]
        if final_rows != output96[field]:
            failures.append(f"final field {field} differs from output96")
    fallback_events = [
        event
        for event in events
        if event["event_type"] == "structured_validation_fallback_applied"
    ]
    if len(fallback_events) != 1:
        failures.append("expected exactly one deterministic fallback application")
    else:
        print(
            f"  fallback removed={fallback_events[0]['removed_paths']} "
            f"normalized={fallback_events[0]['normalized_paths']}"
        )
        if "current_beliefs[7]" not in fallback_events[0]["removed_paths"]:
            failures.append("fallback did not remove the authorized assertion path")
        if set(fallback_events[0]["removed_paths"]) != {
            "current_beliefs[7]",
            "supporting_evidence[7]",
            "current_beliefs[6]",
        }:
            failures.append(
                "fallback removals exceed the recorded authorized obligations: "
                f"{fallback_events[0]['removed_paths']}"
            )
        if fallback_events[0]["normalized_paths"] != [
            "supporting_evidence[6].exact_text"
        ]:
            failures.append("fallback did not restore the exact literal path")


def replay_compliant_fixture(failures: list[str], context: dict) -> None:
    heading("B2. compliant corrected fixtures accepted, siblings preserved")
    from copy import deepcopy

    payload95 = context["payload95"]
    output95 = context["output95"]
    prior_literal = context["prior_literal"]

    # Correction 1: restore the exact prior literal (uniquely anchored
    # replace-only authority) and remove the unsupported assertion (explicit
    # remove authority). Everything else stays byte-for-byte.
    fix1 = deepcopy(output95)
    for row in fix1["supporting_evidence"]:
        if row.get("projection_id") == MUTATED_PID:
            row["exact_text"] = prior_literal
    fix1["current_beliefs"].pop(7)

    # The reconstructed batch grounds signal claims on the stored
    # model_evidence_text (raw XBRL values), so the retained projection's
    # revalidation raises one claim_quantity obligation for the model's
    # scaled liquidity wording. Correction 2 rewrites that claim onto the
    # value of the actually cited evidence item and copies it into the
    # linked assertion — both paths explicitly authorized by that obligation.
    liquidity_rows = [
        row
        for row in payload95["signal_batch"]
        if row.get("signal_ref") == "liquidity_runway_months:v1"
    ]
    cited_row = output95["supporting_evidence"][7]
    cited_item = liquidity_rows[0]["evidence"]["supporting"][
        cited_row["evidence_index"]
    ]
    cited_value = json.loads(cited_item["model_evidence_text"])["val"]
    raw_claim = f"The reported fact value is {cited_value}."
    print(f"  correction-2 grounded claim: {raw_claim}")
    fix2 = deepcopy(fix1)
    fix2["supporting_evidence"][7]["claim"] = raw_claim
    fix2["current_beliefs"][6] = raw_claim

    caller = ScriptedRoleCaller([output95, fix1, fix2])
    caller.max_structured_corrections = 2
    controller = make_controller(caller, payload95)
    step = controller.reflect(
        reflect_plan(payload95),
        ResearchState.from_dict(payload95["research_state"]),
        reconstruct_batch(payload95["signal_batch"]),
    )
    print(f"  llm_calls: {step.usage.llm_calls}")
    if step.usage.llm_calls != 3:
        failures.append(
            f"compliant fixture needed {step.usage.llm_calls} calls, expected 3"
        )
    second_feedback = caller.calls[2]["payload"]["validation_feedback"]
    second_codes = sorted(item["issue_code"] for item in second_feedback["obligations"])
    print(f"  correction-2 feedback codes: {second_codes}")
    if second_codes != ["claim_quantity_not_supported"]:
        failures.append(
            "correction-2 feedback is not exactly the quantity obligation: "
            f"{second_codes}"
        )

    final = step.value
    final_rows = [
        evidence_row(final, index) for index in range(len(final.supporting_evidence))
    ]
    if [str(item) for item in final.current_beliefs] != fix2["current_beliefs"]:
        failures.append("final beliefs differ from the compliant correction")
    if len(final_rows) != len(fix2["supporting_evidence"]):
        failures.append("final evidence row count differs from the correction")
    else:
        for index, (final_row, source_row) in enumerate(
            zip(final_rows, fix2["supporting_evidence"])
        ):
            if final_row != source_row:
                failures.append(f"final evidence[{index}] differs from the correction")
    for field in (
        "next_information_needs",
        "hypotheses",
        "resolved_questions",
        "open_questions",
        "contradictions",
    ):
        if [str(item) for item in getattr(final, field)] != output95[field]:
            failures.append(f"final field {field} drifted from output95")
    print(
        f"  final evidence rows: {len(final_rows)}; beliefs: "
        f"{len(final.current_beliefs)} (restored literal byte-exact: "
        f"{literal_for(final_rows, MUTATED_PID) == prior_literal})"
    )


def replay_negative_fixtures(failures: list[str], context: dict) -> None:
    heading("B3. fail-closed fixtures")
    from copy import deepcopy

    payload95 = context["payload95"]
    output95 = context["output95"]
    prior_literal = context["prior_literal"]

    def run_variant(corrected):
        caller = ScriptedRoleCaller([output95, corrected])
        caller.max_structured_corrections = 1
        controller = make_controller(caller, payload95)
        return controller.reflect(
            reflect_plan(payload95),
            ResearchState.from_dict(payload95["research_state"]),
            reconstruct_batch(payload95["signal_batch"]),
        )

    base = deepcopy(output95)
    for row in base["supporting_evidence"]:
        if row.get("projection_id") == MUTATED_PID:
            row["exact_text"] = prior_literal
    base["current_beliefs"].pop(7)

    claim_changed = deepcopy(base)
    claim_changed["supporting_evidence"][5]["claim"] = "Rewritten earnings claim."
    try:
        step = run_variant(claim_changed)
    except CandidateExecutionRejected:
        print("  changed claim + restored literal: CandidateExecutionRejected")
    else:
        rows = [
            evidence_row(step.value, index)
            for index in range(len(step.value.supporting_evidence))
        ]
        if rows[5].get("claim") != output95["supporting_evidence"][5]["claim"]:
            failures.append("changed claim survived into the final state")
        else:
            print("  changed claim discarded; final claim byte-preserved")

    new_ref = deepcopy(base)
    new_ref["supporting_evidence"][5] = {
        "claim": "Invented basic claim.",
        "exact_text": "invented literal",
        "kind": "basic_info",
        "projection_id": "projection_invented",
    }
    try:
        step = run_variant(new_ref)
    except CandidateExecutionRejected:
        print("  truly new Basic ref: CandidateExecutionRejected")
    else:
        rows = [
            evidence_row(step.value, index)
            for index in range(len(step.value.supporting_evidence))
        ]
        if any(row.get("projection_id") == "projection_invented" for row in rows):
            failures.append("invented Basic ref survived into the final state")
        elif rows[5] != output95["supporting_evidence"][5]:
            failures.append("final evidence[5] differs from the original output95 row")
        else:
            print("  invented ref evicted; original row byte-preserved")

    prior_state = ResearchState.from_dict(payload95["research_state"])
    signal_tweaked = deepcopy(output95)
    for row in signal_tweaked["supporting_evidence"]:
        if row.get("kind") == "signal":
            row["claim"] = "Adjusted signal interpretation text."
            break
    issues = _raw_basic_literal_identity_issues(signal_tweaked, prior_state)
    flagged = {issue.paths[0] for issue in issues}
    print(f"  identity flags on signal-claim tweak: {sorted(flagged)}")
    if flagged != {"supporting_evidence[6].exact_text"}:
        failures.append("signal rows entered the Basic identity check")

    ambiguous_prior = deepcopy(payload95["research_state"])
    ambiguous_prior["supporting_evidence"].append(
        {
            "claim": "The 8-K filing identifies Life Time Group Holdings, Inc. "
            "as the registrant.",
            "exact_text": "another distinct prior literal",
            "kind": "basic_info",
            "projection_id": MUTATED_PID,
        }
    )
    ambiguous_state = ResearchState.from_dict(ambiguous_prior)
    ambiguous_output = deepcopy(output95)
    for row in ambiguous_output["supporting_evidence"]:
        if row.get("projection_id") == MUTATED_PID:
            row["exact_text"] = "an unrelated mutated literal"
    codes = {
        issue.code
        for issue in _raw_basic_literal_identity_issues(
            ambiguous_output, ambiguous_state
        )
    }
    print(f"  ambiguous prior identity codes: {sorted(codes)}")
    if "basic_literal_identity_ambiguous" not in codes:
        failures.append("ambiguous prior literal was not reported as ambiguous")

    substituted = deepcopy(ambiguous_output)
    for row in substituted["supporting_evidence"]:
        if row.get("projection_id") == MUTATED_PID:
            row["exact_text"] = "another distinct prior literal"

    evaluation_context = payload95["evaluation_context"]

    def parse(value):
        normalized = _normalize_research_state_output(
            dict(value),
            previous_state=ambiguous_state,
            evaluation_context=evaluation_context,
        )
        return _validate_research_state_refs(
            ResearchState.from_dict(normalized),
            phase="reflect",
            previous_state=ambiguous_state,
        )

    caller = ScriptedRoleCaller([ambiguous_output, substituted])
    caller.max_structured_corrections = 1
    try:
        _complete_parsed_role(
            caller,
            stage="research_controller_reflect",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=parse,
            allow_outcomes=False,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            stable_correction_prefix=True,
        )
        failures.append("ambiguous literal substitution was accepted")
    except CandidateExecutionRejected:
        print("  ambiguous substitution: CandidateExecutionRejected")


def replay_checks(failures: list[str]) -> None:
    context = diagnose(failures)
    replay_chain(failures, context)
    replay_compliant_fixture(failures, context)
    replay_negative_fixtures(failures, context)
    print("\nno paid model call was made: every role is a ScriptedRoleCaller")


def main() -> int:
    failures: list[str] = []
    try:
        replay_checks(failures)
    except Exception as exc:  # noqa: BLE001 - report and continue
        failures.append(f"replay raised {type(exc).__name__}: {exc}")
    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("\nALL ROUND-17 REPLAY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
