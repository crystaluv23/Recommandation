"""Round-15 deterministic replay of the actual V119 c02/c01 artifacts.

Verifies, through production code only and no model calls:

  1. c02 (Wynn, case2): the need-transition false positive on the raw
     duplicate-occurrence output202 disappears (zero transition errors for
     attempts 202-204), while numeric evidence validation on output202
     stays (the raw defect that actually required correction 203), and
     correction 203/204 remain transition-eligible under the safe scope.
  2. The reviewer's production counterexample — a provided-but-empty
     member-removal allowance root — no longer infers removal authority.
  3. c01 (Newmont, case11): the actual attempt-179 drifted correction still
     reconciles content-anchored to beliefs 0,1,3,5,6,7 with original
     values/order, unrelated fields preserved, and fail-closed probes.

Exit code 0 only when every hard check passes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROUND15 = Path(__file__).resolve().parent
ROOT = ROUND15.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from stock_opportunity_agent.research.evolution_output_validation import (  # noqa: E402
    _project_scoped_correction,
)
from stock_opportunity_agent.research.evolution_research_validation import (  # noqa: E402
    _need_transition_validation_issue,
    _raw_basic_claim_quantity_issues,
    _raw_quantitative_assertion_link_issues,
    _targeted_answer_need_transition_errors,
)

V119 = ROUND15.parent / "v119"


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


def recorded_validation_errors(node, trail: str = "") -> list[str]:
    """Collect recorded validation/error strings from one attempt artifact."""

    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"validation_error", "error"} and isinstance(value, str):
                found.append(f"{trail}.{key}: {value[:400]}")
            else:
                found.extend(recorded_validation_errors(value, f"{trail}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node[:6]):
            found.extend(recorded_validation_errors(item, f"{trail}[{index}]"))
    return found


def replay_c02(failures: list[str]) -> None:
    attempts = load("c02-case2-rejection.json")
    print(f"=== actual V119 c02 attempts: {len(attempts)} ===")
    for number, attempt in enumerate(attempts, start=202):
        payload = attempt.get("payload") or attempt.get("feedback") or {}
        output = attempt.get("output")
        recorded = recorded_validation_errors(attempt)
        for line in recorded:
            print(f"  recorded {line}")
        if not isinstance(output, dict) or not isinstance(payload, dict):
            print(f"attempt {number}: no payload/output pair, skipped")
            continue
        research_state = payload.get("research_state") or (
            payload.get("invalid_output") or {}
        )
        prior_needs = research_state.get("next_information_needs")
        returned_needs = output.get("next_information_needs")
        intents = payload.get("executed_selection_intents") or payload.get(
            "selection_intents"
        ) or []
        if not isinstance(prior_needs, list) or not isinstance(returned_needs, list):
            print(f"attempt {number}: need lists unavailable, skipped")
            continue
        answer_refs = {
            intent["signal_ref"]
            for intent in intents
            if intent.get("reason_code") == "answer_need"
        }
        context = payload.get("evaluation_context")
        errors = _targeted_answer_need_transition_errors(
            SimpleNamespace(next_information_needs=prior_needs),
            SimpleNamespace(next_information_needs=returned_needs),
            tuple(selection_view(intent) for intent in intents),
            answer_refs,
            answer_refs,
            evaluation_context=context,
        )
        print(
            f"attempt {number}: transition errors={len(errors)} "
            f"prior={len(prior_needs)} returned={len(returned_needs)}"
        )
        for error in errors:
            print(
                f"  {error.get('returned_path')} <- "
                f"{error.get('prior_state_path')}: {error.get('issue')}"
            )
            issue = _need_transition_validation_issue(
                error, SimpleNamespace(next_information_needs=returned_needs)
            )
            print(f"  typed paths: {issue.paths}")
        if errors:
            failures.append(
                f"c02 attempt {number} still reports a need-transition error"
            )
        if number == 202:
            quantity_issues = [
                *(issue.code for issue in _raw_basic_claim_quantity_issues(output)),
                *(
                    issue.code
                    for issue in _raw_quantitative_assertion_link_issues(output)
                ),
            ]
            print(f"attempt 202 raw numeric-evidence issues: {quantity_issues}")
            recorded_text = "\n".join(recorded)
            had_transition_rejection = "transition" in recorded_text
            numeric_markers = (
                "quantit", "numeric", "exact_text", "literal", "claim"
            )
            has_numeric_rejection = any(
                marker in recorded_text for marker in numeric_markers
            )
            print(
                f"attempt 202 recorded rejection included transition "
                f"false positive={had_transition_rejection}, "
                f"numeric evidence defect={has_numeric_rejection}"
            )
            if had_transition_rejection and not has_numeric_rejection:
                failures.append(
                    "c02 artifact does not corroborate the corrected diagnosis"
                )


def replay_allowance_counterexample(failures: list[str]) -> None:
    print("=== reviewer empty-allowance counterexample (post-fix) ===")
    result = _project_scoped_correction(
        {"rows": ["invalid", "keep1", "keep2"]},
        {"rows": ["keep2"]},
        ["rows[0]"],
        member_removal_allowances={},
    )
    print(f"result = {result!r}")
    if result is not None:
        failures.append("empty allowance root still infers removal authority")


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
    expected = [failed_beliefs[index] for index in (0, 1, 3, 5, 6, 7)]
    print(f"  projected beliefs: {len(projected['current_beliefs'])}")
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
            failed_beliefs[index] for index in (0, 1, 3, 6, 7)
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


def replay_v89_probe(failures: list[str]) -> None:
    print("=== v89 blind-predictor correction-drift probe ===")
    from tests.evolution_runtime_test_support import ScriptedRoleCaller

    from stock_opportunity_agent.research.evolution_plan_roles import (
        LLMBlindPredictor,
    )
    from stock_opportunity_agent.research.evolution_output_validation import (
        _project_scoped_correction,
    )
    from stock_opportunity_agent.research.scheme_evolution import BlindPrediction

    canonical = BlindPrediction.from_dict(
        {
            "is_surge": False,
            "candidate_judgment": "unlikely",
            "magnitude": None,
            "confidence": {"level": "low"},
            "key_reasons": ["One reason.", "Two reason."],
            "uncertainties": ["Uncertainty."],
            "session_id": "s",
        }
    )
    print(f"from_dict key_reasons type: {type(canonical.key_reasons).__name__}")

    invalid = {
        "candidate_judgment": "unlikely",
        "magnitude": None,
        "confidence": {"level": "low"},
        "key_reasons": [
            "Current price $19.38 is far below the defined doubling threshold.",
            "Management reaffirmed guidance without an upward revision.",
        ],
        "uncertainties": ["Commodity prices may change the outlook."],
        "session_id": "fixture-session",
    }
    drifted = {
        "candidate_judgment": "possible",
        "magnitude": "2-3x",
        "confidence": {"level": "low"},
        "key_reasons": ["Strong momentum may support a re-rating."],
        "uncertainties": ["The price target remains below the threshold."],
        "session_id": "fixture-session",
    }
    projection = _project_scoped_correction(
        invalid, drifted, ["key_reasons[0]"]
    )
    if projection is None:
        print("projection: None")
    else:
        projected, paths = projection
        print(
            f"projected key_reasons type: "
            f"{type(projected['key_reasons']).__name__} = "
            f"{projected['key_reasons']!r}"
        )
        print(f"projected paths: {paths}")

    caller = ScriptedRoleCaller([invalid, drifted])
    prediction = LLMBlindPredictor(caller).predict(
        {
            "prediction_baseline": {
                "status": "available",
                "mean_adjusted_close": 23.982,
                "trading_dates": ["2025-09-29"],
            },
            "final_research_state": {},
        }
    )
    print(f"predictor llm_calls: {prediction.usage.llm_calls}")
    print(f"predictor key_reasons: {prediction.value.key_reasons!r}")
    print(
        f"predictor key_reasons type: "
        f"{type(prediction.value.key_reasons).__name__}"
    )


def main() -> int:
    failures: list[str] = []
    for section in (
        replay_c02,
        replay_allowance_counterexample,
        replay_c01,
        replay_v89_probe,
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
    print("\nALL ROUND-15 REPLAY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
