# V17 committed Fast and learning-boundary recovery

Workspace: `runs/cold_start/evolution/information-evolution-mvp-20260911-v17`.
Frozen code: `75a1a36`. Contract:
`26c9e835c6ddb55954316c5c6ce8a7c11a5e9ffebe8ef6f1be096b6685cf07ef`.
Normal Fast-then-Slow execution used the user's existing external authorization;
it did not extend the completed-cycle bootstrap boundary discussed after V16.

Both candidates completed all 24 cases and were eligible. Candidate 1 binary F1
was 0.7142857143 (TP 10, FP 4, TN 6, FN 4); candidate 2 was 0.7741935484
(TP 12, FP 5, TN 5, FN 2). These are fixed-batch measurements, not proof of
improvement over a baseline. All 48 cases finalized. There were 850 successful
model attempts and two JSON decode failures recovered by bounded correction;
recorded cost was $2.33051756. Eight actual terminal reflection requests succeeded
(three budget-exhausted, five maximum-round triggers). Locked Test remained sealed.

## Information-flow evidence

All 48 Predictor contexts and compact post-hoc reflection contexts match the
actual persisted requests. Request body byte counts and SHA-256 hashes match.
All 48 original post-hoc reflections survive exactly in `meta/round-0001.json`,
alongside both vertical Plan Critic outputs and horizontal reflection.
Actual horizontal request
`f5c5f32944d5cfafca70ce51a554e91ca990f8530c1d55ce4036881cb31c53e9`
contains both Plan records. Its persisted search implications explicitly include
separating missing evidence from negative evidence. The model's reflection is
observational guidance, not automatically enforced domain truth.

The full invariant audit checked 2,750 resolved document references and all 48
blind contexts without finding future-document leakage, repeated execution of
the same Signal within a case, or forbidden outcome/reflection fields in Predictor
input. The repaired financing projection again returned a validated positive,
partial result for the completed June 2025 $2.25 billion notes issuance. These
checks do not establish parser completeness for every possible source format.

## Newly exposed blocker and repair

The authoritative Fast pointer advanced to 1, then learning-profile construction
raised `conflicting duplicate Signal learning observation`. The cycle pointer
remains 0 with an active pre-Slow cycle. No Slow request ran. The partially
published source learning ledger must not be presented as fully reconciled.

Both committed Plans derive 529 learning events. Seven same-case/input
observations have different accepted state or coverage across Plans (two financing,
two guidance, three commercialization). Such model execution disagreement is not
corrupt identity or evidence that a condition/data source is absent.

The minimal generalized repair preserves every raw event, quarantines a disputed
observation from effectiveness counts, exposes a bounded dispute count, and lets
unaffected observations continue. It neither chooses whichever result appeared
first nor adds another unavailable result. Selection reasons and reflection
attribution remain audit counts. True identity/outcome/fingerprint conflicts
still fail integrity validation before events are appended. Profile replay also
rebuilds when event IDs are already durable, recovering interruption between event
append and profile publication without duplicate events.

The repaired pure aggregation successfully replays all 529 source-derived events.
Regression covers disagreement, independent siblings, missing-profile recovery,
idempotence and persistent rejection of identity/outcome corruption. All 647 unit
tests pass. The source run and its frozen contract remain immutable.

## Pending external continuation

Existing runtime code supports an immutable hash-bound committed-Fast pre-Slow
source; the architecture text still restricts bootstrap to rejected Fast cold
start. Confirmation was requested under the repository's ancestor-spec rule
before synchronizing that boundary. No completed-cycle reuse extension is needed
for V17. Once allowed, a successor can reconstruct the exact committed learning
and meta inputs and execute Slow without rewriting V17 or fabricating a Fast
pointer in the successor. Slow mining, candidate validation/promotion outcomes,
and next-cycle visibility remain required acceptance work.
