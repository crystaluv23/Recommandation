# Round17 final report: expose Basic-literal identity defects in the initial reflect feedback; deterministic fallback restoration

Baseline cacf8eb3b9549ea2152d302a7a2c27a3698ddf13 (round14–16 accepted, 899
tests). No production calls, no commit/push (per this round's brief), all
frozen runs and existing audit files preserved untouched. Only the six
whitelisted shell commands were executed.

## 1. Diagnosis (from the original wire files, not the compact artifact)

The rejection artifact's attempts 90–96 span two reflect cycles plus the
signal stages between them; the failing cycle is raw95 (reflect) → 96
(correction) → cached identical correction → budget exhaustion. Original
inputs were located under
`runs/cold_start/evolution/information-evolution-dual-self-evolution-20260920-v120/`
with `attempts.json` mapping attempt → request hash; the full original
request payloads are the `user` message contents of `requests/<hash>.json`
and the outputs are `cache/responses/<request-hash>.json["json_output"]`
(verified: prior literal 1718 chars, output95 1704, output96 1697; deleted
text `'17 CFR 17 CFR '` then one more `'17 CFR '`). The failure artifact
(`experiments/trajectories/plan_r0001_c01/cik_0001869198:20250331.failure.json`,
under the run dir) contains the final plain error verbatim.

Root cause of the masking chain:

1. `_normalize_research_state_output` aggregates only
   `_raw_basic_claim_quantity_issues` and
   `_raw_quantitative_assertion_link_issues` into the correctable
   `StructuredValidationError`. Literal identity versus the prior state was
   enforced only inside `_validate_research_state_refs` (deep tagged-ref
   construction, `raise ValidationError("reflect cannot introduce a new Basic
   Info ref")`) — unreachable while any structured issue remained.
2. Consequently raw95's feedback named only
   `assertion_without_support/current_beliefs[7]`
   (`revenue_growth_yoy=0.182443` without a retained matching claim); the
   1718→1704 literal mutation was invisible, and output96 mutated further
   (1697) while retaining the invalid belief. Correction-2 replayed the
   cached identical response.
3. After budget exhaustion the deterministic fallback removed the assertion;
   only then did the deep guard run and reject the mutated literal as a plain
   construction error — an uncorrectable terminal state with no earlier
   actionable feedback (recorded in the failure artifact).

The initial mutation originates in raw95 itself (not the fallback), and the
assertion instructions also suggested "split the assertion" although
`allowed_repairs` are replace/remove only (round-16 forbids implicit
one-to-many).

## 2. Repair (specs first, then minimal source changes)

Specs:

- `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`:
  reflect-phase raw validation is identity-aware for Basic Info refs — a
  mutated literal is reported together with all other independently decidable
  raw issues in the same initial feedback; unique prior literal ⇒ replace-only
  obligation carrying the exact prior literal; ambiguous (multiple distinct
  prior literals) or unknown projection_id ⇒ remove-only row obligation, no
  invented or ambiguous substitution; the deep guard keeps unchanged
  fail-closed semantics. Assertion obligations now describe exactly their
  replace/remove authority and never suggest splitting one assertion into
  multiple rows.
- `spec/src/stock_opportunity_agent/research/evolution_output_validation.md`:
  the exhausted-budget fallback may restore the exact prior literal of a
  uniquely anchored identity obligation (restored paths reported as
  normalized paths) and may remove explicitly authorized rows; everything
  else still declines.

Source (two files, no scope enlargement):

- `evolution_research_validation.py`: new
  `_raw_basic_literal_identity_issues(value, previous_state)` wired into the
  typed-issue aggregation (previous_state is already available on the reflect
  path). Codes: `basic_literal_identity_mismatch` (paths
  `supporting_evidence[i].exact_text`, repairs `replace`, repair_context
  `{projection_id, prior_exact_text}`), `basic_literal_identity_ambiguous`
  and `basic_ref_not_in_prior_state` (row path, repairs `remove`). Signal
  rows are outside the check. The two assertion messages dropped the "split"
  phrasing.
- `evolution_output_validation.py`
  (`_research_state_evidence_grounding_fallback`): per-obligation authority
  handling — identity-mismatch obligations restore `exact_text` from
  `prior_exact_text` byte-for-byte (reported in `normalized_paths`); the two
  remove-only codes remove the named row through the existing linked-claim
  cleanup; all pre-existing branches keep their remove gate. The deep
  tagged-ref guard, literal-evidence identity, PIT and numeric grounding,
  promotion rules, denominators, permissions, and retry budget are unchanged.

Tests (`tests/test_evolution_output_validation.py`, new class
`ReflectBasicLiteralIdentityTests`, 7 tests): paired
assertion+identity obligations in the initial `StructuredValidationError`;
compliant correction accepted through the production `_complete_parsed_role`
reflect flags with siblings byte-preserved; claim change alongside the
restored literal never survives (rejected or projection-discarded);
truly-new Basic ref remove-only and never surviving; ambiguous prior literal
allows removal but never launders a substitution (all surviving literals are
byte-exact prior literals); signal rows outside the identity check; fallback
restores the prior literal and removes the authorized assertion with the
event reporting both.

## 3. Exact replay (round-17/replay.py, production code only, no model calls)

- B1 original chain: raw95 through production `LLMResearchController.reflect`
  with the ORIGINAL request payload (prior state, evaluation context, skill,
  selection intents, canonical batch), then the original output96, then the
  identical output96 again (faithful cache-hit emulation). Initial feedback
  codes are exactly `['assertion_without_support',
  'basic_literal_identity_mismatch']` with paths
  `['supporting_evidence[6].exact_text']`, repairs `['replace']`, and the
  1718-char prior literal as candidate. 3 llm_calls, then the deterministic
  fallback restores the literal to the exact prior 1718 bytes
  (`normalized_paths=['supporting_evidence[6].exact_text']`) and removes only
  `current_beliefs[7]` (the unsupported assertion) plus
  `supporting_evidence[7]`/`current_beliefs[6]` under the claim_quantity
  obligation's own remove authority exposed on the retained projection (see
  limitations). Final state: 7 evidence rows == output96 rows 0–6 with the
  literal restored; 6 beliefs == output96 beliefs 0–5; needs/hypotheses/
  resolved/open/contradictions byte-equal to output96.
