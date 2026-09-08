# Evolution Transport

## Purpose

Own reproducibility checks, external request persistence, attempt and cost
ledgers, exact-response caching, and the structured model-client boundary.

## Invariants

- Every external request is persisted before transmission.
- Cache reuse requires the exact canonical request hash.
- Attempt, token, and cost ceilings fail closed before network I/O.
- Persisted artifacts never contain provider credentials.
