# Vision

## Status
Done

## Product Identity

This project is a long-running stock opportunity discovery agent. Its job is to find stocks that may be repriced over the next 3-6 months because the market has not fully adjusted to changing fundamentals, industry-chain transmission, catalysts, or early confirmation in price and volume.

The system is an expectation-gap research system, not a price prediction oracle. It should help a human investor decide what deserves attention, not decide trades automatically.

## Core Goal

Produce a repeatable weekly watchlist of high-priority stock opportunities with:

- a clear thesis,
- supporting evidence,
- contrary evidence,
- catalysts,
- disconfirming conditions,
- theme and segment context,
- valuation and risk notes,
- versioned scores,
- and persistent memory for later review.

## MVP Scope

The first useful version should focus on:

- US-listed common stocks.
- Market cap above roughly USD 5 billion by default.
- Liquid names with enough price, filing, news, and transcript coverage to analyze.
- Priority sectors where industry-chain transmission matters, such as semiconductors, AI infrastructure, power equipment, cooling, software, industrials, and defense.
- Weekly Top 20 watchlist output.
- Monthly review of outcomes and false positives.

These thresholds are starting defaults, not permanent beliefs.

## Non-goals

- Do not generate automatic buy/sell orders.
- Do not manage positions, leverage, stops, or brokerage actions.
- Do not present LLM output as reliable financial prediction.
- Do not learn only from winners; every historical study must include controls or failures when possible.
- Do not let the system silently rewrite its own framework without experiment evidence and human confirmation.

## Operating Principles

### LLM as Researcher

The LLM reads, compares, summarizes, critiques, and generates theses. It is strongest on filings, transcripts, news, narrative migration, management tone, supply-chain clues, and cross-company resonance. It is not the final judge of price, probability, valuation, or risk.

### Structured Data as Backbone

Structured price, volume, financial, valuation, analyst revision, event, and market-context data should be the repeatable backbone. LLM search and text retrieval are supplements, not the primary data pipeline.

### Point-in-time Discipline

Historical learning and backtests must only use information public as of the simulated date. Case analysis should use time slices such as T-180, T-120, T-90, T-60, T-30, and T-0 without leaking later explanations.

### Theme-first and Stock-second

Many major opportunities come from an industry-chain segment moving from overlooked to central. The system should discover themes, map transmission paths, score segments, then rank companies inside the right segments.

### Long-term Local Memory

The system must persist company memory, thesis memory, signal memory, case memory, decision memory, review memory, theme memory, and segment memory. Memory exists so the agent can answer why it recommended something, whether it worked, and what it learned.

### Watchlist Output

The primary output is a watchlist and research cards. Recommendation states should include ignore, monitor, high-priority watchlist, and action candidate, but any actual trading decision remains outside this system.

### Review and Meta-learning

The system must review recommendations, label errors, measure signal performance, and propose improvements. Meta-learning can suggest changes to weights, prompts, signals, data sources, and module design, but medium and high-risk changes require experiments and human approval.

## Success Criteria

The system is useful when it can:

- generate a stable weekly Top 20 watchlist,
- explain each candidate with evidence and disconfirming conditions,
- preserve every recommendation with data, prompt, model, and scoring versions,
- review 1-month, 3-month, and 6-month outcomes,
- identify false-positive patterns,
- and improve the research process without erasing auditability.
