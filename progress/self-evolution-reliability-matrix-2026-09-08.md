# Self-Evolution Reliability Acceptance Matrix

## Scope and decision boundary

This records the T6 offline acceptance coverage for
`self-evolution-action-plan-2026-09-06.md`. It tests invariants across generic
failure classes and combinations. It is not evidence that a live model reaches
the suggested 95% first-pass or 99% bounded-recovery targets. Those targets,
sample sizes, confidence method, provider/model configurations, and run budget
still require an approved protocol before external execution.

The matrix keeps three outcomes distinct:

- a domain observation, including a valid `domain_unavailable` result;
- a technical or structural failure, retained with its stable item/case id; and
- a missing frozen result, which makes confirmation incomplete.

No test removes a failed item or changes its cohort before recomputing quality.

## Coverage

| Dimension | Offline acceptance evidence | Required invariant | Remaining live work |
| --- | --- | --- | --- |
| Format and API | `test_evolution_output_validation`, `test_evolution_control`, `test_research_openai`, and role-adapter suites cover missing/extra fields, duplicate stable ids, reorder, malformed/truncated JSON, empty/no-match, refusal/no text, retryable 429/5xx/timeout/URL failures, permanent HTTP failure, absent usage metadata, and unsupported logprobs. | Scoped correction may change only declared paths; valid siblings survive; temporary transport errors retry within bounds; permanent errors and exhausted retries remain technical failures. | Replay at least two approved real provider/model response envelopes and record the observed error distribution. |
| Evidence | Data-resolution, execution-role, reflection-role, Signal-financial, and exploration suites cover nonexistent/fabricated refs, wrong overlap, missing literal quantities, partial/truncated spans, future sources, period coverage, unit-bearing facts, unrelated evidence, and empty evidence packets. | Only exact point-in-time source spans support decisive results. Missing or invalid evidence cannot become a negative domain fact or enter learning. | Build an independently labeled semantic set with third-party/ETF contamination and currency/unit swaps sized by the approved protocol. |
| Recovery | Structured-output, routing, Signal runner, Mining, Update, and Exploration tests cover initial failure then correction, good/bad siblings, correction drift, no improvement, legal no-match, missing source, and microbatch failure. | Recovery is item-scoped and bounded. Valid siblings remain byte-equivalent; all-invalid output cannot be reinterpreted as no-match. | Measure first-pass and post-recovery rates per real role/provider after approval. |
| Persistence | `test_scheme_core`, `test_plan_evolution_engine`, `test_signal_evolution_engine`, and CLI tests cover Raw Info concurrent append, immutable candidate evaluations, every promotion transition stage, cycle-pointer replacement, repeated resume, process locking, and next-cycle Registry visibility. | Only committed pointers prove completion. Recovery completes the same transition or fails closed; partial mixed snapshots are never readable. | Verify the same invariants against a fresh code-bound live workspace. |
| Generalization | Stable-id projection, reordered routing/E1 rows, varied historical evidence positions and wording, generic provider-envelope normalization, and order-independent confirmation reports avoid issuer/model/error-message keys. | Decisions depend on typed fields, hashes, source lineage, and evidence relationships rather than a known ticker, numeric literal, provider wording, or list position. | Add new metamorphic cases when a live pilot exposes a new semantic class; do not add provider-specific acceptance exceptions. |
| Error distribution | `test_evolution_reliability_matrix` injects 0%, 10%, distributed 20%, and issuer-clustered 20% system and capability failures. It also separates failures on negative cases from failures on supporting positive cases. | Every frozen row remains in counts. Positive-label technical failures count as false negatives; negative-label failures remain failures rather than true negatives. Results may pass only within explicit failure, coverage, measurement, and benefit thresholds. | Estimate correlated real failure clusters by role, provider, source family, industry, and Signal after the pilot. |
| No-learning controls | Candidate=baseline predictions produce `no_gain`; missing capability cases produce `incomplete`; a larger candidate corpus is rejected; one cached invocation cannot carry conflicting predictions; existing tests reject identical updates and duplicate candidates, and separately report a promoted candidate that was never executed downstream. | Version/hash changes, candidate creation, promotion, or fixture execution do not prove benefit. Promotion, downstream use, and confirmed system gain remain separate facts. | Run the frozen four-arm protocol only after the actual baseline/candidate Plan and Registry identities are known. |

## Deterministic acceptance commands

```bash
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest \
  tests.test_evolution_output_validation \
  tests.test_research_openai \
  tests.test_evolution_benefit \
  tests.test_evolution_reliability_matrix

PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -p 'test_*.py'

scripts/lint_repo.sh
```

## Exit criteria before T7 external execution

1. Freeze exact provider/model aliases, retry settings, per-role call/token/cost
   ceilings, and the permitted external data scope.
2. Freeze confirmation system/capability case ids without exposing their
   contents or labels to proposer, critic, Mining, or Update.
3. Approve the T5/T6 sample sizes, repetitions, maximum experiment looks,
   minimum F1 gain and uncertainty bound, capability accuracy, coverage loss,
   technical failure, and cost criteria.
4. Create a new code-bound workspace. Existing workspaces remain read-only
   evidence because their contract hashes bind older code.
5. Preserve every request, response, correction, usage record, evidence span,
   failure, checkpoint, Registry hash, and committed pointer. Report
   `no_gain` or `incomplete` without widening the cohort or thresholds.
