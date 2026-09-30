# SEC Revenue Tag Mixing Breaks Deterministic Factors

visit_times: 0

## Trigger

When auditing or changing deterministic SEC-fact factors in `signal_library.py`
(revenue growth/acceleration, margins, cash ratios), or interpreting implausible
deterministic values in blind-prediction contexts.

## Lesson

Literal, point-in-time-correct citations do not make a computed factor correct.
Company Facts routinely contain several revenue tags for the same
(start, end, unit) period with wildly different values: the total under
`Revenues` and a partial slice (or zero) under
`RevenueFromContractWithCustomer(Including|Excluding)AssessedTax`. Two
independent flaws combine into silent garbage:

1. `_duration_series`/`_instant_series` dedupe by period key using static tag
   priority, so a partial or zero value from a "preferred" tag displaces the
   true total (FEIM: 0 displaced $49.8M -> revenue_growth_yoy=-1; Hertz:
   $19M displaced $3.2B -> operating_cash_flow_margin=51.58x).
2. `_yoy_pairs` does not require `current.tag == previous.tag` (the share
   series does), so even non-garbage selections can divide across tags
   (FEIM after the zero-guard fix: +558.8x instead of the true +25.5%).

A zero-value guard alone is insufficient: partial nonzero values and cross-tag
pairing survive it, and `_numeric_result` hardcodes confidence=1.0 with
coverage=sufficient, so garbage reaches the blind predictor with maximum
authority while positive LLM signal results (guidance/order quality) may be
dropped entirely from the compact context.

## Context

Fast round v151, case `cik_0000039020:20250329...` (Frequency Electronics).
The model judged "unlikely" citing revenue_growth_yoy=-1 and
revenue_acceleration=-1.18912 while guidance_acceleration (0.62) and
order_quality (0.7) were positive on funded-backlog evidence. Replay on the
oracle facts reproduced both values exactly; true same-tag growth was +25.5%
(9M) and +38.0% (3M). Hertz (`cik_0000004457`) showed the same displacement
class with a nonzero partial value (margin 51.58x vs true 0.307).

## How to Apply

1. Require same-tag period pairing in `_yoy_pairs` (align with
   `_latest_share_yoy_pair`) and prefer value-consistent series over static
   tag priority when several tags cover the same period.
2. Add plausibility guards before `_numeric_result` (e.g. zero current
   revenue, |growth| or |margin| beyond sane bounds -> unavailable), and never
   publish confidence=1.0/sufficient for a computation whose inputs are
   suspect.
3. When a deterministic factor contradicts filing prose (e.g. "sharp YoY
   revenue improvement" vs growth=-1), treat the deterministic value as the
   suspect, not the prose; replay the exact function on the exact facts.
4. Audit the compact blind-prediction context, not just signal results: a
   positive result that never reaches the prompt is invisible to the judge.

## Limits

Same-tag pairing reduces coverage when a company switches revenue tags
year-over-year; the guard should then prefer a consistent multi-period series
over a single mixed pair rather than returning unavailable by default.
Absolute-threshold factors (cash_reserves) and finance-sector applicability
(e.g. OCF margin for brokers) are design questions, not this bug.
