# Signal and Dual-Loop Evolution

## Purpose

Own Signal-learning aggregation, candidate validation/effectiveness, Slow
Update and Mining, and the finite dual-loop coordinator. It depends on
`evolution_core.py` and `plan_evolution.py`.

## Invariants

- Signal candidates validate before promotion.
- Update uses the same side-effect-free candidate checks during model correction
  and staging. Deterministic candidates may omit the optional null skill; LLM
  candidates still require a complete skill. Target identity, vNext and immutable
  definition constraints remain mandatory and visible in the request contract.
  The candidate schema exposes the complete version-owned retrieval policy rather
  than the legacy singular query alias. Update requests include a runtime-built
  complete vNext template copied from the stable spec and skill plus the exact
  allowed `changed_paths` vocabulary. Candidate retrieval fields overlay that
  baseline before parsing; omitted optional fields are therefore preserved.
  `changed_paths` must exactly match the effective mutable spec/skill differences.
  Candidate/diff correction may edit both coupled fields while preserving every
  unrelated decision field. Version and fixture changes are not substantive
  Signal changes and cannot create a staged candidate.
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
  The fingerprint also includes the exact relevant point-in-time Raw Info
  identities, masked backlog, stable Registry, role protocol, and model work
  identity, while excluding cycle and proposal ids. A technical H1 failure is
  never semantic exhaustion and remains eligible after recovery under the
  existing attempt and cost ceilings. H1's complete runtime need set is the union
  of Fast `signal_need_items[*].need_ref` values and ordinary capability-backlog
  `items[*].request_id` values; the latter must not be dropped merely because
  they are provider, retrieval, or existing-Signal coverage gaps.
- Exploration extraction runs in bounded microbatches keyed by stable case refs.
  A failed microbatch cannot discard valid sibling signatures or become a
  domain observation. The full frozen E1 cohort, failed refs, and usage remain
  visible; E2 runs only if both fixed groups still meet the configured grounded
  evidence floor, without replacing validation cases.
  E2 receives only the runtime-selected grounded induction signatures. A
  semantic zero-candidate result records its limited reason and exactly those
  considered refs; unrelated E1 pool members and holdout cases remain absent.
  After bounded model correction, E1 may quarantine invalid observations while
  preserving independently validated observations and sibling signatures. It
  never clips or invents source text. Quarantine reasons remain technical audit
  metadata, including when a case has no surviving observations; they are not
  evidence that the source or measured condition is absent.
  Source-owned SEC Company Facts context retains each concept's original
  `label` as metric semantics; the transport guard distinguishes this exact path
  from retrospective outcome labels. A runtime budget exception during E1 is
  propagated unchanged to the cycle controller and is never converted into an
  E1 validation failure or masked by a missing exception binding.
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
  Candidate validation uses the same case-preserving strict matchers as outgoing
  contexts: an ordinary lowercase word must not become an uppercase ticker merely
  because the complete candidate was case-folded. Full names retain case-insensitive
  matching; explicit ticker and symbol markers retain their existing treatment.
  All Slow contexts (meta, profiles, H3/Exploration source projections, and
  Update packets) consume this strict aggregate inventory without deriving new
  first-word brands. Local case masking keeps its own alias expansion. Repeated
  identical inventories reuse a bounded compiled-matcher cache; literal source
  checks and final identity scans remain in place.
- Ordinary Fast-to-Slow demand comes from the final unresolved needs of every
  trajectory in committed Plan records, with stable need refs, exact source
  round/fingerprint provenance, and the real terminal reason. Technical Signal
  execution failures are separate diagnostics and never domain learning.
  Mining receives the complete retained, masked meta FIFO; blind extraction,
  Signal execution, and prediction do not receive retrospective meta.
- Update induction buckets accept only successful execution and explicit domain
  unavailability. Provider, parser, budget, and other technical failures retain
  their usage and audit records but never become unavailable learning. Explicit
  misleading targets prefer wrong Discovery cases and may use sourced domain-
  unavailable Discovery cases for applicability or retrieval diagnosis when the
  wrong pool is insufficient; Validation cases never refill that pool and the
  issuer-disjoint holdout minimum remains unchanged. Machine counts derive from
  structured evidence verdicts and outcome relations, not rationale prose.
  Update work keys use the full role/model identity. A substantive committed
  `no_change` may suppress identical work, while defer and technical obstruction
  remain eligible for a later bounded retry.
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
