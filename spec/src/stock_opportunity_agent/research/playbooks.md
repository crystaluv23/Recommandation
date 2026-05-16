# Research Playbooks

## Status
Started

## Purpose

Synthesize reusable cold-start research playbooks from historical winner,
control, and failure comparisons. A playbook is a versioned thinking pattern:
what to inspect, which questions to ask, how to combine evidence, and which
false-positive traps to avoid when looking for possible 3-6 month surge stocks.

## External Interface

The submodule exposes:

- `SurgeResearchPlaybook`: a durable research checklist with core questions,
  reasoning steps, positive/counter patterns, linked signals, linked themes,
  evidence case references, confidence, and hindsight-risk notes.
- `SurgePlaybookSynthesis`: a JSON-compatible batch of synthesized playbooks.
- `SurgePlaybookSynthesizer`: protocol for cross-case synthesizers.
- `HeuristicSurgePlaybookSynthesizer`: deterministic fallback for tests and
  offline runs.
- `OpenAISurgePlaybookSynthesizer`: LLM-backed synthesis for formal cold-start
  runs.

## Invariants

- Playbook synthesis is retrospective and may compare winner/control/failure
  labels, but output must mark that hindsight boundary.
- Playbooks are not executable trading rules and must not produce orders,
  position sizing, or brokerage actions.
- Playbooks are not direct prompt rewrites. They are candidate research
  frameworks that can later be rendered into versioned prompts through
  meta-learning and review.
- LLM-backed synthesis must not use web-search tools.
- LLM-backed synthesis should avoid ticker and company identity in the prompt;
  case references should be anonymized when sent to the model.
- LLM-backed synthesis is a late-stage summary step, not a correctness gate for
  the whole cold-start run. Invalid provider JSON should be retried and then
  fall back to the deterministic synthesizer with an explicit warning in the
  playbook artifact.
- Each playbook should link back to signal ids, theme ids, and case references
  when available so it remains auditable.

## Testing

Tests should cover schema validation, deterministic fallback output, OpenAI
payload construction without tools or company identity, orchestration artifact
writing, and memory persistence.
