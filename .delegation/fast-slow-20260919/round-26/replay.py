"""Round-26 replay of the V125 information_plan_propose rejections.

Loads the original wire (.delegation/fast-slow-20260919/v125/
proposal-rejections.json, attempts 1-6), decodes each original request
payload from request.messages[-1].content, compares the decoded object
(never a raw substring) against the audit payload, rebuilds the exact
stored proposer output as an InformationPlan, and replays it through the
current proposal validation with the original proposal_context
(available_source_types). The recorded rejections were
source_ownership_not_guaranteed raised on locally negated first-party
ownership phrases; this replay reports which objections remain after the
round-26 fix, honestly preserving any other real issues.

Stated limitations: parents for the deterministic change-focus check are
not present in the wire, so _validate_proposal_change_focus is not
replayed; the full LLMInformationPlanProposer adapter (prompt
construction plus role caller) is not driven — the replay calls the same
proposal validation functions the adapter applies.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from stock_opportunity_agent.models import (
    StructuredValidationError,
    ValidationError,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _validate_plan_for_proposer_context,
    _validate_proposed_request_scope,
)
from stock_opportunity_agent.research.scheme_evolution import (
    default_information_plan,
)

WIRE = (
    Path(__file__).resolve().parents[1] / "v125" / "proposal-rejections.json"
)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = (
    PROJECT_ROOT
    / "runs/cold_start/evolution"
    / "information-evolution-dual-self-evolution-20260920-v125"
)
ATTEMPTS = (1, 2, 3, 4, 5, 6)

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def find_mapping_with_keys(
    node: Any, keys: tuple[str, ...]
) -> Mapping[str, Any] | None:
    """Depth-first search for a mapping holding every required key."""

    if isinstance(node, Mapping):
        if all(key in node for key in keys):
            return node
        for value in node.values():
            found = find_mapping_with_keys(value, keys)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = find_mapping_with_keys(item, keys)
            if found is not None:
                return found
    return None


def build_plan(output: Mapping[str, Any]):
    """Rebuild the proposer output on the default plan's request prototype."""

    base = default_information_plan()
    proto = base.basic_info_policy.requests[0]
    rows = [
        replace(
            proto,
            request_id=row.get("request_id") or f"replay_request_{index + 1}",
            description=row["description"],
            source_types=tuple(row.get("source_types", ())),
            max_documents=row.get("max_documents", proto.max_documents),
            lookback_days=row.get("lookback_days", proto.lookback_days),
            query=row.get("query") or None,
        )
        for index, row in enumerate(output["B"]["requests"])
    ]
    return replace(
        base,
        basic_info_policy=replace(base.basic_info_policy, requests=tuple(rows)),
        initial_research_skill=output["H_init"],
        reflection_skill=output["H_reflect"],
        analysis_prompt=output["H_analyse"],
    )


def replay_plan(plan, available: tuple[str, ...]) -> dict[str, str]:
    results: dict[str, str] = {}
    try:
        _validate_proposed_request_scope(plan)
        results["request_scope"] = "accepted"
    except StructuredValidationError as exc:
        results["request_scope"] = (
            "StructuredValidationError "
            + str(sorted({issue.code for issue in exc.issues}))
        )
    except ValidationError as exc:
        results["request_scope"] = "ValidationError " + str(exc)[:160]
    try:
        _validate_plan_for_proposer_context(plan, available_source_types=available)
        results["full_context"] = "accepted"
    except StructuredValidationError as exc:
        results["full_context"] = (
            "StructuredValidationError "
            + str(sorted({issue.code for issue in exc.issues}))
        )
    except ValidationError as exc:
        results["full_context"] = "ValidationError " + str(exc)[:200]
    return results


def probe_plan(description: str, source_types=("company_news",)):
    output = {
        "B": {
            "requests": [
                {
                    "request_id": "probe_news",
                    "description": description,
                    "source_types": list(source_types),
                    "max_documents": 3,
                }
            ]
        },
        "H_init": "Probe hypothesis instruction.",
        "H_reflect": "Probe reflection instruction.",
        "H_analyse": "Probe analysis instruction.",
    }
    return build_plan(output)


