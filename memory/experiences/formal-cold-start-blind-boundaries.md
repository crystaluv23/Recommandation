# Formal Cold Start Blind-Boundary Drift

visit_times: 20

## Trigger

Read this before changing or running the formal cold-start workflow, especially
when the task mentions OpenRouter, GPT, blind LLM analysis, web search,
inflection discovery, anonymous stock packets, seed versus formal runs, or
single cold-start entry points.

## Lesson

The user's requirement was clear enough: the formal cold-start LLM assessment
step should receive an anonymous, point-in-time packet and judge whether the
stock looks like a potential surge case and what pre-surge signals are visible.
Implementation drift happened because the work was shaped around existing
scaffolding instead of restating and verifying the operational contract before
execution.

The main causes were:

- The formal run was treated as a composition of available code paths, so the
  old seed runner and the formal runner both remained visible and blurred the
  intended single entry point.
- Packet completeness was inferred from the existence of data-layer document
  abstractions, but the formal runner only wired price-derived features into
  actual packets. Support in a lower layer is not the same as operational use.
- Two LLM roles were not kept distinct enough: retrospective inflection
  discovery may use ticker identity, outcome windows, and web search; blind
  pre-surge assessment must use only anonymized as-of data and no web-search
  tool.
- Identity masking was checked at obvious fields such as ticker and company
  name, but not adversarially across packet ids, source ids, URLs, document
  text, and other metadata that can still reveal the company.
- The blind LLM schema asked for signal summaries, but did not explicitly ask
  for the core judgment the user expected: whether this anonymous case appears
  to be a surge candidate and why.

## Context

During the May 2026 formal cold-start work in `/Users/l/Project/Recommandation`,
the full-market scan and OpenRouter handoff exposed three issues:

- formal packets did not yet include filings, news, transcripts, or other
  unstructured material even though the architecture expects them;
- the blind prompt masked company fields but leaked the ticker through
  `packet_id`;
- the blind analysis step had no web-search tool, which was correct, but the
  separate retrospective inflection discovery step could use web search and
  needed to remain explicitly separate.

The gap was not caused by an unclear user request. It came from not pinning the
execution contract, acceptance checks, and role boundaries before adapting
existing code.

## 2026-05-09 Correction

The corrective implementation removed the redundant seed script entry point,
added a formal pre-packet context checkpoint for SEC filings, news, transcripts,
and news-derived catalysts, made point-in-time catalyst filtering explicit, and
tightened blind prompt masking across packet ids and text evidence. The lesson
to carry forward is that a clear architecture still needs an execution-contract
check at the boundary where old scaffolding is reused.

## 2026-05-13 Formal Execution Result

The clean formal run `cold-start-formal-openrouter-2026-05-13-clean-universe`
completed 300 blind analyses and wrote signal, theme, playbook, and manifest
artifacts. The run was operationally useful but not yet strong enough to seed
the long-running workflow without another improvement pass:

- OpenRouter JSON output can be malformed or truncated in both blind analysis
  and playbook synthesis, so completed blind analyses need checkpoint resume and
  late-stage playbook synthesis needs retry plus deterministic fallback.
- Filtering common stock before selection matters materially. The first
  universe pass admitted preferreds, notes, ETNs, funds, exchange test symbols,
  and same-issuer suffix variants; the clean rerun removed the obvious
  instrument pollution.
- Packet context remained too thin for signal learning. The completed run
  produced zero promoted deterministic signals, a single `unknown` theme map,
  and a playbook warning that most packets lacked fundamentals, sector,
  valuation, and catalyst substance.
- Blind LLM judgments did not separate winners from controls strongly enough:
  winner and control packets had nearly identical `possible` rates, while
  failure packets still produced many possible surge judgments. Treat this as a
  data/context and control-definition problem before moving into the permanent
  weekly/daily operating loop.

## 2026-05-16 Evidence Coverage Correction

