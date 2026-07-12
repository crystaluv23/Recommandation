# Research Evidence Acquisition

## Status
Started

## Purpose

Collect source-linked company evidence, fundamentals context, catalysts, theme
context, and public research summaries before formal cold-start packet assembly,
then assess whether each built packet has enough context to be useful for
learning.

This submodule is part of retrospective setup, not blind assessment. It uses
known provider APIs first (SEC, Alpha Vantage, Finnhub). Optional web-search
context remains a bounded, explicit enhancement, but it is not the default
evidence path.

## External Interface

The implementation exposes:

- `EvidenceAcquisitionRequest`: symbol, company name, inflection date, packet
  as-of dates, priority themes, existing document titles, and existing feature
  names for one candidate.
- `EvidenceAcquisitionResult`: source-linked `DocumentRecord` values,
  `Catalyst` values, web queries, and warnings.
- `OpenAIWebEvidenceResearcher`: OpenRouter/OpenAI web-search researcher for
  explicit opt-in pre-packet context acquisition.
- `build_web_context_queries()`: deterministic query construction from company,
  sector, industry, priority themes, and the inflection cutoff.
- `ContextCoverageReport` and `apply_context_coverage_gate()`: bucket-level
  packet coverage assessment and optional exclusion of thin packets.

## Coverage Buckets

Each built packet is assessed across these buckets:

- company evidence,
- financial or valuation context,
- theme context,
- catalyst or event context,
- contrary or risk context.

`company evidence`, `financial or valuation context`, and `theme context` must
be present, and at least one of `catalyst or event context` or `contrary or
risk context` must be present for `sufficient_context=true`. `warn` mode
records the report and keeps the packet available for compatibility. `enforce`
mode excludes insufficient packets from blind LLM analysis and signal learning
while keeping the full packet audit artifact.

Bucket presence is only a coarse compatibility check. The next Ralph
information-plan iteration must add requirement-level coverage with explicit
states such as `confirmed`, `contradicted`, `not_applicable`, `not_found`,
`source_unavailable`, `not_fetched`, `extraction_failed`, and `ambiguous`.
Keyword presence alone must not count as confirmed evidence of an order,
contract, customer, financing, strategic transaction, industry-chain
transmission, or catalyst.

Acquisition should become gap-driven. Each information requirement should map
to preferred and fallback sources, point-in-time constraints, retrieval status,
and an extraction contract. A missing deal-status field may trigger SEC
registration, proxy, transaction, and exhibit retrieval; missing capital or
liquidity detail may trigger filings, XBRL, credit agreements, and prospectus
evidence; missing customer or order detail may trigger earnings releases,
transcripts, investor presentations, news, or counterparty evidence. A new paid
API should be proposed only after the coverage ledger shows that the fact is not
available from already-supported sources or public point-in-time documents.

Provider company-profile APIs may contribute stale `profile.sector` and
`profile.industry` features plus a short `THEME_CONTEXT` document. These fields
are industry-chain context only; they must not be treated as point-in-time
valuation, catalyst, or outcome evidence.

Provider topic-news APIs may contribute additional `THEME_CONTEXT` documents for
industry themes such as technology, manufacturing, energy, finance, and life
sciences. Their `time_to` cutoff must be the latest packet as-of date, not the
inflection date, so theme context is actually visible to blind packets.

The catalyst/event bucket requires explicit catalysts or concrete event
language such as contracts, orders, approvals, launches, partnerships, guidance,
awards, rate changes, or leadership appointments. Generic financial or earnings
feature names, and broad words like "customer" without a concrete event, are
not enough by themselves.

## Responsibilities

- Use provider APIs as the default context path. Use web search only when
  explicitly enabled before packet construction and only for source-linked
  public context.
- Fetch company-specific provider news before broader theme/topic news so scarce
  free API quota is spent first on catalyst-bearing company evidence.
- Store short summaries, source URLs, publication dates, availability dates,
  queries, and warnings; do not persist full public research reports or article
  bodies from web search.
- Reject or ignore documents and catalysts published after the candidate
  inflection cutoff.
- Distinguish facts absent from the source, sources not fetched, extraction
  failures, and facts unavailable from supported sources. These states must not
  collapse into one neutral or sufficient value.
- Retain source spans or equivalent provenance for extracted atomic facts so a
  later representation experiment can identify whether a raw-source fact was
  lost, altered, or duplicated in the organized packet.
- Convert public research summaries to `EvidenceKind.RESEARCH_REPORT` and
  theme summaries to `EvidenceKind.THEME_CONTEXT`.
- Keep company-identifying web/context work separate from the later blind,
  anonymous LLM assessment.

## Dependencies

- Parent spec: [`../research.md`](../research.md).
- Uses [`../models.md`](../models.md) for evidence kinds, catalysts, features,
  and validation errors.
- Uses [`../data/documents.md`](../data/documents.md) for `DocumentRecord`
  provenance and packet evidence conversion.
- Consumed by formal cold-start orchestration before packet learning.

## Invariants

- No forward return, winner/control/failure label, or blind-assessment result may
  enter the web evidence prompt.
- Any source with a publication date after the inflection cutoff must not enter
  packet evidence.
- Coverage reports are audit metadata; they do not alter the full historical
  packet checkpoint.
- In `enforce` mode, insufficient packets are excluded before blind LLM calls and
  signal learning.

## Testing

Tests should cover web prompt as-of constraints, no blind-label leakage, future
source exclusion, serialization of `RESEARCH_REPORT` and `THEME_CONTEXT`
documents, coverage bucket sufficiency, and warn versus enforce behavior.
