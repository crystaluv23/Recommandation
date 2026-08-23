# Structured Role Boundary Exactness

visit_times: 4

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

## Limits

Authorization headers and provider secrets never enter artifacts. A generic
test client without a provider request builder can retain logical request
auditing, but production registered providers require byte-level wire records.
