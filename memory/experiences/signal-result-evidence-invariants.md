# Signal Result Evidence Invariants

visit_times: 8

## Trigger

When auditing or changing `SignalResult`, LLM Signal parsing/correction, evidence
validation, or unavailable-rate interpretation.

## Lesson

Validate state/evidence coherence before any unavailable early return. An
`unavailable` result is a semantic statement that visible evidence could not
support a canonical conclusion; it must not retain supporting or counter
citations. Otherwise an apparently fail-closed branch can persist irrelevant or
nonliteral evidence without ever reaching source validation.

Correction feedback must identify the exact supporting/counter group and item
index for a bad citation. For an available state with no evidence, it must state
the safe repair explicitly: add a literal visible citation or return
`unavailable` with both evidence arrays empty. A generic exact-span error makes
it unnecessarily hard for the model to preserve valid citations while fixing
one bad item.

## Context

A completed paid evolution cycle resolved every Signal input and persisted 159
executed results, but one `customer_concentration` result used
`state.value=unavailable` while retaining eight irrelevant filing-cover
citations, six of which were not literal Raw Info substrings. `SignalResult`
allowed the combination and `validate_signal_result()` returned immediately for
unavailable, bypassing all evidence checks. A separate five-citation result had
four literal citations and one invalid citation, but feedback named no item.

## How to Apply

1. Enforce unavailable/no-evidence in the canonical value object so every
   constructor and parser shares the invariant.
2. Keep full Raw Info local and validate every retained non-unavailable citation
   for input membership, as-of time, literal text, and document fingerprint.
3. Audit requested resolutions, unchanged-fingerprint skips, executed results,
   semantic unavailable states, and parser/validator fallbacks as separate
   counts. A resolved request is not the same as an effective Signal result.
4. Preserve historical bad artifacts as fault evidence; prove the current code
   rejects them through exact replay rather than rewriting them.

## Limits

Unavailable remains the correct output when visible point-in-time evidence is
genuinely insufficient. Do not turn it into a neutral/positive/negative state
to improve an availability statistic, and do not accept a fuzzy citation merely
because most other citations in the same result are valid.
