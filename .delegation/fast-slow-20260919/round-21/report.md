# Round 21 report

- round_id: fast-slow-20260919/round-21
- status: in_progress (investigation complete, design fixed; implementation next)
- baseline: 068ec23 (922 tests + lint accepted)

## Investigation findings (pre-coding)

- Evidence decoded properly with `json.loads` from
  `.delegation/fast-slow-20260919/v123/c01-case1-rejection.json` (attempts 5-10,
  stage fields `research_controller_initialize`(+correction), `signal_retrieval_cards`(+correction),
  `llm_signal_batch_execute`(+correction)). Attempt 7 (routing) is the original
  selection payload: `guidance_acceleration:v1`, answer_need/partial, target need
  index 1 = the symbolic-cutoff parent, residual = the exact Kinross residual.
  Attempt 8 corrected only reason/coordination issues (residual byte-identical);
  attempts 9-10 executed the expensive signal batch; the pre-reflection admission
  check `_reject_unrepresentable_partial_selections` then rejected the residual as
  unrepresentable, so no reflection raw response exists.
- Root cause reproduced on helpers: `_future_source_date_refs(parent, 2025-09-30)` = []
  (parent escapes via symbolic bound + "guidance" marker + non-realized phrasing),
  but `_bounded_residual_need(residual, parent, 2025-09-30)` = None: the residual
  dropped BOTH the cutoff clause AND the expectation marker; the shared helper
  restores only the inherited cutoff clause, and clause-only restore still flags
  ['2026'] because the as-of bounded allowance requires an expectation/schedule
  marker. Routing (`evolution_plan_roles.py` ~984) anchors its producer check on
  `_need_as_of_bound_clause` (explicit dates only), so a symbolically bounded
  parent bypasses producer temporal validation entirely - producer and consumer
  disagree for exactly the accepted H1 representation class.
- Planned remedy (minimal, no parser rewrite, no noun exceptions):
  1. consumer: `_bounded_residual_need` additionally inherits the parent's
     noun-form expectation/schedule marker (guidance/outlook/forecast/targets/
     schedules/timelines/milestones/dates/timing/releases/reports/openings/
     commentary/construction plans) as explicit parent-owned framing when the
     clause-only restore still flags; realized-future phrasing never inherits
     (final `_future_source_date_refs` re-check stays the boundary); parent
     without its own validated bound/framing lends nothing.
  2. producer: routing residual temporal-scope check extended to symbolic
     prediction-time cutoffs, checked datelessly against the earliest possible
     cutoff with the same inherited representation requirement; actionable
     correction carries the inherited cutoff clause and framing marker before
     any signal executes. Explicit-date branch behavior unchanged.
- Prototype verified pre-coding: clause+marker composition passes
  `_future_source_date_refs` at both the prediction date and the earliest cutoff;
  clause-only fails (the bug); realized/unbounded negatives stay None.

## Post-implementation / testing

(to be filled after implementation, focused/full/lint, and replay)
