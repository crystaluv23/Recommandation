# Reports

## Status
Not started

## Purpose

Produce human-readable outputs from structured records. Reports help the user inspect opportunities, compare themes, understand decisions, and review system learning.

## External Interface

Expected report families:

- weekly watchlist,
- company research cards,
- theme and segment maps,
- catalyst dashboards,
- monthly review reports,
- meta-learning reports,
- and audit bundles for individual decisions.

## Responsibilities

- Render ranked watchlists with evidence, catalysts, risks, scores, and recommendation states.
- Show old narrative, new narrative, core thesis, disconfirming conditions, and review date for each company.
- Explain additions, removals, upgrades, and downgrades.
- Separate factual evidence, LLM interpretation, and user-facing summary.
- Link reports to memory records and source metadata.

## Dependencies

- Consumes models, rankings, scores, research outputs, themes, memory, review, and meta-learning.
- Does not feed scoring directly; reports are outputs, not hidden inputs.

## Invariants

- Reports must not read like buy/sell instructions.
- Every high-priority candidate must include contrary evidence and thesis break conditions.
- Reported scores must match stored score cards.
- Reports should be reproducible from memory and data records for a given run.

## Testing

Tests should cover report generation from fixtures, presence of required sections, score consistency, links to source records, and omission of secrets.
