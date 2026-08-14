# Vision

## Status
Done

## Product Identity

This project is a long-running stock opportunity discovery agent. Its job is to find stocks that may be repriced over the next 3-6 months because the market has not fully adjusted to changing fundamentals, industry-chain transmission, catalysts, or early confirmation in price and volume.

The system is an expectation-gap research system, not a price prediction oracle. It should help a human investor decide what deserves attention, not decide trades automatically.

The product should feel less like a one-shot screener and more like a persistent research workflow:

```text
learn from historical winners and failures
-> discover and validate what information a stock study needs
-> extract signals, research rubrics, and theme maps
-> scan the current market
-> generate company theses
-> bind each recommendation to validation metrics
-> monitor whether reality confirms or breaks the thesis
-> review outcomes
-> improve signals, themes, prompts, scores, and memory
```

The durable unit of work is the investment thesis and its evidence, not the ticker by itself.

Historical learning has two coupled time scales. The fast loop evolves an
`InformationPlan`: how to bootstrap a company study, formulate the next
information need, reflect over a batch of evidence-backed signals, and assemble
the final blind-prediction context. The slow loop evolves a versioned Signal
Library: which reusable real-world concepts matter and how to extract them from
the point-in-time Raw Info Store. The system evolves research strategy and
cognitive tools, not one prediction prompt.

The coupling is deliberately cumulative. After each Slow Loop, every candidate
that passes the fixed machine-validation contract is atomically promoted into
the local stable Signal Library. The next Fast Loop samples new Plans from that
newest library plus the historical high-F1 Plan Archive. Historical Plans keep
their original blind-evaluation F1 and are not replayed merely because the
Signal Library changed; new Plans must displace them by producing better F1.
Signal version/hash is therefore execution provenance, never a fitness term.

The resulting information plan remains a proposal until it succeeds on
label-hidden evolution validation and later passes a separately locked test.
Only after the information layer reaches a stable validation plateau should the
project compare richer analysis methods such as multi-agent research, debate,
or specialist critique. Weak plain-LLM separation is not by itself evidence
that multi-agent analysis is needed when acquisition, signal extraction, or
context fidelity remains unresolved.

## Core Goal

Produce a repeatable weekly watchlist of high-priority stock opportunities with:

- a clear thesis,
- supporting evidence,
- contrary evidence,
- catalysts,
- disconfirming conditions,
- a validation contract for what must happen over the next 1, 3, and 6 months,
- theme and segment context,
- valuation and risk notes,
- versioned scores,
- and persistent memory for later review.

The weekly watchlist is one moment in a larger loop. A recommendation is not complete until it has been monitored, validated or invalidated, reviewed, and fed back into memory and the signal library.

## Operating Spine

The system's main line is:

```text
historical learning
-> fast-loop information-plan experiments
-> slow-loop signal mining, repair, validation, and versioned promotion
-> locked-test review of a selected research information plan
-> analysis-method experiments
-> theme and industry-chain map
-> weekly theme-first scan
-> structured coarse screen
-> LLM company research and skepticism
-> hybrid scoring
-> cross-sectional comparison
-> watchlist and validation contract
-> daily incremental monitoring
-> earnings and catalyst validation
-> monthly review
-> quarterly meta-learning
```

Each module should make this line easier to audit. Modules are not independent research toys; they exist to move a thesis from discovery, through validation, into review-backed learning.

## MVP Scope

The first useful version should focus on:

- US-listed common stocks.
- Market cap above roughly USD 5 billion by default.
- Liquid names with enough price, filing, news, and transcript coverage to analyze.
- Priority sectors where industry-chain transmission matters, such as semiconductors, AI infrastructure, power equipment, cooling, software, industrials, and defense.
- Weekly Top 20 watchlist output.
- Validation contracts for every high-priority watchlist entry.
- Daily event monitoring for active theses without rerunning full LLM research when nothing material changed.
- Monthly review of outcomes and false positives.

These thresholds are starting defaults, not permanent beliefs.

## Non-goals

- Do not generate automatic buy/sell orders.
- Do not manage positions, leverage, stops, or brokerage actions.
- Do not present LLM output as reliable financial prediction.
- Do not learn only from winners; every historical study must include controls or failures when possible.
- Do not let the system silently rewrite its own framework without experiment evidence and human confirmation. Automatic Signal promotion is permitted only through the explicitly specified Slow-Loop validation and atomic transition contract; changing that contract is a framework change.
- Do not let the fast loop mutate labels, dataset ownership, blind-prediction
  rules, fixed evolution priors, or Signal Registry versions.

## Operating Principles

### LLM as Researcher

The LLM reads, compares, summarizes, critiques, and generates theses. It is strongest on filings, transcripts, news, narrative migration, management tone, supply-chain clues, and cross-company resonance. It is not the final judge of price, probability, valuation, or risk.

### Structured Data as Backbone

Structured price, volume, financial, valuation, analyst revision, event, and market-context data should be the repeatable backbone. LLM search and text retrieval are supplements, not the primary data pipeline.

### Point-in-time Discipline

Historical learning and backtests must only use information public as of the simulated date. Case analysis should use time slices such as T-180, T-120, T-90, T-60, T-30, and T-0 without leaking later explanations.

### Information Before Analysis Complexity

The historical-learning program must distinguish information discovery from
analysis-method research. Label-aware winner/control/failure comparison may
propose information requirements, candidate signals, and research rubrics.
Anonymous holdout evaluation then tests whether the proposed information can be
acquired, extracted, and represented effectively for a fixed plain LLM. The
project should not attribute failure to the analyzer or move to multi-agent
methods until source coverage, atomic-fact fidelity, and representation loss
have been measured separately.

### Theme-first and Stock-second

Many major opportunities come from an industry-chain segment moving from overlooked to central. The system should discover themes, map transmission paths, score segments, then rank companies inside the right segments.

### Long-term Local Memory

The system must persist company memory, thesis memory, signal memory, case memory, decision memory, review memory, theme memory, and segment memory. Memory exists so the agent can answer why it recommended something, whether it worked, and what it learned.

### Validation Contracts

Every high-priority recommendation must specify what future evidence would confirm or break the thesis. Typical validation metrics include revenue acceleration, margin improvement, backlog, management guidance, analyst revisions, customer or supplier corroboration, relative strength, valuation stretch, and peer read-throughs. A recommendation without a validation contract should stay below high-priority watchlist status.

### Watchlist Output

The primary output is a watchlist and research cards. Recommendation states should include ignore, monitor, thesis forming, high-priority watchlist, action candidate, thesis validated, thesis broken, and archived, but any actual trading decision remains outside this system.

### Review and Meta-learning

The system must review recommendations, label errors, measure signal performance, and propose improvements. Meta-learning can suggest changes to weights, prompts, data sources, and module design, but medium and high-risk framework changes require experiments and human approval. Signal candidates produced inside the approved historical-learning Slow Loop follow their separate fixed machine-validation and automatic-promotion contract.

## Success Criteria

The system is useful when it can:

- generate a stable weekly Top 20 watchlist,
- explain each candidate with evidence and disconfirming conditions,
- bind each high-priority candidate to validation metrics and review dates,
- preserve every recommendation with data, prompt, model, and scoring versions,
- review 1-month, 3-month, and 6-month outcomes,
- identify false-positive patterns,
- and improve the research process without erasing auditability.
