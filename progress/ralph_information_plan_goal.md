# Ralph Information-Plan Goal

Use this as the next bounded Ralph Loop objective.

```text
/goal

Objective

Repair the evidence-acquisition, extraction, and representation failures exposed
by the July 7 v27 Ralph experiment, then identify the best validated and useful
research information plan among the tested point-in-time sources, context
budgets, and packet schemes for a fixed blind plain-LLM baseline. Do not begin
multi-agent analysis until the information-plan exit gate passes.

Current baseline

- Freeze `ralph-loop-openrouter-rich-2026-07-07-12sym-sec-augment-live-v27` as
  the failed baseline; preserve its packets, scheme, metrics, and error analysis.
- The baseline passed anonymous preflight but ended `holdout_not_separated` with
  positive-confidence gap 0.0, raw confidence gap 0.075, FP 0.0, and FN 1.0.
- Treat the main unresolved problems as evidence coverage and extraction
  quality, not prompt order alone: document-wide keyword false positives,
  incorrect event family or polarity, mixed entity roles, missing amount/unit/
  status/timing, repeated digests that create false corroboration, and missing
  deal, capital, order, customer, theme-transmission, and expectation-gap facts.
- The repository has no human-curated gold packet. Do not invent one, call an
  automatic packet gold, or make success depend on a gold-packet upper bound.

Required work

1. Discover and version information requirements from label-aware comparisons
   of winner, control, and failure cases across approved point-in-time windows.
   Preserve an `other_or_unclassified` path so the current ontology does not
   prevent discovery of new information families.
2. Map each requirement to preferred/fallback point-in-time sources and record
   `confirmed`, `contradicted`, `not_applicable`, `not_found`,
   `source_unavailable`, `not_fetched`, `extraction_failed`, or `ambiguous` in a
   requirement-level coverage ledger. Propose a new API only when this ledger
   demonstrates a real source gap.
3. Extract source-linked atomic facts with subject/entity role, event type,
   status and negation, amount and unit, period, event/publication dates,
   source reference, and supporting span. Keyword presence alone must not
   confirm orders, contracts, customers, financing, transactions, catalysts,
   or industry-chain transmission. Deduplicate repeated facts across sections.
4. Keep information requirements, atomic evidence, signals, analysis rubrics,
   packet rendering, and prompt wording separate. Preserve raw sources as the
   audit layer and make every organized factual claim traceable.
5. Build fair blind comparison arms from the same anonymous as-of source bundle:
   minimally processed raw-source context versus the organized information-plan
   packet. Hold model, output schema, source set, cutoff, and documented context
   budget constant; fix any deterministic chunk-selection rule before outcomes
   are read.
6. Run targeted add-back and ablation experiments for deal status/timing,
   capital structure/liquidity, orders/contracts, customer/capacity,
   policy/regulatory evidence, theme/industry transmission, and expectation
   gap. Add actual source-backed facts, not instructions saying those facts
   would be useful.
7. Attribute every blind error primarily to `source_unavailable`,
   `acquisition_miss`, `extraction_error`, `signal_error`,
   `representation_loss`, `analysis_error`, or
   `not_predictably_supported_as_of`, and route the next proposal to that layer.
8. Refine on labeled development cases only. After one or two bounded
   iterations, validate the final proposal once on a new untouched company
   holdout. A holdout used for feedback is no longer independent evidence.

Required artifacts

- `research_information_plan.json`
- `information_requirements.json`
- `evidence_coverage_ledger.json`
- `atomic_evidence_by_case.json`
- `raw_source_blind_packets.json`
- `raw_vs_organized_evaluation.json`
- `information_family_experiments.json`
- `layered_failure_attribution.json`
- existing Ralph scheme, packet, leakage, evaluation, and manifest artifacts
  retained side by side with the baseline

Success and stop conditions

- Anonymous, point-in-time, no-web blind invariants pass with no unresolved
  critical identity leak, cross-case contamination, or subject misattribution.
- Requirement coverage and missing reasons are auditable, and organized claims
  remain source-traceable.
- The organized plan is fairly compared with the raw-source baseline using
  positive-confidence separation plus FP/FN, judgment distribution, and
  explicit error analysis. It either produces useful, repeatable fresh-holdout
  separation or reaches a stable representation plateau where residual failures
  are attributable to analysis or irreducible as-of predictability rather than
  missing information.
- Add-back and ablation results no longer expose a material repeatable missing
  information family or representation loss on fresh holdouts.
- Remaining errors are predominantly analysis-method or irreducible as-of
  predictability errors rather than acquisition, extraction, signal, or packet
  failures.
- Stop after the bounded iterations and return the best validated proposal plus
  unresolved risks. Keep it proposal-only pending human review. Describe it as
  best among the tested sources, budgets, and schemes, never as a universal
  optimum.

Only after these conditions are satisfied should the next project phase compare
the fixed plain-LLM baseline with multi-agent, specialist, debate, or skeptic
analysis using exactly the same validated information plan.
```

