# Legacy Artifact to Raw Info Migration

visit_times: 3

## Trigger

Read this before reusing historical cold-start cases, packet JSON, documents, or
price artifacts in the replacement Information-Plan/Signal evolution runtime.

## Lesson

Do not rename and copy a legacy case object wholesale. Split it into three
boundaries: source bodies/facts with original public-availability provenance go
to Raw Info; a minimal point-in-time company profile may become Basic Info; old
winner/failure fields, terminal returns, hidden summaries, and future prices
remain outside Raw Info and must not be used as the active label.

Recompute the active six-month label from adjusted prices using the approved
baseline/smoothing rule. A derived market-data Raw Info snapshot may contain
only bars complete before the case as-of. Keep migration reports and source
hashes outside the Raw Info directory because that directory is parsed as
immutable `RawInfoDocument` records.

## Context

The 2026-08-09 migration audit found 300 legacy cases, 547 source documents,
a compact adjusted-price file for 47 symbols, and a 903 MB archive covering all
60 case symbols. A streaming transform extracted 34,152 bars without loading
the archive as one object; no-network migration produced all 547 source
documents plus 289 as-of-only market snapshots. Recomputing the approved
2x/3x/10x semantics left 288 eligible cases; the proposed 173/74/41 issuer
split had 16/8/3 surge cases and remained proposal-only. The `2-3x` class had
only one Discovery case and none in Validation/Locked.

## How to Apply

1. Hash and inventory all source artifacts.
2. Reject outcome keys recursively before Raw Info append.
3. Preserve `published_at` and `available_at`; never substitute retrieval time.
4. Build trailing market snapshots strictly from pre-as-of completed bars.
5. Recompute labels in the Dataset owner and require exact split approval.
6. Keep Locked Test serialized separately and absent from ordinary loaders.

## Limits

Counts and paths are checkout-specific. New price coverage or a different
human-approved label/split contract requires a new inventory and proposal.