def load_original_request(request_hash: Any):
    """Locate the stored role request for a hash and decode its last message."""

    if not isinstance(request_hash, str) or not request_hash:
        return None, "entry carries no request hash"
    if not WORKSPACE.is_dir():
        return None, f"workspace missing: {WORKSPACE}"
    for candidate in sorted(WORKSPACE.rglob(f"*{request_hash}*")):
        try:
            value = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        holder = find_mapping_with_keys(value, ("messages",))
        if holder is None:
            continue
        messages = holder["messages"]
        if not isinstance(messages, list) or not messages:
            continue
        content = messages[-1].get("content")
        if not isinstance(content, str):
            continue
        try:
            return json.loads(content), str(candidate)
        except json.JSONDecodeError:
            continue
    return None, "no stored request matched the hash"


def main() -> None:
    entries = json.loads(WIRE.read_text(encoding="utf-8"))
    by_attempt = {entry.get("attempt_id"): entry for entry in entries}
    print(f"wire attempts present: {sorted(by_attempt)}")

    for attempt_id in ATTEMPTS:
        entry = by_attempt.get(attempt_id)
        if entry is None:
            check(f"attempt{attempt_id}: present in wire", False)
            continue
        print(f"--- attempt {attempt_id} entry keys={sorted(entry)}")
        for key in ("rejection", "validation_error", "error", "outcome"):
            if key in entry:
                print(f"    recorded {key}: {str(entry[key])[:180]}")

        original, request_source = load_original_request(entry.get("hash"))
        audit = entry.get("payload")
        if original is None:
            print(f"    request wire unavailable: {request_source}")
            print("    payload-equality check skipped (stated limitation)")
        else:
            print(f"    request source: {request_source}")
            check(
                f"attempt{attempt_id}: decoded messages[-1].content equals audit payload",
                isinstance(original, Mapping) and original == audit,
            )

        output = entry.get("output")
        if not isinstance(output, Mapping):
            output = find_mapping_with_keys(
                entry, ("B", "H_init", "H_reflect", "H_analyse")
            )
        if output is None:
            print("    proposer output not located under entry keys above")
            failures.append(f"attempt{attempt_id}: proposer output not found")
            continue
        context = {}
        for source in (original, audit):
            if isinstance(source, Mapping) and isinstance(
                source.get("proposal_context"), Mapping
            ):
                context = source["proposal_context"]
                break
        available = tuple(context.get("available_source_types") or ())
        results = replay_plan(build_plan(output), available)
        print(f"    request_scope: {results['request_scope']}")
        print(f"    full_context:  {results['full_context']}")
        check(
            f"attempt{attempt_id}: false ownership objection removed",
            "source_ownership_not_guaranteed" not in results["request_scope"],
            results["request_scope"],
        )

    print("--- standalone guard probes")
    results = replay_plan(
        probe_plan(
            "Collect target-company-scoped third-party news; treat it as "
            "third-party reporting, not as the issuer's own disclosure."
        ),
        ("company_news", "news"),
    )
    check(
        "probe: negated ownership accepted by request scope",
        results["request_scope"] == "accepted",
        results["request_scope"],
    )
    results = replay_plan(
        probe_plan("Collect the company's own disclosures on orders."),
        ("company_news", "news"),
    )
    check(
        "probe: affirmative ownership still rejected",
        "source_ownership_not_guaranteed" in results["request_scope"],
        results["request_scope"],
    )
    results = replay_plan(
        probe_plan(
            "Include not only third-party reporting but also the company's "
            "own disclosures."
        ),
        ("company_news", "news"),
    )
    check(
        "probe: not-only-but-also still rejected",
        "source_ownership_not_guaranteed" in results["request_scope"],
        results["request_scope"],
    )
    results = replay_plan(
        probe_plan(
            "Collect competitor financing actions from recent news; treat "
            "the coverage as third-party reporting, not as the target "
            "company's own disclosures."
        ),
        ("company_news", "news"),
    )
    check(
        "probe: negated scope does not authorize cross-issuer",
        results["request_scope"].startswith("ValidationError"),
        results["request_scope"],
    )

    print(f"failures={len(failures)}")
    if failures:
        for name in failures:
            print(f"  FAILED: {name}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