## Execution Checkpoint - 2026-07-12

- Implemented the deterministic information-plan foundation and all required
  artifact contracts; it remains proposal-only and does not assume a gold
  packet.
- Added same-source-pool raw/organized packet preparation, shared documented
  context budgets, conservative source-linked atomic facts, requirement-level
  coverage states, source-backed family variants, and layered failure routing.
- The v5 local preflight passed anonymous leakage and packet-budget checks but
  reported `blind_execution_ready=false`: zero requested target families had a
  source-backed fact on the selected holdout.
- Inspection attributes the immediate failure to acquisition/content
  completeness. Saved SEC bodies frequently stop in inline-XBRL/header content
  before substantive filing text, so a plain-LLM comparison would not test the
  information representation hypothesis.
- A live SEC-submissions augmentation attempt could not run because the
  workspace approval service reported that credits were exhausted. No network
  workaround was attempted; the local readiness failure remains the latest
  valid result.
- Next bounded action: obtain complete point-in-time filing/news bodies, rerun
  coverage and atomic extraction, then spend blind-LLM budget only after at
  least one requested family has real holdout facts. After refinement, reserve
  a new untouched company holdout for the one-shot exit-gate validation.
- The objective remains active. The information-plan exit gate has not passed,
  and multi-agent analysis must not begin yet.
- A source-rich local development diagnostic (v6) exercised the complete
  evaluator with a deterministic heuristic researcher. On two deliberately
  selected cases, organized packets moved positive-confidence gap from 0.00 to
  0.77 and false-negative rate from 1.00 to 0.00 with FP 0.00. This is pipeline
  feasibility evidence only, not a plain-LLM result or fresh-holdout claim.
  Orders/contracts, customer/capacity, policy/regulatory, and theme/industry
  transmission still had zero source-backed facts in that diagnostic.

## Execution Checkpoint - 2026-07-13

- Repaired acquisition-layer information loss: fetched filing and transcript
  bodies are now archived in full with explicit complete, summary-only,
  metadata-only, or unknown scope. Packet excerpts remain derived and bounded;
  they no longer replace the retrospective source archive.
- Added document-content audit/readiness artifacts and made a plain-LLM run
  fail closed on truncated, metadata-only, unusable, or critically unsupported
  target-family evidence. The reusable v11 SEC reconstruction produced the
  first source-complete bounded development pool.
- Corrected experiment semantics. Add-back now compares a fixed core baseline
  with core plus exactly one family; ablation compares the full organized plan
  with full minus one family. Every result persists its baseline and delta.
  Heuristic runs are permanently marked `pipeline_diagnostic_only` and cannot
  make effectiveness claims.
- Tightened source-linked extraction against registration, accounting,
  prospectus, award, credit, tariff, hypothetical customer/capacity, and other
  keyword false positives. Added explicit event-date parsing, semantic
  deduplication, family-balanced section selection, and actual-state tests for
  capital and operating facts.
- Made the raw comparison arm cover source documents round-robin under the
  shared budget instead of allowing one long filing to consume the context.
  Expanded identity masking and leakage preflight to historical names,
  acquired-company names, related organizations, and exchange-qualified ticker
  aliases; all organized family variants now reuse the same full-source alias
  inventory.
- Frozen development preflight v19 passes strict leakage and content readiness:
  23 audited holdout sources, 16 usable full bodies, seven summary-only, and no
  truncated, metadata-only, or unusable target-fact sources. Raw packets cover
  all 12 winner and 11 control source documents.
