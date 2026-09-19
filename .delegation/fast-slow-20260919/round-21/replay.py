"""Round-21 investigation/replay script.

Phase A (investigation): locate and print the routing/reflection residual
helpers, reproduce the confirmed Kinross helper behavior, and decode the
v123 c01-case1 rejection evidence (attempts 5-10) from the original JSON.
Phase B (replay) is appended after the fix: replay the original H1 response
selection into the actual reflection context/contract helpers.
"""

from __future__ import annotations

import copy
import inspect
import json
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE / "src"))

import stock_opportunity_agent.research.evolution_plan_roles as plan_roles
import stock_opportunity_agent.research.evolution_research_validation as research_validation

PARENT = (
    "What forward production, cost, and capital expenditure guidance did "
    "Kinross provide by the prediction time for the remainder of 2025 and "
    "2026?"
)
RESIDUAL = (
    "Specific disclosed production, cost, and capital expenditure figures "
    "for the remainder of 2025 and 2026 are not fully covered."
)
AS_OF = date(2025, 9, 30)


def _locate(name: str):
    for module in (plan_roles, research_validation):
        fn = getattr(module, name, None)
        if fn is not None:
            return module, fn
    return None, None


def phase_a() -> None:
    print("=== helper locations ===")
    for name in (
        "_future_source_date_refs",
        "_need_as_of_bound_clause",
        "_bounded_residual_need",
        "_future_actual_need",
        "_future_expectation_need",
    ):
        module, fn = _locate(name)
        if fn is None:
            print(f"{name}: NOT FOUND")
            continue
        try:
            lines, start = inspect.getsourcelines(fn)
            src = "".join(lines)
        except (OSError, TypeError) as exc:
            src = f"<no source: {exc}>"
            start = -1
        print(f"--- {name}: {module.__name__}:{start} ({len(src.splitlines())} lines)")
        print(src)

    print("=== reproduction ===")
    print(
        "_future_source_date_refs(parent) = ",
        plan_roles._future_source_date_refs(
            PARENT, AS_OF, field_name="next_information_needs"
        ),
    )
    for mod_name, mod in (
        ("plan_roles", plan_roles),
        ("research_validation", research_validation),
    ):
        fn = getattr(mod, "_bounded_residual_need", None)
        if fn is not None:
            try:
                print(
                    f"{mod_name}._bounded_residual_need(residual, parent) = ",
                    fn(RESIDUAL, PARENT, AS_OF),
                )
            except TypeError:
                print(
                    f"{mod_name}._bounded_residual_need signature: ",
                    inspect.signature(fn),
                )
                print(
                    f"{mod_name}._bounded_residual_need(residual, parent) = ",
                    fn(RESIDUAL, PARENT),
                )
        print(f"{mod_name}._need_as_of_bound_clause(parent) = ", end="")
        fn = getattr(mod, "_need_as_of_bound_clause", None)
        print(None if fn is None else fn(PARENT))

    print("=== evidence decode ===")
    evidence_path = (
        BASE / ".delegation/fast-slow-20260919/v123/c01-case1-rejection.json"
    )
    data = json.loads(evidence_path.read_text())

    def summarize(value, depth=0, max_depth=3):
        if depth >= max_depth:
            return type(value).__name__
        if isinstance(value, dict):
            return {k: summarize(v, depth + 1, max_depth) for k, v in value.items()}
        if isinstance(value, list):
            return [
                summarize(v, depth + 1, max_depth) if i < 3 else "..."
                for i, v in enumerate(value[:4])
            ]
        if isinstance(value, str):
            return value[:120] + ("..." if len(value) > 120 else "")
        return value

    print("top-level:", json.dumps(summarize(data, max_depth=2), indent=1)[:4000])

    def walk(value, path=""):
        if isinstance(value, dict):
            for k, v in value.items():
                yield from walk(v, f"{path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                yield from walk(v, f"{path}[{i}]")
        else:
            yield path, value

    hits = [
        (p, v)
        for p, v in walk(data)
        if isinstance(v, str) and ("prediction time" in v or "Kinross" in v)
    ]
    print(f"kinross/prediction-time string fields: {len(hits)}")
    for p, v in hits[:40]:
        print(f"  {p}: {v[:220]!r}")


def phase_a2() -> None:
    import pkgutil
    import stock_opportunity_agent.research as research_pkg

    print("=== regex/helper definitions ===")
    for name in (
        "_SYMBOLIC_AS_OF_BOUND",
        "_FUTURE_EXPECTATION_OR_SCHEDULE",
        "_FUTURE_REALIZED_RESULT",
        "_FUTURE_SOURCE_CONTENT_INTENT",
        "_EXPLICIT_AS_OF_BOUND",
    ):
        module, fn = _locate(name)
        if fn is None:
            print(f"{name}: NOT FOUND")
        else:
            print(f"--- {name} ({module.__name__})")
            print(fn.pattern if hasattr(fn, "pattern") else fn)
    module, fn = _locate("_has_prediction_bounded_as_of_clause")
    if fn is not None:
        print("--- _has_prediction_bounded_as_of_clause")
        print(inspect.getsource(fn))

    print("=== consumers of _bounded_residual_need ===")
    for mod_info in pkgutil.iter_modules(research_pkg.__path__):
        mod_name = f"stock_opportunity_agent.research.{mod_info.name}"
        try:
            mod = __import__(mod_name, fromlist=["_"])
        except Exception:
            continue
        try:
            src = inspect.getsource(mod)
        except OSError:
            continue
        if "_bounded_residual_need" in src and mod is not research_validation:
            print(f"references: {mod_name}")
        for attr in ("reflection_selection_intents", "need_transition_contract"):
            if hasattr(mod, attr):
                print(f"defines {attr}: {mod_name}")

    rv_src = inspect.getsource(research_validation)
    idx = 0
    while True:
        idx = rv_src.find("_bounded_residual_need", idx + 1)
        if idx < 0:
            break
        line_no = rv_src[:idx].count("\n") + 1
        print(f"research_validation.py:{line_no}: usage")
        print(rv_src[max(0, idx - 500) : idx + 500])
        print("...")


def phase_a3() -> None:
    print("=== attempts inventory ===")
    evidence_path = (
        BASE / ".delegation/fast-slow-20260919/v123/c01-case1-rejection.json"
    )
    data = json.loads(evidence_path.read_text())
    for entry in data:
        print(
            f"attempt {entry['attempt_id']} stage={entry['stage']} "
            f"hash={entry['hash'][:12]} payload_keys="
            f"{sorted(entry.get('payload', {}))}"
        )
    print()
    for entry in data:
        if entry["attempt_id"] < 5:
            continue
        print(f"===== attempt {entry['attempt_id']} ({entry['stage']}) =====")
        payload = entry.get("payload", {})
        output = entry.get("output", {})
        for key, value in payload.items():
            if key == "basic_info":
                print(f"payload.basic_info: {len(value.get('requests', []))} requests")
                continue
            text = json.dumps(value, ensure_ascii=False)
            print(f"payload.{key}: {text[:2500]}")
        for key, value in output.items():
            text = json.dumps(value, ensure_ascii=False)
            print(f"output.{key}: {text[:2500]}")
        print()


def phase_a4() -> None:
    print("=== module heads (imports) ===")
    for mod in (plan_roles, research_validation):
        src = inspect.getsource(mod)
        print(f"--- {mod.__name__} first 60 lines")
        print("\n".join(src.splitlines()[:60]))
    print("=== plan_roles routing region 840-1000 ===")
    plan_src = inspect.getsource(plan_roles).splitlines()
    print("\n".join(f"{i + 1}: {line}" for i, line in enumerate(plan_src[839:1000])))
    print("=== research_validation pre-reflection legacy validator 1150-1260 ===")
    rv_src2 = inspect.getsource(research_validation).splitlines()
    print("\n".join(f"{i + 1}: {line}" for i, line in enumerate(rv_src2[1149:1260])))
    print("=== test references ===")
    tests_dir = BASE / "tests"
    for path in sorted(tests_dir.glob("test_*.py")):
        text = path.read_text()
        for needle in (
            "temporal scope",
            "legacy partial-answer",
            "_bounded_residual_need",
            "routing_selection_invalid",
        ):
            if needle in text:
                lines = [
                    f"  {n + 1}: {line.strip()[:150]}"
                    for n, line in enumerate(text.splitlines())
                    if needle in line
                ]
                print(f"{path.name} [{needle}]")
                print("\n".join(lines[:12]))
    print("=== _RELATIVE_FUTURE_SCOPE ===")
    module, fn = _locate("_RELATIVE_FUTURE_SCOPE")
    if fn is not None:
        print(fn.pattern)


def phase_a5() -> None:
    print("=== plan_roles imports from research_validation ===")
    plan_src = inspect.getsource(plan_roles).splitlines()
    for n, line in enumerate(plan_src[:200], start=1):
        if "research_validation" in line or (
            n > 30 and line.startswith("    _") and "future" in line
        ):
            print(f"{n}: {line}")

    print("=== fix prototype ===")
    rv = research_validation
    noun_marker = re.compile(
        r"\b(?:guidance|outlook|forecasts?|targets?|goals?|schedules?|timelines?"
        r"|milestones?|dates?|timing|releases?|reports?|openings?|commentary"
        r"|construction\s+plans?)\b"
    )
    marker = noun_marker.search(PARENT)
    print("parent noun marker:", marker.group(0) if marker else None)
    stripped = RESIDUAL.rstrip()
    terminator = stripped[-1] if stripped[-1] in ".?!" else ""
    base = stripped[:-1] if terminator else stripped
    clause = rv._SYMBOLIC_AS_OF_BOUND.search(PARENT).group(0)
    restored = f"{base}, {clause}{terminator or '.'}"
    restored2 = (
        f"{base}, {clause}, within the parent need's "
        f"{marker.group(0)}{terminator or '.'}"
    )
    for label, text in (
        ("residual", RESIDUAL),
        ("clause-only", restored),
        ("clause+marker", restored2),
    ):
        print(
            f"{label}: future_refs=",
            plan_roles._future_source_date_refs(
                text, AS_OF, field_name="next_information_needs"
            ),
            "| date.min refs=",
            plan_roles._future_source_date_refs(
                text, date.min, field_name="next_information_needs"
            ),
        )
    print("restored2 =", restored2)

    print("=== spec sections ===")
    for name in (
        "evolution_plan_roles.md",
        "evolution_research_validation.md",
    ):
        path = (
            BASE / "spec/src/stock_opportunity_agent/research" / name
        )
        lines = path.read_text().splitlines()
        print(f"--- {name}: {len(lines)} lines")
        hits = [
            n + 1
            for n, line in enumerate(lines)
            if re.search(
                r"residual|cutoff|temporal|as-of|bounded", line, re.IGNORECASE
            )
        ]
        print("hit lines:", hits[:80])


def phase_b() -> None:
    print("=== phase B: original-wire replay (post-fix) ===")
    sys.path.insert(0, str(BASE))
    from tests.evolution_runtime_test_support import (  # noqa: E402
        LLMSignalRetrievalAgent,
        PROJECT_ROOT,
        ScriptedRoleCaller,
        SignalRegistry,
        StructuredValidationError,
        validation_error,
    )
    from stock_opportunity_agent.research.scheme_evolution import (
        SignalSelectionDecision,
    )

    print(
        "SignalSelectionDecision fields:",
        [f.name for f in __import__("dataclasses").fields(SignalSelectionDecision)],
    )

    evidence_path = (
        BASE / ".delegation/fast-slow-20260919/v123/c01-case1-rejection.json"
    )
    data = json.loads(evidence_path.read_text())
    routing = next(e for e in data if e["stage"] == "signal_retrieval_cards")
    initialize = next(
        e for e in data if e["stage"] == "research_controller_initialize_correction"
    )
    needs = list(routing["payload"]["information_needs"])
    parent = needs[1]
    selections = routing["output"]["selections"]
    guidance_row = next(
        row
        for row in selections
        if row["signal_ref"] == "guidance_acceleration:v1"
    )
    residual = guidance_row["residual_need"]
    print("parent need (index 1):", parent)
    print("original residual   :", residual)

    bounded = research_validation._bounded_residual_need(
        residual, parent, AS_OF
    )
    print("post-fix bounded representation:", bounded)
    assert bounded is not None and "by the prediction time" in bounded
    assert "guidance" in bounded
    for label, when in (("prediction date", AS_OF), ("earliest cutoff", date.min)):
        refs = research_validation._future_source_date_refs(
            bounded, when, field_name="next_information_needs"
        )
        print(f"bounded representation future refs at {label}: {refs}")
        assert refs == []

    with tempfile.TemporaryDirectory() as directory:
        registry = SignalRegistry(Path(directory) / "signals")
        registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
        composed = copy.deepcopy(routing["output"])
        for row in composed["selections"]:
            if row["signal_ref"] == "guidance_acceleration:v1":
                row["residual_need"] = bounded
        caller = ScriptedRoleCaller(
            [copy.deepcopy(routing["output"]), composed]
        )
        selection = LLMSignalRetrievalAgent(caller).select(
            tuple(needs), registry.freeze(), {},
        )
        adopted = next(
            row
            for row in selection.value
            if row.signal_ref == "guidance_acceleration:v1"
        )
        print(
            "routing adopted the bounded residual on correction:",
            adopted.residual_need == bounded,
        )
        print("routing model calls used:", len(caller.calls))
        feedback = validation_error(caller.calls[1])
        print(
            "producer feedback carries temporal scope / clause / marker:",
            "temporal scope" in feedback,
            "by the prediction time" in feedback,
            "guidance" in feedback,
        )
        assert "temporal scope" in feedback

        unrelated = dict(composed)
        for row in unrelated["selections"]:
            if row["signal_ref"] == "guidance_acceleration:v1":
                row["residual_need"] = (
                    "Specific disclosed cryptocurrency mining figures for "
                    "2027 are not fully covered."
                )
        unrelated_caller = ScriptedRoleCaller(
            [copy.deepcopy(unrelated)] * 4
        )
        try:
            LLMSignalRetrievalAgent(unrelated_caller).select(
                tuple(needs), registry.freeze(), {},
            )
            raise SystemExit("unrelated residual unexpectedly accepted")
        except StructuredValidationError:
            unrelated_feedback = validation_error(unrelated_caller.calls[1])
            print(
                "unrelated residual rejected as ungrounded:",
                "grounded" in unrelated_feedback,
            )
            assert "grounded" in unrelated_feedback

    decision = SignalSelectionDecision(
        signal_ref=guidance_row["signal_ref"],
        reason_code=guidance_row["reason_code"],
        selection_reason=guidance_row["selection_reason"],
        applicability_hypothesis=guidance_row["applicability_hypothesis"],
        expected_role=guidance_row["expected_role"],
        context_tags=tuple(guidance_row["context_tags"]),
        target_need_indices=tuple(guidance_row["target_need_indices"]),
        answer_scope=guidance_row["answer_scope"],
        residual_need=residual,
    )
    context = {"prediction_time": "2025-09-30T00:00:00+00:00"}
    research_validation._reject_unrepresentable_partial_selections(
        (decision,), tuple(needs), context
    )
    print("pre-reflection admission accepts the original selection: True")

    from stock_opportunity_agent.research.scheme_evolution import ResearchState

    prior = ResearchState.from_dict(initialize["output"])
    contract = research_validation._reflection_need_transition_contract
    signature = inspect.signature(contract)
    print("transition-contract signature:", signature)
    kwargs = {}
    for name in signature.parameters:
        if name in ("evaluation_context", "context"):
            kwargs[name] = context
    try:
        obligations = contract(prior, (decision,), **kwargs)
    except TypeError as exc:
        print("transition-contract direct call unavailable:", exc)
    else:
        rendered = json.dumps(obligations, default=str, ensure_ascii=False)
        print(
            "contract embeds the bounded residual:",
            bounded in rendered or "residual_need" in rendered,
        )
        print("contract excerpt:", rendered[:800])

    realized = research_validation._bounded_residual_need(
        "Actual production results and realized cost figures for 2026 are "
        "not fully covered.",
        parent,
        AS_OF,
    )
    unbounded = research_validation._bounded_residual_need(
        residual,
        "What production and cost figures will Kinross report for 2026?",
        AS_OF,
    )
    print("realized-future residual stays None:", realized is None)
    print("unbounded-parent residual stays None:", unbounded is None)
    assert realized is None and unbounded is None
    print(
        "limitations: the original reflect response does not exist (the "
        "c01 case was rejected before any reflection call); the corrected "
        "routing script is the deterministic bounded composition, not a "
        "model output; the full frozen controller canonical batch is "
        "unavailable, so the transition contract is replayed helper-level "
        "against the prior state reconstructed from the accepted "
        "initialize-correction output."
    )


import copy
import tempfile

phase_a()
phase_a2()
phase_a3()
phase_a4()
phase_a5()
phase_b()
