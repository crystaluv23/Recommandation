"""Round-14 deterministic replay of the actual V119 c02/c01 rejections.

Loads the real attempt artifacts captured from
information-evolution-dual-self-evolution-20260920-v119 and verifies, through
production code only:

  1. c02 (Wynn, case2): the need-transition violation for the returned
     partial-answer duplicate is reported with returned-path-first
     coordinates (next_information_needs[3]) and an explicitly labeled
     prior_state_path (next_information_needs[2]); no unlabeled prior
     'path' remains in the instruction prose, typed paths, or metadata.
  2. c02 acceptance probes: replacing or removing the authorized returned
     original at next_information_needs[3] projects cleanly while every
     unrelated field stays byte-for-byte.
  3. c01 (Newmont, case11): the actual attempt-179 drifted correction
     (authorized removals 2/4 plus unauthorized removal 5 and swapped 6/7)
     reconciles content-anchored to exactly beliefs 0,1,3,5,6,7 — the
     unauthorized deletion is undone, valid siblings keep their values and
     order, and every other field of the failed output is preserved
     byte-for-byte; ambiguity and vanished-without-authority
     counterexamples stay fail-closed.

No network, no writes outside this round directory, run artifacts untouched.
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROUND14 = Path(__file__).resolve().parent
ROOT = ROUND14.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_opportunity_agent.research.evolution_output_validation import (  # noqa: E402
    _project_scoped_correction,
)
from stock_opportunity_agent.research.evolution_research_validation import (  # noqa: E402
    _need_transition_validation_issue,
    _targeted_answer_need_transition_errors,
)

V119 = ROUND14.parent / "v119"


def load(name: str) -> list[dict]:
    with (V119 / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def selection_view(intent: dict) -> SimpleNamespace:
    return SimpleNamespace(
        reason_code=intent["reason_code"],
        signal_ref=intent["signal_ref"],
        target_need_indices=list(intent["target_need_indices"]),
        answer_scope=intent.get("answer_scope", "full"),
        residual_need=intent.get("residual_need", ""),
    )


def replay_c02(failures: list[str]) -> None:
    attempts = load("c02-case2-rejection.json")
    first = attempts[0]
    payload = first["payload"]
    prior_needs = payload["research_state"]["next_information_needs"]
    returned_needs = first["output"]["next_information_needs"]
    selection = selection_view(payload["executed_selection_intents"][0])
    evaluation_context = payload["evaluation_context"]

    print("=== actual V119 c02 output202 transition-error coordinates ===")
    errors = _targeted_answer_need_transition_errors(
        SimpleNamespace(next_information_needs=prior_needs),
        SimpleNamespace(next_information_needs=returned_needs),
        (selection,),
        {selection.signal_ref},
        {selection.signal_ref},
        evaluation_context=evaluation_context,
    )
    print(f"transition errors: {len(errors)}")
    if len(errors) != 1:
        failures.append(f"c02 expected 1 transition error, got {len(errors)}")
        return
    error = errors[0]
    print(f"  returned_path={error.get('returned_path')}")
    print(f"  prior_state_path={error.get('prior_state_path')}")
    residual = error["required_residual_need"]
    residual_index = returned_needs.index(residual)
    print(f"  residual already present at returned index {residual_index}")
    if error.get("returned_path") != "next_information_needs[3]":
        failures.append("c02 returned_path is not the actual invalid row [3]")
    if error.get("prior_state_path") != "next_information_needs[2]":
        failures.append("c02 prior_state_path is not the prior rule index [2]")
    if "path" in error:
        failures.append("c02 error dict still carries an unlabeled 'path' key")

    issue = _need_transition_validation_issue(
        error, SimpleNamespace(next_information_needs=returned_needs)
    )
    print("=== user-visible obligation coordinates (actual instruction prose) ===")
    print(f"  typed paths: {issue.paths}")
    print(f"  message head: {issue.message[:180]}...")
    if issue.paths != ("next_information_needs[3]",):
        failures.append(f"c02 typed paths target wrong row: {issue.paths}")
    if "'path':" in issue.message:
        failures.append("c02 instruction prose still shows an unlabeled path")
    if "'returned_path': 'next_information_needs[3]'" not in issue.message:
        failures.append("c02 instruction prose does not name returned_path [3]")
    if "'prior_state_path': 'next_information_needs[2]'" not in issue.message:
        failures.append("c02 instruction prose does not label prior_state_path [2]")
    if issue.paths[0] == f"next_information_needs[{residual_index}]":
        failures.append("c02 correction targets the already-correct residual row")

    print("=== c02 acceptance probes on the actual output202 object ===")
    failed_output = dict(first["output"])
    removed = {
        **failed_output,
        "next_information_needs": [
            need for index, need in enumerate(returned_needs) if index != 3
        ],
    }
    projection = _project_scoped_correction(
        failed_output, removed, ["next_information_needs[3]"]
    )
    if projection is None:
        failures.append("c02 authorized removal of returned needs[3] failed to project")
    else:
        projected, _ = projection
        if projected["next_information_needs"] != removed["next_information_needs"]:
            failures.append("c02 removal projection changed the needs list")
        for field in ("current_beliefs", "supporting_evidence", "decision"):
            if projected[field] != failed_output[field]:
                failures.append(f"c02 removal projection changed unrelated {field}")
        print("  removal of returned needs[3]: projected, unrelated fields intact")
    replaced = {
        **failed_output,
        "next_information_needs": [
            residual if index == 3 else need
            for index, need in enumerate(returned_needs)
        ],
    }
    projection = _project_scoped_correction(
        failed_output, replaced, ["next_information_needs[3]"]
    )
    if projection is None:
        failures.append("c02 authorized replacement of returned needs[3] failed")
    elif projection[0]["next_information_needs"] != replaced["next_information_needs"]:
        failures.append("c02 replacement projection changed the needs list")
    else:
        print("  replacement of returned needs[3] with the residual: projected")


def replay_c01(failures: list[str]) -> None:
    attempts = load("c01-case11-rejection.json")
    last = attempts[-1]
    feedback = last["feedback"]
    failed_output = feedback["invalid_output"]
    corrected_output = last["output"]
    must_change_paths = list(feedback["required_change_paths"])
    allowed_repairs = feedback["obligations"][0]["allowed_repairs"]
    removal_allowances = {
        "current_beliefs": {
            int(path.split("[")[1].rstrip("]"))
            for path in must_change_paths
            if path.startswith("current_beliefs[") and "remove" in allowed_repairs
        }
    }
    failed_beliefs = failed_output["current_beliefs"]

    print("=== actual V119 c01 attempt179 drifted correction reconciliation ===")
    print(f"  failed beliefs: {len(failed_beliefs)}")
    print(f"  corrected beliefs: {len(corrected_output['current_beliefs'])}")
    print(f"  must_change_paths: {must_change_paths}")
    projection = _project_scoped_correction(
        failed_output,
        corrected_output,
        must_change_paths,
        member_removal_allowances=removal_allowances,
    )
    if projection is None:
        failures.append("c01 drifted correction still has no safe projection")
        return
    projected, projected_paths = projection
    expected = [
        failed_beliefs[index] for index in (0, 1, 3, 5, 6, 7)
    ]
    print(f"  projected beliefs: {len(projected['current_beliefs'])}")
    print(f"  projected paths: {projected_paths}")
    if projected["current_beliefs"] != expected:
        failures.append(
            "c01 reconciled beliefs are not exactly 0,1,3,5,6,7 with original "
            "values and order"
        )
    else:
        print("  reconciled beliefs = failed rows 0,1,3,5,6,7 in original order")
    for field, value in failed_output.items():
        if field == "current_beliefs":
            continue
        if projected[field] != value:
            failures.append(f"c01 projection changed unrelated field {field}")

    print("=== c01 fail-closed counterexamples on the same rows ===")
    ambiguous = dict(failed_output)
    ambiguous["current_beliefs"] = [
        failed_beliefs[0], failed_beliefs[0], failed_beliefs[1],
    ]
    ambiguous_corrected = {
        **corrected_output,
        "current_beliefs": [failed_beliefs[0], failed_beliefs[0]],
    }
    if _project_scoped_correction(
        ambiguous,
        ambiguous_corrected,
        ["current_beliefs[1]"],
        member_removal_allowances={"current_beliefs": {1}},
    ) is not None:
        failures.append("c01 duplicate-content mapping was not fail-closed")
    else:
        print("  duplicate content: no projection (fail closed)")
    unauthorized = dict(failed_output)
    unauthorized["current_beliefs"] = list(failed_beliefs)
    unauthorized_corrected = {
        **corrected_output,
        "current_beliefs": [
            failed_beliefs[index]
            for index in (0, 1, 3, 6, 7)
        ],
    }
    probe = _project_scoped_correction(
        unauthorized,
        unauthorized_corrected,
        ["current_beliefs[2]"],
        member_removal_allowances={"current_beliefs": set()},
    )
    if probe is not None:
        failures.append(
            "c01 vanished authorized member without removal authority projected"
        )
    else:
        print("  vanished authorized member without removal authority: no projection")


def main() -> int:
    failures: list[str] = []
    replay_c02(failures)
    replay_c01(failures)
    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("\nALL ROUND-14 REPLAY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
