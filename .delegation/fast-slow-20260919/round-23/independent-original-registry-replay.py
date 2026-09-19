"""Round-23 replay: original V123 routing attempts 7/8 under the actual date.

Original wire evidence comes from ../v123/c01-case1-rejection.json (actual
attempts 5-10). The original raw reflection response never existed because
V123 failed at the pre-reflection admission check, so every artifact below
that follows routing is a clearly labeled synthetic continuation, never an
original model response.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from tests.evolution_runtime_test_support import (  # noqa: E402
    PROJECT_ROOT,
    ScriptedRoleCaller,
    SignalRegistry,
)
from stock_opportunity_agent.research.evolution_plan_roles import (  # noqa: E402
    LLMSignalRetrievalAgent,
)
from stock_opportunity_agent.research.evolution_research_validation import (  # noqa: E402
    _bounded_residual_need,
    _reflection_need_transition_contract,
    _reflection_selection_intents,
    _reject_unrepresentable_partial_selections,
)
from stock_opportunity_agent.research.scheme_evolution import (  # noqa: E402
    ResearchState,
)
from stock_opportunity_agent.signal_library import (  # noqa: E402
    SignalBatchResult,
    SignalEvidence,
    SignalResult,
    SignalValue,
)

EVIDENCE = REPO / ".delegation/fast-slow-20260919/v123/c01-case1-rejection.json"
# Round-21/state.md confirmed prediction_date 2025-09-30 for V123 c01 case 1;
# wire basic_info rows carry available_at 2025-09-30T00:00:00+00:00.
PREDICTION_TIME = datetime(2025, 9, 30, tzinfo=timezone.utc)


def find_selections_output(entry: dict) -> dict:
    for key in ("response", "output", "model_output", "parsed", "result"):
        value = entry.get(key)
        if isinstance(value, dict) and "selections" in value:
            return value
    raise SystemExit(
        f"no selections output found in entry keys={sorted(entry)}"
    )


def main() -> int:
    entries = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    routing = [
        entry
        for entry in entries
        if str(entry.get("stage", "")).startswith("signal_retrieval_cards")
    ]
    print(f"wire entries={len(entries)} routing_attempts={len(routing)}")
    print(
        "wire stages:",
        sorted({str(entry.get("stage")) for entry in entries}),
    )
    first = routing[0]
    payload = first["payload"]
    needs = tuple(payload["information_needs"])
    print(f"attempt_id={first.get('attempt_id')} stage={first.get('stage')}")
    for index, need in enumerate(needs):
        print(f"  information_needs[{index}]: {need}")
    context = {
        "prediction_time": PREDICTION_TIME.isoformat(),
        "horizon": "six_calendar_months",
        "horizon_end": "2026-03-30",
    }
    outputs = [find_selections_output(entry) for entry in routing[:2]]
    for position, output in enumerate(outputs, start=1):
        for row in output["selections"]:
            print(
                f"original wire output {position}: signal_ref="
                f"{row.get('signal_ref')} residual_need={row.get('residual_need')}"
            )
    research_context = payload.get("research_context") or {}
    state = ResearchState(
        hypotheses=tuple(research_context.get("hypotheses", ())),
        current_beliefs=tuple(research_context.get("current_beliefs", ())),
        contradictions=tuple(research_context.get("contradictions", ())),
        resolved_questions=tuple(research_context.get("resolved_questions", ())),
        open_questions=tuple(research_context.get("open_questions", ())),
        next_information_needs=needs,
    )
    with tempfile.TemporaryDirectory() as directory:
        registry = SignalRegistry(REPO / "runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v123/signals")
        snapshot = registry.freeze()
        agent = LLMSignalRetrievalAgent(ScriptedRoleCaller(outputs))
        agent.set_evaluation_context(PREDICTION_TIME)
        selection = agent.select(needs, snapshot, {}, research_state=state)
    caller = agent.caller
    print(f"replay routing calls={len(caller.calls)} (7 then 8 as needed)")
    if len(caller.calls) > 1 and "validation_feedback" in (
        caller.calls[1].get("payload") or {}
    ):
        error = caller.calls[1]["payload"]["validation_feedback"][
            "validation_error"
        ]
        print(f"attempt-7 correction feedback (original wire attempt 8): {error}")
    for row in selection.value:
        print(
            f"accepted selection: signal_ref={row.signal_ref} "
            f"reason={row.reason_code} residual_need={row.residual_need}"
        )
    routed_payload_context = caller.calls[0]["payload"].get(
        "evaluation_context"
    )
    print(f"routing payload evaluation_context={routed_payload_context}")
    if routed_payload_context != context:
        print("FAIL: routing payload did not carry the actual date context")
        return 1
    for row in selection.value:
        if row.reason_code != "answer_need" or row.answer_scope != "partial":
            continue
        if len(row.target_need_indices) != 1:
            continue
        target = needs[row.target_need_indices[0]]
        bounded = _bounded_residual_need(
            row.residual_need, target, PREDICTION_TIME.date()
        )
        print(f"shared bounded representation: {bounded}")
        if bounded is None:
            print("FAIL: accepted residual has no bounded representation")
            return 1
    try:
        _reject_unrepresentable_partial_selections(
            selection.value, needs, context
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: pre-reflection admission rejected the replay: {exc}")
        return 1
    print("pre-reflection admission: PASS (V123 rejected here originally)")
    intents = _reflection_selection_intents(
        selection.value,
        information_needs=needs,
        evaluation_context=context,
    )
    for row in intents:
        print(f"reflection selection intent (synthetic): {row}")
    # Synthetic continuation: an adoptable result per selected ref. The
    # original wire never produced a reflection response.
    synthetic_results = tuple(
        SignalResult(
            signal_id=row.signal_ref.split(":v", 1)[0],
            version=int(row.signal_ref.split(":v", 1)[1]),
            value=SignalValue.POSITIVE,
            confidence=0.9,
            interpretation="synthetic adoptable evidence",
            supporting_evidence=(
                SignalEvidence(
                    document_id="synthetic-doc",
                    exact_span="synthetic adoptable evidence",
                    timestamp=PREDICTION_TIME,
                ),
            ),
        )
        for row in selection.value
    )
    batch = SignalBatchResult(
        results=synthetic_results,
        signal_calls=len(synthetic_results),
    )
    contract = _reflection_need_transition_contract(
        state,
        selection.value,
        batch,
        evaluation_context=context,
    )
    for rule in contract["need_rules"]:
        print(f"need transition contract rule (synthetic): {rule}")
    bounded_needs = tuple(
        row["residual_need"]
        for row in intents
        if isinstance(row.get("residual_need"), str)
    )
    for residual in bounded_needs:
        for rule in contract["need_rules"]:
            for action in rule["available_answer_actions"]:
                if action.get("residual_need") == residual:
                    break
            else:
                continue
            break
        else:
            print(
                "FAIL: bounded residual missing from the transition contract: "
                f"{residual}"
            )
            return 1
    with tempfile.TemporaryDirectory() as directory:
        registry = SignalRegistry(REPO / "runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v123/signals")
        snapshot = registry.freeze()
        next_agent = LLMSignalRetrievalAgent(
            ScriptedRoleCaller([{"selections": []}])
        )
        next_agent.set_evaluation_context(PREDICTION_TIME)
        next_selection = next_agent.select(
            bounded_needs or needs, snapshot, {}
        )
    print(
        "next routing over bounded residual needs: calls=1 "
        f"accepted={len(next_selection.value)} (empty is valid; no temporal "
        "rejection)"
    )
    print("REPLAY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
