# Data / Documents

## Status
Not started

## Purpose

Archive and retrieve unstructured filings, transcripts, news, presentations, and research snippets for LLM research.

## Responsibilities

- Store document metadata, publication time, retrieval time, source type, and text chunks.
- Support retrieval for research packets without becoming the scoring source of record.

## Dependencies

- Parent spec: [`../data.md`](../../../src/stock_opportunity_agent/data.md).
- Feeds research and theme discovery.

## Invariants

- Documents must be filtered by public availability in historical runs.
- Retrieved excerpts need source identifiers for audit.

## Testing

Cover chunk metadata, as-of filtering, duplicate documents, retrieval results, and source links.
