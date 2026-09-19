"""Round-20 replay of the V122 MP Materials case-12 initialize rejection.

Loads the actual wire payloads/outputs for attempts 208 (initialize) and 209
(correction) from .delegation/fast-slow-20260919/v122/c01-case12-rejection.json
and re-executes the production initialize validation and scoped-correction
flow with the corrected temporal guard, using the ORIGINAL basic_info,
evaluation_context, and initial_research_skill from the frozen V122 run
(cross-checked against runs/.../requests/<hash>.json and attempts.json).

Attempt 207 belongs to the previous case's posthoc reflect and is only
accounted for, never replayed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
for entry in (REPO_ROOT, REPO_ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from stock_opportunity_agent.models import StructuredValidationError  # noqa: E402
from stock_opportunity_agent.research.scheme_evolution import (  # noqa: E402
    ResearchState,
)
from stock_opportunity_agent.research.evolution_output_validation import (  # noqa: E402
    _complete_parsed_role,
    _research_state_evidence_grounding_fallback,
)
from stock_opportunity_agent.research.evolution_research_validation import (  # noqa: E402
    _future_source_date_refs,
    _normalize_research_state_output,
    _raw_future_information_issues,
    _validate_research_state_refs,
)

_spec = importlib.util.spec_from_file_location(
    "round20_test_support",
    REPO_ROOT / "tests" / "evolution_runtime_test_support.py",
)
_support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_support)
ScriptedRoleCaller = _support.ScriptedRoleCaller

WIRE_PATH = (
    REPO_ROOT / ".delegation/fast-slow-20260919/v122/c01-case12-rejection.json"
)
WORKSPACE = (
    REPO_ROOT / "runs/cold_start/evolution/"
    "information-evolution-dual-self-evolution-20260920-v122"
)
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def load_attempts_ledger() -> Any:
    path = WORKSPACE / "attempts.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def ledger_hash(ledger: Any, attempt_id: int) -> str | None:
    if isinstance(ledger, list):
        entries = ledger
    elif isinstance(ledger, dict):
        entries = ledger.get("attempts", [])
        if isinstance(ledger.get(str(attempt_id)), dict):
            entries = [ledger[str(attempt_id)]]
    else:
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_id = entry.get("attempt_id", entry.get("id"))
        try:
            if int(raw_id) == attempt_id:
                return entry.get("hash", entry.get("request_hash"))
        except (TypeError, ValueError):
            continue
    return None


def verify_frozen_inputs(attempts: dict[int, dict[str, Any]]) -> None:
    print("== frozen V122 input fidelity ==")
    ledger = load_attempts_ledger()
    if ledger is None:
        print("  note: attempts.json unavailable or unreadable")
    for attempt_id in (208, 209):
        entry = attempts[attempt_id]
        wire_hash = entry["hash"]
        request_path = WORKSPACE / "requests" / f"{wire_hash}.json"
        response_path = WORKSPACE / "cache" / "responses" / f"{wire_hash}.json"
        check(
            f"attempt {attempt_id} frozen request and response cache entries exist",
            request_path.is_file() and response_path.is_file(),
        )
        if ledger is not None:
            check(
                f"attempt {attempt_id} hash matches the attempts ledger",
                ledger_hash(ledger, attempt_id) == wire_hash,
                f"ledger={ledger_hash(ledger, attempt_id)}",
            )
        if not request_path.is_file():
            continue
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request_text = request_path.read_text(encoding="utf-8")
        payload = entry.get("payload", {})
        basic_info = payload.get("basic_info")
        skill = payload.get("initial_research_skill")
        projection_rows = [
            (projection.get("projection_id"), projection.get("exact_text"))
            for request_row in (basic_info or {}).get("requests", ())
            if isinstance(request_row, dict)
            for projection in request_row.get("projections", ())
            if isinstance(projection, dict)
        ]
        unique_ids = sorted({row[0] for row in projection_rows})
        ids_linked = {
            projection_id: projection_id in request_text
            for projection_id in unique_ids
        }
        verbatim = sum(
            1
            for _pid, exact_text in projection_rows
            if isinstance(exact_text, str) and exact_text in request_text
        )
        # The wire basic_info is the canonical validation input; the frozen
        # request prompt renders the same projections through the compacted
        # indexed model view, so ids must link while long exact texts may be
        # compacted rather than verbatim.
        check(
            f"attempt {attempt_id} wire basic_info projections are linked in the "
            "frozen request",
            bool(projection_rows) and all(ids_linked.values()),
            f"{len(unique_ids)} unique ids linked={ids_linked}, "
            f"verbatim exact_texts={verbatim}/{len(projection_rows)} rows "
            "(long projections are compacted in the model view)",
        )
        context = payload.get("evaluation_context") or {}
        context_embedded = {
            key: str(value) in request_text for key, value in context.items()
        }
        check(
            f"attempt {attempt_id} evaluation_context values are embedded in the "
            "frozen request",
            all(context_embedded.values()),
            f"{context_embedded}",
        )
        skill_in_request = isinstance(skill, str) and skill in request_text
        # The literal skill text is embedded verbatim inside the frozen prompt.
        check(
            f"attempt {attempt_id} initial_research_skill text is embedded in the "
            "frozen request",
            skill_in_request,
        )


def guard_probes() -> None:
    print("== independent temporal-guard probes ==")
    prediction = date(2025, 3, 31)
    refs = lambda text: _future_source_date_refs(  # noqa: E731
        text, prediction, field_name="next_information_needs"
    )
    false_positive = (
        "What specific magnet-production milestones, volumes, or customer "
        "commitments did MP Materials disclose by 2025-03-31 for the period "
        "through 2025-09-30?"
    )
    check(
        "V122 false positive is gone (plural milestones, bounded as-of)",
        refs(false_positive) == [],
        f"refs={refs(false_positive)}",
    )
    check(
        "singular control still accepted",
        refs(false_positive.replace("milestones", "milestone")) == [],
    )
    check(
        "plural realized results still rejected",
        refs(
            "What results did the company report by 2025-03-31 for the period "
            "through 2025-09-30?"
        )
        == ["2025-09-30"],
    )
    check(
        "plural actuals still rejected",
        refs(
            "What actuals did the company disclose by 2025-03-31 for the period "
            "through 2025-09-30?"
        )
        == ["2025-09-30"],
    )
    check(
        "unbounded plural milestones still rejected",
        refs("What specific milestones will the company disclose through 2025-09-30?")
        == ["2025-09-30"],
    )
    check(
        "post-cutoff as-of bound on plural milestones still rejected",
        refs(
            "What specific milestones did the company disclose by 2025-06-30 for "
            "the period through 2025-09-30?"
        )
        == ["2025-06-30", "2025-09-30"],
    )
    check(
        "mixed pair: bounded plural targets/schedules accepted",
        refs(
            "Which disclosed capacity targets and delivery schedules had the "
            "company committed to as of 2025-03-31 for the quarters ending "
            "through 2025-09-30?"
        )
        == [],
    )
    check(
        "mixed pair: bounded realized/actuals question still rejected",
        refs(
            "Which realized volumes and actuals had the company achieved as of "
            "2025-03-31 for the period through 2025-09-30?"
        )
        == ["2025-09-30"],
    )


def normalize_codes(
    output: dict[str, Any], basic_info: dict[str, Any], context: dict[str, Any]
) -> list[str]:
    try:
        _normalize_research_state_output(
            dict(output),
            initialize=True,
            basic_info=basic_info,
            evaluation_context=context,
        )
    except StructuredValidationError as exc:
        return [issue.code for issue in exc.issues]
    except Exception as exc:  # noqa: BLE001
        return [f"untyped:{type(exc).__name__}"]
    return []


def describe_state(state: ResearchState) -> str:
    lines = [f"  decision={state.decision}"]
    for name in ("current_beliefs", "next_information_needs"):
        lines.append(f"  {name} ({len(getattr(state, name))}):")
        lines.extend(f"    [{i}] {item}" for i, item in enumerate(getattr(state, name)))
    lines.append(f"  supporting_evidence ({len(state.supporting_evidence)}):")
    for index, ref in enumerate(state.supporting_evidence):
        if ref.kind == "basic_info":
            lines.append(
                f"    [{index}] basic_info projection_id={ref.projection_id} "
                f"claim={ref.claim!r}"
            )
        else:
            lines.append(
                f"    [{index}] signal signal_ref={ref.signal_ref} "
                f"group={ref.evidence_group}[{ref.evidence_index}] "
                f"claim={ref.claim!r}"
            )
    return "\n".join(lines)


def replay_initialize(attempts: dict[int, dict[str, Any]]) -> None:
    print("== MP Materials initialize replay (attempts 208/209) ==")
    payload = attempts[208]["payload"]
    basic_info = payload["basic_info"]
    context = payload["evaluation_context"]
    raw = attempts[208]["output"]
    correction = attempts[209]["output"]

    raw_codes = normalize_codes(raw, basic_info, context)
    temporal_issues = _raw_future_information_issues(raw, context)
    check(
        "raw 208 no longer raises the bounded plural-schedule temporal issue",
        not temporal_issues,
        f"remaining temporal issues={len(temporal_issues)}, raw codes="
        f"{ {code: raw_codes.count(code) for code in sorted(set(raw_codes))} }",
    )

    def parse(value):
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
        )

    try:
        parse(correction)
        correction_valid = True
    except Exception as exc:  # noqa: BLE001
        correction_valid = False
        print(f"  raw 209 alone still rejected: {str(exc)[:240]}")
    correction_codes = normalize_codes(correction, basic_info, context)
    print(
        "  raw 209 normalize codes: "
        f"{ {code: correction_codes.count(code) for code in sorted(set(correction_codes))} }"
    )

    caller = ScriptedRoleCaller([raw, correction])
    try:
        value, usage = _complete_parsed_role(
            caller,
            stage="research_controller_initialize",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=parse,
            allow_outcomes=False,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            stable_correction_prefix=True,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )
        print("  final accepted state (exact fields):")
        print(describe_state(value))
        print(f"  llm_calls={usage.llm_calls}")
        raw_needs = list(raw["next_information_needs"])
        final_needs = [str(need) for need in value.next_information_needs]
        check(
            "final needs preserve the original 208 need list byte-for-byte",
            final_needs == raw_needs,
            f"needs={len(final_needs)} vs raw={len(raw_needs)}",
        )
        try:
            direct_209 = parse(json.loads(json.dumps(correction)))
            provenance = (
                "raw 209 accepted directly"
                if canonical(direct_209.to_dict()) == canonical(value.to_dict())
                else "owner-authorized fallback narrowed raw 209"
            )
        except Exception as exc:  # noqa: BLE001
            provenance = f"fallback result (raw 209 alone rejects: {str(exc)[:120]})"
        print(f"  final-state provenance: {provenance}")
        check(
            "controller completed honestly (no empty-evidence acceptance)",
            len(value.supporting_evidence) > 0,
            f"evidence rows={len(value.supporting_evidence)}",
        )
    except Exception as exc:  # noqa: BLE001
        print(
            "  controller replay rejected the candidate honestly: "
            f"{type(exc).__name__}: {str(exc)[:400]}"
        )
        check(
            "raw 209 correction classified honestly (still invalid, not forced)",
            not correction_valid,
            "correction alone parses" if correction_valid else "as expected",
        )


def main() -> int:
    wire = json.loads(WIRE_PATH.read_text(encoding="utf-8"))
    attempts = {entry["attempt_id"]: entry for entry in wire}
    print(
        f"wire attempts: {sorted(attempts)} "
        "(207 is the previous case's posthoc reflect; not replayed)"
    )
    verify_frozen_inputs(attempts)
    guard_probes()
    replay_initialize(attempts)
    print(f"\n{len(FAILURES)} failure(s)" + (f": {FAILURES}" if FAILURES else ""))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
