# Research / Agents

## Status
Not started

## Purpose

Define LLM research roles and their orchestration boundaries.

## Responsibilities

- Coordinate Research, Skeptic, Theme, Valuation, and Judge roles.
- Keep each role grounded in prepared packets and retrieved evidence.

## Dependencies

- Parent spec: [`../research.md`](../research.md).
- Consumes prompts, schemas, data packets, memory, themes, and signals.

## Invariants

- A bullish thesis must always face a skeptical pass.
- Agents cannot mutate memory or scoring weights directly.

## Testing

Use stub LLM clients to verify role calls, grounding requirements, and synthesis behavior.
