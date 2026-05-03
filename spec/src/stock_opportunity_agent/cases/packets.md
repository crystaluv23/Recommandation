# Cases Packets

## Status
Started

## Purpose

Build point-in-time historical case packets for cold start from data-layer
records and retrospective outcome labels.

## External Interface

The submodule exposes:

- `CaseSlicePlan`: pre-outcome as-of offsets such as T-180/T-120/T-90/T-60/T-30.
- `build_historical_cases_from_packets`: bridge from data-layer listings,
  prices, features, documents, and catalysts into labeled `HistoricalCase`
  records with `ResearchPacket` inputs.

## Invariants

- Forward outcome data can label the case but cannot enter the packet evidence.
- Each packet is assembled at its own as-of date with the data-layer point-in-time
  builder.
- Missing or insufficient future bars should skip the case rather than invent a
  label.

## Limits

The initial implementation expects data-layer records to be provided by the
caller or a later storage/fetch layer. It does not yet fetch the whole universe
by itself.
