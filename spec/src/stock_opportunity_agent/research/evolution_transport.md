# Evolution Transport

## Purpose

Own reproducibility checks, external request persistence, attempt and cost
ledgers, exact-response caching, and the structured model-client boundary.

## Independent local role execution (engineering MVP)

An explicitly selected `independent-subagent` backend replaces every structured
LLM call with an independent role, without network/API execution. It uses the
same stage contract, egress identity projection, request hash, parser, typed
correction, fallback and consumers. The backend identity is local and cannot
claim a registered remote model was tested. Before dispatch, enforce the frozen
byte-plus-output request reservation and cumulative local-call ceiling. An
unanswered request pauses as control flow; it is neither no-pattern nor a
technical research result. Persist an immutable inbox containing only the exact
model messages, output contract and request binding. Independent role agents
receive no acceptance answers, prior chat or repository access beyond that
request and explicitly supplied tool results. Each correction is a new request
with the original runtime correction payload.

Raw role responses bind the request hash, inbox hash and agent identity and are
saved before parsing. Resume consumes the same response, never silently asks
again; exact request cache and no-progress correction rules remain active.
Malformed output follows `StructuredOutputInvalid` and the existing correction
path. Agent token usage/internal cost are unknown: byte-plus-output accounting
is a conservative reservation, API cost is zero, and log probabilities are
absent. Local execution proves this backend's behavior only; provider API
transport and statistical prediction benefit remain separately unverified.
For this native backend, AgentUsage.llm_calls and tokens are conservative
logical budget units, not measured physical executions or host token use. Each
verified original role request contributes one budget call and its unchanged
byte-plus-output reservation on both first consumption and exact cache replay,
including document/compute reads and typed corrections within one role. Replay
creates no new inbox, receipt or external charge; count actual independent
executions from unique verified receipts/inbox changes. This keeps aggregation
and native stopping decisions invariant across interrupted replay. Remote cache
usage/accounting and attempt ledgers retain their existing zero-new-usage rule.
Original request/raw/receipt/cache bytes remain unchanged.

Production factories that select this alias use the same constructor: when an
exchange is not explicitly supplied it binds `workspace/local_roles` with the
required frozen `limits.max_local_role_calls`. Missing limits or external mode
are rejected before dispatch. Existing remote aliases and contracts retain their
original execution path. This does not authorize a full successor run.

## Invariants

- Every external request is persisted before transmission.
- Runtime case evaluation scopes every participating production caller to a
  thread-local identity projection, including initialize, routing, Signal
  execution, document reads, corrections and posthoc. Masking only the final
  Predictor cannot establish a blind research chain. Exact known aliases,
  issuer CIK representations and ticker-derived XBRL/filing prefixes are
  replaced at egress with reversible opaque tokens. Numeric `cik` fields are
  projected as identity, while ordinary financial numbers remain unchanged.
  Request estimation, persisted request and actual wire use the same view.
  Provider/cache responses retain that view; local validation restores only
  tokens supplied by the exact request, preserving literal evidence and typed
  repair snapshots. Unknown tokens and guessed target names fail closed.
  Authoritative source records, projection IDs, source hashes and reflection
  indexes are never rewritten. Context is unwound on failure/cancellation and
  never inherited by another worker or case.
  Explicit `company_id`, `ticker`, `symbol` and `known_aliases` fields are
  identity coordinates: an exact member of the bound inventory is always
  projected, including a one/two-character ticker. The short-ticker prose
  exception does not apply to these fields or their array members. Ordinary
  unmarked abbreviations in source prose keep the existing matching rules.
  The shared matcher recognizes the reverse securities-table order, where a
  known short ticker precedes a US exchange name, including preferred-series
  suffixes and Trading Symbol(s) labels. Estimation, wire masking, response
  identity checking and inverse citation restoration use the same inventory
  and matcher; ordinary unmarked MS/AI/Q2/Z remain research text. A copied
  opaque table code restores byte-exactly only through its supplied token.
  The same rule covers explicit ticker/symbol/company_id JSON string metadata
  embedded in source literals. Replace only the known identity value, preserving
  surrounding syntax (including escaped quotes), numbers and raw source hashes.
  An active identity scope also projects explicit SEC source coordinates:
  dashed accession numbers, plus issuer-directory and18-digit accession-directory
  coordinates in SEC Archives/edgar/data URLs or paths. A filing agent's accession
  prefix need not equal the bound issuer CIK. Project these coordinates before
  issuer aliases so partial masking cannot expose the remaining accession.
  Recognize complete numeric directory segments, including terminal/query URLs
  and nested JSON slash escaping, without masking numeric filename prefixes.
  Keep surrounding URL/source-family syntax and hash identities; exact inverse
  restoration recovers original spelling. Bare financial integers, dates and
  ordinary document-local prose are not source coordinates. Estimation, native
  request, output quarantine, correction and cache use the same projection;
  canonical records and completed historical requests are never backfilled.
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

