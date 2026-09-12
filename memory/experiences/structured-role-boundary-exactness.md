# Structured Role Boundary Exactness

visit_times: 24

## Trigger

When changing structured LLM output correction, explicit empty domain results,
Predictor output contracts, exact request auditing, or provider serialization.

## Lesson

A schema-valid empty domain answer and a model/schema failure are different
control states. Only an explicit validated empty value may become domain
`no_match`; invalid output that remains invalid after bounded correction must
raise with cumulative usage.

Prompt, parser, durable request, provider request builder, and HTTP bytes form
one contract. Prompt text must name only fields accepted by the parser. Build a
provider body through one deterministic method, persist its canonical UTF-8
text/length/hash, rebuild and compare it before attempt reservation, and send
the same canonical bytes through transport. Semantically equivalent JSON is not
sufficient for exact approval, cache identity, or request replay.

An output-contract example is also executable prompt content. A placeholder in
that example can be copied verbatim and pass a merely non-empty schema check;
even a logically valid example can collapse exploration if accepted as candidate
content. Examples therefore need valid role semantics, an explicit do-not-copy
boundary, and a local template/example-echo plus role-substance validator before
the domain object is accepted.

Schema-valid state can still be logically non-adaptive or semantically outside a
skill's domain. If a reflection adopts new evidence but preserves the exact same
open needs, validate the transition rather than accepting the snapshot fields in
isolation. If one response has several independently decidable shape or literal
support defects, aggregate them before spending the only correction. Extraction
skills must state negative applicability boundaries as concretely as positive
criteria; ordinary output from a mature operation is not evidence that a new
technical product crossed into commercialization.

An unavailable model interpretation is unsafe downstream even when its enum and
evidence arrays are valid: “no evidence found” is routinely shortened into “the
condition is absent.” Keep the original interpretation only in the canonical
artifact and give downstream roles one deterministic coverage-only statement.
Transition checks should also compare normalized content, because appending a
qualifier to an entire old question can evade exact equality without advancing
research. When a compact card has a genuinely unambiguous direct need phrase,
version it with the Signal and use it only to challenge an empty selection once;
never turn that phrase into a local automatic selection.

## Context

The Signal selector once converted two invalid outputs into an empty selection,
mislabeling model failure as `NO_SIGNAL_MATCH`. The Blind Predictor asked for
`is_surge` even though its fixed schema accepted only `candidate_judgment`.
Structured role artifacts stored compact user JSON while execution regenerated
spaced JSON, so the artifact and provider message were not byte-identical.

## How to Apply

1. Parse explicit empty results through the same strict schema as non-empty
   results.
2. Use the common bounded-correction helper and preserve all reported usage.
3. Derive binary/internal fields only after validating the provider schema.
4. Serialize model payloads once with canonical Unicode-preserving JSON.
5. Make provider `prepare_request` the single source for preview and execution.
6. Compare exact secret-free provider body bytes before reserving an attempt.
7. Make structured examples safe if copied, but reject exact example/template
   echoes and validate the field's intended domain actions before acceptance.
8. Validate state transitions when new evidence should change the next action;
   do not rely only on the next state's schema.
9. Aggregate every locally decidable defect into the single correction message.
10. Put explicit non-applicable cases in both the compact routing card and the
    full extraction skill.
11. Canonicalize unavailable in every model-facing view while retaining the
    original interpretation locally.
12. Reject normalized full-question carryover, not only byte-identical state.
13. Version conservative direct routing phrases and use them only for bounded
    empty-result correction.
14. Separate directly invalid paths from bounded permitted dependency paths. A
    mandatory evidence-literal repair may invalidate its same-claim assertions; do not
    simultaneously freeze those dependents and then reject the required consequence.
15. For unsupported numbers, identify the complete authored token with path, span, and
    verbatim context; a one-digit token is not satisfied by the same character inside a
    decimal. After bounded corrections, a deterministic fallback is safe only when it
    copies an already-visible short source literal or removes mechanically invalid whole
    items, preserves all unrelated state, and reruns the complete validator.
16. Optional structured portfolios need row-level failure containment. If every final
    obligation names an indexed row or descendant, removing only those complete rows and
    reparsing is safer than either accepting them or discarding valid siblings. Preserve
    mandatory-nonempty and all other collection invariants through that reparse.
17. Give evidence-backed observations an explicit empty-plus-gap branch and exact
    ref/span grounding; gate downstream comparison on complete fixed groups and use
    only bounded, label-hidden replacement for missing evidence.
18. Outcome-leakage guards must match an outcome concept together with its horizon.
    Bare horizon vocabulary is unsafe: `short-term investments` and a source-stated
    six-month cash runway are point-in-time facts, while short-term returns or price
    performance are replacement outcomes and remain invalid.
19. When independent structured pipelines intentionally continue after one sibling's
    locally handled failure, emit a typed stage/error/usage event before starting the
    sibling and also retain the failure in the durable result. Otherwise the next
    provider request can make the failed stage invisible during live diagnosis.
20. Reflection transport is not action routing. A downstream role must distinguish
    lessons inside its own domain from retrieval, analysis, and prediction-policy
    actions owned by another role. Give out-of-domain actions an explicit bounded
    route that the owning pipeline already consumes; never force them into a
    superficially actionable but semantically false artifact.
21. A portfolio role must receive evidence in the same structural scope in which it
    reasons. A global packet pool plus per-item refs lets the model count sibling
    evidence even when local code can resolve the refs correctly; nest the exact
    packets under each owning comparison and derive readiness from that same scope.
22. Correction must preserve semantic intent across a shape failure. Define the
    complete row contract, runtime-owned ids, and evidence bindings in the initial
    prompt; report an indexed row obligation that permits replacing the row. An
    undocumented candidate shape followed by a generic field-list error can turn a
    real candidate proposal into a schema-valid empty result, which is not domain
    evidence of no candidate.

A semantic extraction schema must never force positive-looking content when the
source packet can legitimately be empty. Make empty observations an explicit
validated branch with a specific evidence gap, require every non-empty observation
to cite a supplied ref and byte-exact visible span, and run the same local validator
after both production and scripted adapters. Downstream contrast should proceed only
with complete fixed groups of grounded signatures; bounded same-group replacement
may recover missing evidence without using outcome content or model-authored semantics.

## Limits

Authorization headers and provider secrets never enter artifacts. A generic
test client without a provider request builder can retain logical request
auditing, but production registered providers require byte-level wire records.
