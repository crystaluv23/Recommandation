# V130/V138 Prompt-Flow Repair and Offline Acceptance

Date: 2026-09-22. This change follows
`reports/v130-v138-prompt-flow-audit-20260922.md`. Production behavior is fixed
through general contracts; historical run artifacts remain immutable.

## Implemented repairs

1. Signal-quantity corrections may edit only the `evidence_group` and
   `evidence_index` coordinates of same-claim, same-Signal evidence refs when
   the validator has proved that a missing literal exists at another location.
   Claims remain required repair paths and the complete ResearchState validator
   still runs after projection.
2. Framework-created technical abstentions remain in the official scoring
   denominator, but model-facing Critic, proposer, round reflection, meta FIFO,
   and Slow magnitude input receive a typed technical-exclusion record rather
   than synthetic judgment, magnitude, or post-hoc research feedback.
3. New run contracts freeze `max_parallel_plans` (CLI default 2, bounded by
   candidate count). Production builds one mutable role/evaluator stack per
   worker, shares the thread-safe external ledger, serializes workspace event
   writes, and retains the direct serial path for legacy contracts.
4. Slow discovery now enforces a symmetric exploration opportunity for every
   available structured or narrative modality before a domain terminal. It
   does not impose candidate quotas: evidence and the unchanged validation /
   promotion gates decide which factors survive. Per-modality proposal,
   materialization, and validation counts are persisted.
5. Dashboard records separate technical completion from official metrics and
   show research-completed magnitude truth/prediction distributions and recall.

## Zero-call replay

`scripts/replay_v130_v138_acceptance.py` reads V130/V138 committed records,
requests, cached responses, meta, Slow audits, and the approved development
dataset. It does not deserialize Locked Test or contact any provider. The saved
result is `reports/v130-v138-replay-acceptance-20260922.json`.

- Stored metrics recompute exactly: V130 F1 `0.800000`, V138 F1 `0.689655`.
- Replacing only V138's five technical abstentions with the same-case V130
  predictions yields diagnostic counterfactual F1 `0.812500`. This is evidence
  that technical completion explains the regression; it is not a post-fix live
  score.
- Three historical correction responses (including the audited Ciena and Wynn
  cases) gain the exact provenance-coordinate permission that old feedback
  requested but did not authorize. Unrelated response drift remains rejected
  and full validation remains mandatory.
- Round-1 reflection is found in the real round-2 proposer request. The current
  model view converts all five legacy technical rows to typed exclusions and
  exposes no synthetic research feedback.
- The approved ge3 target contains `577` 2-3x low cases and `224` >=3x high
  cases; all `5` available 10x+ development cases are in the high group. Locked
  Test remains sealed.
- V138's previously successful non-structured path is preserved: both Slow
  seeds explored structured and narrative evidence, and
  `order_backlog_conversion_or_cancellation_rights_disclosed:v1` reached
  narrative materialization and validation. The V100-V114 controller,
  literal-evidence, materialization, tiered evaluation, and promotion mechanisms
  are reused rather than replaced.

## Acceptance boundary

Offline replay proves the repaired contracts, information flow, historical F1
arithmetic, target population, and preservation of narrative mining. It cannot
claim a new observed F1 or factor promotion. A fresh revision-bound run is the
remaining gate for provider-dependent prediction quality and real parallel
throughput.
