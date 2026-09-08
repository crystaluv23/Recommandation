# Evolution Output Validation

## Purpose

Parse and validate structured role output, produce machine-readable issues,
and apply only explicitly allowed deterministic recovery transforms.

## Invariants

- Validation never infers write authority from diagnostic prose.
- Scoped correction preserves unrelated valid siblings byte-for-byte.
- A recovery transform must be generic to the declared schema; it must not
  encode provider-, company-, or case-specific exceptions.
