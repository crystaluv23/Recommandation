# Reports / Cards

## Status
Not started

## Purpose

Render company research cards for individual candidates.

## Responsibilities

- Present company profile, old/new narrative, thesis, evidence, risks, catalysts, valuation notes, memory context, and review date.

## Dependencies

- Parent spec: [`../reports.md`](../reports.md).
- Consumes research, memory, scores, and data metadata.

## Invariants

- Cards must separate factual evidence from LLM interpretation.
- Source references must be available for audit.

## Testing

Cover complete cards, missing sections, source references, and secret omission.
