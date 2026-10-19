# Historical market proof review — 2026-10-19

This is a source-review result, not admission to the frozen SEC-only stages.
The user permits read-only source queries and forbids external LLM APIs. The
collector made exactly three authenticated, read-only Massive GET attempts,
each once, all HTTP 200. Authentication headers are absent from artifacts.
The separate documentation lookup used public web search/open; those are not
included in the three data GETs. External LLM calls remain zero.

## Retained evidence and findings

[Request plan and exact response hashes](../runs/diagnostics/bmbl_market_readonly_proof_20261019/results.json),
[raw comparison](../runs/diagnostics/bmbl_market_readonly_proof_20261019/comparison.json)
and the collector are retained together. The original provider cache and
canonical market record named in the
[previous local review](bmbl-market-input-review-20261019.json) are unchanged.

| Query | Actual result | Supported conclusion |
| --- | --- | --- |
| Historical ticker identity, date 2025-09-29 | BMBL, CIK 0001830043, XNAS, common stock, USD | The provider's historical identity agrees with the reviewed SEC issuer and symbol. |
| All split event types, execution dates 2025-09-30 through 2026-08-16 | `OK`, empty results, no next page | This provider ledger reports no split in the post-cutoff interval through the old adjusted-series retrieval date. This is not an unrestricted absence claim. |
| Unadjusted daily bars, requested 2024-09-30 through 2025-09-29 | 235 bars, 2024-10-21 through 2025-09-29, no next page | All five OHLCV fields exactly match the old adjusted response on all 235 shared dates. The response does not establish coverage of the full requested interval. |

The old response has 250 bars. Fifteen earlier bars, 2024-09-30 through
2024-10-18, are absent from the new response and were not independently
reverified. No account tier, entitlement explanation or completeness claim is
inferred from that omission. The five latest shared closes have arithmetic
mean 6.494; this is a source-review calculation, not an injected runtime
baseline or an accepted Predictor result.

Massive documents split event execution dates, cumulative adjustment factors
and pagination in its [split endpoint](https://massive.com/docs/rest/stocks/corporate-actions/splits).
Its [adjustment explanation](https://massive.com/knowledge-base/article/does-massive-adjust-historic-dividends-for-splits)
says aggregates default to split adjustment and `adjusted=false` requests the
quoted price basis. Its [bar differences explanation](https://massive.com/knowledge-base/article/why-is-massives-market-data-different-from-other-providers)
also describes later corrections in REST history. These documentation pages
were checked on 2026-10-19; their text is not evidence that a particular old
bar was or was not corrected.

## Existing contract and evidence limit

The owning [PIT spec](../spec/src/stock_opportunity_agent/data/point_in_time.md)
excludes facts/documents available after the cutoff. The
[Raw Info contract](../spec/src/stock_opportunity_agent/data/raw_info.md) and
[structured normalization](../spec/src/stock_opportunity_agent/data/structured.md)
preserve source, retrieval and availability separately. The
[source spec](../spec/src/stock_opportunity_agent/data/sources.md) supports
historical backfill, while [resolution](../spec/src/stock_opportunity_agent/data/resolution.md)
requires chronological adjusted closes and observation-level lookback.
These contracts do not explicitly require every bar to have been downloaded
and archived before the research cutoff.

Independent counterexample review corrected its initial recommendation:
failure to prove an exact cutoff-time vendor vintage is a methodological
limitation, not by itself an existing mandatory rejection condition. A new
policy requiring cutoff-time archives would be a separate design decision.
Current production dating is not proof that every historical revision is
authorized or harmless. No exact cutoff-time vendor-vintage guarantee is
claimed here.

The independent reviewer checked the retained response hashes and recomputed
the 235-bar comparison, including the 15 missing dates and zero extra dates.
It also reconstructed the entire old 250-row RawInfoDocument with the current
production price parser and HistoricalPriceAdapter, preserving its original
retrieval time: the complete record, content and metadata.prices match exactly.
The post-cutoff split ledger supplies a share-basis check for the entire old
response through its retrieval date. The 235-row comparison is additional
evidence; the 15 dates missing from that second download do not themselves
invalidate the old original or create a requirement to download every row twice.

These source, normalization and adjustment proofs support considering the
exact old 250-row record for a new bounded reviewed view under the existing
contract. The remaining work is mechanical proof binding and negative checks,
not an observed contamination of the 15 rows. Such a view must bind the
original request/raw response, date scope, normalization, issuer, split query
coverage/pagination, cutoff and retrieval time. Its negative checks must
reject scope expansion and cross-source substitution. Until implemented and
checked, market admission remains pending; the frozen SEC-only stages remain
unchanged. No cutoff-time vendor-vintage or absolute source-authentication
guarantee follows from this review.
