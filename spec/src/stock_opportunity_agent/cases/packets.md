# Cases Packets

## Status
Started

## Purpose

Build point-in-time historical case packets for cold start from data-layer
records and retrospective outcome labels.

## External Interface

The submodule exposes:

- `CaseSlicePlan`: pre-inflection/as-of offsets, defaulting to T-180/T-90/T-30.
- `build_historical_cases_from_packets`: bridge from data-layer listings,
  prices, features, documents, and catalysts into labeled `HistoricalCase`
  records with `ResearchPacket` inputs, using supplied inflection dates as the
  anchor for T-180/T-90/T-30 slices.

## Invariants

- Forward outcome data after the inflection anchor can label the case but cannot
  enter the packet evidence.
- Each packet is assembled at its own as-of date with the data-layer point-in-time
  builder.
- Historical slices should be before the inflection anchor, not after the surge
  is already visible.
- Missing or insufficient future bars should skip the case rather than invent a
  label.

## Limits

The initial implementation expects data-layer records to be provided by the
caller or a later storage/fetch layer. It does not yet fetch the whole universe
by itself.
