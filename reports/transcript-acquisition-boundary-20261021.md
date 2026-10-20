# Transcript acquisition boundary — 2026-10-21

The approved availability rule is unchanged: verify complete public conference
content, issuer/fiscal identity and its public-time boundary. The fixed original
inventory remains **26 records, 0 accepted public-content time proofs**. No
original, correction preview or completed experiment is migrated by this work.

## Source evidence and limits

The bounded public-source review inspected KGC 2025 Q1 and FIBK 2025 Q1/Q2.
Their original provider bodies have opening, questions and closing; that does
not establish their historical public availability. The independent
[source-only standards](../runs/diagnostics/transcript_public_content_time_20261021_v1/independent/source-only-standards.json)
bind all 26 original files and identify the three bodies' exact anchors.

| Target | First-party lead inspected | Disposition |
| --- | --- | --- |
| KGC Q1 | [May 6 earnings release](https://www.kinross.com/news-and-investors/news-releases/press-release-details/2025/Kinross-reports-2025-first-quarter-results/default.aspx), [May 7 event listing](https://www.kinross.com/news-and-investors/events/event-details/2025/First-Quarter-2025-Results-Conference-Call--Webcast/default.aspx) | Scheduled call and promised archive; attempted replay navigation returned an error. Complete historical public content/time unverified. |
| FIBK Q1 | [SEC earnings release](https://www.sec.gov/Archives/edgar/data/860413/000086041325000057/fibk-20250331x8kpr.htm) | April 30 call and later replay announced prospectively; fulfillment/completion unverified. |
| FIBK Q2 | [SEC earnings release](https://www.sec.gov/Archives/edgar/data/860413/000086041325000114/fibk-20250630x8kpr.htm) | July 30 call and later replay announced prospectively; fulfillment/completion unverified. |

All three remain unknown, with the other 23 not newly body-reviewed in this
probe. A current modified third-party transcript and historical publication
label were not accepted as proof of the historical complete body. Search hits
for First Internet Bancorp (INBK) and Kinross's AGM were different issuers/events
and rejected. The correct FIBK IR entry was located at
[fibk.com](https://fibk.com/overview/default.aspx); its historical event/replay
metadata is a distinct next lead, not a proof already obtained.

This search used 2 search calls / 4 query strings, 6 navigation attempts and one
cached find call with 3 patterns. Underlying web-engine HTTP counts are unknown.
These are separate from the existing 147 managed-provider GETs, which did not
increase. Rendered web observations are not a managed raw HTTP archive. No
external LLM API or production role was called.

## Production error family

The Alpha Vantage acquisition adapter converted earnings `reportedDate + 1 day`
into transcript availability. Its old test asserted that same rule using one
management remark, so it tested the erroneous implementation rather than the
approved public-content obligation. Independent producer review also found the
legacy formal Finnhub collector treating a provider list date, or even a fiscal
quarter end, as publication of a complete body.

Neither automatic producer has a reviewed complete-public-content proof input.
Their unsafe materialization must stop before unnecessary provider requests,
using existing typed gaps / formal warnings. Raw provider clients and managed
cache, local-first resolution and other context sources remain available.
This is a local producer repair, not a substantive transcript capability
positive control, a new proof interface or approval of legacy local records.
Proof-backed materialization, explicit reviewed successor exclusions and actual
qualified content consumption remain open.

## Implemented boundary and verification

The Alpha adapter retains its public constructor/signature and reports
`available=False` / `historical_data_unavailable` to capability probes. Direct
acquisition raises that existing typed failure before touching the client. The
formal Finnhub producer returns no documents with an explicit warning; disabled
requests and absent clients retain their previous quiet behavior. The unused
calendar-to-publication helpers are removed from both producers. Provider raw
clients, source caches and the shared resolver are unchanged.

[232 associated tests](../runs/diagnostics/transcript_acquisition_boundary_20261021_v1/root/associated-result.json)
passed across the two new boundary suites, data resolution, factory control,
raw data/cache, cold start and provider-response handling. An actual socket
tripwire recorded zero network attempts, and product/test hashes remained
unchanged during that run. Controls exercise the real adapter through the real
resolver, typed-gap serialization and repeat memo, existing local-source reads,
fallback to an independent source, configured factory introspection, and raw
client through managed cache. A resolver attempt still reserves one existing
adapter-budget unit; zero provider requests does not mean zero reservation.

The local-first positives use explicitly synthetic stored sources and prove
consumer preservation only. Neither they nor raw-cache success verify public
availability, accept any of the 26 records, or prove a fresh model's behavior.
All [26 originals remain byte-identical](../runs/diagnostics/transcript_acquisition_boundary_20261021_v1/root/original26-preservation.json).

[Independent counterexample review](../runs/diagnostics/transcript_acquisition_boundary_20261021_v1/independent/final-review.json)
passed 8/8 methods; the exact old Git versions fail five methods (nine failing
assertions/subcases) while three preservation controls already pass. Both raw
Alpha and Finnhub client paths preserve complete parsed JSON through managed
cache and a fresh reopen/cache hit, with fake innermost HTTP only. This verifies
the local guard and preservation, not actual provider access or raw HTTP bytes.

The initial independent baseline copy raced with an edit and captured the
candidate. Its apparent Alpha success is excluded from old-version evidence;
the corrected comparison loads the hash-verified Git originals. A first focused
test command used an invalid class selector, and the first independent seal
check confused an enum string with a unittest error header. All initial logs
remain alongside the corrected results; none caused a product relaxation.

The broader content-chain and transcript-capability acceptance remain open.