- B2 compliant chain: correction 1 restores the exact literal + removes the
  unsupported assertion; correction 2 answers the one claim_quantity
  obligation exposed on the retained projection by rewriting the liquidity
  claim onto the cited item's grounded value and copying it into the linked
  assertion (both explicitly authorized). Accepted in 3 llm_calls; 8 evidence
  rows / 7 beliefs, literal byte-exact, all other fields byte-equal to
  output95.
- B3 fail-closed fixtures: changed claim + restored literal → the rewrite is
  discarded, final claim byte-preserved; truly new Basic ref → evicted, the
  original row byte-preserved (or rejected); ambiguous prior →
  `basic_literal_identity_ambiguous` remove-only, substitution rejected;
  signal-claim tweak → identity flags only the Basic row.
- Output ends with `ALL ROUND-17 REPLAY CHECKS PASSED`; every role is a
  `ScriptedRoleCaller` (offline).

## 4. Exact commands and results (exit codes)

- focused: `PYTHONPATH=src …python3 -m unittest discover -s tests -p
  test_evolution_output_validation.py -v > …round-17/focused.log 2>&1` →
  exit 0, Ran 41 tests OK.
- full: `PYTHONPATH=src …python3 -m unittest discover -s tests -v >
  …round-17/full-tests.log 2>&1` → exit 0, Ran 906 tests OK (899 pre-existing
  + 7 new).
- lint: `sh scripts/lint_repo.sh > …round-17/lint.log 2>&1` → exit 0, "Lint
  result: PASS".
- replay: `PYTHONPATH=src …python3 .delegation/fast-slow-20260919/round-17/
  replay.py > …round-17/replay.log 2>&1` → exit 0.
- `git status --short` / `git diff --check`: changes limited to the allowed
  files; no whitespace errors; V117/V118/V119/V120 run dirs and prior-round
  audit files untouched.

## 5. Changed files

- `spec/src/stock_opportunity_agent/research/evolution_research_validation.md`
- `spec/src/stock_opportunity_agent/research/evolution_output_validation.md`
- `src/stock_opportunity_agent/research/evolution_research_validation.py`
- `src/stock_opportunity_agent/research/evolution_output_validation.py`
- `tests/test_evolution_output_validation.py`
- `progress/status.md`, `progress/changelog.md`
- `.delegation/fast-slow-20260919/round-17/{replay.py,replay.log,focused.log,
  full-tests.log,lint.log,report.md}`

No source outside the allowed scope; no retry-budget, company-specific
exception, permission widening, denominator, promotion-rule, or PIT change.

## 6. Acceptance mapping

- Raw95 initial feedback contains the accurate numeric assertion obligation
  AND the Basic ref identity defect (with exact prior literal) — verified in
  B1 against the original wire inputs.
- Corrected valid object accepted via the production parser with unchanged
  siblings byte-preserved — B2.
- Genuinely novel/ambiguous evidence rejected (or deterministically evicted,
  never surviving into the final state) — B3 and the unit regressions.
- No paid model call in the replay — ScriptedRoleCaller only.
- Existing 899 tests preserved (906 OK including the 7 new), focused/full/
  lint pass.
- Main joint goal still requires a fresh live successor after independent
  Codex acceptance of this round.

## 7. Limitations

- The canonical `exact_span`/interpretation grounding of the real batch is
  only partially visible in the model view. The replay reconstructs the batch
  from the stored `model_evidence_text` (raw XBRL values), which cannot
  ground the model's scaled liquidity wording ("$10.879M"/"$575.117M");
  therefore, after the identity/assertion repairs, production raises one
  additional `claim_quantity` obligation for that row (the real canonical
  batch may or may not raise it — the real run never reached the deep check).
  B1's final state accordingly also evicts that signal row and its linked
  belief under that obligation's own remove authority; B2 shows the fully
  compliant two-correction path. No fabricated equivalence is claimed.
- Correction-2's request in the replay differs from correction-1 (the
  retained projection changed the invalid output); the real run's byte
  identical cache hit is emulated by replaying the identical output96. Both
  behaviors are recorded, and the identity obligation stays present in the
  second feedback either way.
- The brief's "short progress report before implementation" was given
  in-conversation (diagnosis section above) rather than as a separate saved
  file, to stay within the turn budget; the diagnosis is fully reproducible
  from replay.py's section A.
- Per the round brief, no git checkpoint was created (commits explicitly
  forbidden for this round); the changed files above remain uncommitted for
  the independent review.
