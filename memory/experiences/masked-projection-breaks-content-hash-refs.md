# Masked Projection Must Never Precede Content-Hash Graph Construction

visit_times: 0

## Trigger

Masking, pseudonymizing, or projecting persisted records that carry
content-hash identities (item_ref, source_ref, snapshot hashes) before
loading them into an index, cache, or validator that recomputes those hashes.

## Lesson

A content hash is a contract over exact bytes. Applying identity masking,
reference projection, or any normalization to records BEFORE the boundary
that verifies or derives those hashes breaks the graph in two ways: stored
refs stop verifying (hash of masked content differs), and refs newly derived
under the projection bind to projected content that no authoritative view can
ever resolve again. The failure is load-path dependent — narrow alias sets
(none of this round's identities appear in the text) pass while
full-population guards fail, so unit fixtures with small vocabularies never
reproduce it. Build the graph from authoritative unmasked rows and remove
identity only at model-facing egress: view payloads, disclosure reads, and
staged on-demand originals. Keep the masked-input path rejected by a
regression test so the pattern cannot silently return.

## Context

V142 (2026-09-28) ran the first live Fast+Slow cycle on the sourced
reflection memory. Every Slow mining cycle died with "reflection item
content hash mismatch": four sites masked entries before
`ReflectionMemoryIndex.from_entries`, while item_ref/source_ref hash exact
content. 13 of 119 authored case-reflection items embedded third-population
company names (peer comparisons), so full-population slow-role guards
rewrote them; the fast roles' 24-case alias sets never hit those strings,
which is why only mining died. The same pre-masking also risked persisted
plan/round items citing source refs computed over masked content.

## How to Apply

- Treat "mask at the boundary where the model sees data" as the only legal
  masking point; entry-level masking of hash-bound records is always wrong.
- When a validator/index recomputes a ref, grep every construction site for
  pre-mutations of its inputs, including projections that look harmless
  (case_id pseudonymization rewrites typed fields and their content hashes).
- Reproduce with the FULL production alias/guard population, not the round's
  own cases; cross-population strings (peer company names) are the killers.
- Verify the fix by replaying the real workspace state offline: authoritative
  build succeeds, old masked-input build still fails, egress views leak zero
  aliases, and sampled refs stay resolvable through read paths.

## Limits

Egress masking preserves ref stability but makes masked views slightly
larger or smaller than originals; budget enforcement stays fail-closed. This
concerns protocol wiring, not whether authored reflections are semantically
useful.

Evidence: [V142/V143 live validation report](../../reports/jev-v142-v143-masked-index-fix-20260928.md)
