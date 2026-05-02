# Research / Prompts

## Status
Not started

## Purpose

Version and assemble prompts for company research, theme analysis, skepticism, valuation critique, ranking support, and postmortems.

## Responsibilities

- Keep prompt versions explicit.
- Include point-in-time instructions and evidence requirements.
- Avoid language that forces over-optimistic recommendations.

## Dependencies

- Parent spec: [`../research.md`](../../../src/stock_opportunity_agent/research.md).
- Consumed by agents and meta-learning.

## Invariants

- Prompt changes that affect recommendation behavior require a new version.
- Prompts must require contrary evidence and disconfirming conditions.

## Testing

Cover template rendering, missing variables, version stamps, and required guardrail text.
