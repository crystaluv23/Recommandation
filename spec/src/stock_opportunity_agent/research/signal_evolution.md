# Signal and Dual-Loop Evolution

## Purpose

Own Signal-learning aggregation, candidate validation/effectiveness, Slow
Update and Mining, and the finite dual-loop coordinator. It depends on
`evolution_core.py` and `plan_evolution.py`.

## Invariants

- Signal candidates validate before promotion.
- Registry transitions remain version-bound and auditable.
- Slow-loop results and cycle completion preserve existing recovery semantics.
- The module never imports the `scheme_evolution.py` compatibility facade.
- H1 runtime fields are deterministic and cycle-bound. The committed audit
  stores the structured conclusion and an input fingerprint so a later cycle
  can distinguish changed evidence or search strategy from identical work.
  An identical prior `no_testable_hypothesis` or exhausted structured recovery
  suppresses the same H1 work; changed demand, visible capability, Registry,
  applicability inventory, visible Fast meta-memory, limits, contract, or model
  identity creates new work. H1 fingerprints the exact masked `meta_info` view
  it receives so new reflection cannot be suppressed by an older empty result.
- Exploration extraction runs in bounded microbatches keyed by stable case refs.
  A failed microbatch cannot discard valid sibling signatures or become a
  domain observation. The full frozen E1 cohort, failed refs, and usage remain
  visible; E2 runs only if both fixed groups still meet the configured grounded
  evidence floor, without replacing validation cases.
- Update evidence packets separate label-free source observations from the
  locally computed outcome relation. Model diagnostics must cite a supplied
  document ref and literal span for every fact before an update draft can be
  considered; source facts are stored as literals without a model-authored
  claim. Mining decisions persist the runtime-derived positive/control sample
  basis used for their statistical association.
- Mining anonymizes persisted meta reflections, backlog prose, and prior Slow
  work before assembling the guarded model context. Persisted originals remain
  unchanged; the outgoing identity guard remains mandatory.
  One- and two-character ticker aliases require an explicit dollar, ticker,
  symbol, or exchange marker in prose; standalone letters and quarter notation
  are not issuer identities. Full company names remain masked.
  All Slow contexts (meta, profiles, H3/Exploration source projections, and
  Update packets) consume this strict aggregate inventory without deriving new
  first-word brands. Local case masking keeps its own alias expansion. Repeated
  identical inventories reuse a bounded compiled-matcher cache; literal source
  checks and final identity scans remain in place.
- Update assigns opaque document refs before masking source text, so the current
  result and its executed evidence resolve to the same supplied document. Literal
  facts have no field-length ceiling; exact source membership and the existing
  response transport budgets remain required. A long valid quote is not a missing
  evidence error. Runtime outcome relations remain authoritative.
- Every staged Slow validation records a `search_input_fingerprint` over the
  input Registry, relevant point-in-time Raw Info identities, Discovery case
  identities, capability backlog, meta context, Mining limits, and Mining/Update
  model identities. Cycle ids and model-authored proposal ids are excluded.
  This fingerprint diagnoses repeated search separately from changed-input
  retries; it does not turn a no-candidate result into a domain failure.
- Each H3 hypothesis comparison also records a cycle-independent work
  fingerprint over the structured hypothesis without its runtime proposal id,
  the exact visible induction packets, frozen validation case identities,
  Registry input, Mining protocol, and model identity. A committed terminal
  `refine`, `rejected`, `inconclusive`, evidence-unavailable, or locally invalid
  candidate result suppresses only the identical comparison in later cycles.
  Changed evidence, cohort, Registry, model, protocol, or structured hypothesis
  creates new work; unaffected sibling hypotheses continue in the same batch.
