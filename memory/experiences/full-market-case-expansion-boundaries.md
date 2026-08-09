# Full-Market Case Expansion Boundaries

visit_times: 2

## Trigger

Read this before expanding historical cases from a broad listing/price archive,
changing expansion strata/dates, or acquiring data for an expanded case set.

## Lesson

Do not turn a full-market price archive into more cases by merely increasing the
old extreme-return winner/control/failure caps. Use shared predeclared calendar
dates, recompute the active label independently at every date, deduplicate by
issuer, and preserve issuer-disjoint ownership. Outcome-enriched sampling is a
valid learning benchmark only when its bias is explicit; its class prevalence
cannot be presented as live-market prevalence.

The acquisition layer should never consume the label-aware selected/split
artifacts. Emit a separate exact scope containing only company/CIK/ticker and
required as-of dates, then use that file for bounded provider plans.

## Context

The 2026-08-09 full-market scan started from 5,394 clean listings and a 903 MB
local price archive. Five shared prediction dates left 4,001 issuer identities
with complete six-month five-day-smoothed labels. A first audit exposed 21
selected names whose recorded IPO date followed the earliest prediction date;
making that a hard gate excluded 662 candidates that could represent ticker
reuse, relisting, or a different historical security.

The v4 proposal selected 240 issuers into five explicit maximum-multiple strata
and produced 1,200 cases split 720/300/180 without issuer overlap. Its label-free
acquisition scope showed only four issuers had saved documents and 1,184/1,200
point-in-time observations had none. The exact first provider plan contains 237
SEC submissions requests and three missing-CIK records, with zero external calls
at preflight.

The post-primary implementation keeps that boundary intact: only cached SEC
`filings.files` references can create history requests, every stage has its own
atomic progress file, and filing bodies are selected per midnight case cutoff
from explicit acceptance timestamps or a conservative next-day fallback.

The v5 regeneration resolved the three v4 missing-CIK identities without
editing the clean-universe artifact. One canonical, hashed, date-bounded
decision file excludes stale CPSR and supplies official SEC CIK evidence for
OAKU and SCPX. That input participates in the proposal inventory hash, and its
agent-proposed review status remains an approval blocker. The regenerated
label-free scope has 240 CIKs and both SEC and news plans remain zero-network
until separately authorized.

## How to Apply

1. Fix calendar prediction dates before scanning outcomes.
2. Require complete label eligibility at every date for a rectangular panel.
3. Reject any prediction before recorded IPO/listing date.
4. Deduplicate by CIK when available; validate historical registrant/ticker and
   security type before dataset approval.
5. Record available and selected outcome strata plus the enrichment weights.
6. Split by issuer and stratum, never by individual case.
7. Hand providers only a label-free, split-free acquisition scope.
8. Keep API requests exact, cached, quota-bounded, and resumable.
9. Derive SEC history files only from cached `filings.files` references, then
   select bounded primary documents by timezone-aware acceptance time; when that
   time is absent or timezone-naive, use next-day UTC rather than guessing.
10. Represent stale tickers and missing CIKs as canonical, hashed, date-bounded
    proposal inputs backed by official filings; never patch the source inventory
    or treat agent-proposed evidence as human-approved.

## Limits

The exact dates, 240-issuer target, weights, counts, symbols, and artifact hashes
belong to the 2026-08-09 v4/v5 proposals. They are not permanent defaults and
must be regenerated when the price archive, label contract, identity-decision
hash, or reviewed research design changes. SEC submissions metadata is only
discovery evidence; it does not prove filing bodies, company profiles, news,
transcripts, or historical identity are complete.
