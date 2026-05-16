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
- Text chunking must preserve document ids and source metadata.

## Testing

Cover as-of filtering, duplicate replacement in the early store, chunk metadata, source-linked evidence conversion, and future-document exclusion.
