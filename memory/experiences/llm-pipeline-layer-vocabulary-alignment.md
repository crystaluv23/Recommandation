# LLM Pipeline Layer Vocabulary Alignment

visit_times: 6

## Trigger

When adding a new evidence modality, action surface, or candidate contract that
spans controller, materialization, retrieval validation, and executor layers —
or when a bounded correction loop keeps failing on mechanical-looking errors.

## Lesson

Every layer that touches the same concept must share one vocabulary, enforced
at the boundary where the vocabulary is authoritative. The V100–V108 narrative
sprint found the same defect class three times: the predicate contract spoke
normalized source families (`news`, `filing`, `transcript`) while materialization
validation compared raw document source types (`company_news`, `sec_filing`)
with a literal set intersection — even though the executor's retrieval matching
was already family-aware. Structured-fact excerpts likewise omitted the cited
document's source type entirely, so the model guessed and burned its correction
budget. Fix: reuse the executor's `source_types_compatible` at every validating
boundary and put the authoritative vocabulary into the model-facing payload.

Model-facing inputs must be masked at the boundary, not trusted from internal
replay-grade artifacts. Verbatim evidence spans are correct for the ledger but
routinely embed cohort identities; handing them to a model that is instructed
to copy spans verbatim into fixtures guarantees identity-gate rejections. Mask
inputs with the guard inventory (union the validator's forbidden terms) and
keep verbatim only in the ledger.

Correction feedback must carry the downstream judge's actual reasoning, not
just expected-vs-received. Adding the LLM executor's interpretation summary to
fixture failures let the authoring model resolve taxonomy disagreements in one
round; per-modality correction bounds (an LLM-judged fixture set converges
slower than a deterministic function) and per-candidate failure keys (a shared
key lets a sibling candidate's failure overwrite the diagnostic) complete the
loop.

Finally, classify transient provider anomalies by their nature, not their
transport shape: a 200 response with no message output chunk (reasoning
truncated the message away) kills a whole production cycle if raised as a
non-retryable error, while the existing bounded-retry plus run-level auto-resume
path handles it cleanly. An explicit provider refusal stays non-retryable and
surfaces its text.

Research modality and execution type are also separate vocabulary layers.
Persist the modality carried by the controller into the canonical Signal spec,
then validate its allowed executor at every materialization boundary. Inferring
modality only from `llm` versus `deterministic` hides structured formulas behind
LLM skills and makes later correction look like a behavior update instead of an
identity repair. Preserve legacy omission only for byte-compatible historical
reads; require explicit modality for every new or vNext candidate, and keep a
missing structured implementation as a capability gap rather than silently
changing the observable's modality.

## Context

Nine single-cycle production workspaces (V100–V108, 755 real calls, $4.59)
drove narrative-factor mining from first proposal to reliable first-try
materialization + standard validation. Six generalized fixes landed (c2adf1c,
ee6b877, 35110e5, 86b65b8, a4428b0, 84c7d04); after them, every proposed
narrative candidate passed materialization, contract validation, and the
validation pipeline on the first attempt, entering tiered admission as
provisional residents. Full evidence: `reports/slow_round_prompt_audit_20260913.md`
(V100–V105 and V105–V108 sections).
