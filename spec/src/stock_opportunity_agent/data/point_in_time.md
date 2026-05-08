# Data / Point In Time

## Status
Started

## Purpose

Construct point-in-time research packets for current scans and historical case learning. This module applies availability filters across normalized features and documents, then assembles a `ResearchPacket` with explicit missing data when needed.

## External Interface

The implementation exposes:

- `feature_records_as_of()` for strict feature availability filtering.
- `latest_features_by_name()` for deterministic as-of-safe feature selection.
- `features_to_evidence()` for converting normalized feature metadata into concise evidence.
- `build_research_packet()` for assembling `ResearchPacket` records from company profile, features, documents, catalysts, themes, memory refs, and versions.
- `catalysts_as_of()` for excluding catalysts whose source evidence was not
  public by the packet date.

## Responsibilities

- Exclude features whose availability date is after the packet `as_of_date`.
- Exclude documents whose public availability date is after the packet `as_of_date`.
- Exclude catalysts unless their supporting evidence was available by the packet
  `as_of_date`; future catalyst articles cannot leak backward into earlier
  historical slices.
- Carry data cutoff and creation time in `AsOfContext`.
- Ensure a packet contains structured features and evidence, using explicit missing feature records when no structured data is available.

## Dependencies

- Parent spec: [`../data.md`](../data.md).
- Uses [`structured.md`](structured.md), [`documents.md`](documents.md), and [`../models.md`](../models.md).

## Invariants

- Future information leakage is a blocking bug.
- Every packet must say what structured data was unavailable, stale, estimated, or confirmed.
- Feature evidence must remain source-linked when the feature has source metadata; feature-derived inference evidence must be marked as inference.
- Document evidence should carry bounded excerpts or summaries so a packet can
  contain 10-K/10-Q/8-K, news, and transcript content without forcing the LLM to
  browse.
- Packet construction must not score opportunities or generate theses.

## Testing

Use historical fixtures with future features and documents to ensure strict exclusion, deterministic source-priority selection, packet reproducibility, and explicit missing-feature behavior.
