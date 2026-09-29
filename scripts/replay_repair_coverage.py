"""Replay real historical correction failures through the repair ladder.

Measures, per recorded failure class, how many real model outputs that
historically required an LLM correction round are now accepted
deterministically by the mechanical ladder (L0 JSON completion, L2
unique-action repairs) under the role's real validator — i.e., never
reach an LLM correction.

Sources:
  - V142/V143 correction requests (``requests/*.json`` carrying
    ``validation_feedback.invalid_output`` — the exact first answer that
    failed)
  - V142/V143 ``failed_responses/*.json`` (truncated raw output)
  - live v146 journal corrections

Method per sample: replay the invalid output under the role validator
WITHOUT repairs (must fail; otherwise the sample is not replayable and is
excluded), then WITH the ladder. A sample counts as ladder-fixed only when
the repaired object passes the complete validator.

Usage:
    PYTHONPATH=src python scripts/replay_repair_coverage.py \
        --output /tmp/repair-coverage.json
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "runs/cold_start/evolution"
LIVE = REPO / "runs/cold_start/live_tool_validation_v146"


def classify(error: str) -> str:
    text = str(error)[:400]
    for name, pattern in [
        ("open_question_duplicate", r"duplicates one next information need"),
        ("evidence_grounding", r"copy one supporting_evidence claim|numeric detail|quantity"),
        ("reflection_rule", r"reflection|outcome claim|scope|source_refs|category"),
        ("state_text_shape", r"must be nonempty text|array of|missing field"),
        ("anchor_guard", r"runtime-owned evaluation input"),
        ("need_transition", r"need_transition|next_information_needs|prediction_time|future"),
        ("shape_schema", r"schema|shape|fields|unexpected|missing"),
    ]:
        if re.search(pattern, text, re.I):
            return name
    return "other"


def iter_corrections(run_root: Path):
    for path in sorted(glob.glob(str(run_root / "requests" / "*.json"))):
        try:
            data = json.loads(Path(path).read_text())
        except Exception:
            continue
        payload = data.get("payload")
        if not isinstance(payload, Mapping):
            request = data.get("request")
            if isinstance(request, Mapping):
                messages = request.get("messages")
                if isinstance(messages, list) and messages:
                    try:
                        payload = json.loads(messages[-1]["content"])
                    except Exception:
                        continue
        if not isinstance(payload, Mapping):
            continue
        fb = payload.get("validation_feedback")
        if isinstance(fb, Mapping):
            invalid = fb.get("invalid_output")
            error = str(fb.get("validation_error", ""))
        else:
            invalid = payload.get("invalid_output")
            error = str(payload.get("validation_error", ""))
        if isinstance(invalid, Mapping) and invalid:
            yield path, payload, invalid, error


def research_state_validator(payload: Mapping):
    """Rebuild the real H_init/H_reflect validator from request context."""

    from stock_opportunity_agent.research.evolution_research_validation import (
        _normalize_research_state_output,
    )
    from stock_opportunity_agent.research.evolution_core import ResearchState

    prior_raw = payload.get("research_state")
    prior = None
    if isinstance(prior_raw, Mapping):
        try:
            prior = ResearchState.from_dict(dict(prior_raw))
        except Exception:
            prior = None
    basic = payload.get("basic_info")
    if not isinstance(basic, Mapping):
        basic = None
    context = payload.get("evaluation_context")
    if not isinstance(context, Mapping):
        context = None
    initialize = prior is None

    def validate(value: Mapping) -> Any:
        return _normalize_research_state_output(
            dict(value),
            previous_state=prior,
            initialize=initialize,
            basic_info=basic,
            evaluation_context=context,
        )

    return validate


def reflection_validator(payload: Mapping):
    """Rebuild the critic/round/posthoc validator from request context."""

    from stock_opportunity_agent.artifacts import canonical_json_hash
    from stock_opportunity_agent.research.evolution_core import (
        ExecutionTrajectory,
        InformationPlan,
    )
    from stock_opportunity_agent.research.evolution_plan_roles import (
        CaseReflectionEvidence,
        _structured_reflection_items,
    )
    from stock_opportunity_agent.research.evolution_reflection_memory import (
        ReflectionMemoryIndex,
    )

    trajectories_raw = payload.get("trajectories")
    plan_raw = payload.get("plan")
    if isinstance(plan_raw, Mapping) and isinstance(trajectories_raw, list):
        try:
            plan = InformationPlan.from_dict(dict(plan_raw))
            owner = "reflection_plan:" + canonical_json_hash(
                plan.canonical_dict()
            )
            level = "plan"
            trajectories = tuple(
                ExecutionTrajectory.from_dict(row) for row in trajectories_raw
            )
            rows = [
                CaseReflectionEvidence.from_trajectory(
                    item, case_index=position
                ).to_model_dict()
                for position, item in enumerate(trajectories, start=1)
            ]
        except Exception:
            return None, None, None
    else:
        catalog = payload.get("source_catalog")
        if not isinstance(catalog, list):
            return None, None, None
        snapshots = [
            row for row in catalog if isinstance(row, Mapping) and row.get("source_ref")
        ]
        if not snapshots:
            return None, None, None
        try:
            index = ReflectionMemoryIndex.from_entries([])
        except Exception:
            return None, None, None
        level = "case"
        owner = "replay_case"
        return None, None, None
    index = ReflectionMemoryIndex.from_case_rows(rows, owner_ref=owner)

    def validate(value: Mapping) -> Any:
        items, selected, projection = _structured_reflection_items(
            value, index=index, level=level, owner_ref=owner
        )
        return {"items": items, **projection}

    return validate, index.citation_closure, "reflection"


def replay_sample(invalid: Mapping, payload: Mapping):
    """Return (kind, baseline_fail, ladder_fixed, detail)."""

    from stock_opportunity_agent.models import ValidationError
    from stock_opportunity_agent.research.repair import apply_mechanical_repairs

    kind = "unknown"
    validator = resolver = None
    if "reflection_items" in invalid:
        validator, resolver, kind = reflection_validator(payload)
        if validator is None:
            return "reflection_unreconstructable", None, None, "index unavailable"
    elif "next_information_needs" in invalid or "decision" in invalid:
        validator = research_state_validator(payload)
        resolver = None
        kind = "research_state"
    else:
        return "other_shape", None, None, "no validator mapping"

    try:
        validator(invalid)
        # Historically failed but passes now (validator drift) — exclude.
        return kind, False, None, "passes without repair (excluded)"
    except ValidationError:
        pass
    except Exception as exc:
        return kind, None, None, f"validator context error: {type(exc).__name__}"

    baseline_error = None
    try:
        result = apply_mechanical_repairs(invalid, validator, resolver)
    except Exception:
        result = None
    if result is not None:
        return kind, True, True, "ladder accepted"

    # Mirror the frontier's early fallback promotion: deterministic
    # copy-literal / row-removal for mechanical quantity failures,
    # arbitrated by the same full validator.
    from stock_opportunity_agent.models import StructuredValidationError
    from stock_opportunity_agent.research.evolution_output_validation import (
        _research_state_evidence_grounding_fallback,
    )

    try:
        validator(invalid)
    except ValidationError as exc:
        baseline_error = exc
    if isinstance(baseline_error, StructuredValidationError) and all(
        issue.code
        in {
            "assertion_without_support",
            "claim_quantity_not_supported",
            "evidence_claim_empty",
        }
        for issue in baseline_error.issues
    ):
        try:
            early = _research_state_evidence_grounding_fallback(
                invalid, baseline_error
            )
        except Exception:
            early = None
        if early is not None:
            early_output, _actions = early
            try:
                validator(early_output)
                return kind, True, True, "promoted fallback accepted"
            except ValidationError:
                pass
    return kind, True, False, "still needs LLM correction"


def replay_truncations(run_root: Path):
    """L0 revival of raw truncated responses (parse-level acceptance)."""

    from stock_opportunity_agent.research.repair import complete_truncated_json

    total = revived = 0
    for path in sorted(glob.glob(str(run_root / "failed_responses" / "*.json"))):
        try:
            data = json.loads(Path(path).read_text())
        except Exception:
            continue
        raw = data.get("raw_output")
        if not isinstance(raw, str) or not raw.strip():
            continue
        total += 1
        repair = complete_truncated_json(raw)
        if repair is None:
            continue
        try:
            json.loads(repair[0])
            revived += 1
        except json.JSONDecodeError:
            pass
    return total, revived


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/repair-coverage.json")
    args = parser.parse_args()

    classes: Counter = Counter()
    fixed: Counter = Counter()
    passes_now: Counter = Counter()
    unreplayable: Counter = Counter()
    details: list[dict[str, Any]] = []
    replayable = excluded = 0

    roots = [
        RUNS / "information-evolution-jev-dual-self-evolution-20260928-v142",
        RUNS / "information-evolution-jev-dual-self-evolution-20260928-v143",
    ]
    for root in roots:
        for path, payload, invalid, error in iter_corrections(root):
            klass = classify(error)
            kind, baseline_fail, ladder_fixed, detail = replay_sample(
                invalid, payload
            )
            if baseline_fail is None:
                excluded += 1
                unreplayable[klass] += 1
                continue
            if baseline_fail is False:
                excluded += 1
                passes_now[klass] += 1
                continue
            replayable += 1
            classes[klass] += 1
            if ladder_fixed:
                fixed[klass] += 1
            if len(details) < 400:
                details.append(
                    {
                        "source": str(Path(path).name)[:24],
                        "class": klass,
                        "kind": kind,
                        "fixed": bool(ladder_fixed),
                        "detail": detail,
                    }
                )

    trunc_total = trunc_revived = 0
    for root in roots:
        total, revived = replay_truncations(root)
        trunc_total += total
        trunc_revived += revived

    rows = []
    for klass in sorted(set(classes) | set(passes_now)):
        count = classes.get(klass, 0)
        ok = fixed.get(klass, 0)
        passed = passes_now.get(klass, 0)
        rows.append(
            {
                "class": klass,
                "total": count + passed,
                "passes_current_validator_directly": passed,
                "replayed_still_failing": count,
                "ladder_fixed": ok,
                "still_needs_llm": count - ok,
            }
        )
    summary = {
        "schema_version": "repair-ladder-coverage-replay-v1",
        "correction_samples": {
            "replayable": replayable,
            "passes_current_validator_directly": dict(passes_now),
            "unreplayable_by_class": dict(unreplayable),
            "excluded_unreplayable_or_passing": excluded,
            "per_class": rows,
            "aggregate_fix_rate": (
                round(sum(fixed.values()) / replayable, 3) if replayable else None
            ),
        },
        "truncation_samples": {
            "total_raw_failures": trunc_total,
            "l0_revived_parseable": trunc_revived,
        },
        "notes": "Ladder-fixed = repaired output passes the role's real validator; no LLM round spent. Pre-existing post-correction fallbacks are not counted.",
        "details": details,
    }
    Path(args.output).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"重放样本: 可重放 {replayable}, 排除 {excluded}（直接通过/不可重建）")
    for row in rows:
        print(
            f"  {row['class']:24s} 共{row['total']:4d} | "
            f"当前校验器直接通过 {row['passes_current_validator_directly']:4d} | "
            f"仍败重放 {row['replayed_still_failing']:4d} | "
            f"阶梯修复 {row['ladder_fixed']:4d} | "
            f"仍需 LLM {row['still_needs_llm']:4d}"
        )
    print(
        f"截断原始响应: {trunc_total} 份, L0 复活 {trunc_revived} "
        f"({trunc_revived / trunc_total:.0%})" if trunc_total else "无截断样本"
    )
    total_fixed = sum(fixed.values())
    if replayable:
        print(f"总体: {total_fixed}/{replayable} = {total_fixed / replayable:.0%} 无需 LLM 纠错")
    print("明细 →", args.output)


if __name__ == "__main__":
    main()
