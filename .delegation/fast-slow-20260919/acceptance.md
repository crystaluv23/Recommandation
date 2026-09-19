# Joint-run acceptance checklist and evidence ledger

## Local repair (accepted through round09;875tests/lint and independent replays pass)

- Raw V117 requests 12 and 262 explicitly demand temporally invalid partial residuals. See v117-required-residual.json and v117-second-candidate-feedback.json. Correct both producer and consumer semantics, not just untouched fields.
- Production regression must cover bounded parent need -> narrower partial residual retaining cutoff -> exact H_reflect transition and temporal validation -> next routing input.
- No whole-object escape that admits unrelated valid sibling drift. See round-03/review.md. Legitimate explicitly justified dependencies and list changes remain possible.
- Focused/full tests and lint; source/spec/progress synchronized; accepted code checkpoint before freeze.

## Real successor run (not frozen, no calls made yet)

Use verified inputs in live-inputs.json and immutable new workspace. Keep V117 unchanged. Freeze exact code revision, approved dataset hash, v6 source Registry/history, models, case cohort, and bounded budget. Track cumulative production attempts/cost across successor repairs; never reset accounting by renaming workspaces.

## Logical joint acceptance

- Authoritative state.json:last_completed_round and cycle_state.json:last_completed_cycle advance; logs/cached cases/staged artifacts alone are not completion.
- Join real requests, cached responses, trajectories and correction obligations. Check both candidate failures from V117 no longer arise due conflicting contracts. Any new systematic contradiction stops acceptance and becomes next repair evidence.
- Demonstrate accepted reflection needs/decisions change the next actual routing/Signal work, with exact artifact links, not merely presence in a prompt. Check finite per-case continuation/finalization, evidence/quantity grounding and point-in-time cutoff.
- Inspect Fast fitness/selection/reflection -> persisted demand/Slow input -> mining/update/validation/reflection/Registry transition. Distinguish no candidate, failed validation, and passed-but-not-promoted. A genuine research-quality rejection is not automatically a code defect; explain it from evidence.
- Check prior Slow reflection/history visible in actual next consumer payload; if cross-cycle behavior remains unobserved, explicitly identify the gap and run the needed bounded continuation rather than claim it was demonstrated.
- Source data/evidence available by prediction_time; no outcome information in blind prediction inputs. Preserve denominator, promotion and uncertainty rules.
- Final audit gives exact workspace/contract/code revision, pointers, real cost/calls, causal evidence examples and remaining limitations. Complete goal only after actual joint acceptance, not local green tests.
