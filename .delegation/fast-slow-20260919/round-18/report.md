# Round18 final report: finish narrow identity-feedback boundaries

round_id: round-18
status: completed (all checks pass; awaiting independent acceptance)

Baseline: HEAD cacf8eb with round-17's uncommitted changes preserved and
extended. No subagents, no paid model calls, no commit/push, no
frozen-workspace or round-17 evidence modifications. Only the six
whitelisted shell commands were executed. A new untracked
`.delegation/fast-slow-20260919/v121/` directory appeared from outside this
round during execution; it was not created or touched by this round.

## 1. Repairs (exactly the three brief items, specs first)

1. Restoration-only fallback progress
   (`src/stock_opportunity_agent/research/evolution_output_validation.py`,
   `_research_state_evidence_grounding_fallback`): the gate became
   `if not removal_paths and not literal_restorations: return None`, so an
   obligation set with only `basic_literal_identity_mismatch` now produces
   the byte-exact literal restoration instead of None. Before mutating, the
   restoration index and target row are validated against the failed output
   (bounds + Mapping + kind == basic_info), removing the IndexError path.
   Acceptance still flows only through the existing production caller
   `_complete_parsed_role`, which re-parses the fallback output with the full
   production parser before returning it; mixed restoration+removal paths and
   sibling preservation are unchanged (covered by the round-17 wire replay B1
   and the existing tests).
2. Novel Basic ref with an empty prior Basic map
   (`src/stock_opportunity_agent/research/evolution_research_validation.py`,
   `_raw_basic_literal_identity_issues`): removed `if not prior_literals:
   return []`. A non-null prior with only Signal evidence now yields the
   remove-only `basic_ref_not_in_prior_state` typed obligation for every
   returned Basic ref; `previous_state is None` (initialize) still returns [].
3. Remove authority for the remove-only identity codes (same fallback): the
   `basic_ref_not_in_prior_state` / `basic_literal_identity_ambiguous`
   branches now require `"remove" in allowed_repairs` before their row
   eviction (they previously ran ahead of the generic guard). The restoration
   branch remains replace-only. No authority was broadened anywhere.

Specs updated first:
`spec/src/stock_opportunity_agent/research/evolution_research_validation.md`
(absent projection includes a non-null prior with no Basic refs at all;
initialize exempt) and
`spec/src/stock_opportunity_agent/research/evolution_output_validation.md`
(restoration-only progress with safe index/type validation; remove-only
identity codes evict only under their own remove authority; every fallback
result accepted only after production-parser revalidation).

## 2. Reproduction before the fix (focused run, exit 1, log kept)

The four new tests were added and run BEFORE the source fix
(`.delegation/fast-slow-20260919/round-18/focused.log`, first run):
- `test_literal_only_identity_fallback_restores_without_removals` FAIL —
  helper returned None for the literal-only obligation set.
- `test_novel_basic_ref_flagged_when_prior_has_only_signal_evidence` FAIL —
  helper returned [] with a signal-only prior.
- `test_remove_only_identity_codes_require_remove_authority` FAIL for
  repairs ("replace",)/("add",) — the row was evicted without remove
  authority. (An initial `()`-repairs subTest errored inside
  `ValidationIssue` construction — the model forbids empty repair sets — and
  was dropped; replace-only/add-only cover "no remove authority".)
- `test_literal_restoration_validates_index_and_row_type` passed pre-fix
  (pure safety net for the new validation loop).

## 3. Exact commands and results

- focused (pre-fix): `PYTHONPATH=src …python3 -m unittest discover -s tests
  -p test_evolution_output_validation.py -v > …round-18/focused.log 2>&1`
  → exit 1 with exactly the reproductions above.
- focused (post-fix): same command → exit 0, Ran 45 tests OK (41 + 4 new).
- full: `PYTHONPATH=src …python3 -m unittest discover -s tests -v >
  …round-18/full-tests.log 2>&1` → exit 0, Ran 910 tests OK (906 + 4).
- lint: `sh scripts/lint_repo.sh > …round-18/lint.log 2>&1` → exit 0.
- replay: `PYTHONPATH=src …python3 .delegation/fast-slow-20260919/round-18/
  replay.py > …round-18/replay.log 2>&1` → exit 0.
- `git status --short` → only the allowed files plus this round's logs;
  round-17 evidence untouched; `git diff --check` → clean.

## 4. Replay content (round-18/replay.py, offline ScriptedRoleCaller only)

- Part 1 loads round-17/replay.py by path (unaltered) and reruns its checks
  on the original V120 wire files: diagnosis A (1718→1704→1697 chain),
  B1 original raw95/96 chain (initial feedback carries both obligations,
  3 llm_calls, fallback restores the 1718-char literal, authorized removals
  only), B2 compliant chain, B3 fail-closed fixtures — all pass with the
  post-fix code, so round-17 behavior is preserved.
- R1 restoration-only: literal-only feedback codes are exactly
  ['basic_literal_identity_mismatch']; the fallback reports removed=() and
  normalized=('supporting_evidence[0].exact_text',); the production
  `_complete_parsed_role` run accepts after revalidation (llm_calls=2) with
  beliefs/signal row/needs/hypotheses/resolved questions byte-preserved and
  exactly one fallback event with removed_paths=[].
- R2 signal-only prior: novel Basic ref reported as
  ('basic_ref_not_in_prior_state', ['supporting_evidence[0]'], ['remove']);
  previous_state=None stays []; combined numeric+novel feedback carries both
  codes together; the deep tagged-ref guard still rejects a surviving novel
  ref; the full role chain accepts only after the novel row is evicted
  (survived=False).
- R3 remove authority: both remove-only codes decline under ("replace",)/
  ("add",) repairs; under ("remove",) each evicts exactly
  ('supporting_evidence[0]', 'current_beliefs[0]') with the signal sibling
  preserved; failed_output is never mutated.
- Output ends with `ALL ROUND-18 REPLAY CHECKS PASSED`.

## 5. Changed files

- `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`
- `spec/src/stock_opportunity_agent/research/evolution_output_validation.md`
- `src/stock_opportunity_agent/research/evolution_research_validation.py`
- `src/stock_opportunity_agent/research/evolution_output_validation.py`
- `tests/test_evolution_output_validation.py` (4 new tests in
  `ReflectBasicLiteralIdentityTests`)
- `progress/status.md`, `progress/changelog.md`
- `.delegation/fast-slow-20260919/round-18/{report.md,replay.py,replay.log,
  focused.log,full-tests.log,lint.log}`

## 6. Limitations

- The round-17 wire replay's batch-reconstruction limitation is unchanged
  and explicit: the canonical `exact_span` grounding of the real signal
  batch is only partially visible in the model view, so B1's reconstructed
  batch raises one additional claim_quantity obligation and B2 shows the
  compliant two-correction path; no fabricated equivalence is claimed.
- R1–R3 use compact offline fixtures (not the wire data) because the wire
  prior state contains Basic refs; the signal-only-prior scenario is a
  lifecycle possibility, not the recorded V120 case.
- Per the round brief, no git checkpoint was created (commits forbidden for
  this round); the changed files remain uncommitted for independent review.
- A new untracked `v121/` directory (outside this round's scope) appeared
  during execution and was left untouched.
