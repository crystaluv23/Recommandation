# Evolution Transport

## Purpose

Own reproducibility checks, external request persistence, attempt and cost
ledgers, exact-response caching, and the structured model-client boundary.

## Invariants

- Every external request is persisted before transmission.
- Cache reuse requires the exact canonical request hash.
- Attempt, token, and cost ceilings fail closed before network I/O.
- Persisted artifacts never contain provider credentials.

## Frozen reasoning output reservation

A frozen nonnegative integer `structured_reasoning_token_reserve` adds output
headroom to structured JSON calls whose registered effort is neither none nor
absent. Standard freeze sets 32000 when the evolution alias enables reasoning,
and zero otherwise. Role output limits remain the base reservation; effective
provider output limit is base plus this explicit reserve, including corrections.
Estimator, request hash, persisted provider body, network body and pre-send cost
gates all use the effective limit. Binary judge calls never receive the reserve.
Old contracts without this field retain zero. This reserves reasoning and final
JSON together; it does not claim the provider reports or enforces separate caps.
