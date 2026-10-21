# Official transcript archives: content corroboration and unresolved clocks

2026-10-22. This source-only review retained two issuer-linked full PDFs and
identified an additional clock discrepancy. It does not establish a historical
complete-public-content time for either record. The original fixed denominator
remains **26 records, accepted public-content time proofs 0**.

## New evidence

| Target | Official source | Observation and limit |
| --- | --- | --- |
| GPRE 2025 Q1 | [Issuer event page](https://investor.gpreinc.com/events-and-presentations/events/event-details/2025/Green-Plains-Inc-First-Quarter-2025-Results/default.aspx) and its [19-page transcript](https://s201.q4cdn.com/120229500/files/doc_events/2025/May/08/GPRE-First-Quarter-2025-Earnings-Transcript.pdf) | The event page says May 8 at 09:00 ET. The PDF cover says May 8 at 14:00 GMT, one hour later than 09:00 EDT. Prepared remarks, distinctive protein-volume discussion, Q&A and actual closing correspond to the original provider body. Neither the CDN path nor the PDF creation clock establishes historical public access. |
| ENB 2025 Q1 | [Issuer-linked 23-page transcript](https://www.enbridge.com/~/media/Enb/Documents/Investor-Relations/2025/2025_Q1_Transcript_FINAL.pdf) | The corrected transcript identifies May 9 and contains the matching executives, operating results, Q&A and closing. Its PDF metadata records creation on May 9 and modification on May 14. This does not prove when the revision became public, that its entire current text was public on May 9, or that the provider body contains a future change. |

The issuer GPRE [announcement](https://investor.gpreinc.com/news/news-details/2025/Green-Plains-to-Host-First-Quarter-2025-Earnings-Conference-Call-on-May-8-2025/default.aspx)
and its [SEC earnings release](https://www.sec.gov/Archives/edgar/data/1309402/000130940225000084/gpreq12025earningsrelease.htm)
repeat the 09:00 ET schedule. A third-party search hit labels 10:00 ET; it is
not a deciding first-party clock. No schedule-change or actual start/end/public
replay timestamp was established. Do not silently choose one of these labels.
The clock discrepancy does not change the existing May 30 case cutoff, and
does not itself prove a cutoff leak.

The original provider documents are corroborated at selected identity, factual
and closing anchors. This is not a turn-by-turn semantic equivalence proof.
All 26 originals were hash-checked and their first/last turns inspected locally;
the remaining 24 received no new first-party body comparison in this batch.
Fiscal-period echoes, opening/closing wording and file completeness are not
complete-public-time evidence. The already known RZLV full-year/fiscal mapping
conflict is retained rather than interpreted as a calendar Q4 proof.

## Bounded replay-metadata attempt

The actual GPRE issuer link reaches a Q4 application shell. Its HTML contains
no start/end/duration publication record. The public application bundle declares
separate API interfaces. Root's minimal read-only `getEvent` query, taken from
that shared bundle, selected title and event clocks only; the attendee endpoint
first rejected missing Apollo content headers, then rejected `getEvent` as an
unsupported Query field. This was an endpoint-selection error, not an event
absence, expired replay or proof failure. Both exact errors are retained.

Stop this metadata attempt after four direct GETs: HTML, public application
bundle, original query and the same query with ordinary content headers.
No guest registration/authentication, mutation, credentials, media retrieval
or endpoint enumeration followed. Two additional direct GETs archived the two
already identified PDFs; their capture/creation/modification headers are not
promoted to historical publication times.

## Evidence, preservation and resources

[Retained source review](../runs/diagnostics/transcript_official_archive_20261022_v1/source-review.json)
binds PDF bytes, extraction bytes, selected original anchors and all 26 original
hashes. Raw HTML, application code and extraction text have byte-exact gzip
archives to retain source whitespace; local originals remain unchanged. Only
public response headers needed for source review are retained. A root self-audit
checks bindings and the nonadmission verdict; no independent reviewer or fresh
model is claimed.

This batch used four web search calls/eleven query strings, four new web
navigations and seven existing-page find/open operations. Underlying web HTTP
counts are unknown. The six direct public GETs above are separate from the
unchanged **147 managed-provider GETs**. The first search unnecessarily included
DLocal, outside the fixed inventory; no result from that query entered the
review. Scope was then bound to the actual 26-record inventory. No model role,
external LLM API, label access, source normalization/oracle append, accepted
source manifest, completed-stage entry or full successor occurred.

The previous source strategy inspected prospective event metadata but had no
retained complete official body. This review supplies that body evidence for two
targets and exposes why inferring publication from the event label or PDF
metadata remains unsafe. It closes that diagnostic distinction only; no
transcript source is newly admitted and no normal capability pass is asserted.

Do not extend this archive strategy merely to add searches. Historical complete
public access or actual live start/end evidence is still needed under the
approved policy. F5 bounded-reading and Mining namespace-interface decisions
remain pending; this review neither selects them nor authorizes a new interface.
