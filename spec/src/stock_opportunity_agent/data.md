# Data

## Status
Started

## Purpose

Provide structured and unstructured data to the rest of the system with point-in-time discipline. The data layer is the source of repeatability; LLM research should consume prepared data instead of improvising raw searches.

## External Interface

The module should expose services for:

- universe snapshots,
- price and volume history,
- financial statement features,
- valuation features,
- analyst revision features when available,
- events and catalysts,
- filings and transcript metadata,
- document retrieval,
- sector and benchmark context,
- and point-in-time `ResearchPacket` construction.

Initial implementation uses a provider registry under `src/stock_opportunity_agent/data/sources/`. Data-source modules register factories with `@register("source_name")`; core pipeline code should request providers by name/capability instead of importing a vendor directly. Source-specific rules live in [`data/sources.md`](data/sources.md).

Post-source implementation adds active data-layer submodules:

- [`data/structured.md`](data/structured.md): normalize prices, profile fields, valuation ratios, and SEC company facts into `FeatureRecord` values.
- [`data/documents.md`](data/documents.md): archive, chunk, and retrieve source-linked documents with public-availability metadata.
- [`data/point_in_time.md`](data/point_in_time.md): filter features and documents by availability and assemble `ResearchPacket` records.
- [`data/raw_info.md`](data/raw_info.md): append-only facts and source bodies for
  adaptive Signal execution, filtered by `available_at <= prediction_time`.
- [`data/backfill.md`](data/backfill.md): audited, bounded, resumable repair of
  incomplete historical source bodies and SEC XBRL facts into append-only Raw
  Info.
- [`data/historical_news.md`](data/historical_news.md): exact, quota-aware,
  point-in-time company-news summary acquisition for label-free case scopes.

## Data Need Rationalization

The source layer keeps these non-redundant capabilities:

| Capability | Keep / merge decision |
| --- | --- |
| Universe and identifiers | Keep separate from company profile because ticker/CIK/FIGI/exchange hygiene is needed before any company data lookup. |
| Daily price and volume | Keep as a raw market-data capability. Intraday and real-time data are out of MVP scope unless explicitly added later. |
| Company profile | Keep for sector, industry, name, exchange, and market-cap context; normalize provider taxonomies later. |
| Financial statements | Keep as the authority input for fundamentals. SEC XBRL is preferred over derived vendor statements. |
| Valuation | Keep as a derived feature family, but treat vendor valuation ratios as convenience raw inputs, not source of record. |
| Filings and filing documents | Keep both metadata and document retrieval; metadata feeds catalysts and point-in-time filters, documents feed research packets. |
| News | Keep for evidence and catalyst monitoring, with licensing restrictions carried in source metadata. |
| Transcripts | Keep as a document subtype because management commentary matters for expectation gaps. |
| Analyst estimates and revisions | Keep only when free endpoints expose them; unavailable estimates must be explicit missing data. |
| Earnings calendar and corporate actions | Keep as event/catalyst inputs; they are not the same as system-generated catalysts. |
| Sector, benchmark, and macro context | Keep for theme transmission and market-regime context. |

Do not add separate first-class source capabilities for brokerage, order routing, position sizing, real-time quotes, options chains, or paid-only proprietary sentiment without explicit top-down design approval.

## Responsibilities

- Ingest and cache raw vendor responses or public filings when allowed.
- Normalize data into stable feature records.
- Normalize high-priority source outputs into `FeatureRecord` values without embedding scoring semantics.
- Retrieve and chunk source-linked documents for packet assembly.
- For formal cold-start packets, retrieve point-in-time filing and news context
  for selected symbols before blind LLM assessment; SEC filings and facts,
  material news such as orders or contracts, transcripts when available, public
  research summaries, theme context, and other source-backed information should
  be included when it can help judge whether the stock looked like a potential
  surge candidate.
- Construct point-in-time packets for live scans and historical case learning.
- Preserve source, timestamp, and availability metadata.
- Separate raw archives, feature stores, and document stores.
- Reject Raw Info replacement or deletion through the store API; corrected
  source content must be a new document with its own id and lineage metadata.
- Select sources by capability using the catalog preference order before invoking a provider.
- Track request outcomes and source quotas so free API limits produce resumable deferred work instead of hidden partial data.
- Audit historical coverage and backfill only exact, source-linked requests
  under an explicit per-invocation network ceiling.

## Dependencies

- Uses `models` for packet and evidence records.
- Uses `config` for data-source and storage configuration.
- Feeds scanner, themes, cases, research, scoring, monitoring, review, and reports.

## Invariants

- Historical packets must not include documents, catalysts, or features
  unavailable as of `as_of_date`.
- Missing data must be explicit; absence cannot be silently treated as neutral evidence.
- Source freshness and retrieval time must be recorded for data used in scoring.
- Cache hits must be distinguishable from fresh upstream fetches.
- Quota exhaustion must be explicit and carry a retry time when the source exposes a predictable reset window.
- LLM web findings, if used, must be converted into source-linked evidence before affecting durable records.

## Testing

Tests should cover point-in-time filtering, missing data semantics, packet construction, source metadata, document availability filtering, and fixture-based feature normalization.
