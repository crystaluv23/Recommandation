# Review

## Status
Not started

## Purpose

Review past recommendations, validate or invalidate theses, label errors, and update memory with lessons. Review is the feedback loop that turns watchlists into learning.

## External Interface

Expected outputs:

- 1-month, 3-month, and 6-month outcome records,
- benchmark-relative performance,
- thesis validation labels,
- error labels,
- signal attribution,
- and review lessons.

Common error labels:

- thesis wrong,
- too early,
- valuation overstretched,
- regime shift,
- right theme wrong stock,
- narrative without data,
- one-time item mistaken as trend,
- squeeze not fundamental,
- catalyst too far away,
- risk underestimated.

## Responsibilities

- Compare recommendations against SPY, QQQ, and relevant sector benchmarks when available.
- Measure hit rate, large-winner rate, false-positive rate, drawdown, and post-recommendation path.
- Preserve what worked and what failed.
- Feed signal memory and meta-learning.
- Avoid rewriting the original decision record.

## Dependencies

- Consumes data, memory, rankings, scores, themes, and reports.
- Feeds memory, signals, meta-learning, and future research packets.

## Invariants

- Review must use the original decision as recorded, not a reconstructed story.
- Price outcome and thesis outcome are related but separate.
- Reviews must include failures and stale theses.
- Lessons must distinguish observed evidence from speculation.

## Testing

Tests should cover return windows, benchmark comparison, error-label validation, thesis status updates, and preservation of original decisions.
