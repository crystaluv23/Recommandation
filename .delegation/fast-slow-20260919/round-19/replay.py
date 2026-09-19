"""Round-19 independent replay of the V121 Bumble reflect and Kinross initialize rejections.

Loads the actual wire payloads/outputs from
.delegation/fast-slow-20260919/v121/rejections-wire.json and re-executes the
production reflect/initialize role validation and scoped-correction flow.

Known limitation (as in round 17): the persisted Bumble signal batch is the
compact H_reflect model view, not the canonical SignalBatchResult, so the
replay reconstructs a lossy stand-in batch from that view. Only the
price_momentum_126d result is adopted by the raw outputs, and its canonical
interpretation is carried in the view, so the adopted-claim quantity checks
use the same literals the production run saw.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
for entry in (REPO_ROOT, REPO_ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from stock_opportunity_agent.models import StructuredValidationError  # noqa: E402
from stock_opportunity_agent.research.scheme_evolution import (  # noqa: E402
    ResearchState,
)
from stock_opportunity_agent.signal_library import (  # noqa: E402
    SignalCoverage,
    SignalValue,
)
from stock_opportunity_agent.research.evolution_output_validation import (  # noqa: E402
    _complete_parsed_role,
    _research_state_evidence_grounding_fallback,
)
from stock_opportunity_agent.research.evolution_research_validation import (  # noqa: E402
    _normalize_research_state_output,
    _raw_basic_claim_quantity_issues,
    _raw_future_information_issues,
    _research_evidence_key,
    _signal_result_has_adoptable_evidence,
    _targeted_answer_need_transition_errors,
    _validate_research_state_refs,
)

_spec = importlib.util.spec_from_file_location(
    "round19_test_support",
    REPO_ROOT / "tests" / "evolution_runtime_test_support.py",
)
_support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_support)
ScriptedRoleCaller = _support.ScriptedRoleCaller

WIRE_PATH = (
    REPO_ROOT / ".delegation/fast-slow-20260919/v121/rejections-wire.json"
)
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def fake_selections(rows: list[dict[str, Any]]) -> tuple[Any, ...]:
    return tuple(
        SimpleNamespace(
            signal_ref=row["signal_ref"],
            reason_code=row["reason_code"],
            selection_reason=row.get("selection_reason", ""),
            target_need_indices=tuple(row.get("target_need_indices", ())),
            answer_scope=row.get("answer_scope"),
            residual_need=row.get("residual_need"),
        )
        for row in rows
    )


def fake_batch(rows: list[dict[str, Any]]) -> Any:
    results = []
    for row in rows:
        fallback_span = row.get("exact_claim_if_adopted") or row.get(
            "interpretation", {}
        ).get("summary", "")
        groups = {}
        for group in ("supporting", "counter"):
            groups[group] = [
                SimpleNamespace(
                    exact_span=item.get("model_evidence_text") or fallback_span,
                    timestamp=None,
                )
                for item in row.get("evidence", {}).get(group, [])
            ]
        results.append(
            SimpleNamespace(
                ref=row["signal_ref"],
                signal_id=row["signal_id"],
                version=row["version"],
                value=SignalValue(row["state"]["value"]),
                confidence=row["state"]["confidence"],
                coverage=SignalCoverage(row["status"]["coverage"]),
                interpretation=(
                    row.get("exact_claim_if_adopted")
                    or row.get("interpretation", {}).get("summary", "")
                ),
                supporting_evidence=groups["supporting"],
                counter_evidence=groups["counter"],
            )
        )
    return SimpleNamespace(results=results)


def reflect_parser(prior: ResearchState, batch: Any, selections, context):
    def parse(value):
        normalized = _normalize_research_state_output(
            dict(value),
            previous_state=prior,
            evaluation_context=context,
        )
        return _validate_research_state_refs(
            ResearchState.from_dict(normalized),
            phase="reflect",
            previous_state=prior,
            batch=batch,
            selections=selections,
            evaluation_context=context,
        )

    return parse


def transition_error_count(
    prior: ResearchState,
    output: dict[str, Any],
    selections,
    batch: Any,
    context,
) -> tuple[int, dict[str, int]]:
    """Independently validate need-transition obligations and exact counts."""

    normalized = _normalize_research_state_output(
        dict(output), previous_state=prior, evaluation_context=context
    )
    state = ResearchState.from_dict(normalized)
    results = {result.ref: result for result in batch.results}
    prior_keys = {
        _research_evidence_key(ref) for ref in prior.supporting_evidence
    }
    adopted = {
        str(ref.signal_ref)
        for ref in state.supporting_evidence
        if ref.kind == "signal"
        and _research_evidence_key(ref) not in prior_keys
        and str(ref.signal_ref) in results
    }
    available = {
        result.ref
        for result in batch.results
        if _signal_result_has_adoptable_evidence(result)
    }
    errors = _targeted_answer_need_transition_errors(
        prior, state, selections, adopted, available, evaluation_context=context
    )
    needs = tuple(state.next_information_needs)
    counts = {
        need: needs.count(need)
        for need in dict.fromkeys(tuple(prior.next_information_needs))
    }
    return len(errors), counts


def _preview(mapping: dict[str, int]) -> dict[str, int]:
    return {key[:48]: value for key, value in mapping.items()}


def replay_bumble(attempts: dict[int, dict[str, Any]]) -> None:
    print("== Bumble reflect (attempts 102/103) ==")
    payload = attempts[102]["payload"]
    raw = attempts[102]["output"]
    correction = attempts[103].get("output")
    if correction is None:
        print(
            "note: attempt 103 carries no distinct output snapshot; the raw "
            "102 output is replayed as the failed correction object"
        )
        correction = raw
    prior = ResearchState.from_dict(payload["research_state"])
    context = payload["evaluation_context"]
    selections = fake_selections(payload["executed_selection_intents"])
    batch = fake_batch(payload["signal_batch"])

    error_count, raw_counts = transition_error_count(
        prior, raw, selections, batch, context
    )
    check(
        "raw 102 violates the need transition contract",
        error_count == 2,
        f"errors={error_count}, counts={_preview(raw_counts)}",
    )

    try:
        reflect_parser(prior, batch, selections, context)(correction)
        direct = True
    except Exception as exc:  # noqa: BLE001
        direct = False
        print(f"       correction alone rejected: {str(exc)[:160]}")
    check(
        "the correction alone is not a valid final state",
        not direct,
        "still missing one duplicate occurrence",
    )

    caller = ScriptedRoleCaller([raw, correction])
    value, _usage = _complete_parsed_role(
        caller,
        stage="research_controller_reflect",
        system_prompt="Return the fixed contract.",
        payload={},
        parser=reflect_parser(prior, batch, selections, context),
        allow_outcomes=False,
        enforce_scoped_correction=True,
        exact_compaction_scope=True,
        stable_correction_prefix=True,
        final_validation_fallback=_research_state_evidence_grounding_fallback,
    )
    final_dict = value.to_dict()
    needs = list(final_dict["next_information_needs"])
    prior_needs = [str(need) for need in prior.next_information_needs]
    guidance = prior_needs[0]
    blackstone = prior_needs[5]
    check(
        "final state restores both duplicate occurrences",
        needs.count(guidance) == 2,
        f"guidance count={needs.count(guidance)}",
    )
    check(
        "final state restores the omitted need exactly once",
        needs.count(blackstone) == 1,
        f"blackstone count={needs.count(blackstone)}",
    )
    check(
        "every prior need keeps at least its prior multiplicity",
        all(needs.count(need) >= prior_needs.count(need) for need in prior_needs),
        f"total rows={len(needs)}",
    )
    final_errors, final_counts = transition_error_count(
        prior, final_dict, selections, batch, context
    )
    check(
        "final state independently validates with zero transition errors",
        final_errors == 0,
        f"counts={_preview(final_counts)}",
    )
    feedback = caller.calls[1]["payload"]["validation_feedback"]
    restore = [
        obligation
        for obligation in feedback["obligations"]
        if obligation["issue_code"] == "research_need_transition_invalid"
    ]
    check(
        "initial feedback carries restore_exactly with occurrence counts",
        len(restore) == 2
        and all(
            obligation["required_action"] == "restore_exactly"
            and isinstance(obligation.get("required_need_occurrences"), int)
            for obligation in restore
        ),
        f"obligations={len(restore)}",
    )


_NUMBER_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])[-+]?\d[\d,]*(?:\.\d+)?"
    r"(?:\s*(?:trillion|billion|million|thousand|mm|bn|tn|k|m|b|t))?"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def strip_quantities(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _NUMBER_TOKEN.sub(" ", text)).strip()


def replay_kinross(attempts: dict[int, dict[str, Any]]) -> None:
    print("== Kinross initialize (attempts 104-106) ==")
    payload = attempts[104]["payload"]
    basic_info = payload["basic_info"]
    context = payload["evaluation_context"]
    raw = attempts[104]["output"]

    codes: list[str] = []
    try:
        _normalize_research_state_output(
            dict(raw),
            initialize=True,
            basic_info=basic_info,
            evaluation_context=context,
        )
    except StructuredValidationError as exc:
        codes = [issue.code for issue in exc.issues]
    except Exception as exc:  # noqa: BLE001
        codes = [f"untyped:{type(exc).__name__}"]
    quantity_codes = [code for code in codes if code == "claim_quantity_not_supported"]
    decidable_groups = len(_raw_basic_claim_quantity_issues(raw))
    check(
        "raw 104 initial feedback aggregates temporal and quantity issues",
        bool(codes)
        and codes[0] == "future_information_unavailable"
        and len(quantity_codes) == decidable_groups
        and decidable_groups >= 1,
        f"codes={ {code: codes.count(code) for code in sorted(set(codes))} }, "
        f"claim_groups={decidable_groups}",
    )

    corrected_codes: list[str] = []
    corrected = attempts[105].get("output")
    if corrected is not None:
        try:
            _normalize_research_state_output(
                dict(corrected),
                initialize=True,
                basic_info=basic_info,
                evaluation_context=context,
            )
        except StructuredValidationError as exc:
            corrected_codes = [issue.code for issue in exc.issues]
        except Exception as exc:  # noqa: BLE001
            corrected_codes = [f"untyped:{type(exc).__name__}"]
        corrected_groups = len(_raw_basic_claim_quantity_issues(corrected))
        check(
            "attempt 105 output exposes every independently decidable "
            "quantity group in one feedback",
            "future_information_unavailable" not in corrected_codes
            and corrected_codes.count("claim_quantity_not_supported")
            == corrected_groups,
            f"codes={ {code: corrected_codes.count(code) for code in sorted(set(corrected_codes))} }, "
            f"claim_groups={corrected_groups}",
        )

    future_need_indexes = sorted(
        int(match.group(1))
        for match in (
            re.fullmatch(r"next_information_needs\[(\d+)\]", issue.paths[0])
            for issue in _raw_future_information_issues(raw, context)
            if issue.paths
        )
        if match is not None
    )

    def kparse(value):
        normalized = _normalize_research_state_output(
            dict(value),
            initialize=True,
            basic_info=basic_info,
            evaluation_context=context,
        )
        return _validate_research_state_refs(
            ResearchState.from_dict(normalized),
            phase="initialize",
            basic_info=basic_info,
            evaluation_context=context,
        )

    compliant = json.loads(json.dumps(raw))
    for index in reversed(future_need_indexes):
        compliant["next_information_needs"].pop(index)
    narrowed: list[tuple[str, str]] = []
    for item in compliant["supporting_evidence"]:
        old_claim = item.get("claim") or ""
        new_claim = strip_quantities(old_claim) or (
            "The cited disclosure is retained."
        )
        item["claim"] = new_claim
        narrowed.append((old_claim, new_claim))

    def narrow_belief(belief: str) -> str:
        for old_claim, new_claim in narrowed:
            if belief == old_claim:
                return new_claim
        return belief

    compliant["current_beliefs"] = [
        narrow_belief(belief) for belief in compliant["current_beliefs"]
    ]
    caller = ScriptedRoleCaller([raw, compliant])
    caller.max_structured_corrections = 2
    try:
        value, usage = _complete_parsed_role(
            caller,
            stage="research_controller_initialize",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=kparse,
            allow_outcomes=False,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            stable_correction_prefix=True,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )
        check(
            "compliant fixture corrects every aggregated issue in budget",
            True,
            f"llm_calls={usage.llm_calls}, "
            f"needs={len(value.next_information_needs)}, "
            f"evidence={len(value.supporting_evidence)}",
        )
    except Exception as exc:  # noqa: BLE001
        check(
            "compliant fixture corrects every aggregated issue in budget",
            False,
            f"{type(exc).__name__}: {str(exc)[:300]}",
        )

    raw106 = attempts.get(106, {}).get("output")
    if raw106 is None:
        print("[SKIP] raw 106 output snapshot unavailable in wire evidence")
        return
    try:
        kparse(raw106)
        check(
            "raw 106 classified honestly",
            False,
            "raw 106 output validated; expected an honest still-invalid verdict",
        )
    except Exception as exc:  # noqa: BLE001
        check(
            "raw 106 classified honestly as still invalid",
            True,
            f"{type(exc).__name__}: {str(exc)[:200]}",
        )


def main() -> int:
    wire = json.loads(WIRE_PATH.read_text(encoding="utf-8"))
    attempts = {entry["attempt_id"]: entry for entry in wire}
    print(f"wire attempts: {sorted(attempts)}")
    print(
        "outputs present: "
        + str(
            {
                attempt_id: "output" in entry
                for attempt_id, entry in sorted(attempts.items())
            }
        )
    )
    replay_bumble(attempts)
    replay_kinross(attempts)
    print(f"\n{len(FAILURES)} failure(s)" + (f": {FAILURES}" if FAILURES else ""))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
