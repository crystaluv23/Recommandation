# Skill: Order Confirmation Disclosed

## Purpose
Determine whether, within the lookback window (180 days before as_of), the company or its official filings/press releases disclose a new customer order, contract, offtake agreement, or binding award with a named counterparty or named program and a stated or implied value, volume, or delivery schedule.

## Inputs
- as_of: ISO-8601 timestamp
- documents: list of documents, each with source_type, published_at, available_at, content

## Lookback Window
Only consider documents with published_at >= as_of - 180 days and <= as_of.

## Source Families
Consider documents from: filing, news, transcript, 10-k, 10-q, 8-k, company_news, sec_filing, earnings_call.

## Semantic Condition
A qualifying event is a new customer order, contract, offtake agreement, or binding award that:
- is disclosed by the company or its official filings/press releases;
- names a counterparty or program;
- states or implies a value, volume, or delivery schedule;
- meets the materiality threshold: value >= $1,000,000 or volume >= 1,000 units (or equivalent). Below threshold is neutral.

## Classification Rules
- **positive**: A confirmed qualifying event is present in at least one document within the lookback window. This includes explicit announcements of new orders, contracts, offtake agreements, or binding awards that meet the materiality threshold and name a counterparty/program. Paraphrases that clearly confirm such an event also qualify. A binding award with only a stated maximum or ceiling value does not meet the materiality threshold unless a minimum or expected value is stated or implied.
- **negative**: An explicit cancellation or denial of a qualifying event is present in at least one document within the lookback window. This includes statements that a previously announced order, contract, offtake agreement, or binding award has been cancelled, terminated, or denied.
- **neutral**: Documents within the lookback window are adequate but contain only proposals, memoranda, non-binding intent, lookalikes, below-threshold mentions, or non-qualifying arrangements. Proposals are statements of possible future agreements without confirmation. Non-binding intent includes expressions of interest, exploratory discussions, or memoranda of understanding. Lookalikes are generic mentions of orders/contracts without any specific new event. Below-threshold mentions are qualifying events that do not meet the materiality threshold. Non-qualifying arrangements include distribution agreements, joint pursuit agreements, and similar arrangements that do not themselves constitute a new customer order, contract, offtake agreement, or binding award with a stated or implied value, volume, or delivery schedule.
- **unavailable**: No documents within the lookback window, or the available documents are genuinely insufficient to make a judgment (e.g., only cover pages, boilerplate, or text that does not address orders/contracts). Post-cutoff-only corpora (all documents published after as_of) also yield unavailable.

## Evidence Citation
For positive: cite the verbatim span that confirms the qualifying event.
For negative: cite the verbatim span that cancels or denies the event.
For neutral: cite the verbatim span that shows the proposal, non-binding intent, lookalike, below-threshold mention, or non-qualifying arrangement.
For unavailable: explain why evidence is insufficient.

## Output
Return a JSON object with:
- value: one of "positive", "neutral", "negative", "unavailable"
- confidence: float between 0 and 1
- evidence: list of cited spans (verbatim) with document_id and text
