"""Round-11 deterministic replay of the actual V118 request74 anchor question.

Imports the round-10 replay utilities, reads only immutable artifacts under
the frozen V118 workspace, and verifies the round-11 intent repair on the
real wire sample rather than invented text:

  1. every actual request74 next_information_need is classified by the
     production guard; the issuer-guidance question that uses the supplied
     baseline must no longer be nominated as a runtime-owned lookup;
  2. the full production initialize parser now rejects the actual request74
     response only for its real numeric-evidence defects (if any), never for
     a runtime-owned lookup error;
  3. genuine baseline/current-price lookups and a mixed issuer+runtime
     question still request a runtime-owned input, while reference-only
     anchor uses do not.

No network, no writes outside this round directory, run artifacts untouched.
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROUND11 = Path(__file__).resolve().parent
ROOT = ROUND11.parents[2]
for entry in (
    ROOT,
    ROOT / "src",
    ROUND11.parents[0] / "round-10",
):
    sys.path.insert(0, str(entry))

import replay as round10_replay  # noqa: E402  round-10 utilities
from stock_opportunity_agent.research.evolution_research_validation import (  # noqa: E402
    _normalize_research_state_output,
    _runtime_evaluation_input_requested,
)

INIT_ATTEMPT = 74

GENUINE_RUNTIME_LOOKUPS = (
    "What is the exact baseline date and price for the six-month evaluation "
    "outcome?",
    "What is the baseline price for the six-month evaluation outcome?",
    "Confirm the exact baseline date used by the runtime evaluation.",
    "What was the adjusted close price of the issuer on 2025-03-31?",
    "What is the current share price?",
)

MIXED_RUNTIME_LOOKUP = (
    "What did the company disclose by 2025-03-31 about its 2025 full-year "
    "revenue guidance, and what is the current adjusted share price "
    "relative to the supplied baseline?"
)

REFERENCE_ONLY_ANCHOR_USES = (
    "What did the company disclose by 2025-03-31 about its 2025 full-year "
    "revenue, adjusted EBITDA, membership, or center-opening guidance, and "
    "did any such guidance quantify a bridge to a doubling of the adjusted "
    "share price from the supplied baseline?",
    "What did the company disclose by 2025-03-31 that could move the "
    "adjusted share price above the current market level?",
    "What did the company disclose by 2025-03-31 about achieving an exact "
    "doubling of the adjusted share price?",
)


def prediction_date_texts(evaluation_context: dict) -> set[str]:
    from datetime import datetime

    try:
        prediction_date = datetime.fromisoformat(
            str(evaluation_context.get("prediction_time")).replace("Z", "+00:00")
        ).date()
    except ValueError:
        return set()
    return {
        prediction_date.isoformat(),
        f"{prediction_date.strftime('%B')} {prediction_date.day}, "
        f"{prediction_date.year}",
    }


def main() -> int:
    failures: list[str] = []
    attempts = round10_replay._load(round10_replay.WS / "attempts.json")["attempts"]
    by_id = {item["attempt_id"]: item for item in attempts}
    request = round10_replay._load(
        round10_replay.WS / "requests" / f"{by_id[INIT_ATTEMPT]['request_hash']}.json"
    )
    response = round10_replay.extract_output(
        round10_replay._load(
            round10_replay.WS
            / "cache/responses"
            / f"{by_id[INIT_ATTEMPT]['request_hash']}.json"
        )
    )
    payload = round10_replay.extract_payload(request)
    basic_info = payload["basic_info"]
    evaluation_context = payload.get("evaluation_context")
    texts = prediction_date_texts(evaluation_context or {})

    print("=== actual V118 request74 need classification (wire text) ===")
    for index, need in enumerate(response["next_information_needs"]):
        requested = _runtime_evaluation_input_requested(need, texts)
        print(f"needs[{index}] runtime_input_requested={requested}")
        print(f"  {need[:120]}")
        if index == 0 and requested:
            failures.append("actual request74 needs[0] still requests runtime input")

    print(
        "\n=== actual request74 response through the production parser ==="
    )
    try:
        _normalize_research_state_output(
            response,
            initialize=True,
            basic_info=basic_info,
            evaluation_context=evaluation_context,
        )
        print("parser: ACCEPTED (no runtime-owned rejection)")
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        runtime_owned = "runtime-owned evaluation input" in message
        print(f"parser: {type(exc).__name__}")
        print(f"  runtime-owned lookup error present: {runtime_owned}")
        print(f"  first 400 chars: {message[:400]}")
        if runtime_owned:
            failures.append(
                "actual request74 response still rejected as a runtime-owned "
                "evaluation input"
            )

    print("\n=== guard unit checks on genuine/mixed/reference strings ===")
    for text in GENUINE_RUNTIME_LOOKUPS:
        requested = _runtime_evaluation_input_requested(text, texts)
        print(f"genuine lookup requested={requested}: {text[:80]}")
        if not requested:
            failures.append(f"genuine lookup no longer requests: {text[:60]}")
    requested = _runtime_evaluation_input_requested(MIXED_RUNTIME_LOOKUP, texts)
    print(f"mixed lookup requested={requested}: {MIXED_RUNTIME_LOOKUP[:80]}")
    if not requested:
        failures.append("mixed issuer+runtime question was bypassed")
    for text in REFERENCE_ONLY_ANCHOR_USES:
        requested = _runtime_evaluation_input_requested(text, texts)
        print(f"reference use requested={requested}: {text[:80]}")
        if requested:
            failures.append(f"reference-only use rejected: {text[:60]}")

    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("\nALL ROUND-11 REPLAY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise SystemExit(2)
