# Data / Documents

## Status
Started

## Purpose

Archive and retrieve source-linked unstructured text for point-in-time research
packets. Documents include filings, transcripts, news, public research-report
summaries, theme-context summaries, and other source-backed material that LLM
research may quote or summarize later.

## External Interface

The implementation exposes:

- `DocumentRecord` for source-linked document text with publication, availability, and retrieval metadata.
- `DocumentChunk` for deterministic text chunks carrying the same provenance.
- `DocumentStore` as an in-memory early store for deterministic as-of retrieval.
- `documents_as_of()`, `chunk_document_text()`, and `documents_to_evidence()` helpers.

## Responsibilities

- Store document metadata, publication date, public availability date, retrieval time, source id, source URL, and text.
- Preserve the complete fetched body for filings and transcripts in
  `DocumentRecord`; do not apply packet-context truncation while acquiring or
  serializing the source archive. Provider or web APIs that expose only a
  summary must be marked and stored as summary-only evidence rather than
  described as a complete document body.
- Support point-in-time filtering by ticker and evidence kind.
- Produce source-linked evidence metadata and short text excerpts for research
  packets so LLM research sees the substance of filings, transcripts, news,
  public research summaries, and theme summaries rather than only knowing that a
  document exists.
- Keep document retrieval separate from scoring and from source adapters.
- Keep web-acquired public research and theme context as short summaries with
  source URLs and dates, not as downloaded full reports or article bodies.

## Dependencies

- Parent spec: [`../data.md`](../data.md).
- Uses [`../models.md`](../models.md) for evidence kinds and evidence records.
- Consumes source-layer filing, transcript, and news outputs when adapters provide them.
- Consumes research evidence-acquisition summaries for public research reports
  and theme context.

## Invariants

- Documents and chunks may enter a historical packet only when their public availability date is on or before the packet `as_of_date`.
- Document evidence must include source identifiers, source URLs, and a bounded
  excerpt or summary suitable for packet prompts.
- Bounded packet excerpts and chunks are derived representations. They must not
  replace or overwrite the archived source body used for extraction and audit.
- Text chunking must preserve document ids and source metadata.

## Disclosure Interface

The document archive exposes the shared three-layer disclosure interface
(`data/disclosure.py`), pure over immutable documents and the supplied
point-in-time cutoff:

- **Catalog** (`document_catalog`): bounded pages of deterministic cards —
  provider news titles, filing form types (authoritative acquisition
  metadata first, entity-tolerant cover-text detection as fallback), SEC
  Part/Item section indexes with exact raw offsets, availability dates, and
  readable sizes. The envelope discloses eligible/included/omitted counts
  with cursor pagination; a title query filters by deterministic extracted
  text. Point-in-time filtering is enforced: future documents never appear.
- **Fetch** (`fetch_entry`): one bounded working view of summary plus a
  content-addressed reference (document id, content hash, raw span). A unit
  that fits the budget returns complete verbatim readable text — including
  an exact section when a section id is supplied; an oversized unit returns
  head windows plus bounded readable omission markers, and the reference
  stays valid for distillation and provenance reads.
- **Provenance** (`read_provenance`): a reference resolves to the exact raw
  substring, failing closed on hash mismatch, invalid offsets, or a budget
  exceeding read. Filesystem paths are never used as references.

## Testing

Cover as-of filtering, duplicate replacement in the early store, chunk
metadata, source-linked evidence conversion, future-document exclusion, and
proof that complete filing/transcript bodies survive acquisition while packet
evidence remains bounded. Cover the disclosure interface content-level:
title/form/section metadata on cards, envelope counts and pagination,
title-query catalyst discovery, verbatim-versus-bounded fetch semantics with
omission markers, exact section fetch, and provenance byte-exactness with
hash/offset rejection.
