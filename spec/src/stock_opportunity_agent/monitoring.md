# Monitoring

## Status
Not started

## Purpose

Monitor catalysts, filings, news, price action, segment changes, and watchlist state transitions after a candidate enters memory.

## External Interface

The module should support states:

- `ignore`
- `monitor`
- `thesis_forming`
- `high_priority_watchlist`
- `action_candidate`
- `thesis_validated`
- `thesis_broken`
- `archived`

It should emit reanalysis triggers when meaningful events occur.

State labels may be rendered in reports as `Ignore`, `Monitor`, `Thesis Forming`, `High Priority Watchlist`, `Action Candidate`, `Validated`, `Broken`, and `Archived`, but durable records should use stable machine-readable enum values.

## Responsibilities

- Track earnings, filings, management commentary, analyst revisions, major orders, customer news, sector moves, price/volume events, short interest, options signals when available, and peer read-throughs.
- Decide whether an event requires data refresh, LLM research, score refresh, or only memory annotation.
- Update current universe state with material new information and reanalysis reasons.
- Compare material events against active validation contracts and mark which metrics were confirmed, weakened, broken, or still unknown.
- Keep watchlist state changes auditable.
- Avoid rerunning full research when nothing material changed.
- Reactivate archived names only when a material event plausibly changes the old conclusion, such as new leadership, major order, industry-cycle reversal, spin-off, earnings surprise, or abnormal price and volume confirmation.

## State Transition Semantics

Common transitions:

- `monitor` -> `thesis_forming`: new evidence suggests a possible expectation gap but the thesis is not complete.
- `thesis_forming` -> `high_priority_watchlist`: research, scoring, review gate, and validation contract are complete.
- `high_priority_watchlist` -> `action_candidate`: a catalyst or market event materially confirms the thesis before full validation is complete.
- `high_priority_watchlist` -> `thesis_validated`: earnings, filings, analyst revisions, price action, or other events satisfy most critical validation metrics.
- `high_priority_watchlist` -> `thesis_broken`: the validation contract fails or contrary evidence dominates.
- `thesis_broken` -> `archived`: the broken thesis is preserved for review and future lessons.
- `archived` -> `monitor`: a new material event justifies fresh monitoring without erasing the archived thesis.

## Dependencies

- Consumes data, memory, themes, signals, scores, rankings, and config.
- Feeds research, review, reports, and orchestration.

## Invariants

- State transitions must include reason, timestamp, and triggering evidence.
- State transitions out of `high_priority_watchlist` must reference the active validation contract.
- A thesis-broken state should preserve the original thesis and explain the break.
- Monitoring cannot create a trade order.
- Event freshness and source must be recorded.

## Testing

Tests should cover state transitions, validation-contract comparisons, trigger routing, duplicate event suppression, stale event handling, archived-name reactivation, and thesis-broken conditions.
