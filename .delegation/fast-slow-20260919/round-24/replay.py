"""Round-24 replay of the V124 Kinross c01 case-1 initialize rejection.

Loads the actual wire payloads/outputs for attempts 3 (initialize), 4 and 5
(corrections) from .delegation/fast-slow-20260919/v124/c01-case1-rejection.json
and re-executes the production initialize validation and scoped-correction
flow with the corrected temporal guard (equivalent before/prior-to as-of
bounds and the projected/projection(s)/anticipated bounded-expectation
vocabulary), using the ORIGINAL basic_info, evaluation_context, and
initial_research_skill from the frozen V124 run.

Attempts 1-2 belong to earlier plan stages and 6-8 to later attempts; they
are only accounted for, never replayed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime
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
    "round24_test_support",
    REPO_ROOT / "tests" / "evolution_runtime_test_support.py",
)
_support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_support)
ScriptedRoleCaller = _support.ScriptedRoleCaller

WIRE_PATH = (
    REPO_ROOT / ".delegation/fast-slow-20260919/v124/c01-case1-rejection.json"
)
EVOLUTION_RUNS = REPO_ROOT / "runs" / "cold_start" / "evolution"
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def resolve_workspace() -> Path | None:
    if not EVOLUTION_RUNS.is_dir():
        return None
    matches = sorted(EVOLUTION_RUNS.glob("*v124*"))
    return matches[0] if matches else None


def load_attempts_ledger(workspace: Path | None) -> Any:
    if workspace is None:
        return None
    path = workspace / "attempts.json"
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
    print("== frozen V124 input fidelity ==")
    workspace = resolve_workspace()
    print(f"  frozen workspace: {workspace}")
    ledger = load_attempts_ledger(workspace)
    if ledger is None:
        print("  note: attempts.json unavailable or unreadable")
    for attempt_id in (3, 4, 5):
        entry = attempts[attempt_id]
        wire_hash = entry["hash"]
        request_path = (
            workspace / "requests" / f"{wire_hash}.json"
            if workspace is not None
            else None
        )
        response_path = (
            workspace / "cache" / "responses" / f"{wire_hash}.json"
            if workspace is not None
            else None
        )
        check(
            f"attempt {attempt_id} frozen request and response cache entries exist",
            request_path is not None
            and request_path.is_file()
            and response_path is not None
            and response_path.is_file(),
        )
        if ledger is not None:
            check(
                f"attempt {attempt_id} hash matches the attempts ledger",
                ledger_hash(ledger, attempt_id) == wire_hash,
                f"ledger={ledger_hash(ledger, attempt_id)}",
            )
        if request_path is None or not request_path.is_file():
            continue
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
        # Like round 20: the wire basic_info is the canonical validation
        # input; the frozen prompt renders projections through a compacted
        # model view, so ids must link while long exact texts may be
        # compacted rather than verbatim.
        check(
            f"attempt {attempt_id} wire basic_info projections are linked in "
            "the frozen request",
            bool(projection_rows) and all(ids_linked.values()),
            f"{len(unique_ids)} unique ids linked={ids_linked}, "
            f"verbatim exact_texts={verbatim}/{len(projection_rows)} rows",
        )
        context = payload.get("evaluation_context") or {}
        context_embedded = {
            key: str(value) in request_text for key, value in context.items()
        }
        check(
            f"attempt {attempt_id} evaluation_context values are embedded in "
            "the frozen request",
            all(context_embedded.values()),
            f"{context_embedded}",
        )
        skill_in_request = isinstance(skill, str) and skill in request_text
        check(
            f"attempt {attempt_id} initial_research_skill text is embedded in "
            "the frozen request",
            skill_in_request,
        )


def guard_probes(prediction: date) -> None:
    print("== independent temporal-guard probes ==")
    refs = lambda text: _future_source_date_refs(  # noqa: E731
        text, prediction, field_name="next_information_needs"
    )
    raw3_need1 = (
        "What forward guidance for full-year 2025 and 2026 production, "
        "cost of sales, and capital expenditures did Kinross provide in "
        "its Q2 2025 earnings call or subsequent filings available "
        "before the prediction time, and did it revise prior guidance?"
    )
    check(
        "V124 raw3 need1 (before the prediction time) false positive is gone",
        refs(raw3_need1) == [],
        f"refs={refs(raw3_need1)}",
    )
    check(
        "symbolic prior-to bound accepted",
        refs(
            "What cost and capital expenditure guidance for 2026 had "
            "Kinross disclosed prior to the prediction time?"
        )
        == [],
    )
    explicit_bound = f"{prediction.strftime('%B')} {prediction.day}, {prediction.year}"
    future_year = prediction.year + 1
    check(
        "explicit before/prior-to cutoffs at the prediction date accepted",
        refs(
            f"What capital expenditure guidance did Kinross provide prior "
            f"to {explicit_bound} for its {future_year} production plans?"
        )
        == []
        and refs(
            f"Which disclosed production targets for {future_year} were "
            f"available before {explicit_bound}?"
        )
        == [],
    )
    raw5_need3 = (
        "What proven and probable reserve and measured and indicated "
        "resource quantities, by asset, had Kinross disclosed as of "
        "the prediction time to support its projected annual "
        "attributable gold equivalent production of 2.0 million oz "
        "between 2025 and 2027?"
    )
    check(
        "V124 raw5 need3 (bounded projected expectation) false positive is gone",
        refs(raw5_need3) == [],
        f"refs={refs(raw5_need3)}",
    )
    check(
        "projected realized results still rejected",
        refs(
            f"What projected {future_year} results had Kinross reported as "
            "of the prediction time?"
        )
        == [str(future_year)],
    )
    check(
        "projected actuals with a before bound still rejected",
        refs(
            f"What projected actuals for {future_year} were available "
            "before the prediction time?"
        )
        == [str(future_year)],
    )
    check(
        "unbounded projection still rejected",
        refs(
            f"What is management's projection for {future_year} "
            "attributable production?"
        )
        == [str(future_year)],
    )
    check(
        "cutoff after prediction rejected",
        bool(
            refs(
                f"What {future_year} production guidance did Kinross provide "
                f"prior to March {future_year}?"
            )
        ),
    )
    check(
        "open-ended after window rejected",
        bool(
            refs(
                f"What production updates will Kinross publish after "
                f"March {future_year}?"
            )
        ),
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
        lines.extend(
            f"    [{i}] {item}" for i, item in enumerate(getattr(state, name))
        )
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
    print("== Kinross c01 initialize replay (attempts 3/4/5) ==")
    payload = attempts[3]["payload"]
    basic_info = payload["basic_info"]
    context = payload["evaluation_context"]
    raw = attempts[3]["output"]
    first = attempts[4]["output"]
    second = attempts[5]["output"]
    prediction = datetime.fromisoformat(
        str(context["prediction_time"]).replace("Z", "+00:00")
    ).date()
    print(f"  prediction_time={prediction.isoformat()}")

    raw_needs = [
        need
        for need in raw.get("next_information_needs", [])
        if isinstance(need, str)
    ]
    print(f"  raw 3 needs ({len(raw_needs)}):")
    for index, need in enumerate(raw_needs):
        print(
            f"    [{index}] refs="
            f"{_future_source_date_refs(need, prediction, field_name='next_information_needs')}"
            f" :: {need}"
        )
    temporal = _raw_future_information_issues(raw, context)
    temporal_paths = [issue.paths[0] for issue in temporal]
    need1_index = next(
        (
            index
            for index, need in enumerate(raw_needs)
            if "forward guidance for full-year 2025 and 2026" in need
        ),
        None,
    )
    check(
        "raw 3 need1 (bounded 2026 guidance, before the prediction time) no "
        "longer raises the temporal issue",
        need1_index is not None
        and f"next_information_needs[{need1_index}]" not in temporal_paths,
        f"need1 index={need1_index}, temporal paths={temporal_paths}",
    )
    unbounded_index = next(
        (
            index
            for index, need in enumerate(raw_needs)
            if "projected annual attributable gold equivalent production" in need
            and "schedule supports that projection" in need
        ),
        None,
    )
    check(
        "raw 3 unbounded projection need still rejected",
        unbounded_index is not None
        and f"next_information_needs[{unbounded_index}]" in temporal_paths,
        f"unbounded index={unbounded_index}, paths={temporal_paths}",
    )
    raw_codes = normalize_codes(raw, basic_info, context)
    print(
        "  raw 3 normalize codes: "
        f"{ {code: raw_codes.count(code) for code in sorted(set(raw_codes))} }"
    )
    numeric = {
        "claim_quantity_not_supported",
        "assertion_without_support",
    } & set(raw_codes)
    check(
        "raw 3 numeric issues remain independently enforced",
        bool(numeric),
        f"numeric codes={sorted(numeric)}",
    )
    for attempt_id, output in ((4, first), (5, second)):
        codes = normalize_codes(output, basic_info, context)
        print(
            f"  raw {attempt_id} normalize codes: "
            f"{ {code: codes.count(code) for code in sorted(set(codes))} }"
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

    caller = ScriptedRoleCaller([raw, first, second])
    caller.max_structured_corrections = 2
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
        final_needs = [str(need) for need in value.next_information_needs]
        flagged_need_paths = set(temporal_paths)
        feedback = caller.calls[1]["payload"].get("validation_feedback", {})
        for path in feedback.get("required_change_paths", []):
            if str(path).startswith("next_information_needs["):
                flagged_need_paths.add(str(path))
        need1_text = raw_needs[need1_index] if need1_index is not None else ""
        check(
            "final needs keep raw 3 need1 (legal 2026 scope) byte-for-byte",
            bool(need1_text)
            and "2026" in need1_text
            and need1_text in final_needs,
            f"need1 kept with 2026={bool(need1_text) and '2026' in need1_text and need1_text in final_needs}",
        )
        unflagged = [
            need
            for index, need in enumerate(raw_needs)
            if f"next_information_needs[{index}]" not in flagged_need_paths
        ]
        missing = [need for need in unflagged if need not in final_needs]
        check(
            "unflagged raw 3 needs preserved byte-for-byte (sibling preservation)",
            not missing,
            f"missing={missing}",
        )
        projected_need = next(
            (
                need
                for need in second.get("next_information_needs", [])
                if isinstance(need, str)
                and "proven and probable" in need
                and "projected" in need
            ),
            None,
        )
        if projected_need is not None:
            check(
                "raw 5 final corrected projected reserve need accepted",
                projected_need in final_needs,
            )
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
            "rejection did not reinstate the raw3 need1 temporal objection",
            "next_information_needs[0]" not in str(exc)[:2000]
            or "future" not in str(exc)[:2000].lower(),
        )


def main() -> int:
    wire = json.loads(WIRE_PATH.read_text(encoding="utf-8"))
    attempts = {entry["attempt_id"]: entry for entry in wire}
    print(
        f"wire attempts: {sorted(attempts)} "
        "(3 initialize; 4/5 corrections; others not replayed)"
    )
    verify_frozen_inputs(attempts)
    context = attempts[3]["payload"]["evaluation_context"]
    prediction = datetime.fromisoformat(
        str(context["prediction_time"]).replace("Z", "+00:00")
    ).date()
    guard_probes(prediction)
    replay_initialize(attempts)
    print(f"\n{len(FAILURES)} failure(s)" + (f": {FAILURES}" if FAILURES else ""))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
