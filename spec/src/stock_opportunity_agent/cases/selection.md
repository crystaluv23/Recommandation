# Cases Selection

## Status
Started

## Purpose

Scan the historical listed-stock universe to select real cold-start winner,
control, and failure candidates before LLM case learning begins.

## External Interface

The submodule exposes:

- `HistoricalCandidate`: one symbol's selected retrospective anchor and label.
- `HistoricalCandidateSelection`: scan window, selected candidates, counts, and
  warnings.
- `eligible_common_stock_listings`: conservative listing filter for US common
  stock candidates; it excludes obvious warrants, rights, units, preferred
  shares, depositary receipts, notes, ETNs, funds, LPs, structured products, and
  exchange test symbols by listing name, non-common-stock asset types, and
  symbol variants that look like exchange-coded preferred/notes for an already
  listed common issuer.
- `select_historical_candidates`: price-history scan that labels each symbol
  using a versioned `OutcomeDefinition` over the most recent matured one-year
  anchor window.

## Initial Production Assumptions

- The run date is the data cutoff date.
- Because the default outcome horizon is 180 calendar days, the most recent
  one-year selection window ends 180 days before the run date so every selected
  anchor has a matured forward outcome.
- The scanner first identifies candidate symbols and a rough matured outcome
  anchor, then the formal case packet builder must determine a retrospective
  inflection date for each selected symbol and construct packets at dates before
  that inflection, such as T-180/T-120/T-90/T-60/T-30.
- Winner/control/failure labels use `surge-close-return-v0.1` until a new
  version is approved.
- The scanner may find many winners, but the first LLM cold-start run processes
  a bounded top slice of winners and enough controls/failures for comparison.
- The formal runner must treat price-source coverage as a first-class run
  quality metric. It should prefer the configured keyed daily-price source and
  fall back through other available providers rather than treating one source as
  authoritative when it is timing out or returning no data.
- Before filtering the formal universe, the runner should enrich active listings
  with SEC ticker mapping names when available so exchange-traded notes,
  preferreds, and structured products are not admitted only because a vendor's
  listing row used the issuer's common company name.
- After candidate selection and before packet construction, the formal runner
  should enrich selected symbols with source-backed unstructured context:
  point-in-time SEC filing documents, news, transcript-like management
  commentary when available, and catalyst evidence such as orders, contracts,
  backlog, approvals, or major customer events.

## Invariants

- Outcome labels and forward returns are retrospective metadata and must stay
  outside blind packets.
- Candidate selection may use future price data only for retrospective labeling,
  never as packet evidence.
- Point-in-time case packets must be anchored to detected inflection dates, not
  to the later date when a matured forward return label is known.
- Sampling independence: the `as_of` selection rule must not depend on the
  forward price path. Packets sit at fixed offsets before a detected
  inflection (T-180/T-120/T-90/T-60/T-30) or at data-availability anchors; an
  `as_of` chosen with hindsight (for example the day before a known run
  starts, or mid-surge) turns the task into momentum recognition and
  contaminates both evaluation and everything the reflection loop learns from
  the pair.
- Scanner summaries must record the selection window, input universe size,
  successful price histories, skipped symbols, selected candidates, and
  definition versions.
- Full price histories used for candidate labeling must be checkpointed before
  LLM research begins so a later OpenRouter interruption does not force a fresh
  universe scan or lose the actual evidence used for selection.

## Limits

The initial implementation still uses historical daily price bars as the
whole-universe backbone, then enriches only the bounded selected candidate set
with filing/news/transcript context before blind LLM assessment. Sector,
market-cap, and valuation enrichment remain incomplete when historical
point-in-time source data is not available for the anchor dates.
