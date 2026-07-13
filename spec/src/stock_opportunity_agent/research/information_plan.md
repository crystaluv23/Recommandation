# Research Information Plan

## Status
Started

## Purpose

Own the broad Ralph information-plan research contract before analysis-method
experiments. This submodule discovers what information a stock study needs,
maps requirements to point-in-time sources, extracts source-linked atomic facts,
builds fair raw-versus-organized blind comparison arms, evaluates information-
family variants, and attributes failures to the layer that should change.

It does not replace the packet-level `InformationScheme` in `ralph_loop.py`.
That record still owns section order, token budgets, compression, and blind
prompt structure. The information plan composes requirements, source coverage,
atomic facts, packet variants, and evaluation results around that scheme.

## External Interface

The submodule should expose:

- `InformationRequirement`: one versioned evidence need with a family, source
  preferences, extraction contract, and analysis rubric.
- `RequirementCoverageState` and `RequirementCoverageEntry`: explicit per-case
  states that distinguish confirmed, contradicted, not applicable, not found,
  source unavailable, not fetched, extraction failed, and ambiguous.
- `AtomicEvidence`: a source-linked fact carrying entity role, event type,
  status/negation, amount/unit/period, dates, and supporting source span.
- `DocumentContentAudit`: point-in-time source-body state, size, content hash,
  and reasons distinguishing usable, summary-only, likely truncated,
  metadata-only, and unusable documents.
- `ResearchInformationPlan`: proposal-only requirement inventory plus its
  source, extraction, and packet-scheme references.
- `InformationPlanExperimentResult`: raw and organized packets, analyses,
  evaluations, information-family experiments, and layered failure attribution.
- deterministic builders and artifact writers for the required information-plan
  JSON outputs.

## Discovery Contract

Requirement discovery is retrospective and label-aware. It may compare
winner/control/failure cases across approved point-in-time windows, but it must
use only refinement symbols when proposing requirements. It keeps a stable core
inventory and an `other_or_unclassified` route for source-backed facts outside
the current ontology. Outcome labels may affect proposal statistics but never
atomic extraction or blind packet contents.

## Atomic Evidence Contract

Keyword presence is candidate retrieval, not fact confirmation. A confirmed
fact requires a source reference and supporting span with enough local context
to identify the event or measurement. Event extraction must prioritize specific
form/item and action semantics, handle negation and proposed/closed/terminated
states, keep issuer/target/counterparty roles distinct, preserve amount units and
periods, and deduplicate repeated representations of the same source fact.

The initial implementation may be conservative and return `ambiguous` or
`not_found`. It must not convert generic risk-factor, boilerplate, index-removal,
or document-wide co-occurrence into positive orders, financing, transactions,
or AI-chain pull-through.

## Comparison Contract

Raw and organized blind arms must use the same cases, source evidence, as-of
cutoff, model/researcher, output schema, and documented context budget. Raw
packets apply only deterministic cleaning, masking, ordering, and truncation.
Their chunks are selected round-robin across the audited source documents so a
single long filing cannot consume the whole raw arm. This is source-coverage
balancing, not semantic ranking. Historical names, acquired-company names,
exchange-qualified ticker aliases, and other source-derived organization
identities must be included in both masking and leakage preflight.
Organized packets render source-linked atomic facts and compact structured
features through the active `InformationScheme`. Neither arm receives labels,
future outcomes, source URLs, ticker/company identity, or web tools.

Information-family experiments use actual source-backed facts. Ablation removes
one family from an otherwise fixed organized packet. Add-back is valid only
when the baseline omitted available facts from that family; an instruction that
the family would be useful is not evidence and cannot count as add-back.
Add-back reports the delta between a fixed core-only baseline and that same
baseline plus one family. Ablation reports the delta between the full organized
baseline and that same packet with one family removed. The baseline metrics and
deltas must be persisted so a family-only score is never mistaken for marginal
contribution.

Heuristic evaluation is a pipeline diagnostic because raw and organized
representations may require different deterministic parsing rules. Its
artifacts must set `effectiveness_claim_allowed=false`. Only an anonymous
plain-LLM run on a declared untouched-company holdout may support an
effectiveness or Phase-1 exit claim.

## Failure Attribution

Each failed blind case may link multiple causes but must identify one primary
layer:

- `source_unavailable`
- `acquisition_miss`
- `extraction_error`
- `signal_error`
- `representation_loss`
- `analysis_error`
- `not_predictably_supported_as_of`

