# Evolution Output Validation

## Purpose

Parse and validate structured role output, produce machine-readable issues,
and apply only explicitly allowed deterministic recovery transforms.

## Invariants

- Validation never infers write authority from diagnostic prose.
- Scoped correction preserves unrelated valid siblings byte-for-byte.
- A recovery transform must be generic to the declared schema; it must not
  encode provider-, company-, or case-specific exceptions.

Ordinary structured correction obligations use their explicit change paths and
permitted dependency paths even when a Controller enables exact compaction scope.
The compaction-specific scope resolver runs only for actual compaction obligations;
absence of compaction must never disable ordinary sibling preservation. Any
projected correction is fully revalidated before acceptance.