- Latest local evaluator v22 is diagnostic only. Organized positive-confidence
  gap is 0.19 versus raw 0.00, but winner and control are both `possible`, so FP
  is 1.00 and FN is 0.00. This supersedes v6 as the current heuristic result and
  confirms that rules-based section counting cannot establish plan efficacy.
- Only deal status/timing, capital structure/liquidity, and expectation gap have
  source-backed facts in this development pair. Orders/contracts,
  customer/capacity, policy/regulatory, and theme/industry transmission still
  have zero facts and need requirement-driven acquisition on suitable cases.
- A four-call plain-LLM raw-versus-organized development diagnostic was prepared
  but not sent to OpenRouter because external transmission of anonymous project
  research packets requires explicit informed user authorization. No workaround
  was attempted.
- At this checkpoint the objective remained active and the frozen v19 arms were
  the planned authorized comparison. The v25-v27 checkpoint below supersedes
  that next action. Multi-agent work remains gated.

## Execution Checkpoint - 2026-07-13 v25-v27

- Audited all 300 formal historical cases and 547 saved documents with the
  action-qualified coverage ledger. The revised extractor recovered two SRM
  winner customer-demand windows, four HUBC failure contract windows, six total
  customer/capacity windows, and one HUBC theme-transmission window. Earlier
  ADTX/KNW `extraction_failed` states disappeared because proposal invitations
  and planned regulatory submissions are correctly `not_found`.
- Replaced the lossy single-family span classifier with traceable multi-family
  facts, while limiting theme joins to one sentence or a strictly adjacent
  two-sentence context. Added issuer relevance for provider ticker news and
  exact phrase boundaries so third-party stories and `designed`/`signed`
  substring collisions do not become issuer contracts.
- Added bounded Alpha Vantage historical company-news augmentation for selected
  development symbols. Requests contain only public tickers and historical date
  ranges; provider summaries remain `summary_only`. Added source-URL
  deduplication and reused SEC submissions augmentation for complete filings.
- v25 is the current source-complete preflight for WOLF winner versus EXC
  control. It passes leakage and content readiness on 111 sources: 16 usable
  full bodies, 94 summary-only, one metadata-only, and no critical issue. Five
  families are packet-ready. WOLF has source-backed federal defense contract,
  CHIPS funding-status, fab expansion, utilization, and supply-agreement facts;
  theme/industry transmission remains absent for this pair.
- v27 is the final local heuristic diagnostic for this development revision.
  Raw positive-confidence gap is 0.00; organized gap is -0.05 with FP 1.00 and
  FN 0.00. Contract add-back is +0.11, customer/capacity and policy are 0.00,
  and expectation-gap add-back is -0.11 because EXC also has genuine positive
  estimate evidence. This confirms the rule-based evaluator cannot interpret
  status, baseline, or discriminative direction and must not guide more prompt
  or extraction tuning.
- The objective remains active. No project packet was sent externally. After
  explicit informed authorization, run exactly four fixed plain-LLM calls on
  the v25 anonymous WOLF/EXC raw and organized packets. Then route at most one
  bounded proposal from that result and reserve new companies for the one-shot
  untouched holdout. Multi-agent work remains gated.

## Execution Checkpoint - 2026-07-19 v31 and Next Bounded Loop

- The fixed four-call plain-LLM comparison completed on WOLF winner versus EXC
  control. Both raw and organized arms returned `insufficient_information` for
  both cases. Raw winner/control confidence was 0.38/0.34; organized was
  0.34/0.34. Both positive-confidence gaps were 0.0, with organized FP 0.0 and
  FN 1.0.
- Organization improved the specificity of missing-context feedback but did
  not improve discrimination. The winner still lacked current cash/covenant
  compliance, debt/liquidity runway, binding CHIPS funding status,
  backlog/order/customer qualification, fab utilization/margin conversion,
  and fresh expectation revisions.
- Start one bounded acquisition/extraction proposal without changing prompt
  weighting: add filing-date-bounded SEC Company Facts and selected historical
  SEC/Alpha Vantage evidence for the development benchmark.
