# Information-Plan Self-Evolution Audit - 2026-08-14

## Verdict

The active v3 implementation now matches the intended separation of concerns:
point-in-time Raw Info and a frozen Signal snapshot feed the Fast Information
Plan loop; label-visible Discovery data is confined to the Slow Signal loop;
Evolution Validation is sampled through a shared immutable round snapshot; the
Locked Test remains unavailable; and committed pointers, not logs or staged
files, define progress.

The previous overnight workspace is not evidence of a working learning loop.
It committed six rounds and three cycles, but every one of its 12 Plan records
has `TP=0, FP=0, TN=50, FN=3`, hence Binary F1/precision/recall are all zero.
Cycle 4 started round 7 and stopped immediately after two proposal responses,
leaving `state.json:last_completed_round=6` and
`cycle_state.json:last_completed_cycle=3`. That workspace used the retired
full-pool evaluator and old model-owned Plan lineage semantics.

The current 53-case approved manifest also cannot support the v3 evaluation
contract: its Evolution Validation split has only `50/0/2/1` cases across
`non_surge/2_3x/3_10x/10x_plus`, versus the required `8/6/4/2` per round. A
real stable-launcher smoke check now returns
`evaluation_dataset_infeasible`, reports zero external calls, creates no frozen
contract, and does not access Locked Test.

## Correctness repairs in this audit

- External acknowledgement, missing-key, and attempt/cost exhaustion states
  are control-plane pauses. They cannot be swallowed as malformed candidate
  output, converted into a rejected round, or misreported as model quality.
- Role deserialization requires real JSON booleans, arrays, objects, required
  fields, and finite numeric values. In particular, `"false"` can no longer be
  interpreted as a positive prediction and strings cannot be iterated as lists
  of categories, refs, hypotheses, or evidence.
- An empty stable Signal Registry cannot be frozen. Enabled source-data access
  requires explicit provider, capability, and source-type allowlists plus
  positive ceilings; dormant or partially specified authorization is rejected.
- Restore verifies the authoritative state checkpoint, checkpoint/meta links,
  unique Plan ids, and each linked Plan's exact id and round before it can enter
  parent selection. Equivalent absolute/relative path spellings resolve to the
  same target, so invoking status/resume with a relative workspace does not
  create a false corruption result.
- The capability backlog derived from durable Fast-loop trajectories is now an
  explicit Slow-Agent input instead of a file that was written but never used.
- Human-approved Signal candidates are prevalidated as one batch before any
  approval or stable-file change, preventing a later invalid item from leaving
  a partial promotion.
- The stable launcher now exposes source-data contract/execution authorization,
  rejects reuse of an existing workspace, and defaults to two Fast rounds with
  three independent Plan candidates. The former one-round/one-candidate default
  could not provide within-round comparison and made a first-round TP miss too
  fragile.
- Freeze reproducibility is scoped to runtime-bearing `src/`, `scripts/`, and
  `configs/`; unrelated progress or memory notes no longer block a valid code
  snapshot.

## Default review

| Default | Assessment |
| --- | --- |
| `8/6/4/2`, 20 cases, one case per company | Correct for a controlled development benchmark. It is deliberately enriched and its F1 is not a live-market prevalence estimate. |
| Two Fast rounds and three candidates per round | Reasonable cold-start default for comparison and exploration. One candidate remains an explicit low-cost diagnostic mode. |
| Top-3 plus two random parents, cosine threshold `0.9`, seed `42` | Safe and reproducible, but heuristic rather than empirically calibrated. It affects search efficiency, not label/evidence correctness. |
| Proposal temperature `1.0`, judge temperature `0.0` | Correct division between exploration and repeatable evaluation. Both values are frozen into request identity. |
| Five Signal rounds, 20 Signal calls, 40 LLM calls, 120k tokens, and `$5` per case | Conservative bounded-research heuristics. Hitting them remains an explicit stop reason and can make a candidate diagnostic-only; it cannot silently become fitness. |
| 2,500 external attempts and `$100` cumulative cost | Bounded one-run operational defaults, not a promise of indefinite unattended evolution. Exhaustion now pauses explicitly; a longer authorized run must choose reviewed ceilings when the contract is created. |
| Data acquisition disabled | Correct safety default. Enabling it is a separate frozen allowlist plus per-resume authorization. |
| Signal candidates never auto-promote | Correct governance default. Exact hash and reviewer identity are mandatory. |

## Remaining gates and design debt

1. A fresh real run remains blocked on an approved feasible dataset with enough
   distinct companies and exact `8/6/4/2` support. The expanded v7 proposal is
   large enough in shape, but identity/security-type review and point-in-time
   source coverage still precede approval.
2. A fitness gate cannot guarantee that a model will produce a nonzero F1. It
   guarantees the more important correctness property: all-negative or `TP=0`
   attempts stay diagnostic, cannot become parents, and pause the round without
   advancing either committed pointer.
3. Human Signal promotion changes the frozen Registry hash. The current runtime
   correctly refuses to continue the same contract afterward, but it does not
   yet define an operator workflow for a reviewed next-generation contract and
   workspace. That rollover changes cross-cycle comparability and therefore
   needs an explicit top-down design decision before implementation.
4. The numerical search/budget defaults above need empirical calibration after
   the first valid v3 run. They are safety and efficiency choices, not learned
   truths.

## Verification

- 250 repository tests pass under the bundled Python 3.12 runtime.
- Repository lint passes.
- Bash syntax and stable-launcher boundary tests pass.
- The real legacy approved manifest is rejected before contract creation with
  zero external calls and no Locked Test access.
- No LLM, source-data, approval, Signal-promotion, or Locked-Test action was
  authorized or performed by this audit.
