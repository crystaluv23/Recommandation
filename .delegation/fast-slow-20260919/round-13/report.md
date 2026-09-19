# Round13 report: close two demonstrated reference-guard holes

round_id: round-13
status: completed

## Diagnosis (confirmed on the real guard before coding)

A pre-fix diagnostic run of the round-13 replay (exact permitted command,
exit 1, log quoted below) reproduced exactly the two independent-review
holes: `_runtime_evaluation_input_requested` returned False (no rejection)
for both brief examples and four same-mechanism variants, while the actual
V118 request74 needs, all prior negatives, and all reference positives
behaved correctly.

1. Bare ambiguous preposition: `_RUNTIME_ANCHOR_REFERENCE_PREPOSITIONS`
   contained bare "with". In dative requests the "with" introduces the
   requested object ("Please provide me WITH the baseline date and
   price."), so the left scan reached "with" and wrongly returned
   reference use before ever seeing the request verb.
2. Incomplete enumeration: `_RUNTIME_EVALUATION_BASELINE_INPUT` uses a
   greedy `.{0,48}` span, so one match swallowed "baseline price, what is
   the baseline price"; nomination used `word_pattern.search` (first
   occurrence only), so only the early, "using"-governed mentions were
   classified and the later same-anchor direct lookup was never nominated.
   The same first-occurrence pattern existed in the scalar price-noun
   fallback.

## Fix (spec-first, mechanisms, no verb vocabulary)

Spec: `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`
— the runtime-owned-input invariant now states that bare "with" is not a
reference preposition (dative "with" fails closed on the request verb;
reference "with" only via explicit phrases) and that nomination enumerates
every anchor-word occurrence inside each proximity span, so an early
reference mention never hides a later same-anchor lookup.

Code (`src/stock_opportunity_agent/research/evolution_research_validation.py`):

- Removed "with" from `_RUNTIME_ANCHOR_REFERENCE_PREPOSITIONS` (with a
  comment stating the dative constraint). Reference "with" stays licensed
  by the existing `_RUNTIME_ANCHOR_REFERENCE_PHRASES` ("compared with",
  "with respect to"), which are matched as single tokens before the scan.
  No verb list added; every dative verb ("provide", "supply", ...) now
  fails closed automatically.
- Checked the same generic issue for the other set members
  (from/against/versus/vs/using/above/below/beyond/near/than): none can
  introduce a dative requested object; the request verb before the anchor
  already rejects those forms. Only "with" was ambiguous.
- Nomination in `_runtime_evaluation_input_requested` now iterates
  `finditer` over each proximity span for baseline / date|price words and
  for the scalar price-noun fallback, so every occurrence in every
  (possibly clause-spanning) match is classified. The current-price
  trigger's existing exhaustive current-word iteration is unchanged.
- Docstrings updated to match. Nomination patterns, classification scan,
  PIT future-fact guard, and the accepted round-10 output_validation
  patch are untouched.

## Tests (tests/test_evolution_execution_roles.py)

- New `test_v118_bare_with_lookup_rejects_but_compared_with_reference_allows`:
  provide-with dative negatives for baseline/current-price/definition vs
  the contiguous "compared with the supplied baseline price" positive.
- New `test_v118_same_anchor_reference_does_not_hide_repeated_lookup`:
  reference-then-lookup same-anchor negatives ("Using the supplied
  baseline price, what is the baseline price?" and two variants,
  including a compared-with preamble hiding a baseline-date request) vs a
  repeated same-anchor dual-reference positive ("relative to the supplied
  baseline, as measured from the supplied baseline date").
- All prior v118/v111/v109 regressions, the six verbatim request74 needs
  test, and PIT checks unchanged and passing.

## Actual verification (exact permitted commands; exit codes in brackets)

Pre-fix diagnostic (same replay command, before code changes): [1] —
exactly the six round-13 negatives wrongly passed ("bare-with direct
lookup still passes" x3, "hidden same-anchor lookup still passes" x3);
holes confirmed on the real guard.

1. `PYTHONPATH=src .../python3 .delegation/fast-slow-20260919/round-13/replay.py > .../round-13/replay.log 2>&1` [0]
   → ALL ROUND-13 REPLAY CHECKS PASSED (replay.log): all six actual V118
   request74 needs classify non-requesting; the actual request74 response
   through the production parser carries no runtime-owned error; all
   prior ordinary/genuine/mixed lookups reject; all six reference
   positives pass, including the new compared-with and repeated-reference
   pairs.
2. `PYTHONPATH=src .../python3 -m unittest discover -s tests -p test_evolution_execution_roles.py -v > .../round-13/focused.log 2>&1` [0]
   → Ran 79 tests, OK (77 prior + 2 new).
3. `PYTHONPATH=src .../python3 -m unittest discover -s tests -v > .../round-13/full-tests.log 2>&1` [0]
   → Ran 888 tests, OK (886 prior + 2 new; all prior scope protections
   pass).
4. `sh scripts/lint_repo.sh > .../round-13/lint.log 2>&1` [0]
   → Lint result: PASS.
5. `git status --short` → only the pre-existing delegated-task dirty files
   plus this round's artifacts; no unrelated files touched, round-10
   patch preserved untouched.
6. `git diff --check` [0] → clean.

No pytest, no subagents, no commit/push, no production model calls per
round brief (no live-completion claim).

## Files changed (within the round-13 allowed-writes list)

- `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`
- `src/stock_opportunity_agent/research/evolution_research_validation.py`
- `tests/test_evolution_execution_roles.py`
- `progress/status.md`, `progress/changelog.md`
- `.delegation/fast-slow-20260919/round-13/{report.md,replay.py,replay.log,focused.log,full-tests.log,lint.log}`

## Unresolved limitations (same-mechanism review; no complete semantic
correctness claimed)

1. A lookup phrased as a pure reference construct still silently passes,
   e.g. "Retrieve the share price from the supplied baseline": "from" is
   a legitimate reference preposition and rejecting the request verb
   would reintroduce the verb list this design deliberately deleted
   (round-12 residual, same mechanism family, unobserved on the wire).
2. Non-contiguous or inflected compare-with forms ("compare/compares/
   comparing X with the supplied baseline") now reject conservatively:
   bare "with" is no longer licensed and only the contiguous phrase is a
   closed construct. Same conservative direction as other unrecognized
   governors; unobserved on the wire.
3. Round-12 residuals unchanged by design: oblique reference mentions
   with unrecognized governors reject and require rephrasing, and the
   scalar trigger's value-word nomination remains loose outside the
   outcome-noun "of" family.
