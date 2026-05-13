# Memory Playbooks

## Status
Started

## Purpose

Persist reusable research playbooks learned during cold-start so future scans
can retrieve not only measurable signals, but also the research thinking
patterns behind those signals.

## External Interface

Initial implementation exposes `FilePlaybookLibrary`, a JSON-backed store for
`surge_research_playbooks.json`.

The stored records should preserve:

- playbook id, version, name, purpose, and promotion status,
- core questions and reasoning steps,
- positive patterns, counter-patterns, and false-positive traps,
- linked signal ids and theme ids,
- evidence case references and hindsight-risk notes.

## Invariants

- Playbook memory is structured research memory, not a raw chat transcript.
- Playbooks should not silently overwrite prompt versions or scoring rules.
- Playbooks are candidates for future prompt/meta-learning changes; promotion
  into default prompts requires versioning and review.
- Records must remain traceable to the cold-start run that produced them.

## Testing

Tests should cover write/read behavior, idempotent overwrite for the latest
cold-start library snapshot, and schema round-tripping.
