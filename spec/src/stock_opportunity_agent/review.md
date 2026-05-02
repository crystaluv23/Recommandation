# Review

## Status
Not started

## Purpose

Review past recommendations, validate or invalidate theses, label errors, and update memory with lessons. Review is the feedback loop that turns watchlists into learning.

## External Interface

Expected outputs:

- 1-month, 3-month, and 6-month outcome records,
- earnings validation reports,
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
- right stock wrong timing,
- narrative without data,
- financial validation missing,
- one-time item mistaken as trend,
- squeeze not fundamental,
- catalyst too far away,
- crowded trade,
- LLM over-optimism,
- data missing,
- risk underestimated.

## Responsibilities

- Compare recommendations against SPY, QQQ, and relevant sector benchmarks when available.
- Compare observed earnings, filings, transcripts, analyst revisions, price reactions, and peer read-throughs against the original validation contract.
- Measure hit rate, large-winner rate, false-positive rate, drawdown, and post-recommendation path.
- Preserve what worked and what failed.
- Separate price outcome from thesis outcome: a stock can rise for the wrong reason or fall before a thesis is disproved.
- Feed signal memory and meta-learning.
- Avoid rewriting the original decision record.

## Earnings Validation

When a watched company reports earnings or releases a comparable high-signal event, review should generate an `EarningsValidationReport` or event validation report:

```text
active thesis
-> original validation contract
-> reported financials and guidance
-> transcript or management commentary
-> analyst revisions
-> price and relative-strength reaction
-> metric-by-metric validation result
-> thesis validation score
-> recommended research-state update
```

The report should say which contract items were validated, unvalidated, contradicted, or still unavailable. It should not replace monthly outcome review; it is an event-time check that feeds monitoring and future review memory.

## Dependencies

- Consumes data, memory, rankings, scores, themes, and reports.
- Feeds memory, signals, meta-learning, and future research packets.

## Invariants

- Review must use the original decision as recorded, not a reconstructed story.
- Validation must use the original validation contract as recorded, not a later cleaner version of the thesis.
- Price outcome and thesis outcome are related but separate.
- Reviews must include failures and stale theses.
- Lessons must distinguish observed evidence from speculation.

## Testing

Tests should cover return windows, benchmark comparison, validation-contract evaluation, error-label validation, thesis status updates, event validation reports, and preservation of original decisions.
