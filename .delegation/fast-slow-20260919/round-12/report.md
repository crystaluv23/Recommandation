# Round12 report: fail-closed anchor classification, real verification executed

round_id: round-12
status: completed

## Diagnosis (confirmed by real replay before coding)

The diagnostic replay (run first, exact permitted command) confirmed the
round-11 independent review on the real guard: `_anchor_occurrence_requested`
returned False (permission) for every unrecognized left governor, so all five
brief negatives passed ("What is the value of the baseline price?",
"Please obtain the baseline date and price.", "Can we look up the baseline
price?", "The baseline price is what?", "The baseline date and price must be
identified."), because "of"/"obtain"/"up"/no-governor were treated as evidence
of a different topic. The actual V118 request74 needs[0] positive passed only
through the same fail-open path (its paired "price" anchor is governed by
"doubling of ..."), i.e. the guard had no conservative default at all.

## Fix (spec-first, generic, less machinery)

Spec: `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`
— the round-11 invariant was rewritten: classification fails closed; an anchor
occurrence is reference use ONLY when a closed reference construct licenses it.

Code (`src/stock_opportunity_agent/research/evolution_research_validation.py`):

- `_anchor_occurrence_requested` replaced by `_anchor_occurrence_reference_use`:
  scanning left across noun-phrase fillers, the first external word must be a
  reference preposition/phrase ("from / relative to / compared with / above /
  using ... the supplied baseline"), or "of" whose head is a fixed-outcome noun
  ("a doubling of the adjusted share price"). Anything else — request operator,
  unrecognized governor ("the value of", "obtain", "look up"), inverted/passive
  restatement, no governor — rejects. Unknown wording is never permission.
- `_RUNTIME_ANCHOR_REQUEST_OPERATORS` (~60 words) deleted: no ever-growing verb
  list exists anymore; the mechanism is the closed allowlist above.
- The current-price trigger now classifies at the "current"/"prediction-time"
  word itself (`_RUNTIME_ANCHOR_CURRENT_WORD`), because the paired price noun
  usually belongs to the fixed-outcome phrase: "move the adjusted share price
  above the current market level" stays allowed (governed by "above") while
  "what is the current adjusted share price" and "retrieve the current adjusted
  close price" still reject.
- `_RUNTIME_ANCHOR_OUTCOME_NOUNS` (doubling/2x/reprice family) is the only new
  closed set, reusing the fixed-outcome vocabulary already in the module.
- Nomination proximity patterns, error text/paths, PIT future-fact guard, and
  the round-10 output_validation patch are untouched; per-occurrence and
  per-paired-keyword classification keeps mixed and repeated clauses rejecting
  actual lookups.

## Tests (tests/test_evolution_execution_roles.py)

- Round-11 test corrected: `test_v118_reference_only_outcome_terms_mention_is_allowed`
  → `test_v118_unrecognized_outcome_terms_governor_fails_closed` ("bears on the
  ... outcome's terms" is an unrecognized governor and now documents the
  conservative rejection with repair).
- New `test_v118_ordinary_direct_anchor_queries_fail_closed`: the five brief
  negatives plus "Could you provide the current share price?" and "Please define
  the terms of the fixed six-month evaluation outcome."
- New `test_v118_multiple_clauses_reject_lookup_among_reference_anchors`:
  reference-baseline + genuine baseline-date lookup in one item (repeated
  anchor mentions), outcome-reference + current-price lookup (different
  anchors), and a both-references positive (preposition + "measured from" +
  outcome-noun "of") that stays accepted.
- Unchanged round-11 tests kept: six verbatim request74 needs accepted,
  genuine baseline lookups rejected, mixed issuer+runtime lookup rejected,
  reference-only current-price and scalar-doubling mentions accepted,
  reference-anchor does not waive future-fact rejection.

## Actual verification (exact permitted commands, all exit 0)

1. `PYTHONPATH=src .../python3 -m unittest discover -s tests -p test_evolution_execution_roles.py -v > .delegation/fast-slow-20260919/round-12/focused.log 2>&1`
   → Ran 77 tests, OK (focused.log).
2. `PYTHONPATH=src .../python3 -m unittest discover -s tests -v > .delegation/fast-slow-20260919/round-12/full-tests.log 2>&1`
   → Ran 886 tests, OK (884 prior + 2 new; all prior scope protections pass) (full-tests.log).
3. `sh scripts/lint_repo.sh > .delegation/fast-slow-20260919/round-12/lint.log 2>&1`
   → Lint result: PASS (lint.log).
4. `git status --short` → only the delegated-task files plus this round's
   artifacts; no unrelated files touched by this round.
5. `git diff --check` → clean (no whitespace/conflict issues).
6. `PYTHONPATH=src .../python3 .delegation/fast-slow-20260919/round-12/replay.py > .delegation/fast-slow-20260919/round-12/replay.log 2>&1`
   → ALL ROUND-12 REPLAY CHECKS PASSED (replay.log): all six actual V118
   request74 needs classify non-requesting; the actual request74 response
   through the production parser is rejected only by its real numeric-evidence
   defect (missing claim quantities), never the runtime-owned error; all
   ordinary/genuine/mixed lookups (including the two multi-clause forms)
   reject; all clearly-reference uses pass.

Round-11's blocker did not recur: every listed command was accepted verbatim
this round. No pytest was used (unittest + bundled runtime, as the brief
states). No commit/push per round brief.

## Files changed (within the round-12 allowed-writes list)

- `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`
- `src/stock_opportunity_agent/research/evolution_research_validation.py`
- `tests/test_evolution_execution_roles.py`
- `progress/status.md`, `progress/changelog.md`
- `.delegation/fast-slow-20260919/round-12/{report.md,replay.py,replay.log,focused.log,full-tests.log,lint.log}`

Round-10 patch (evolution_output_validation.*) untouched; no scoring/dataset/
promotion/schema/correction-budget changes; no production model calls; no
claim of real joint completion.

## Outstanding semantic limitations

1. Reference use is only recognized through the closed construct set (left
   reference preposition/phrase; outcome-noun "of"). Oblique mentions with
   unrecognized governors (e.g. "bears on the ... outcome's terms",
   "the current environment affecting the share price") now reject and require
   rephrasing in correction — the conservative direction the brief chose; no
   such form appears in the observed V117/V118 wire data.
2. A lookup phrased as a pure reference construct can still pass, e.g.
   "Retrieve the share price from the supplied baseline" (the guard reads it
   as deriving from the supplied anchor). Unobserved on the wire; noted as a
   residual boundary of proximity nomination.
3. The scalar trigger's "exact ... price noun" nomination remains loose
   (e.g. it nominates "exact doubling of the adjusted share price"); the
   outcome-noun "of" construct clears exactly that family, but other
   value-word + noun combinations depend on the closed construct check.
