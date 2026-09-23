# Evolution Transport

## Purpose

Own reproducibility checks, external request persistence, attempt and cost
ledgers, exact-response caching, and the structured model-client boundary.

## Invariants

- Every external request is persisted before transmission.
- Cache reuse requires the exact canonical request hash.
- Attempt, token, and cost ceilings fail closed before network I/O.
- The attempt ledger admits a new request against settled cost: finalized
  attempts count their `actual_cost`, while in-flight attempts hold their
  full reservation until they finalize. Transient retries therefore never
  permanently consume ceiling headroom the run did not actually spend.
- Persisted artifacts never contain provider credentials.
- A provider 200 response that carries no message output text (for example a
  reasoning-heavy completion truncated before any message chunk) is a transient
  provider anomaly: it is classified retryable and never a permanent domain
  verdict. An explicit provider refusal is not retryable.

## Same-request correction guard

Within one logical structured-correction chain, a correction attempt whose
canonical request is byte-identical to an earlier request of the same chain is
a no-progress retry: the exact-response cache would replay the prior response
and the chain would loop until budget exhaustion. The transport therefore
fails such a retry closed with an explicit no-progress diagnostic before any
cache lookup or transmission, while preserving the full audit trail. The guard
scope is the correction chain only — it is keyed by the chain's prior request
hashes, never by a global "hash seen once" blacklist — so three semantics stay
distinct: (a) an identical corrected re-send of a rejected request inside the
same chain is rejected as no progress; (b) the same request issued
independently by a different plan, candidate, or role is a legal shared cache
hit, not a correction loop; (c) a transport-layer retry of a recoverable
failure follows the retry/unknown-send rules and is never conflated with a
domain rejection. Adding a nonce or any field whose only purpose is to dodge
the guard or the cache is invalid.

## Concurrency boundary (bounded plan-parallel evaluation)

Fast-round candidate evaluation may run under one coordinator with bounded
worker threads. The attempt ledger's read-modify-write (reserve/finalize,
attempt-id assignment) is protected by a single-process mutex; admission is
arbitrated in stable candidate-slot order so a fast candidate cannot starve
its siblings of ceiling headroom. Identical canonical requests issued
concurrently by different workers share one physical attempt: the first
admitted request leads, later ones wait on and reference the same response
and attempt id, and the ledger records the physical call once. Leader failure
and waiter cancellation follow the bounded-recovery rules; waiting must never
hang indefinitely. The request/response cache remains hash-addressed and
read-only shared. The `data_requests.jsonl` and
`data_acquisition_requests.jsonl` ledgers are coordinated writes with the
same integrity rules (no partial lines, no duplicate identities, settled
status preserved across recovery); the Raw Info append lock alone does not
cover them.

Resume reconciliation is explicit and single-owner. After the workspace
execution lock is held and before role clients or worker ledgers are created,
the coordinator converts inherited `in_progress` attempts to `interrupted` and
charges their full reservation conservatively. `interrupted` is terminal for
attempt-count and cost accounting, preserves uncertainty rather than pretending
provider failure, and can never be finalized a second time. A fresh ledger in
the same live process must not run reconciliation while worker requests are
active.

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
