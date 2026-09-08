# Local Artifact Utilities

## Status

Done

## Purpose

Own the byte-level mechanics repeated by data, Signal, dashboard, and evolution
modules when they hash or atomically replace local JSON artifacts. Domain modules
continue to own schemas, validation, immutability rules, and commit ordering.

## Public Interface

- `canonical_json_hash(value)`: SHA-256 of UTF-8 JSON with sorted keys and compact
  separators.
- `atomic_write_json(path, value, indent=2)`: write one JSON value plus a trailing
  newline through a same-directory temporary file, flush and `fsync`, then replace
  the destination atomically. `indent=None` preserves compact cache-record output.
- `atomic_write_text(path, text)`: the same crash-safe replacement boundary for
  already serialized text.

## Invariants

- Temporary files are created in the destination directory so replacement stays on
  one filesystem.
- A failed write removes its temporary file when possible and never exposes a
  partially written destination.
- Serialization remains deterministic: sorted keys, standard-library JSON behavior,
  and exactly one trailing newline.
- This module does not read artifacts, decide whether an existing artifact may be
  replaced, or convert persistence failures into domain outcomes.

## Dependencies

Standard library only. Higher-level modules depend on this utility; it never imports
data, research, Signal, orchestration, or domain-model modules.
