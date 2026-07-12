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
