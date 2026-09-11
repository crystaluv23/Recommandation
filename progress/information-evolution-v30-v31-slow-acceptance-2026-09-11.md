# V30/V31 Slow Acceptance Audit — 2026-09-11

## Acceptance question

Does a replayed committed-Fast boundary always execute real Slow Signal Mining,
including label-revealed positive/control comparison independent of new Fast Signal
demand, while Update and Registry promotion remain fail-closed?

## Frozen runs

- V30: `runs/cold_start/evolution/information-evolution-mvp-20260911-v30-slow-semantic-empty-repair`
  under contract `b7a2f66afd316e8c5cc8a12c918656ddeb7ddb8b894a17f8444d4173b94d83df`.
- V31: `runs/cold_start/evolution/information-evolution-mvp-20260911-v31-slow-h1-acceptance`
  under contract `78893524e59dbe78fe382f0e9197e2bdfaafc68364c1a9970e14791e19a2fdd5`.
- Both replay the immutable committed-Fast source from V21, use the approved
  24-case Discovery dataset and point-in-time Raw Info, and finish at authoritative
  `last_completed_round=0`, `last_completed_cycle=1`, `active_cycle=null`.
- Locked Test remained sealed throughout.

## Mining result

Both cycles ran the production `hypothesis_then_exploration_fallback` track rather
than gating Mining on the presence of a new Fast Signal request. In each cycle E1
produced eight grounded, identity-hidden and label-hidden signatures from literal
point-in-time source spans. E2 then received exactly four selected signatures with
two frozen positive and two frozen control labels.

Neither E2 call produced a new Signal candidate. Both returned the structured
semantic outcome `no_measurable_pattern`: the selected observations were isolated
financial concepts, cover-page facts, prices and single news events without a
repeated cross-case measurement. This is a completed, evidence-grounded mining
result, not skipped work, malformed output, validation failure or a claim that
Signal Mining is unnecessary.

The persisted V31 H1 wire payload also proves the intended split: H1 receives the
bounded, identity-masked, outcome-aware Fast meta-memory, including retrospective
prediction/truth feedback, but not the direct Discovery candidate roster or its
positive/control membership. V31 H1 accounted for all 145 retained need refs and
returned the valid semantic result `no_testable_hypothesis`; the controller then
continued into independent Exploration.

## Update and promotion result

V30 provides the productive Registry mutation proof:

- Update staged `max_drawdown_1y:v2` and `cash_reserves:v2`.
- `max_drawdown_1y:v2` passed contract validation and paired effectiveness, then
  was promoted by `signals/.transitions/cycle-0001.json`.
- Registry advanced atomically from v1 to v2 with output hash
  `9b8ada092c89a8d9aa8b8c39fc0359f39ae479c6b0e2447b47d4cd40332ec406`.
- `cash_reserves:v2` was rejected because it showed no strict paired effectiveness
  gain.

V31 provides the fail-closed negative proof. Update evaluated three targets.
`cash_reserves:v2` staged but its immutable positive fixture executed as
`unavailable`; the max-drawdown and financing drafts failed stable-fixture and
source-citation contracts. No candidate validated or promoted, so Registry
correctly remained v1.

## Defect repaired and verification

V30 exposed an H1 leakage-guard false positive: the point-in-time balance-sheet
term `short-term investments` was treated as if it proposed a future stock-return
outcome. The guard now requires horizon language to co-occur with an outcome
concept. A source-stated cash runway remains valid, while future short-term stock
returns, price performance and revenue growth remain rejected.

- Exact saved V30 H1 replay accepts all three hypotheses after one correction.
- Focused Signal role and engine tests: 119 passed.
- Full repository suite: 692 passed.
- Repository lint: passed.
- V31 live H1: completed semantically after one correction, with no technical
  failure.
- V31 attempt ledger: 27 completed attempts, recorded actual cost `$0.1447978`.

## Conclusion

The requested Slow behavior is accepted. Mining is independent of new Fast demand,
uses outcome-aware meta-memory plus a guarded positive/control reveal, and records a
semantic empty result when the evidence supports no reusable factor. Update can
still validate and promote an effective version into the Signal Registry, as V30
demonstrates, while invalid V31 drafts are rejected without partial Registry state.