## Aggregate source identity scope (2026-10-01)

The existing reversible egress scope also accepts an explicit aggregate identity
inventory without derived prose aliases. Every explicit `cik_...` issuer supplies
its padded CIK/accession and typed numeric CIK patterns. Known aliases occurring
inside URL domains use the existing URL-aware matcher; unrelated source URLs and
financial amounts remain intact. Compact namespaces use only the authorized
inventory when expansion is disabled. Source-owned scoped Slow inventories
exclude generic business words; arbitrary corpus-wide brand expansion is invalid.

The shared transport applies this same projection to every request carrying an
explicit `anonymous_aliases` inventory, even outside a case context. An active
case context takes precedence; otherwise the aggregate inventory is used without
derived prose aliases. Estimation and transmission select the identical scope.
Role adapters do not need their own aggregate context wrappers. This covers
Slow feedback reflection, Mining, Update, tool receipts and retry feedback.
Tokens restore requested event/document
handles before execution; original sources and ledger coordinates remain unchanged.
Scope unwinds on interruption and cannot bleed into another worker. A new scope is
not an alternative transport or a bypass of stage/label/budget checks.

## Provider envelope failure lifecycle

Provider-envelope failure remains outside structured role correction. Each failed
external attempt saves a request/attempt-bound diagnostic in failed_responses and
binds that immutable record hash in the settled attempt; no valid cache entry is
written. Known valid usage settles measured cost, otherwise the reservation is
charged as a conservative upper bound with cost_basis recorded explicitly. A
valid completion without measured usage has the same conservative accounting
basis. Historical attempts remain unchanged. On restart, completed exact requests
still hit cache for zero new usage; only the unfulfilled request may reserve a
new attempt under unchanged ceilings. Provider exceptions propagate without
advancing case/cycle pointers or being converted into research findings.
See the owning [provider-envelope contract](../llm.md#provider-response-envelope-and-diagnostics).

## Derived brand casing

Case egress uses the shared formal-name matcher: a derived brand is prose, not
a ticker. Mixed-case mentions of an all-caps legal name are masked in source
quotes, state, signal cards and final Predictor input. Reversible projection
restores exact local strings; persisted sources and evidence hashes remain
unchanged. Request estimation, preparation, cache lookup and transmission use
the same projection. Strict aggregate guards retain their exact inventory.

## Quarantined identity output (2026-10-02)

An otherwise parseable response that invents a raw target identity or an
undisclosed opaque token still rejects at the shared egress boundary. A typed
`IdentityOutputRejected`, compatible with existing candidate rejection, carries
only a noncanonical quarantine view and exact violation paths: offending string
or identity scalar leaves become null, and an offending mapping key quarantines
its whole mapping. It never adds guessed names to the supplied inverse table.
Safe siblings restore only request-supplied tokens. Raw provider/cache bytes are
immutable and remain local audit evidence. This view is diagnostic, not a valid
role result or a mechanical repair. Only an explicitly supporting role may
isolate dependent units, fully validate safe siblings, and use its existing
bounded correction; other roles continue to reject. Unknown-token errors in
keys must also fail closed. Provider/control-plane errors are unaffected.
