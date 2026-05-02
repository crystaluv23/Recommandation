# Memory

## Status
Not started

## Purpose

Persist long-term local memory so the agent can remember companies, theses, signals, themes, decisions, reviews, and lessons across runs.

## External Interface

Memory collections should include:

- Company Memory
- Thesis Memory
- Signal Memory
- Case Memory
- Decision Memory
- Review Memory
- Theme Memory
- Segment Memory
- Experiment Memory
- User Preference Memory

The module should expose repository-style interfaces for reading, writing, querying, and versioning these records.

## Responsibilities

- Store every watchlist decision with its evidence, scores, and version stamps.
- Store active and archived theses separately by status.
- Track signal performance and false-positive patterns.
- Track theme and segment stage histories.
- Preserve error labels and lessons from reviews.
- Support retrieval of relevant prior memory for research packets.

## Dependencies

- Uses `models` for durable records.
- Uses `config` for storage locations.
- Feeds research, scoring, monitoring, review, meta-learning, and reports.

## Invariants

- Memory is not a chat transcript; it stores structured research history.
- A thesis belongs to a claim and evidence set, not just a ticker.
- Failed recommendations must remain queryable.
- Memory updates should be append-friendly; destructive rewrites require explicit migration or human approval.
- Records must be traceable back to the run or review that created them.

## Testing

Tests should cover create/read/update/archive flows, idempotent writes, query filters, version tracking, and preservation of failed decisions.
