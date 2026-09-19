"""Round-10 deterministic replay of the two actual V118 stalled correction pairs.

Reads immutable artifacts under the frozen V118 workspace, reconstructs the
production research_controller_initialize parser from the stored request
(basic_info / evaluation_context / initial_research_skill), and:

  pass A (reproduce): replays stored responses through the production
      controller with a cache-emulating script and proves the correction-2
      request is byte-identical to correction-1 (the stall mechanism);
  diagnosis: emits the exact original error, obligation scope, drift paths,
      the safe projected object, and the projected object's revalidation
      error, using production validators only.

No network, no writes outside this round directory.
"""

from __future__ import annotations

import copy
import json
import sys
import traceback
from dataclasses import replace
from pathlib import Path

ROOT = Path("/Users/l/Project/Recommandation")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.evolution_runtime_test_support import ScriptedRoleCaller  # noqa: E402
from stock_opportunity_agent.research.evolution_plan_roles import (  # noqa: E402
    LLMResearchController,
)
from stock_opportunity_agent.research import evolution_output_validation as ov  # noqa: E402
from stock_opportunity_agent.research.evolution_research_validation import (  # noqa: E402
    _normalize_research_state_output,
    _validate_research_state_refs,
)
from stock_opportunity_agent.research.scheme_evolution import (  # noqa: E402
    CandidateExecutionRejected,
    default_information_plan,
)

WS = ROOT / "runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v118"

CASES = [
    ("c01_lifetime_case5_cik_0001869198_20250331", 74, 75),
    ("c02_kinross_first_case", 76, 77),
]


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def extract_output(response: dict) -> dict:
    for key in ("json_output", "output", "value", "parsed_output", "json"):
        candidate = response.get(key)
        if isinstance(candidate, dict):
            return candidate
    content = response.get("content")
    if isinstance(content, str):
        return json.loads(content)
    raise AssertionError(
        f"unknown response envelope keys={sorted(response)} "
        f"types={ {k: type(v).__name__ for k, v in response.items()} }"
    )


def extract_payload(request: dict) -> dict:
    inner = request.get("request") if isinstance(request.get("request"), dict) else request
    candidates: list[dict] = []
    for key in ("payload", "body"):
        if isinstance(inner.get(key), dict):
            candidates.append(inner[key])
    messages = inner.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    candidates.append(parsed)
            elif isinstance(content, dict):
                candidates.append(content)
    for candidate in candidates:
        if "basic_info" in candidate:
            return candidate
    inner_keys = sorted(inner)
    raise AssertionError(f"payload with basic_info not found; inner_keys={inner_keys}")


def canonical_hash(value) -> str:
    from stock_opportunity_agent.artifacts import canonical_json_hash

    return canonical_json_hash(value)


def make_parser(basic_info, evaluation_context):
    def parser(value):
        return _validate_research_state_refs(
            ResearchState.from_dict(
                _normalize_research_state_output(
                    value,
                    initialize=True,
                    basic_info=basic_info,
                    evaluation_context=evaluation_context,
                )
            ),
            phase="initialize",
            basic_info=basic_info,
        )

    return parser


from stock_opportunity_agent.research.scheme_evolution import ResearchState  # noqa: E402


