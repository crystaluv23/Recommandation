# Next repair proposal: literal shared object versus retained facet

Read-only diagnosis. No product/spec/stage edits, no native replay, no model or
Signal calls. The completed routing result and its source oracle stay unchanged.
The observations below come from actual persisted input/raw/validation feedback,
not a new author response. Future controls below have not been executed.

## Actual failure and impact

The original `order_confirmation_disclosed:v3` row targets need index1 and
contains a legitimate split between a recent qualifying commitment and remaining
sales/economics/qualification/history questions. The native request explicitly
permits a shared research topic in `selection_reason`. It does not authorize a
claim that unavailable economic details were answered.

Target:

> What Ultra-High Protein sales volumes, realized premiums, incremental production costs, customer qualification progress and binding offtake commitments had been disclosed by prediction time, including any then-published milestones capable of changing earnings expectations within the forecast horizon?

Original reason:

> Check Ultra-High Protein binding offtake commitments for named counterparties or programs, delivery schedules and the existing $1M or 1000-unit materiality threshold.

Original residual:

> Using disclosures available by 2025-05-30, establish Ultra-High Protein sales volumes, realized premiums, incremental production costs, customer qualification progress, earnings-relevant milestones, and any still-effective commitments disclosed before the 180-day window.

The full parser produced exactly one ownership issue for this row:
`shared phrase 'ultra high protein'`, then instructed removal of all three
words as residual-only. The first-answer finance and liquidity rows were not
invalidated. Correction reservation54598 exceeded the native remaining18995,
so no second fresh answer was consumed; existing fallback changed only the
order row to context. Accepted finance partial and liquidity context persisted;
core truncated the batch to its first finance ref and stopped at executor entry
before preparation/calculation. The completed result is not a successful order
ownership verdict and must not be rewritten after a validator fix.

## Why the existing rule and checks missed this