The next correction was to add evidence acquisition before packet construction
instead of asking blind LLM analysis to compensate for thin packet context.
OpenRouter web search is allowed in this setup layer for public summaries,
theme context, and source URLs, but its outputs must become short
`DocumentRecord` summaries with publication/availability dates. Research-report
and theme-context documents are packet evidence kinds; full public reports or
article bodies should not be downloaded into durable artifacts.

The important boundary is the coverage gate: keep the full historical packet
audit, but do not treat every generated packet as learning-ready. In enforce
mode, packets without company evidence plus enough financial, theme, catalyst,
or risk context should be excluded before blind LLM calls and signal learning.

## 2026-05-20 Provider-First Evidence Smoke

The provider-only two-symbol smoke test showed that known APIs can materially
improve packet substance without crawler-like code. With Alpha Vantage
historical symbol news, SEC filings, provider profile context, and Finnhub/SEC
fallbacks, the context checkpoint reached dozens of documents and multiple
news-derived catalysts for the winner/control pair; the strict coverage gate
kept only the latest as-of slice for each side and excluded thinner earlier
slices.

Two operational lessons came out of the smoke:

- Free API quota is a research-quality constraint. Fetch company-specific news
  before broad theme/topic news so scarce calls are spent first on
  catalyst-bearing evidence.
- Provider error strings can include credentials. Adapter-level errors must be
  secret-redacted before warnings or artifacts are written.

The blind LLM distinction test could not complete because OpenRouter returned a
402 insufficient-credits response after packet/coverage construction. Treat
that as an external execution blocker, not evidence that the packet layer is
still empty.

## 2026-07-13 Information-Plan Boundary Correction

A full-source archive and a blind packet are different artifacts. Fetching a
filing and then storing only its 1,500-character packet excerpt destroys the
ability to distinguish acquisition failure from extraction or representation
failure. Preserve complete fetched filing/transcript bodies with an explicit
content scope, audit them before blind calls, and derive bounded packet views
later.

Anonymous masking must use identities discovered from the complete source pool,
not only the facts selected into one packet variant. Historical names,
acquisition targets, related organizations, and exchange-qualified ticker
aliases can survive otherwise-correct ticker/company masking. Reuse one
source-derived alias inventory across raw, organized, add-back, and ablation
packets, then scan every exact prompt variant.

Finally, a fixed raw context budget needs deterministic source coverage. If
chunks are appended document-by-document, one long recent 10-K can consume the
entire raw arm and turn a representation experiment into a file-order test.
Round-robin chunks across the frozen source pool before truncation. Keep this
mechanical and outcome-independent.

## How to Apply

Before executing or modifying formal cold start:

1. Identify the single official entry point and remove or clearly deprecate
   seed/demo paths from the formal execution surface.
2. Write down the phase contract:
   universe scan -> historical labels kept outside packets -> inflection
   anchoring -> T-180/T-120/T-90/T-60/T-30 as-of packets -> blind assessment.
3. Inventory actual packet contents from the runner, not just available data
   abstractions. If filings, news, transcripts, or catalysts are expected, prove
   they are loaded and passed into packet construction.
4. Audit the exact prompt JSON before spending LLM budget. Check labels,
   forward returns, ticker/company name, packet ids, source ids, source URLs,
   and document text.
5. Keep LLM role boundaries explicit: web-enabled retrospective inflection
   discovery is allowed; web-disabled anonymous blind surge assessment is
   required.
6. Treat coverage as a first-class gate: generated packets are audit material,
   while only context-sufficient packets should feed blind LLM learning when the
   formal run is in quality/enforce mode.
7. Add or run tests that assert no label leakage, no identity leakage, no
   web-search tool in blind analysis, and the expected blind output schema.

## Limits

This lesson applies to formal cold-start execution and historical blind case
learning. It does not forbid web search in retrospective setup or live research
stages when the spec explicitly allows those stages to use identity and web
retrieval.
