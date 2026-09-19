"""Round-18 replay: rerun the round-17 original-wire replay unaltered, then
verify the three narrow boundary repairs with offline fixtures.

Part 1 loads round-17/replay.py by path and runs its replay_checks on the
original V120 wire files (raw95/96 chain, compliant fixture, fail-closed
fixtures) without modifying any round-17 evidence.

Part 2 (offline, ScriptedRoleCaller only):
  R1. literal-only basic_literal_identity_mismatch obligation: the
      deterministic fallback restores the exact prior literal with no
      removals, and the production _complete_parsed_role accepts it only
      after full parser revalidation with untouched siblings preserved.
  R2. prior state with only Signal evidence: a novel Basic ref is reported
      as a remove-only typed obligation even though the prior Basic map is
      empty; a combined numeric+novel defect appears in the same initial
      feedback; the novel ref never survives and the deep tagged-ref guard
      still rejects it if it does.
  R3. the remove-only identity codes evict their row only under explicit
      remove authority; replace-only/add-only obligations remove nothing.

Exit code 0 only when every check passes.
"""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

ROUND18 = Path(__file__).resolve().parent
ROOT = ROUND18.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.evolution_runtime_test_support import ScriptedRoleCaller  # noqa: E402

from stock_opportunity_agent.models import (  # noqa: E402
    StructuredValidationError,
    ValidationError,
    ValidationIssue,
)
from stock_opportunity_agent.research.evolution_output_validation import (  # noqa: E402
    _complete_parsed_role,
    _research_state_evidence_grounding_fallback,
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

PRIOR_LITERAL = "8-K body with 17 CFR 230.425 and 17 CFR 240.14a-12 markers"
PRIOR_STATE = {
    "contradictions": [],
    "current_beliefs": [
        "The filing identifies the registrant.",
        "cash_reserves=42",
    ],
    "decision": "continue",
    "hypotheses": ["One hypothesis."],
    "next_information_needs": ["Need one?"],
    "open_questions": [],
    "resolved_questions": ["Resolved one."],
    "supporting_evidence": [
        {
            "claim": "The filing identifies the registrant.",
            "exact_text": PRIOR_LITERAL,
            "kind": "basic_info",
            "projection_id": "projection_lit_a",
        },
        {
            "claim": "cash_reserves=42",
            "evidence_group": "supporting",
            "evidence_index": 0,
            "kind": "signal",
            "signal_ref": "cash_reserves:v1",
        },
    ],
}
EVALUATION_CONTEXT = {
    "prediction_time": "2025-03-31T00:00:00+00:00",
    "horizon": "six_calendar_months",
    "horizon_end": "2025-09-30",
}


def heading(title: str) -> None:
    print(f"\n=== {title} ===")


def make_parser(prior: ResearchState):
    def parse(value):
        normalized = _normalize_research_state_output(
            dict(value),
            previous_state=prior,
            evaluation_context=EVALUATION_CONTEXT,
        )
        return _validate_research_state_refs(
            ResearchState.from_dict(normalized),
            phase="reflect",
            previous_state=prior,
        )

    return parse


def run_role(caller, prior: ResearchState):
    return _complete_parsed_role(
        caller,
        stage="research_controller_reflect",
        system_prompt="Return the fixed contract.",
        payload={},
        parser=make_parser(prior),
        allow_outcomes=False,
        enforce_scoped_correction=True,
        exact_compaction_scope=True,
        stable_correction_prefix=True,
        final_validation_fallback=_research_state_evidence_grounding_fallback,
    )


def identity_failure(failures: list[str]) -> StructuredValidationError:
    try:
        _normalize_research_state_output(
            dict(_literal_only_invalid()),
            previous_state=ResearchState.from_dict(PRIOR_STATE),
            evaluation_context=EVALUATION_CONTEXT,
        )
    except StructuredValidationError as exc:
        return exc
    failures.append("literal-only invalid output unexpectedly normalized")
    raise AssertionError("unreachable")


def _literal_only_invalid() -> dict:
    invalid = deepcopy(PRIOR_STATE)
    invalid["supporting_evidence"][0]["exact_text"] = (
        "8-K body with 230.425 and 17 CFR 240.14a-12 markers"
    )
    return invalid


def check_literal_only_restoration(failures: list[str]) -> None:
    heading("R1. restoration-only fallback accepted after revalidation")
    invalid = _literal_only_invalid()
    failure = identity_failure(failures)
    codes = sorted(issue.code for issue in failure.issues)
    print(f"  literal-only feedback codes: {codes}")
    if codes != ["basic_literal_identity_mismatch"]:
        failures.append(f"literal-only feedback is not exactly the identity defect: {codes}")
    recovered = _research_state_evidence_grounding_fallback(invalid, failure)
    if recovered is None:
        failures.append("restoration-only obligation set was declined")
        return
    restored, actions = recovered
    print(
        f"  fallback removed={actions['removed_paths']} "
        f"normalized={actions['normalized_paths']}"
    )
    if actions["removed_paths"] != ():
        failures.append("restoration-only fallback removed unauthorized rows")
    if actions["normalized_paths"] != ("supporting_evidence[0].exact_text",):
        failures.append("restoration-only fallback did not report the literal path")
    if restored["supporting_evidence"][0]["exact_text"] != PRIOR_LITERAL:
        failures.append("restored literal is not byte-exact")

    caller = ScriptedRoleCaller([invalid, deepcopy(invalid)])
    caller.max_structured_corrections = 1
    events: list[dict] = []
    caller.on_progress = events.append
    value, usage = run_role(caller, ResearchState.from_dict(PRIOR_STATE))
    print(
        f"  production run llm_calls={usage.llm_calls}; "
        f"literal_restored={value.supporting_evidence[0].exact_text == PRIOR_LITERAL}"
    )
    if value.supporting_evidence[0].exact_text != PRIOR_LITERAL:
        failures.append("production run did not restore the exact prior literal")
    if [str(item) for item in value.current_beliefs] != PRIOR_STATE["current_beliefs"]:
        failures.append("production run changed untouched beliefs")
    if value.supporting_evidence[1].claim != "cash_reserves=42":
        failures.append("production run changed the untouched signal row")
    if [str(item) for item in value.next_information_needs] != ["Need one?"]:
        failures.append("production run changed untouched needs")
    if [str(item) for item in value.hypotheses] != ["One hypothesis."]:
        failures.append("production run changed untouched hypotheses")
    if [str(item) for item in value.resolved_questions] != ["Resolved one."]:
        failures.append("production run changed untouched resolved questions")
    fallback_events = [
        event
        for event in events
        if event["event_type"] == "structured_validation_fallback_applied"
    ]
    if len(fallback_events) != 1:
        failures.append("expected exactly one fallback application")
    else:
        print(
            f"  fallback event removed={fallback_events[0]['removed_paths']} "
            f"normalized={fallback_events[0]['normalized_paths']}"
        )
        if fallback_events[0]["removed_paths"] != []:
            failures.append("fallback event records unauthorized removals")
        if fallback_events[0]["normalized_paths"] != [
            "supporting_evidence[0].exact_text"
        ]:
            failures.append("fallback event lacks the normalized literal path")


def check_signal_only_prior(failures: list[str]) -> None:
    heading("R2. novel Basic ref against a signal-only prior state")
    signal_only = deepcopy(PRIOR_STATE)
    signal_only["supporting_evidence"].pop(0)
    prior = ResearchState.from_dict(signal_only)
    output = deepcopy(PRIOR_STATE)
    issues = _raw_basic_literal_identity_issues(output, prior)
    summary = [
        (issue.code, list(issue.paths), list(issue.allowed_repairs))
        for issue in issues
    ]
    print(f"  issues with empty prior Basic map: {summary}")
    expected = [
        ("basic_ref_not_in_prior_state", ["supporting_evidence[0]"], ["remove"])
    ]
    if summary != expected:
        failures.append(f"novel Basic ref not reported remove-only: {summary}")
    if _raw_basic_literal_identity_issues(output, None) != []:
        failures.append("initialize (previous_state=None) entered the identity check")

    combined = deepcopy(output)
    combined["current_beliefs"][1] = "revenue_growth_yoy=0.182443"
    try:
        _normalize_research_state_output(
            dict(combined),
            previous_state=prior,
            evaluation_context=EVALUATION_CONTEXT,
        )
    except StructuredValidationError as exc:
        codes = sorted(issue.code for issue in exc.issues)
        print(f"  combined numeric+novel feedback codes: {codes}")
        if codes != ["assertion_without_support", "basic_ref_not_in_prior_state"]:
            failures.append(f"combined defects not reported together: {codes}")
    else:
        failures.append("combined numeric+novel output unexpectedly normalized")
    try:
        _validate_research_state_refs(
            ResearchState.from_dict(dict(combined)),
            phase="reflect",
            previous_state=prior,
        )
    except ValidationError as exc:
        print(
            "  deep guard rejects surviving novel ref: "
            f"{'reflect cannot introduce a new Basic Info ref' in str(exc)}"
        )
        if "reflect cannot introduce a new Basic Info ref" not in str(exc):
            failures.append("deep guard rejected the novel ref for another reason")
    else:
        failures.append("deep guard accepted a surviving novel Basic ref")

    caller = ScriptedRoleCaller([combined, deepcopy(combined)])
    try:
        value, _usage = run_role(caller, prior)
    except CandidateExecutionRejected:
        print("  novel ref chain: CandidateExecutionRejected (never survived)")
        return
    final_rows = [
        row.to_dict() if hasattr(row, "to_dict") else dict(row)
        for row in value.supporting_evidence
    ]
    survived = any(
        row.get("projection_id") == "projection_lit_a" for row in final_rows
    )
    print(f"  novel ref chain accepted after eviction; survived={survived}")
    if survived:
        failures.append("novel Basic ref survived into the final state")


def check_remove_authority(failures: list[str]) -> None:
    heading("R3. remove-only identity codes require remove authority")
    output = dict(PRIOR_STATE)
    for code in ("basic_ref_not_in_prior_state", "basic_literal_identity_ambiguous"):
        for repairs in (("replace",), ("add",)):
            declined = _research_state_evidence_grounding_fallback(
                output,
                StructuredValidationError(
                    [
                        ValidationIssue(
                            code=code,
                            message="identity defect",
                            paths=("supporting_evidence[0]",),
                            allowed_repairs=repairs,
                            repair_context={"projection_id": "projection_lit_a"},
                        )
                    ]
                ),
            )
            if declined is not None:
                failures.append(
                    f"{code} evicted a row under repairs={repairs} (no remove authority)"
                )
        recovered = _research_state_evidence_grounding_fallback(
            output,
            StructuredValidationError(
                [
                    ValidationIssue(
                        code=code,
                        message="identity defect",
                        paths=("supporting_evidence[0]",),
                        allowed_repairs=("remove",),
                        repair_context={"projection_id": "projection_lit_a"},
                    )
                ]
            ),
        )
        if recovered is None:
            failures.append(f"{code} declined its own remove-authorized eviction")
        else:
            restored, actions = recovered
            print(
                f"  {code} remove-authorized eviction: "
                f"removed={actions['removed_paths']}"
            )
            if actions["removed_paths"] != (
                "supporting_evidence[0]",
                "current_beliefs[0]",
            ):
                failures.append(f"{code} eviction removed unexpected paths")
            if restored["current_beliefs"] != ["cash_reserves=42"]:
                failures.append(f"{code} eviction left unexpected beliefs")
    if output != PRIOR_STATE:
        failures.append("failed_output was mutated by the fallback probes")


def load_round17():
    spec = importlib.util.spec_from_file_location(
        "round17_replay", ROUND18.parent / "round-17" / "replay.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    failures: list[str] = []
    try:
        round17 = load_round17()
        round17.replay_checks(failures)
        check_literal_only_restoration(failures)
        check_signal_only_prior(failures)
        check_remove_authority(failures)
        print("\nno paid model call was made: every role is a ScriptedRoleCaller")
    except Exception as exc:  # noqa: BLE001 - report and continue
        failures.append(f"replay raised {type(exc).__name__}: {exc}")
    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("\nALL ROUND-18 REPLAY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
