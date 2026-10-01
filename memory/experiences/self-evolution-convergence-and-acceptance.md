# Self-evolution Convergence and Acceptance

visit_times: 16

## Trigger

Read before another Fast/Slow repair or live successor, when the same class of
failure returns, when adding a new model/axis/modality, or when deciding whether
self-evolution has improved rather than merely executed. Also read when the user
asks why many iterations still fail.

## Lesson

Treat reliable execution, correct learning feedback, and independently confirmed
research gain as separate claims. A passing test suite, committed cycle, new
Signal, richer reflection, or higher confidence does not substitute for the next
claim. Repeated technical failures do not disprove the learning direction, but
they can corrupt its feedback and prevent it from being tested at all.

The recurring project failure was not simply insufficient prompting. It was
inconsistent contracts across producer, parser, validator, correction authority,
fallback, production construction, persistence, and the next-cycle consumer.
Local repair repeatedly left an adjacent or later lifecycle boundary untested.

## Context

The 2026-09-27 retrospective at code `381f32a` found:

- V109–V114 pooled admission read production nested records as flat records;
  tests fabricated the flat shape and could never expose decisive=0 in production.
- V126/V129 reached previously unexercised post-commit paths: missing runtime
  stats after definition-only Registry materialization, then imported/local meta
  round-id collision.
- V138 had tested parallel engine code without the production factory wiring;
  V140 mocked the precise controller/axis boundary where axis_id was missing.
- V138 correction suggested citation edits but did not authorize their paths;
  technical abstentions then entered critic feedback as if research had failed.
- V141 committed a cycle but made no new promotion or assessed Fast consumption;
  its next proposal reserved 403,119 budget units against 256,000. This was
  conservative HTTP UTF-8 bytes plus maximum output tokens, not measured input
  tokens; local preflight blocked transmission. Complete history storage and
  complete per-call history serialization were conflated.
- Later V141 replay reclassified a mixed candidate as a capability/split gap;
  the original blanket statement that all rejections proved insufficient evidence
  was too strong. Offline repair was not a completed live successor.

Full evidence and limits: [2026-09-27 retrospective](../../reports/self-evolution-retrospective-20260927.md).
Run version numbers must be paired with date, full workspace path, and revision.
These are historical examples, not assertions about whichever run is current.

## How to Apply

Before the next iteration, write a compact, reviewable acceptance statement:

1. **Failure class and evidence:** data availability, provider/control plane,
   contract/implementation, unsupported capability, or completed research with
   inadequate quality. Name the exact persisted frontier; mark unknown causes.
2. **Same-class history:** identify the earlier analogous failure and explain why
   the existing check did not catch this occurrence. Read the accumulated failure
   trajectory before designing the new patch.
3. **Whole contract:** check the producing payload, normal prompt, parsed object,
   validation obligations, permitted corrections, fallback and downstream reader.
   A suggested fix must be representable and authorized. Stop duplicate transport
   without accidentally skipping an existing safe deterministic fallback.
4. **Production composition:** exercise the real entry/factory and real serialized
   producer-to-consumer shape. Mock external I/O where needed, not the boundary
   whose behavior is being accepted. Verify that a new regression fails on the
   original defect when practical.
5. **Lifecycle:** verify commit, interruption, resume, exact-version Registry
   continuity, imported history, next-cycle reads, and context/budget growth.
   Match the replay scope to the affected lifecycle; never extrapolate a one-cycle
   pass to indefinite operation.
6. **Feedback consumption:** trace exact evidence -> diagnosis -> next prompt ->
   permitted action -> observed action. Keep technical outcomes out of invented
   research lessons. A stored reflection is only one link in this chain.
7. **Claim level:** separately report code/local replay, committed live execution,
   subgoal fulfillment, promoted, used, and benefit_confirmed. For benefit, use the
   existing fixed-cohort paired/four-arm protocol, failure denominator, independent
   coverage, and uncertainty; do not infer gain from confidence, Signal count,
   changed cohorts, or a non-significant comparison.

Prefer one stable baseline and close one whole failure class before adding more
axes or mechanisms. If reliable, comparable independent evaluations still show no
gain, revisit the research objective/data/candidate space rather than indefinitely
adding engineering guards. No-candidate can be a valid research result, but only
after the relevant engineering path executed correctly.

Keep deterministic formulas and mechanical state/evidence operations at their
deterministic owning boundaries. Do not make the LLM repeatedly reconstruct facts
and exact bookkeeping that the runtime already knows. Audit the actual wire
payload before blaming the model or adding prompt rules.

Full immutable history and a bounded model-facing read view need separate design.
The present additive-history ancestor contract forbids silently replacing earlier
layers with summaries. Any new projection/selection policy must be reviewed and
specified top-down, preserve provenance and important lessons, and be verified for
cross-cycle behavior. Increasing budget or opening fresh workspaces alone does not
resolve accumulation.

## Limits

This is a review/acceptance discipline, not a new runtime gate, scoring definition,
threshold, or permission to launch external calls. Existing PIT, literal evidence,
identity/label separation, Locked Test, atomic pointers, and promotion contracts
remain binding. Keep failures in formal frozen-cohort accounting; successful-only
diagnostics may localize causes but may not replace official results.

Do not promise that every future run succeeds, require every cycle to promote, or
claim that engineering repairs prove market-research value. Recheck current code,
contracts, pointers and artifacts before applying historical conclusions.
