# Evolution Settings

## Purpose

Own frozen runtime constants and deterministic source/model catalogs used when
constructing an evolution contract. It contains no workspace or network I/O.

## Invariants

- Hashes derive only from canonical public configuration.
- Defaults used to freeze a contract remain explicit and versioned.
- Source-type availability is resolved without reading outcome data.
