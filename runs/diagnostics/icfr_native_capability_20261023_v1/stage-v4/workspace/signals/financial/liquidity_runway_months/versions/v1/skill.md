# Liquidity Runway Months Skill

## Purpose
Judge whether point-in-time evidence supports a low liquidity runway condition using the specified operating-cash-flow liquidity runway measurement.

## Measurement
The skill computes liquidity_runway_months = latest CashAndCashEquivalentsAtCarryingValue / (abs(NetCashProvidedByUsedInOperatingActivities) / months_in_reported_period). Use only documents with available_at <= as_of and published_at within raw_retrieval.lookback_days. Prefer the most recent available_at for the same entity and period when facts conflict. Months_in_reported_period is the number of months in the reported period (for example 3 for a quarter, 12 for a year).

## Classification rules
- confirmed_event: If an adequate point-in-time cash fact and an adequate point-in-time operating cash flow fact for the same period and entity produce liquidity_runway_months <= positive_runway_max_months (default 6), return positive.
- proposal_or_memorandum: If documents contain only proposals, memoranda, non-binding intent, or plans about liquidity without a completed point-in-time cash and operating cash flow pair, return neutral.
- cancellation_or_denial: If documents explicitly cancel or deny the qualifying low-runway condition, return negative.
- below_threshold_amount: If an adequate point-in-time cash and operating cash flow pair produces liquidity_runway_months > positive_runway_max_months and < negative_runway_min_months (default 12), return neutral.
- paraphrase: If a document paraphrases the same qualifying low-runway condition in different words and adequate point-in-time cash and operating cash flow facts are present, return positive.
- lookalike: If a document mentions a runway or cash metric that is not the specified operating-cash-flow liquidity runway, or lacks the required operating cash flow fact, return neutral.
- post_cutoff_only: If all documents are post-cutoff or outside the lookback window, return unavailable.
- insufficient_evidence: If the corpus is empty or contains only isolated facts without adequate narrative and without a complete same-period cash and operating cash flow pair, return unavailable.

## Evidence citation
For every non-unavailable classification, cite up to three verbatim supporting spans and up to three verbatim counter spans from the retrieved documents. Spans must be exact substrings of document content and include document_id, source_type, published_at, available_at. For positive, cite the cash and operating cash flow facts and any paraphrase. For negative, cite the explicit cancellation/denial or no-burn facts. For neutral, cite the proposal, lookalike, or below-threshold facts. For unavailable, no supporting span is required.

## Output
Return a JSON object with fields: value (positive, neutral, negative, or unavailable), confidence (float 0 to 1), evidence (array of cited spans), and reason (short string). Do not invent facts not present in the documents.
