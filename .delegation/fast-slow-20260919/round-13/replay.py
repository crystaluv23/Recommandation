"""Round-13 deterministic replay of the actual V118 request74 anchor question.

Reuses the round-12 replay harness (round-10 utilities, immutable frozen V118
workspace artifacts) and adds the round-13 paired negatives/positives:

  1. every actual request74 next_information_need is classified by the
     production guard as non-requesting (needs[0] is the issuer-guidance
     question that uses the supplied baseline as a reference anchor);
  2. the full production initialize parser rejects the actual request74
     response only for its real numeric-evidence defects (if any), never
     for a runtime-owned lookup error;
  3. the round-11/12 fail-open counterexamples still reject;
  4. the round-13 counterexamples reject: dative "provide/supply ... with"
     direct lookups (bare "with" is ambiguous, not reference evidence) and
     same-anchor repetition where an early reference mention must not hide
     a later direct lookup ("Using the supplied baseline price, what is
     the baseline price?");
  5. explicit reference constructs stay accepted: contiguous "compared
     with the supplied baseline price" and repeated reference mentions of
     the same anchor, while genuine/mixed lookups still reject.

No network, no writes outside this round directory, run artifacts untouched.
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROUND13 = Path(__file__).resolve().parent
ROOT = ROUND13.parents[2]
for entry in (
    ROOT,
    ROOT / "src",
    ROUND13.parents[0] / "round-10",
):
    sys.path.insert(0, str(entry))

import replay as round10_replay  # noqa: E402  round-10 utilities
from stock_opportunity_agent.research.evolution_research_validation import (  # noqa: E402
    _normalize_research_state_output,
    _runtime_evaluation_input_requested,
)

INIT_ATTEMPT = 74

# Round-11/12 fail-open regressions: must keep rejecting.
ORDINARY_DIRECT_LOOKUPS = (
    "What is the value of the baseline price?",
    "Please obtain the baseline date and price.",
    "Can we look up the baseline price?",
    "The baseline price is what?",
    "The baseline date and price must be identified.",
    "Could you provide the current share price?",
    "Please define the terms of the fixed six-month evaluation outcome.",
    "What did the company disclose by 2025-03-31 that bears on the "
    "fixed six-month evaluation outcome's terms?",
)

# Round-13 brief negatives plus same-mechanism variants: must reject.
BARE_WITH_DIRECT_LOOKUPS = (
    "Please provide me with the baseline date and price.",
    "Please supply us with the current share price.",
    "Please provide me with the definition of the six-month evaluation "
    "outcome.",
)

HIDDEN_SAME_ANCHOR_LOOKUPS = (
    "Using the supplied baseline price, what is the baseline price?",
    "Using the supplied baseline date, what is the baseline date and price?",
    "Compared with the supplied baseline price, please provide the "
    "baseline date.",
)

GENUINE_RUNTIME_LOOKUPS = (
    "What is the exact baseline date and price for the six-month evaluation "
    "outcome?",
    "What is the baseline price for the six-month evaluation outcome?",
    "Confirm the exact baseline date used by the runtime evaluation.",
    "What was the adjusted close price of the issuer on 2025-03-31?",
    "What is the current share price?",
    "Using the supplied baseline, retrieve the current adjusted close price.",
)

MIXED_RUNTIME_LOOKUPS = (
    "What did the company disclose by 2025-03-31 about its 2025 full-year "
    "revenue guidance, and what is the current adjusted share price "
    "relative to the supplied baseline?",
    "What did the company disclose by 2025-03-31 about guidance relative "
    "to the supplied baseline, and what is the baseline date for the "
    "evaluation?",
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
    "What did the company disclose by 2025-03-31 that could move the "
    "adjusted share price above the current market level, as measured from "
    "the supplied baseline date?",
    # Round-13 paired positives: explicit compared-with reference and
    # repeated same-anchor reference mentions.
    "What did the company disclose by 2025-03-31 about guidance momentum "
    "compared with the supplied baseline price?",
    "What did the company disclose by 2025-03-31 about guidance relative "
    "to the supplied baseline, as measured from the supplied baseline date?",
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
        if requested:
            failures.append(
                f"actual request74 needs[{index}] requests runtime input"
            )

    print(
        "\n=== actual V118 request74 response through the production parser ==="
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

    print("\n=== prior ordinary direct lookups must keep rejecting ===")
    for text in ORDINARY_DIRECT_LOOKUPS:
        requested = _runtime_evaluation_input_requested(text, texts)
        print(f"ordinary lookup requested={requested}: {text[:80]}")
        if not requested:
            failures.append(f"ordinary direct lookup still passes: {text[:60]}")

    print("\n=== round-13 bare-with dative lookups must reject ===")
    for text in BARE_WITH_DIRECT_LOOKUPS:
        requested = _runtime_evaluation_input_requested(text, texts)
        print(f"bare-with lookup requested={requested}: {text[:80]}")
        if not requested:
            failures.append(f"bare-with direct lookup still passes: {text[:60]}")

    print("\n=== round-13 hidden same-anchor lookups must reject ===")
    for text in HIDDEN_SAME_ANCHOR_LOOKUPS:
        requested = _runtime_evaluation_input_requested(text, texts)
        print(f"hidden lookup requested={requested}: {text[:80]}")
        if not requested:
            failures.append(f"hidden same-anchor lookup still passes: {text[:60]}")

    print("\n=== genuine and mixed lookups still reject ===")
    for text in (*GENUINE_RUNTIME_LOOKUPS, *MIXED_RUNTIME_LOOKUPS):
        requested = _runtime_evaluation_input_requested(text, texts)
        print(f"lookup requested={requested}: {text[:80]}")
        if not requested:
            failures.append(f"genuine or mixed lookup no longer rejects: {text[:60]}")

    print("\n=== clearly identified reference uses still pass ===")
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
    print("\nALL ROUND-13 REPLAY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise SystemExit(2)
