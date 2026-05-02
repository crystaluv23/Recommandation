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

## Responsibilities

- Track earnings, filings, management commentary, analyst revisions, major orders, customer news, sector moves, price/volume events, short interest, options signals when available, and peer read-throughs.
- Decide whether an event requires data refresh, LLM research, score refresh, or only memory annotation.
- Update current universe state with material new information and reanalysis reasons.
- Keep watchlist state changes auditable.
- Avoid rerunning full research when nothing material changed.

## Dependencies

- Consumes data, memory, themes, signals, scores, rankings, and config.
- Feeds research, review, reports, and orchestration.

## Invariants

- State transitions must include reason, timestamp, and triggering evidence.
- A thesis-broken state should preserve the original thesis and explain the break.
- Monitoring cannot create a trade order.
- Event freshness and source must be recorded.

## Testing

Tests should cover state transitions, trigger routing, duplicate event suppression, stale event handling, and thesis-broken conditions.
