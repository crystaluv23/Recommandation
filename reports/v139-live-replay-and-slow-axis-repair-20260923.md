# V139 Live Replay and Slow-Axis Repair

Date: 2026-09-23. This report audits the immutable V139 live workspace and
records the production repairs made after that audit. Historical V139 artifacts
were not rewritten.

## What V139 proved

- Authoritative pointers are committed through Fast round 1 and Slow cycle 1.
- The two Fast Plans genuinely overlapped in wall-clock execution. A c02 case
  started while a c01 case was still in flight, so this is not merely a
  configured concurrency value.
- The better V139 Plan scored Binary F1 `0.740741`, precision `0.769231`, recall
  `0.714286`, and magnitude macro-F1 `0.196078` on the same 24 cases as V130.
  V130 scored Binary F1 `0.800000`.
- The paired F1 delta is `-0.059259`; the 20,000-sample paired bootstrap 95%
  interval is `[-0.269231, 0.131868]`, and exact McNemar p is `1.0` (four
  V130-only-correct versus three V139-only-correct cases). This run does not
  detect a statistically significant decline, but the small sample leaves a
  wide interval and therefore does not establish equivalence.
- Locked Test was not accessed.

## What V139 did not prove

V139 consumed two committed magnitude-feedback rows, but its production Slow
controller ran only the `surge_direction` axis. Both 2-3x and >=3x cases were
positive under that label, so the run could not discover or validate a factor
that separates the two magnitude groups. `magnitude_contribution.assessed`
correctly remained false.

The V139 mining audit also claimed two narrative explorations after catalog or
fetch activity while recording zero raw narrative-span reads. Under the repaired
contract those claims are not grounded exploration. Availability, discovery,
raw reading, proposal, materialization, and validation are separate states.

The paused workspace retained two `in_progress` external attempts beside 989
completed attempts. They were not a new-call authorization and could remain
ambiguous indefinitely under the old resume path.

## Production repairs

1. Cycle startup now builds the active `magnitude_ge3_v1` group and balanced,
   issuer-disjoint sampling manifests from the contract-bound Discovery set.
   The direction and magnitude tracks run separately.
2. Every controller view carries an explicit research axis and its own label
   map. Candidate ownership, sampling, effectiveness identity, cache identity,
   audit, validation, and result persistence retain that axis. A magnitude
   candidate cannot fall back to `is_surge`.
3. The magnitude check uses 2-3x as low and >=3x as high, including 10x+ in the
   high group. A target-supported candidate remains provisional until a frozen
   Fast absent/present consumption experiment establishes incremental value and
   satisfies Binary-F1 protection.
4. Narrative exploration now requires a bounded raw event/document read. Merely
   listing or fetching a narrative family cannot mark it explored.
5. The shared cancellation flag reaches each parallel evaluator's case boundary,
   so a paused worker cannot start a later case. On resume, inherited
   `in_progress` attempts are atomically terminalized as `interrupted`, with the
   reserved cost charged conservatively rather than silently released.

## Zero-call acceptance

`scripts/replay_v139_live_acceptance.py` recomputes metrics, finds a real Fast
overlap witness, audits Slow, and reconciles an attempts-ledger temporary copy.
It performs no external calls and does not mutate V139. Its machine-readable
output is `reports/v139-live-replay-audit-20260923.json`.

The current ge3 sampler produces 16 high and 16 low development cases plus 8
high and 8 low check cases, with no issuer overlap. The corrected integration
fixture uses a genuine high-versus-low factor rather than a direction proxy and
asserts target support without premature promotion.

## Remaining live gate

This checkpoint proves production wiring and deterministic invariants, not model
research quality. A fresh revision-bound live cycle is required to verify that
the actual Slow requests read both modalities, compare 2-3x with >=3x, and
produce either a supported factor or an honest no-factor result. If a supported
candidate appears, the separately frozen Fast absent/present experiment remains
required before magnitude contribution may be marked assessed or any
target-adapted promotion can be considered.