`evolution_plan_roles.py:1530–1605` first evaluates coordinated temporal facets,
then calls `_shared_distinctive_phrase(reason, residual, target_need=target)`.
The helper's 2026-10-20 contrast splits on commas/semicolons. It does not split
this target's final `customer qualification progress and binding offtake
commitments` arm. That arm retains customer-qualification anchors, so it is not
recognized as an answered arm. Further, `commitments` intentionally remains in
the residual with an older-window qualifier. Thus the helper cannot establish
its existing answered/retained clause contrast and falls back to generic
three-word overlap. The product name alone meets that threshold. The emitted
instruction consequently calls a shared object a residual-only facet.

The old tests cover explicit question-clause contrasts, shared share-count
objects/years, literal cutoff clauses, unsplit conservative fallback, real
retained-facet overclaims and loss of one modifier. They do not cover a shared
multiword object prefix governing a comma-separated noun-facet list whose last
arm contains `and`, with the reason addressing that last arm and the residual
retaining the earlier arms. Their native green results established those listed
surfaces, not general semantic object/facet recognition. The one-modifier
counter is especially important: merely deleting `prospective`, substituting
`future`, or dropping another adjective must not erase the underlying retained
`net equity dilution` facet.

## Minimal candidate, with a conservative fallback

Keep the current public/private helper signature, normalization, whole-word and
calendar-bound rules. Extend only the helper's **positive literal-contrast
proof**, not a global overlap exemption or product-name recognizer:

1. Within an already explicit compound/list target, obtain bounded literal arms
   from the existing comma/semicolon split and a local coordinated arm only
   where both sides have independent multi-token facet anchors. Do not split
   arbitrary conjunctions globally (for example a one-token `research and
   development` expression is not automatically two facets). Preserve offsets
   or original arm text for diagnostics; do not rewrite the need.
2. Establish both an answered arm (its distinguishing literal anchors occur in
   the reason and were removed from the residual) and retained arms (their
   distinct literal anchors remain in the residual). Reuse the existing
   singularization and scope-word handling. A generic keyword, cardinality
   threshold, query term or Signal name alone cannot establish this split.
3. A shared ordered prefix in the first list arm can be a common object only
   when the two independently witnessed sides above also hold, the suffix of
   that first arm still identifies a retained facet, and the reason identifies
   a different answered arm. This permits object-prefix inheritance within
   that one proven list, without guessing proper nouns, brands or a domain
   vocabulary. It is not a rule to ignore every phrase present in the target.
4. Remove only that proven common object and genuine global scope from the
   retained-facet conflict comparison. Keep retained-specific anchors visible;
   a reason additionally claiming `sales volumes`, `realized premiums` or
   `customer qualification progress` must still fail. A shortened reason that
   repeats one retained-specific head such as `premiums` alongside the answered
   arm must not be rescued by the shared-object exception. An anchor shared by
   both arms (such as `commitments`) is not by itself a retained-only claim;
   preserve its explicit time/window qualifications and all existing temporal
   checks. If literal arm assignment/one-word provenance is ambiguous, retain
   conservative behavior rather than infer ownership.
5. If the positive proof is absent, use the current conservative overlap
   predicate unchanged. Keep indexed obligations, exact row/source refs,
   permitted paths, one-correction budget and context-only fallback unchanged.
   Do not auto-edit the reason, split a row, add a need or wrap an answer.

This is a proposal for a bounded proof extension, not an English grammar or a
claim of exhaustive NLP correctness. If the actual row cannot satisfy the
literal proof without a brand dictionary or approving a new claim, stop and
report that limitation rather than exempt it by identity. No canonical field,
Registry version, source qualification, measurement or research definition
needs to change.

## Frozen regression and counterexample plan

A future spec-first patch should own the opening “Routing residual facet
contrast” section of `evolution_research_validation.md`, this helper, and focused
routing tests. The role consumer need not change unless richer exact repair
context is genuinely required. Keep its prompt's existing shared-topic allowance.

- Freeze and replay the exact recorded raw portfolio through the native parser
  offline: original order reason/residual should remain partial; finance and
  liquidity siblings byte-identical; no invented full scope or resolved need.
- Independent synthetic multiword object variations (e.g. `High Density Cooling
  Modules`, `Advanced Ceramic Power Units`), punctuation/case/hyphen variants,
  prefix-scoped list with a final coordinated arm, and repeated-object explicit
  clauses. Expected safety rests on literal facet contrast, not those names.
- Genuine overclaim variants append retained `sales volumes and realized
  premiums`, `customer qualification progress`, and the shortened distinctive
  `premiums` head to the otherwise legal reason. All must receive the original
  indexed typed ownership error; unrepaired output still context-falls back.
- Existing exact 2026-10-20 reason variants, period-end/common-share overclaims,
  prospective→future/removed one-modifier negatives, whole-word/substrings,
  unsplit-target conservative control, timestamp/forecast preservation,
  cosmetic residual, wrong target/version and partial siblings all remain.
- A common object with no independently separated answered arm remains
  conservative. A different product, a generic source qualifier or a near-word
  is not a new ownership witness. Do not promote lexical contrast into proof of
  actual data availability or evidence that a Signal answered the need.

First run only the focused helper/native parser controls plus related routing
and typed-repair tests. A later bounded fresh stage, separately authorized and
frozen, is needed for new author behavior; replaying this completed raw alone
can prove the guard fix but cannot prove fresh obedience. Do not rerun the old
stage or its costly correct prefix merely to obtain an all-green result.

## Exact observed bindings

- `src/stock_opportunity_agent/research/evolution_plan_roles.py` — `29f1b3c057dc825ca77bed377a3f3be329c9eb6914ad5ad24774f88281d8aa07`
- `src/stock_opportunity_agent/research/evolution_research_validation.py` — `8a8b0e797bb3e66bddeb66f828db07c8e20b35f881a0a8ea2b5fafdf49faf55f`
- `tests/test_evolution_routing_plan_roles.py` — `689b5099ecf6e9b4396e19974c7bab327df30a8c3041fe390c154e9a15873c3c`
- `runs/diagnostics/gpre_native_routing_20261021_v1/stage/exchange/outbox/6dd836684a001330e31e78797bfbb439f2d751fc1aa79a6364224836029aabf8.txt` — `a388947bb9fbcabee75ee4445497a15545bf44649fc8fa4ce26e7554c794be91`
- `runs/diagnostics/gpre_native_routing_20261021_v1/stage/accepted-selection.json` — `6dc28a13a4811968dbfcf05954abd8c574a773a331586a865322e9c126ef9ab3`
- `runs/diagnostics/gpre_native_routing_20261021_v1/stage/completion.json` — `2c0c476a4ec7d46e05e0a17ec45463fbcf5e0cd62e876d725e01144a5aa31ad4`


## Actual pure-function reproduction (after the static diagnosis)

The saved `shared-product-predicate-probe.py` called the current helper exactly
once on the sealed original reason/residual and target. It did not invoke a
Controller, selector, Signal or native stage. `sys.settrace` only observed that
helper's return locals; it did not replace any predicate or parser.

- Actual return: `ultra high protein`.
- Literal clauses: 5; answered arms: 0; retained arms: 5.
- The compound `customer qualification progress and binding offtake commitments`
  remained one clause. Its unique-topic set intersects the residual through
  customer/qualification/progress and commitment. All 5 topical clauses
  consequently fell into retained, leaving no answered witness. The safe
  contrast condition failed and the conservative three-word fallback matched
  the product object. This confirms the mechanism, not just its error text.
- Completed stage 19 file hashes/membership and helper source bytes were
  equal before/after this read-only predicate probe.
- Result SHA: `5feeb113938e4279d46b511ad4c72d13f690c2701ed9f124cfceb0a819c3d278`.

The whole recorded portfolio remains **strict0/1**: the already accepted core
first-finance entry is not evidence that order ownership or the full portfolio
passed. The future test plan above remains unexecuted and is not fresh author
behavior.