def replay_case(name: str, init_id: int, corr_id: int) -> None:
    attempts = _load(WS / "attempts.json")["attempts"]
    by_id = {a["attempt_id"]: a for a in attempts}
    request0 = _load(WS / "requests" / f"{by_id[init_id]['request_hash']}.json")
    request1 = _load(WS / "requests" / f"{by_id[corr_id]['request_hash']}.json")
    response0 = extract_output(_load(WS / "cache/responses" / f"{by_id[init_id]['request_hash']}.json"))
    response1 = extract_output(_load(WS / "cache/responses" / f"{by_id[corr_id]['request_hash']}.json"))
    payload0 = extract_payload(request0)
    payload1 = extract_payload(request1)
    basic_info = payload0["basic_info"]
    evaluation_context = payload0.get("evaluation_context")
    parser = make_parser(basic_info, evaluation_context)

    print(f"=== {name}: attempts {init_id}->{corr_id} ===")
    print(f"request_hashes: {by_id[init_id]['request_hash'][:16]}… / {by_id[corr_id]['request_hash'][:16]}…")

    # --- exact original error on the raw initialize output ---
    try:
        parser(response0)
        raise AssertionError("initial output unexpectedly passed validation")
    except Exception as exc:  # noqa: BLE001
        print(f"\n[original error]\n{type(exc).__name__}: {exc}")
        failure0 = exc

    obligations = ov._validation_obligations(failure0, response0)
    must_change_paths = [
        path
        for obligation in obligations["obligations"]
        for path in (
            *obligation["must_change_paths"],
            *obligation.get("must_change_any_of_paths", ()),
            *obligation.get("permitted_dependency_paths", ()),
        )
    ]
    print(f"\n[obligation scope] must_change_paths={must_change_paths}")

    # --- diagnosis of projection on the actual correction response ---
    drift = ov._scoped_correction_drift_paths(response0, response1, must_change_paths)
    print(f"[drift paths vs failed output] {drift}")
    projection = ov._project_scoped_correction(response0, response1, must_change_paths)
    if projection is None:
        print("[projection] None (no safe projection applicable)")
    else:
        projected, projected_paths = projection
        print(f"[projected paths] {projected_paths}")
        print(f"[projected object] {json.dumps(projected, ensure_ascii=False, sort_keys=True)}")
        try:
            parser(projected)
            print("[projected revalidation] PASSED")
        except Exception as exc:  # noqa: BLE001
            print(f"[projected revalidation error]\n{type(exc).__name__}: {exc}")

    def run_controller(script, label):
        caller = ScriptedRoleCaller(script)
        caller.max_structured_corrections = 2
        controller = LLMResearchController(caller)
        controller.evaluation_context = dict(evaluation_context) if evaluation_context else None
        plan = replace(
            default_information_plan(), initial_research_skill=payload0["initial_research_skill"]
        )
        try:
            step = controller.initialize(plan, basic_info)
            print(f"[{label}] SUCCEEDED via production validation")
            return caller, step
        except CandidateExecutionRejected as exc:
            print(f"[{label}] CandidateExecutionRejected: {str(exc)[:400]}")
        except Exception as exc:  # noqa: BLE001
            print(f"[{label}] {type(exc).__name__}: {str(exc)[:400]}")
        return caller, None

    # --- pass A: the cached identical correction response no longer stalls ---
    caller_a, step_a = run_controller([response0, response1, response1], "pass A cached-response")
    calls = caller_a.calls
    print(f"[pass A] role calls={len(calls)} stages={[c['stage'] for c in calls]}")
    if len(calls) >= 3:
        fb1 = calls[1]["payload"].get("validation_feedback")
        fb2 = calls[2]["payload"].get("validation_feedback")
        same = canonical_hash(fb1) == canonical_hash(fb2)
        print(
            f"[pass A] correction-2 feedback identical to correction-1: {same} "
            f"(hash1={canonical_hash(fb1)[:16]}… hash2={canonical_hash(fb2)[:16]}…)"
        )
        if not same and fb2 is not None:
            print(
                "[pass A] correction-2 targets new failure paths: "
                f"{fb2['obligations'][0].get('issue_code')} "
                f"{fb2['obligations'][0]['must_change_paths']}"
            )

    # --- pass B: a meaningful final correction passes production validation ---
    if name.startswith("c01"):
        narrow0 = (
            "The most recent observed adjusted close in the market series is "
            "30.5 on 2025-03-28."
        )
        shared = (
            "The adjusted close path shows a decline from 32.34, with an "
            "intermediate low of 27.7 and a rebound to 32.57."
        )
        final = copy.deepcopy(projection[0]) if projection else None
        if final is not None:
            final["supporting_evidence"][0]["claim"] = narrow0
            for index in (1, 2, 3):
                final["supporting_evidence"][index]["claim"] = shared
            final["current_beliefs"][0] = narrow0
            final["current_beliefs"][1] = shared
            final["current_beliefs"][7] = final["supporting_evidence"][7]["claim"]
    else:
        final = copy.deepcopy(projection[0]) if projection else None
        if final is not None:
            final["current_beliefs"][0] = final["supporting_evidence"][0]["claim"]
    if final is None:
        print("[pass B] skipped: no safe projection to repair")
        return
    caller_b, step_b = run_controller([response0, response1, final], "pass B scripted repair")
    calls_b = caller_b.calls
    if len(calls_b) >= 3 and step_b is not None:
        fb1 = calls_b[1]["payload"].get("validation_feedback")
        fb2 = calls_b[2]["payload"].get("validation_feedback")
        print(
            f"[pass B] correction-2 feedback differs meaningfully: "
            f"{canonical_hash(fb1) != canonical_hash(fb2)}"
        )
        needs_state = step_b.value if hasattr(step_b, "value") else step_b[0]
        needs = list(needs_state.next_information_needs)
        offending = response0["next_information_needs"][0]
        print(
            f"[pass B] offending runtime-owned need absent from final state: "
            f"{offending not in needs}"
        )
        if name.startswith("c01"):
            preserved = set(response0["next_information_needs"][1:])
            print(
                "[pass B] all non-offending original needs preserved: "
                f"{preserved.issubset(set(needs))}"
            )
        else:
            original = projection[0]
            print(
                "[pass B] unrelated drifted values (beliefs[3]/[5], "
                "resolved_questions) preserved from safe projection: "
                f"{needs_state.current_beliefs[3] == original['current_beliefs'][3] and needs_state.current_beliefs[5] == original['current_beliefs'][5] and list(needs_state.resolved_questions) == original['resolved_questions']}"
            )
    print()


def main() -> None:
    for name, init_id, corr_id in CASES:
        try:
            replay_case(name, init_id, corr_id)
        except Exception:  # noqa: BLE001
            print(f"=== {name} FAILED TO REPLAY ===")
            traceback.print_exc()


if __name__ == "__main__":
    main()
