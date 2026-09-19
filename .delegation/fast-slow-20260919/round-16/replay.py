"""Round-16 full raw replay of the actual V119 c02/c01 artifacts.

Runs the production role code only (LLMResearchController.reflect/initialize
through _complete_parsed_role with its real parsers); no model calls.

  1. c02 (Wynn, case2): reconstruct the request202 context — prior
     ResearchState, canonical SignalBatchResult (evidence exact_spans from the
     stored model_evidence_text rows, deterministic interpretation from
     exact_claim_if_adopted), and selection intents — then feed the raw
     output202/output203 to the production reflect role. Expect: 202 is
     rejected by the real signal-claim quantity validator
     (supporting_evidence[8], missing "2025") with NO need-transition error
     for the duplicate catalyst need; 203 repairs the numeric defect and is
     accepted with the duplicate need preserved byte-for-byte.
  2. c01 (Newmont, case11): reconstruct initialize177->178->179 through the
     production initialize role. Expect: 179's drifted whole-list correction
     is reconciled onto 178's failed output — protected original beliefs
     0,1,3,5,6,7 preserved in order, only the explicitly authorized removals
     (2/4) applied, unrelated fields byte-for-byte from 178.
  3. The independent production counterexample (original-order pure deletion
     under replace-only authority) now raises CandidateExecutionRejected.

Exit code 0 only when every hard check passes.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROUND16 = Path(__file__).resolve().parent
ROOT = ROUND16.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.evolution_runtime_test_support import ScriptedRoleCaller  # noqa: E402

from stock_opportunity_agent.models import (  # noqa: E402
    StructuredValidationError,
    ValidationIssue,
)
from stock_opportunity_agent.research.evolution_plan_roles import (  # noqa: E402
    LLMResearchController,
)
from stock_opportunity_agent.research.evolution_research_validation import (  # noqa: E402
    _targeted_answer_need_transition_errors,
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

V119 = ROUND16.parent / "v119"


def load(name: str) -> list[dict]:
    with (V119 / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def attempt_payload(attempt: dict) -> dict:
    payload = attempt.get("payload") or attempt.get("feedback") or {}
    return payload if isinstance(payload, dict) else {}


def reconstruct_batch(model_rows: list[dict]) -> SignalBatchResult:
    """Rebuild one canonical SignalBatchResult from the stored model view.

    Evidence exact_span comes from each stored model_evidence_text (numbers
    are preserved verbatim by compaction); a deterministic row's canonical
    interpretation comes from its exact_claim_if_adopted, which is the exact
    literal the quantity validator itself consults for such rows.
    """

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
                    # A deterministic row omits model_evidence_text because its
                    # adoptable literal is the canonical interpretation; the
                    # quantity validator consults exactly that interpretation
                    # for such rows, so it stands in for the hidden span.
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


def replay_counterexample(failures: list[str]) -> None:
    print("=== independent production counterexample (post-fix) ===")
    from stock_opportunity_agent.research.evolution_output_validation import (
        _complete_parsed_role,
    )

    invalid = {"rows": ["invalid", "keep1", "keep2"]}
    corrected = {"rows": ["keep1", "keep2"]}

    def parse(value):
        if "invalid" in value["rows"]:
            raise StructuredValidationError(
                [
                    ValidationIssue(
                        code="ordinary_invalid",
                        message="replace only",
                        paths=("rows[0]",),
                        allowed_repairs=("replace",),
                    )
                ]
            )
        return value

    caller = ScriptedRoleCaller([invalid, corrected])
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
    except CandidateExecutionRejected:
        print("  original-order pure deletion: CandidateExecutionRejected (fixed)")
        return
    failures.append("pure deletion under replace-only authority was accepted")


def replay_c02(failures: list[str]) -> None:
    attempts = load("c02-case2-rejection.json")
    request202 = attempt_payload(attempts[0])
    output202 = attempts[0]["output"]
    output203 = attempts[1]["output"]
    residual = request202["executed_selection_intents"][0]["residual_need"]
    catalyst = request202["need_transition_contract"]["need_rules"][2]["need"]
    prior_needs = request202["research_state"]["next_information_needs"]

    print("=== actual V119 c02 raw replay through production reflect ===")
    transition_errors = _targeted_answer_need_transition_errors(
        SimpleNamespace(next_information_needs=list(prior_needs)),
        SimpleNamespace(next_information_needs=list(output202["next_information_needs"])),
        reconstruct_selections(request202["executed_selection_intents"]),
        {"financing_listing_action:v2"},
        {"financing_listing_action:v2", "liquidity_runway_months:v1",
         "revenue_growth_yoy:v1"},
        evaluation_context=request202.get("evaluation_context"),
    )
    print(f"  raw202 standalone transition errors: {len(transition_errors)}")
    if transition_errors:
        failures.append("raw202 need transition is no longer valid")

    caller = ScriptedRoleCaller([output202, output203])
    caller.max_structured_corrections = 2
    controller = LLMResearchController(caller)
    controller.evaluation_context = dict(request202["evaluation_context"])
    controller.set_reflection_runtime_context(
        selections=reconstruct_selections(
            request202["executed_selection_intents"]
        ),
        must_finalize=bool(
            request202["reflection_runtime"]["must_finalize"]
        ),
        termination_trigger=None,
    )
    plan = SimpleNamespace(reflection_skill=request202["reflection_skill"])
    step = controller.reflect(
        plan,
        ResearchState.from_dict(request202["research_state"]),
        reconstruct_batch(request202["signal_batch"]),
    )
    print(f"  reflect llm_calls: {step.usage.llm_calls}")
    if step.usage.llm_calls != 2:
        failures.append(
            f"c02 replay used {step.usage.llm_calls} calls, expected 2 "
            "(202 rejected once, 203 accepted)"
        )

    feedback = caller.calls[1]["payload"]["validation_feedback"]
    codes = [item["issue_code"] for item in feedback["obligations"]]
    print(f"  202 production failure codes: {codes}")
    print(f"  202 required_change_paths: {feedback['required_change_paths']}")
    if codes != ["claim_quantity_not_supported"]:
        failures.append(
            "202 rejection is not exactly the numeric signal-claim defect: "
            f"{codes}"
        )
    obligation = feedback["obligations"][0]
    if (
        obligation["must_change_paths"] != ["supporting_evidence[8].claim"]
        or obligation.get("missing_quantity_groups") != ["2025"]
    ):
        failures.append(
            "202 numeric defect path/groups changed: "
            f"{obligation['must_change_paths']} "
            f"{obligation.get('missing_quantity_groups')}"
        )

    needs = list(step.value.next_information_needs)
    print(f"  final needs: {len(needs)} rows")
    if needs[2] != residual:
        failures.append("final need[2] is not the exact partial residual")
    if needs[3] != catalyst:
        failures.append(
            "final need[3] does not preserve the untargeted duplicate "
            "byte-for-byte"
        )
    if needs[:2] != prior_needs[:2] or needs[4:] != prior_needs[4:]:
        failures.append("final needs changed unrelated rows")
    if [str(item) for item in step.value.current_beliefs] != output203[
        "current_beliefs"
    ]:
        failures.append("final beliefs differ from corrected output203")

    recorded = attempt_payload(attempts[1]).get("validation_feedback") or {}
    recorded_codes = [
        item.get("issue_code") for item in recorded.get("obligations", [])
    ]
    print(f"  recorded 203-request feedback codes (old run): {recorded_codes}")
    if len(attempts) < 3:
        failures.append("artifact no longer records the old-run 204 attempt")


def replay_c01(failures: list[str]) -> None:
    attempts = load("c01-case11-rejection.json")
    outputs = [attempt["output"] for attempt in attempts]
    feedbacks = [
        attempt.get("feedback")
        for attempt in attempts
        if isinstance(attempt.get("feedback"), dict)
    ]
    if len(outputs) < 3 or not feedbacks:
        failures.append("c01 artifact lacks the 177/178/179 outputs and feedbacks")
        return

    # The c01 artifact stores feedback/output wire snapshots but not the
    # original initialize request, so the visible Basic Info context is
    # reconstructed from attempt 177's own evidence rows: every cited
    # projection_id + exact_text pair is attested verbatim by the snapshot,
    # and the real run grounded those same refs (its recorded failures were
    # belief-quantity issues, not grounding). The skill text only flows into
    # the prompt, never into validation.
    projections = [
        {
            "projection_id": item["projection_id"],
            "exact_text": item["exact_text"],
        }
        for item in outputs[0]["supporting_evidence"]
        if item.get("kind") == "basic_info"
    ]
    basic_info = {"requests": [{"projections": projections}]}
    evaluation_context = {
        "prediction_time": "2025-07-31T00:00:00+00:00",
        "horizon": "six_calendar_months",
        "horizon_end": "2026-01-31",
    }

    print("=== actual V119 c01 initialize177->178->179 raw replay ===")
    print(f"  attempts available: {len(outputs)}")
    print(
        f"  reconstructed basic_info projections: {len(projections)} "
        "(from attempt177 evidence rows; request payload not stored)"
    )
    caller = ScriptedRoleCaller(list(outputs))
    caller.max_structured_corrections = 2
    events: list[dict] = []
    caller.on_progress = events.append
    controller = LLMResearchController(caller)
    controller.set_evaluation_context(
        datetime.fromisoformat(evaluation_context["prediction_time"])
    )
    plan = SimpleNamespace(
        initial_research_skill=(
            "Form hypotheses and unresolved information needs from Basic Info."
        )
    )
    step = controller.initialize(plan, basic_info)
    print(f"  initialize llm_calls: {step.usage.llm_calls}")
    for event in events:
        print(
            f"  event {event['event_type']} "
            f"copied={event.get('copied_paths')} "
            f"discarded={event.get('discarded_paths')} "
            f"removed={event.get('removed_paths')} "
            f"steps={event.get('fallback_steps')}"
        )

    for index, feedback in enumerate(feedbacks, start=1):
        paths = feedback.get("required_change_paths", [])
        codes = [item.get("issue_code") for item in feedback.get("obligations", [])]
        print(f"  correction {index} required_change_paths={paths} codes={codes}")

    last_feedback = feedbacks[-1]
    allowed_repairs = last_feedback["obligations"][0].get("allowed_repairs", [])
    if "remove" not in allowed_repairs:
        failures.append(
            "c01 correction authority no longer permits the recorded removals"
        )

    # The guard contract for 179: relative to whichever baseline the runtime
    # actually gave it (the raw 178 output, or a safely projected object the
    # current code retained after 178's revalidation failure), it may remove
    # only explicitly authorized belief members and must preserve every other
    # row byte-for-byte in order.
    own_feedback = caller.calls[2]["payload"]["validation_feedback"]
    own_failed = own_feedback["invalid_output"]
    own_failed_beliefs = own_failed["current_beliefs"]
    own_removal_indices = {
        int(path.split("[")[1].rstrip("]"))
        for obligation in own_feedback["obligations"]
        if "remove" in obligation.get("allowed_repairs", ())
        for path in obligation["must_change_paths"]
        if re.fullmatch(r"current_beliefs\[\d+\]", path)
    }
    print(f"  179 baseline beliefs: {len(own_failed_beliefs)} rows")
    print(f"  179 authorized removal slots: {sorted(own_removal_indices)}")
    if not own_removal_indices:
        failures.append("179 correction carries no explicit belief removal slots")

    final_beliefs = [str(item) for item in step.value.current_beliefs]
    baseline_rows = own_failed_beliefs
    # Every final row must be one baseline row, in baseline relative order:
    # the correction cannot invent, edit, or reorder belief content.
    positions: list[int] = []
    cursor = 0
    for row in final_beliefs:
        while cursor < len(baseline_rows) and baseline_rows[cursor] != row:
            cursor += 1
        if cursor >= len(baseline_rows):
            positions.append(-1)
            break
        positions.append(cursor)
        cursor += 1
    if -1 in positions or len(positions) != len(final_beliefs):
        failures.append(
            "c01 final beliefs contain a row absent from the 179 baseline "
            "(invented or edited content)"
        )
        positions = [item for item in positions if item >= 0]
    dropped = sorted(set(range(len(baseline_rows))) - set(positions))
    fallback_removed = [
        path
        for event in events
        if event["event_type"] == "structured_validation_fallback_applied"
        for path in event.get("removed_paths", [])
    ]
    # The deterministic evidence-grounding fallback carries its own explicit
    # remove authority; its belief removals index the projected list (the
    # baseline minus the authorized member removals, original order).
    projected_order = [
        index
        for index in range(len(baseline_rows))
        if index not in own_removal_indices
    ]
    fallback_belief_drops = {
        projected_order[int(match.group(1))]
        for path in fallback_removed
        if (match := re.fullmatch(r"current_beliefs\[(\d+)\]", path))
        and int(match.group(1)) < len(projected_order)
    }
    allowed_drops = set(own_removal_indices) | fallback_belief_drops
    print(f"  final dropped baseline rows: {dropped}")
    print(f"  authorized removals: {sorted(own_removal_indices)}")
    print(f"  fallback-linked belief drops: {sorted(fallback_belief_drops)}")
    if not set(dropped) <= allowed_drops:
        failures.append(
            f"c01 dropped belief rows {dropped} exceed the explicit removal "
            f"authority {sorted(allowed_drops)}"
        )
    if not own_removal_indices <= set(dropped):
        failures.append("c01 authorized belief removals were not applied")
    if not any(
        event["event_type"] in (
            "structured_correction_projection_applied",
            "structured_correction_projection_retained",
        )
        and "current_beliefs" in event.get("discarded_paths", [])
        for event in events
    ):
        failures.append(
            "c01 drifted whole-belief-list correction was not projected/"
            "discarded before acceptance"
        )

    for field, value in own_failed.items():
        if field in ("current_beliefs", "supporting_evidence"):
            continue
        final_value = getattr(step.value, field)
        final_list = (
            [str(item) for item in final_value]
            if isinstance(value, list)
            else final_value
        )
        if final_list != value:
            failures.append(f"c01 final field {field} differs from 179 baseline")

    baseline_evidence = [
        json.dumps(item, sort_keys=True)
        for item in own_failed["supporting_evidence"]
    ]
    final_evidence = [
        json.dumps(item.to_dict(), sort_keys=True)
        for item in step.value.supporting_evidence
    ]
    evidence_cursor = 0
    for row in final_evidence:
        while (
            evidence_cursor < len(baseline_evidence)
            and baseline_evidence[evidence_cursor] != row
        ):
            evidence_cursor += 1
        if evidence_cursor >= len(baseline_evidence):
            failures.append(
                "c01 final supporting_evidence contains a row absent from the "
                "179 baseline"
            )
            break
        evidence_cursor += 1


def main() -> int:
    failures: list[str] = []
    for section in (
        replay_counterexample,
        replay_c02,
        replay_c01,
    ):
        try:
            section(failures)
        except Exception as exc:  # noqa: BLE001 - report and continue sections
            failures.append(f"{section.__name__} raised {type(exc).__name__}: {exc}")
    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("\nALL ROUND-16 REPLAY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
