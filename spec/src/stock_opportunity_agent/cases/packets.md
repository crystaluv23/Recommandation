# Cases Packets

## Status
Started

## Purpose

Build point-in-time historical case packets for cold start from data-layer
records and retrospective outcome labels.

## External Interface

The submodule exposes:

- `CaseSlicePlan`: pre-inflection/as-of offsets, defaulting to
  T-180/T-120/T-90/T-60/T-30.
- `build_historical_cases_from_packets`: bridge from data-layer listings,
  prices, features, documents, and catalysts into labeled `HistoricalCase`
  records with `ResearchPacket` inputs, using supplied inflection dates as the
  anchor for T-180/T-90/T-30 slices.

## Invariants

- Forward outcome data after the inflection anchor can label the case but cannot
  enter the packet evidence.
- Each packet is assembled at its own as-of date with the data-layer point-in-time
  builder.
- Formal cold-start callers should pass comprehensive point-in-time context when
  available: price/volume features, financial/profile features, SEC filings
  such as 10-K/10-Q/8-K, news, transcript-like management commentary, and known
  catalysts, plus bounded public research and theme-context summaries collected
  before the packet cutoff.
- Packet construction should preserve the full audit set even when a later
  coverage gate decides that some packets are too thin for blind LLM learning.
- Historical slices should be before the inflection anchor, not after the surge
  is already visible.
- Missing or insufficient future bars should skip the case rather than invent a
  label.
- A larger evolution benchmark should prefer shared, predeclared calendar
  prediction dates over selecting each issuer's most extreme retrospective
  outcome anchor. If labels are used to enrich learnable strata, the manifest
  must disclose that sampling bias and preserve issuer-disjoint ownership.

## Limits

The packet builder expects data-layer records to be provided by the caller. The
evolution runtime owns a proposal-only offline transform from the saved full
universe/prices into an expanded issuer manifest; packet materialization and
targeted point-in-time source acquisition remain later explicit steps.