- Create exactly six blind development cases. Draw the winner/control ratio
  once from a recorded seed with at least one of each label, then freeze exact
  case ids, labels, and as-of dates in `case_selection_label_aware.json`.
  Refinement cases are separate.
- First run current-source raw/organized on that frozen benchmark. Then run the
  enriched-source raw/organized pair on the same manifest. Compare acquisition
  lift, organization lift, and end-to-end lift case by case. These six cases
  become consumed development data; a separate untouched holdout is still
  required for the exit gate.

## Execution Checkpoint - 2026-07-22 v35-v37

- Froze the six-case development benchmark from seed `20260719`: SRM, WW, and
  QMMM are winners; BPRN, WRB, and VTR are controls. TRON and CHCO remain
  separate refinement cases. Future development iterations replay the exact
  manifest rather than resampling.
- Added first-class confusion-matrix reporting (`TP`, `FP`, `TN`, `FN`) plus
  precision, recall, specificity, and accuracy without changing the positive
  threshold. Raw-to-organized comparisons now persist count and rate deltas.
- Current-source v35 preflight passes: 144 audited point-in-time documents, 32
  usable full bodies, 112 summary-only sources, no unusable sources, all six
  holdouts covered, 12 blind requests prepared, and zero leakage findings.
- SEC Company Facts v37 preflight also passes on the same cases and documents.
  Filing-date-bounded XBRL added 57 atomic facts across five holdout cases,
  including revenue, cash, debt, operating cash flow, and capex. SRM has no CIK
  in the current mapping and remains an explicit acquisition miss.
- The current-source and enriched-source OpenRouter comparisons remain pending.
  The tenant safety policy blocked the first 12-call attempt because sending
  anonymous project research packets to a third party requires renewed,
  informed user authorization. No provider response or confusion matrix has
  been fabricated or replaced by heuristic output.

## Execution Checkpoint - 2026-07-24 v36-v38

- Completed all 24 explicitly authorized OpenRouter calls on the frozen
  six-case development manifest. Both runs passed leakage and content
  readiness, and both produced 12 cached responses.
- Current-source v36 raw results were `TP=0`, `FP=1`, `TN=2`, `FN=3`
  (accuracy 0.3333, recall 0.0, specificity 0.6667, positive-confidence gap
  -0.1567). Organized results were `TP=0`, `FP=0`, `TN=3`, `FN=3`
  (accuracy 0.5, recall 0.0, specificity 1.0, positive-confidence gap 0.0).
  Organization removed the VTR false positive but recovered no winner.
- SEC Company Facts v38 produced exactly the same raw and organized confusion
  matrices. Candidate organized winner/control average confidence was
  0.22/0.3067 versus 0.20/0.3033 for v36, moving the raw confidence gap from
  -0.1033 to -0.0867 but leaving positive-confidence gap, TP, and FN unchanged.
  This small confidence movement is not effectiveness evidence.
- The XBRL proposal supplied useful materiality and solvency denominators but
  did not supply the missing discriminative events. SRM still has no CIK and
  lacks revenue scale, orders/backlog, customer pull-through, financing, and
  listing-compliance resolution. WW's added cash, debt, and negative-equity
  facts reinforced distress without establishing a restructuring or operating
  catalyst. QMMM's small revenue, low cash, and negative operating cash flow
  clarified risk but did not establish orders, customers, theme transmission,
  or a fresh expectation gap.
- Static Company Facts should not receive another immediate add-more-fields
  iteration. The next bounded acquisition proposal should target point-in-time
  event evidence: binding orders/backlog/customer wins, transaction or
  restructuring status, financing and listing-compliance actions, identity-safe
  business and industry-chain transmission, and fresh guidance/estimate changes.
- The same SRM packet produced raw confidence 0.40 in v36 and 0.38 in v38 under
  the current OpenRouter temperature. The runner now defaults future paired
  blind tests to temperature 0.0, keys caches by packet plus model settings,
  records those settings in manifests, and can reuse one shared cache so an
  unchanged packet does not create false information lift.
- The objective remains active. The six companies are consumed development
  data, the information-plan exit gate has not passed, and multi-agent analysis
  remains gated pending a materially better development result followed by a
  separate untouched-company holdout.
