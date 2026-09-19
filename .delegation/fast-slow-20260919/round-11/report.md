# Round 11 Report: distinguish use of supplied evaluation anchors from retrieval

round_id: round-11
status: completed (code/spec/tests/replay written; executed verification BLOCKED — see blocker)

## Blocker (report-first, unchanged since the initial report)

Every shell command in this delegated session — including `git status`, `pwd`,
`echo`, and `python -m pytest` — was rejected by the session's permission
hook with "Outside delegation scope". Per the brief ("do not expand
permissions"), the round proceeded with Read/Edit/Write only. Therefore:

- The full test suite (expected 877 + 7 = 884), `sh scripts/lint_repo.sh`,
  and the replay script were NOT executed. All behavioral claims below are
  trace-verified against the actual guard code, prompts, and existing tests,
  and must be confirmed by the successor before any live acceptance.
- No git checkpoint could be created (AGENTS.md session-end commit step is
  shell-bound). All changes are in the working tree, staged nowhere.

## Diagnosis (actual wire evidence, not invented cases)

Real failure (v118-rejection-evidence.json, c01 Life Time, attempt 74):
`next_information_needs[0]` = "What did the company disclose by 2025-03-31
about its 2025 full-year revenue, adjusted EBITDA, membership, or
center-opening guidance, and did any such guidance quantify a bridge to a
doubling of the adjusted share price from the supplied baseline?" — an
issuer-guidance question that USES the supplied baseline as a reference
anchor. `_RUNTIME_EVALUATION_BASELINE_INPUT`
(src/stock_opportunity_agent/research/evolution_research_validation.py)
matched "price … baseline" proximity alone and rejected it as a
runtime-owned evaluation input; the correction then reordered the need and
the run died in the round-10-diagnosed stall family. The owning initialize
system prompt (evolution_plan_roles.py:161-185) already expresses the
correct semantics — baseline date/price "are runtime inputs, not issuer
facts **to request**" — so the guard was stricter than its own contract.

## Fix (spec-first, generic intent distinction)

Spec: `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`
gained the invariant: proximity nominates candidate anchors; each anchor
occurrence is classified (after underscore normalization, like the temporal
checks) by the governor immediately to its left. A reference
preposition/phrase ("from / relative to / compared with / above … the
supplied baseline") or an embedding under other content marks a supplied
anchor the question uses; a request operator directly governing the anchor
(interrogative, copula, lookup verb — "What is the exact baseline date",
"Confirm the current share price") still fails closed.

Code (`src/stock_opportunity_agent/research/evolution_research_validation.py`):
new `_anchor_occurrence_requested` (left token scan over
noun-phrase-internal tokens; first external word decides: reference
preposition/phrase → reference use, request operator → lookup, other
content → embedded use) and `_runtime_evaluation_input_requested`
(collects anchor positions from the four unchanged proximity triggers —
baseline+date/price, current/prediction-time price, definition, scalar
(with prediction-date gate) — classifies each occurrence and each paired
keyword, rejects iff any occurrence is requested).
`_raw_research_evaluation_boundary_issues` now calls the helper instead of
the raw proximity OR. Error message text and paths are unchanged, so
downstream `_validation_obligations` parsing (round-10 accepted patch,
unmodified) behaves identically for genuine rejections.

Properties: no company/case/string exception; no word-list bypass
("supplied"/"using" only classify the mention they govern — a mixed
question still rejects via its other anchor); genuine
baseline/date/current-price/definition/scalar lookup rejection preserved
(`test_initialize_rejects_runtime_baseline_need_above_summary_target` and
both v109 tests classify REQUESTED); all PIT future-fact rejection is a
different guard and untouched.

## Tests (written; NOT executed — blocker)

File: `tests/test_evolution_execution_roles.py` (class
SignalExecutionAndInitializeRoleTests, inserted after the v109 pair):

1. `test_v118_initialize_allows_issuer_guidance_using_supplied_baseline` —
   all six verbatim request74 needs accepted in one call (prediction_time
   2025-03-31).
2. `test_v118_baseline_anchor_still_rejects_genuine_runtime_lookups` —
   "What is the baseline price…" and "Confirm the exact baseline date…"
   rejected with the runtime-owned error and repaired.
3. `test_v118_mixed_issuer_and_runtime_lookup_is_not_bypassed` — issuer
   guidance + "what is the current adjusted share price relative to the
   supplied baseline?" still rejected.
4. `test_v118_reference_only_current_price_mention_is_allowed` —
   "…move the adjusted share price above the current market level?".
5. `test_v118_reference_only_outcome_terms_mention_is_allowed` —
   "…bears on the fixed six-month evaluation outcome's terms?".
6. `test_v118_reference_only_scalar_doubling_mention_is_allowed` —
   "…achieving an exact doubling of the adjusted share price?" (scalar
   alt-2 trigger fires; classifier clears it).
7. `test_v118_reference_anchor_does_not_waive_future_fact_rejection` —
   reference-anchored question with "after 2025-06-30" still rejected by
   `future_information_unavailable`, and the bounded correction passes.

Commands the successor must run (none could be run this round; exit codes
N/A):

- `python -m pytest tests/test_evolution_execution_roles.py -q` (focused)
- `python -m pytest tests/ -q` (full suite, expect 884 = 877 + 7)
- `sh scripts/lint_repo.sh`
- `python .delegation/fast-slow-20260919/round-11/replay.py`

Logs: no execution logs could be produced this round (shell blocked);
`round-11/replay.py` prints the per-need classification, the actual
request74 parser outcome (must show a numeric-evidence failure or
acceptance, never "runtime-owned evaluation input"), and guard unit checks,
exiting non-zero on any unexpected result.

## Replay (script provided, not executed)

`round-11/replay.py` imports the round-10 replay utilities, reads only
immutable V118 artifacts (attempts/requests/cache under the frozen v118
workspace; nothing altered), and asserts: every actual request74 need is
classified non-requesting (needs[0] in particular), the actual request74
response through the production parser no longer produces the runtime-owned
error (other real numeric-evidence errors may remain), genuine and mixed
lookups still request, reference-only uses do not.

## Files changed (all within the round-11 allowed-writes list)

- `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`
- `src/stock_opportunity_agent/research/evolution_research_validation.py`
- `tests/test_evolution_execution_roles.py`
- `progress/status.md`, `progress/changelog.md`
- `.delegation/fast-slow-20260919/round-11/{report.md,replay.py}`

Round-10 patch (evolution_output_validation.*) untouched; no
scoring/dataset/promotion/schema/correction-budget changes; no paid
production calls; no commit or push.

## Unresolved issues

1. Tests, lint, replay, and the git checkpoint are unexecuted (blocker
   above). The successor must run them before the successor live run;
   do NOT claim live success from this round.
2. Residual known boundary (documented in the spec invariant): passive or
   inverted restatements of a runtime value ("The baseline price is what?",
   right-side "must be identified") are not governed by a left-side request
   operator and can pass this guard; the prompt-level prohibition remains
   the backstop. No such form appears in the observed V117/V118 wire data.
3. Upstream prompt wording was reviewed and left unchanged (already
   intent-consistent; changing it would also rotate live request hashes
   unnecessarily).