Attribution uses coverage state, raw-versus-organized disagreement, missing
context, atomic-fact presence, and variant results. It remains retrospective and
proposal-only.

## Artifacts

- `research_information_plan.json`
- `information_requirements.json`
- `evidence_coverage_ledger.json`
- `atomic_evidence_by_case.json`
- `point_in_time_source_documents.json`
- `document_content_audit.json`
- `raw_source_blind_packets.json`
- `raw_vs_organized_evaluation.json`
- `information_family_experiments.json`
- `layered_failure_attribution.json`

Artifacts that contain case ids, labels, or source ids must be marked
`retrospective_label_aware`. Exported blind packet payloads must remain anonymous
and contain no source URLs. The repository has no human-curated gold packet;
none of these artifacts may be called gold.

## Dependencies

- Consumes `HistoricalCase`, `ResearchPacket`, and source-linked evidence.
- Reuses `InformationScheme`, `BlindSchemePacket`, `RalphBlindResearcher`, and
  `SchemeEvaluation` from `research/ralph_loop`.
- Feeds Ralph experiment manifests and later meta-learning analysis-method
  comparisons.

## Invariants

- Preserve point-in-time availability and full source provenance.
- Preserve full fetched filing/transcript bodies in the retrospective audit
  layer while keeping blind packet excerpts bounded and identity-safe.
- Treat accounting policies, statutory thresholds, generic prospectus terms,
  and hypothetical risk language as non-events. Capital and operating facts
  must describe an actual issuer state or transaction, not merely contain a
  financial keyword and an unrelated number.
- Balance each organized section across its represented information families
  before filling remaining slots; repeated table rows from one family must not
  displace a distinct deal, liquidity, catalyst, or risk fact.
- Keep outcome labels out of extraction and blind packet rendering.
- Keep requirement discovery, evidence extraction, signals, rubrics, packet
  rendering, and prompt text as separate records or stages.
- Preserve the frozen v27 baseline; new artifacts are side-by-side proposals.
- A holdout used to produce a proposal is not independent validation for that
  proposal.
- Keep the selected information plan proposal-only pending human review.

## Testing

Tests should cover requirement discovery without holdout labels, all coverage
states, conservative event extraction, negation, entity roles, amount/unit/date
preservation, source-span traceability, deduplication, identity masking,
raw/organized source parity, family ablation/add-back semantics, failure
attribution, source-body completeness, heuristic effectiveness guards, artifact
paths, and manifest integration.

## Current Implementation State

The deterministic foundation is implemented in
`research/information_plan.py` and wired into
`scripts/run_ralph_loop_experiment.py` as the default experiment kind. It now
produces the requirement inventory, coverage ledger, atomic evidence, shared-
source raw and organized packets, family variants, failure attribution, and
standard Ralph manifests. Raw and organized arms share one context-budget
ceiling and one audited point-in-time source pool; organized facts may use only
sources in that pool.

The July 12 v5 local preflight correctly stopped because legacy saved filing
bodies were truncated before substantive text. The July 13 v11 SEC
reconstruction removed that acquisition blocker for the bounded development
pair, and v19 froze the cleaned preflight after conservative extraction and
packet revisions. Its strict checks passed with 23 audited sources: 16 usable
full bodies, seven explicitly summary-only records, and no truncated,
metadata-only, or unusable target-fact source. Raw packet chunks are now
round-robin across all 12 winner and 11 control source documents, while every
organized arm and family variant uses the same source-derived alias set. The
expanded leakage scan passes.

The v22 local heuristic diagnostic is the latest completed evaluator run. Its
organized positive-confidence gap was 0.19 versus 0.00 for raw, but both winner
and control were labeled `possible`, producing FP 1.00 and FN 0.00. This is
pipeline evidence only: the raw and organized heuristic parsers are different,
and the rules react to section counts rather than perform the fixed plain-LLM
analysis. Deal status/timing, capital/liquidity, and expectation gap have
source-backed development facts; orders/contracts, customer/capacity,
policy/regulatory, and theme/industry transmission remain at zero. The bounded
plain-LLM raw-versus-organized development run was not sent to OpenRouter
because external transmission of the anonymous project packets still requires
explicit informed authorization. No effectiveness or Phase-1 exit claim is
available, and a later one-shot claim still requires new untouched companies.
