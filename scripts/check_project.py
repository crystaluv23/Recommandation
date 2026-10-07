#!/usr/bin/env python3
"""Check assistant meta records; never execute or approve a research run.

Usage: python3 scripts/check_project.py [--before-successor]
Default checks are administrative consistency only. The explicit successor check
also requires a fresh active goal receipt, reviewed prerequisites and a concrete
frozen plan. Neither mode verifies economic truth or invokes external services.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

LEVELS = {"unknown": 0, "diagnosed": 1, "local": 2, "live": 3, "independent": 4}
REQUIRED = (
    "AGENTS.md", "spec/agent-workflow.md", "progress/status.md",
    "memory/GUIDE.md", "memory/meta/reviews.md",
)


def check_state(root: Path, state: dict, *, before_successor: bool = False,
                now: datetime | None = None) -> list[str]:
    """Return failures without modifying state; evidence paths must stay in root."""
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    def text_fields(record: dict, names: tuple[str, ...], owner: str) -> None:
        for name in names:
            require(isinstance(record.get(name), str) and bool(record[name].strip()),
                    f"{owner}: missing {name}")

    def evidence(paths: object, owner: str) -> None:
        if not isinstance(paths, list) or not paths:
            errors.append(f"{owner}: missing evidence")
            return
        for value in paths:
            if not isinstance(value, str) or not value:
                errors.append(f"{owner}: invalid evidence path")
                continue
            candidate = (root / value).resolve()
            require(not Path(value).is_absolute() and candidate.is_relative_to(root.resolve())
                    and candidate.is_file(), f"{owner}: inaccessible evidence {value}")

    require(state.get("schema_version") == 1, "unsupported meta schema")
    text_fields(state, ("objective",), "state")
    goals = state.get("acceptance", [])
    require(isinstance(goals, list) and bool(goals), "missing acceptance items")
    by_id = {}
    for item in goals:
        text_fields(item, ("id", "remaining"), "acceptance")
        require(item.get("id") not in by_id, "duplicate acceptance id")
        by_id[item.get("id")] = item
        require(item.get("level") in LEVELS and item.get("required_level") in
                {"diagnosed", "local", "live", "independent"},
                "invalid acceptance level")
        require(isinstance(item.get("closed"), bool), "closed must be boolean")
        evidence(item.get("evidence"), f"acceptance {item.get('id')}")
        if item.get("closed"):
            require(LEVELS.get(item.get("level"), -1) >=
                    LEVELS.get(item.get("required_level"), 99),
                    f"{item.get('id')}: closure below required evidence level")

    rounds = state.get("iterations", [])
    require(isinstance(rounds, list) and bool(rounds), "missing iteration history")
    seen = set()
    previous_families = set()
    recurrent = False
    for iteration in rounds:
        text_fields(iteration, ("id", "strategy"), "iteration")
        require(iteration.get("id") not in seen, "duplicate iteration id")
        seen.add(iteration.get("id"))
        evidence(iteration.get("evidence"), f"iteration {iteration.get('id')}")
        families = iteration.get("failure_families")
        require(isinstance(families, list) and all(isinstance(x, str) and x for x in families),
                "invalid failure families")
        families = set(families or [])
        recurrent = bool(families & previous_families)
        previous_families.update(families)
        advances = iteration.get("acceptance_advances")
        require(isinstance(advances, list), "missing acceptance advances (use [] for none)")
        for advance in advances or []:
            item = by_id.get(advance.get("acceptance_id"))
            require(item is not None, "advance references unknown acceptance item")
            require(LEVELS.get(advance.get("level"), -1) >=
                    LEVELS.get((item or {}).get("required_level"), 99),
                    "advance substitutes lower-level evidence")
            evidence(advance.get("evidence"), "advance")

    stagnant = (len(rounds) >= 2 and rounds[-1].get("strategy") == rounds[-2].get("strategy")
                and not rounds[-1].get("acceptance_advances")
                and not rounds[-2].get("acceptance_advances"))
    review = state.get("review") or {}
    if stagnant or recurrent or before_successor:
        require(bool(rounds) and review.get("after_iteration") == rounds[-1].get("id"),
                "latest stagnation/recurrence requires a current review")
        evidence(review.get("evidence"), "review")
        require(isinstance(review.get("blind_spots"), list) and
                bool(review.get("blind_spots")) and
                all(isinstance(x, str) and x.strip() for x in review["blind_spots"]),
                "review must explain missed assumptions")
        decision = review.get("decision") or {}
        text_fields(decision, ("strategy", "action", "question", "pass", "fail", "stop"), "review")
        if rounds and decision.get("strategy") == rounds[-1].get("strategy"):
            text_fields(decision, ("new_evidence", "distinguishing_variable"), "unchanged strategy")

    prerequisites = state.get("successor_prerequisites")
    require(isinstance(prerequisites, list) and bool(prerequisites), "missing successor prerequisites")
    prerequisite_ids = set()
    for item in prerequisites or []:
        text_fields(item, ("id",), "prerequisite")
        require(item.get("id") not in prerequisite_ids, "duplicate prerequisite id")
        prerequisite_ids.add(item.get("id"))
        require(item.get("status") in {"pending", "met"}, "unknown prerequisite status")
        evidence(item.get("evidence"), f"prerequisite {item.get('id')}")
        if before_successor:
            require(item.get("status") == "met", f"successor blocked: {item.get('id')} pending")

    snapshot = state.get("goal_snapshot") or {}
    require(snapshot.get("status") in {"none", "active", "usageLimited", "budgetLimited",
                                       "paused", "blocked", "complete"}, "unknown goal status")
    stamp = datetime.fromisoformat(snapshot.get("checked_at", "").replace("Z", "+00:00"))
    require(stamp.tzinfo is not None, "goal receipt must include timezone")
    if before_successor:
        require(snapshot.get("status") == "active", "successor blocked: goal is not active")
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
        require(-30 <= age <= 600, "successor blocked: goal receipt stale or future")
        plan = state.get("successor_plan") or {}
        text_fields(plan, ("question", "pass", "fail", "stop", "strategy"), "successor plan")
        evidence(plan.get("authorization_evidence"), "successor authorization")
        evidence(plan.get("freeze_evidence"), "successor freeze")
        require(bool(re.fullmatch(r"[0-9a-f]{40}", plan.get("revision", ""))),
                "successor requires exact frozen revision")
        require(bool(re.fullmatch(r"[0-9a-f]{64}", plan.get("manifest_sha256", ""))),
                "successor requires exact manifest hash")
        require(plan.get("strategy") == (review.get("decision") or {}).get("strategy"),
                "successor strategy differs from reviewed decision")

    archive = state.get("history_archive") or {}
    evidence([archive.get("path")], "status archive")
    if isinstance(archive.get("path"), str):
        path = (root / archive["path"]).resolve()
        if path.is_relative_to(root.resolve()) and path.is_file():
            body = path.read_bytes()
            require(len(body) == archive.get("bytes") and
                    hashlib.sha256(body).hexdigest() == archive.get("sha256"),
                    "historical status bytes/hash changed")
    return errors


def check_project(root: Path, *, before_successor: bool = False) -> list[str]:
    """Load and fail closed on malformed records; do not inspect research source code."""
    errors = [f"missing meta file: {name}" for name in REQUIRED if not (root / name).is_file()]
    for name, limit in (("AGENTS.md", 120), ("progress/status.md", 100)):
        path = root / name
        if path.is_file() and len(path.read_text().splitlines()) > limit:
            errors.append(f"{name}: current entry exceeds {limit} lines; move history out")
    try:
        state = json.loads((root / "progress/convergence.json").read_text())
        errors.extend(check_state(root, state, before_successor=before_successor))
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        errors.append(f"invalid meta record: {exc}")
    return errors


def main() -> int:
    """Print concise administrative diagnostics and exit nonzero on any failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-successor", action="store_true")
    args = parser.parse_args()
    errors = check_project(Path(__file__).resolve().parents[1], before_successor=args.before_successor)
    for error in errors:
        print(f"FAIL: {error}")
    if errors:
        return 1
    print("Meta check: PASS (administrative only; not live/learning/benefit acceptance)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
