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

## End-to-End Experiment Workflow

The information-plan loop follows this order:

1. Freeze a versioned development outcome definition, surge-inflection rule,
   control pseudo-anchor rule, control-matching policy, and symbol-level
   refinement/development/untouched-holdout split. Outcome labels, inflection
   dates, and packet as-of cutoffs are distinct records.
2. Define versioned information requirements before choosing provider APIs.
   Map each requirement to preferred and fallback point-in-time sources, while
   preserving `other_or_unclassified` evidence so the initial ontology can
   expand.
3. Acquire and freeze the full source archive for each approved pre-inflection
   window. Retrieval and content-readiness state are audited before extraction.
4. On refinement symbols only, compare winner, control, and failure evidence
   across windows to propose measurable signals and analysis rubrics. A useful
   instruction is not a signal until it has source-linked facts and a repeatable
   observation or calculation.
5. Preserve source facts, then derive auditable working features such as event
   status, event age, event amount versus reported revenue or as-of market cap,
   expectation-evidence timelines, and industry-demand-to-company pull-through.
   Every calculation names its input fact ids and formula; derived values never
   replace the source archive.
6. Render a minimally processed raw arm and an organized arm from the same
   anonymous source pool, cutoff, context budget, model, prompt rubric, and
   output schema. The prompt specifies how to reason but cannot substitute for
   absent facts.
7. Run no-web plain-LLM development validation, reveal labels only after outputs
   are frozen, and attribute errors to acquisition, extraction, signal,
   representation, analysis, or irreducible point-in-time support. Feedback may
   produce at most one or two bounded proposals; a used holdout becomes
   refinement data.
8. Evaluate the frozen final proposal once on new untouched companies. Persist
   all artifacts and meta-experience, but keep schemes and signals proposal-only
   until human review.

The bounded development benchmark contains exactly six blind companies.
Winner/control composition is drawn once from a recorded random seed with at
least one company from each label, then exact case ids, labels, and as-of dates
are frozen in a replayable selection manifest. Refinement cases are separate.
Every acquisition or representation iteration reuses the same six cases; only
versioned source manifests, extraction, and packet rendering may change. The
current-source raw/organized pair and candidate-source raw/organized pair form
a paired 2x2 comparison. Repeated use makes these six companies development
data, never the final untouched holdout.

The WOLF/EXC comparison is a development diagnostic that inherits the existing
frozen historical labels and as-of dates. It does not approve the default
180-calendar-day terminal-return rule as the production definition. Before the
one-shot untouched holdout, the project must separately approve the winner
threshold, whether maximum or terminal return defines a surge, the deterministic
inflection rule, and the control pseudo-anchor/matching contract.

## External Interface

The submodule should expose:

- `InformationRequirement`: one versioned evidence need with a family, source
  preferences, extraction contract, and analysis rubric.
- `RequirementCoverageState` and `RequirementCoverageEntry`: explicit per-case
  states that distinguish confirmed, contradicted, not applicable, not found,
  source unavailable, not fetched, extraction failed, and ambiguous.
- `AtomicEvidence`: a source-linked fact carrying entity role, event type,
  status/negation, amount/unit/period, dates, and supporting source span. A
  deterministic derived fact additionally carries input fact ids and its
  calculation.
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
Provider ticker-news results must also demonstrate issuer relevance; industry
articles about another named company cannot inherit the queried ticker as their
subject. Action terms use token or phrase boundaries, so words such as
`designed` cannot satisfy a `signed` contract rule.

The initial implementation may be conservative and return `ambiguous` or
`not_found`. It must not convert generic risk-factor, boilerplate, index-removal,
or document-wide co-occurrence into positive orders, financing, transactions,
or AI-chain pull-through.

One source span may support more than one requirement when the semantics are
independently present. For example, a signed AI customer agreement may yield an
orders/contracts fact, a customer-adoption fact, and a theme-transmission fact,
all linked to the same span. Extraction must preserve those labels instead of
forcing a lossy single-family choice. This does not permit document-wide joins:
the theme and the qualifying commercial or operating action must occur in one
sentence or a strictly adjacent two-sentence local span.

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
For paired baseline-versus-candidate runs, an unchanged packet hash must reuse
the same cached model response. The run must record model and sampling settings;
otherwise response drift on identical packets is model noise, not acquisition
or organization lift.

Information-family experiments use actual source-backed facts. Ablation removes
one family from an otherwise fixed organized packet. Add-back is valid only
when the baseline omitted available facts from that family; an instruction that
the family would be useful is not evidence and cannot count as add-back.
Add-back reports the delta between a fixed core-only baseline and that same
baseline plus one family. Ablation reports the delta between the full organized
baseline and that same packet with one family removed. The baseline metrics and
deltas must be persisted so a family-only score is never mistaken for marginal
contribution. Every raw, organized, add-back, and ablation evaluation persists
`TP`, `FP`, `TN`, and `FN` counts plus precision, recall, specificity, and
accuracy under the unchanged positive threshold (`likely` or `possible` with
confidence at least 0.45). Organized-minus-raw artifacts include both rate and
confusion-count deltas.

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
- Diagnose an extraction failure only from sentence-scoped, action-qualified
  candidate evidence. Bare words such as `contract`, `customer`, `FDA`, or `AI`
  elsewhere in a document are not enough. Invitations, proposals, intended
  submissions, and plans to seek approval remain `not_found` until a source
  reports an actual qualifying event or status.
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
- Keep deterministic derived features traceable to source fact ids and never
  use outcome labels in their calculations.
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

The Ralph experiment entry point may augment only the selected development
symbols with bounded Alpha Vantage historical company news. The request sends a
public ticker and historical date range, not case labels or research packets.
Returned provider summaries remain explicitly `summary_only`, preserve their
publication date and URL in the retrospective source archive, and pass through
the same as-of, content-readiness, masking, and leakage checks as every other
source.

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

The July 24 frozen six-case plain-LLM comparison is the latest completed
development result. Current-source v36 raw produced `TP=0`, `FP=1`, `TN=2`,
`FN=3`; organization removed the false positive but left `TP=0`, `TN=3`, and
`FN=3`. Filing-date-bounded SEC Company Facts v38 added 57 atomic facts across
five holdouts, including revenue, cash, debt, operating cash flow, and capex,
but produced the same raw and organized confusion matrices. The candidate
organized confidence gap improved only from -0.1033 to -0.0867, while
positive-confidence gap remained 0.0 and recall remained 0.0.

The v38 diagnosis is that static financial denominators improve risk and
materiality interpretation but do not recover the missing winner-side causal
events. The next proposal should target binding orders/backlog/customer wins,
transaction or restructuring status, financing and listing-compliance actions,
identity-safe business and industry-chain transmission, and fresh
guidance/estimate changes. Identical SRM packet hashes yielded raw confidence
0.40 and 0.38 in separate calls, so future paired comparisons must share the
packet-and-model-settings response cache and treat small single-call confidence
changes as sampling noise. The experiment runner now defaults paired blind
evaluation to temperature 0.0 and records provider, model, temperature, and
context budget in its manifest. These six companies are consumed development
data; no effectiveness or Phase-1 exit claim is available without a later
untouched company holdout.
