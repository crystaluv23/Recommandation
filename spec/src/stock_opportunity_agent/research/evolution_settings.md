# Evolution Settings

## V8 Slow settings

Canonical settings expose explicit positive defaults for
`min_new_signals_per_cycle`, bounded reflection additions/source reads, and one
independent exploration batch per Slow cycle. Contract creation copies these
values; runtime code does not silently substitute missing v8 fields and does not
introduce a general configuration framework.

## Purpose

Own frozen runtime constants and deterministic source/model catalogs used when
constructing an evolution contract. It contains no workspace or network I/O.

## Invariants

- Hashes derive only from canonical public configuration.
- Defaults used to freeze a contract remain explicit and versioned.
- Source-type availability is resolved without reading outcome data.
