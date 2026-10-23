# Skill: cash_burn_rate_elevated

## Purpose
Determine whether a company has an elevated cash burn rate based on point-in-time documents within the lookback window.

## Definition
Cash burn rate = abs(operating cash flow) / cash and cash equivalents, when operating cash flow is negative. If operating cash flow is positive, burn rate is zero. Elevated if ratio >= burn_threshold (default 0.10). Higher ratio means faster cash consumption.

## Inputs
- Source types: company_facts, financials.
- Lookback window: as_of minus lookback_days (default 550).
- Only documents with published_at <= as_of and available_at <= as_of are usable.

## Procedure
1. Filter documents to lookback window and source types.
2. Extract verbatim operating cash flow and cash and cash equivalents facts with exact spans, source, and timestamp.
3. Match periods: operating cash flow is a duration fact; cash is an instant fact. Use the closest cash balance at or before the operating cash flow period end.
4. If operating cash flow is negative, compute ratio = abs(OCF) / cash. If OCF >= 0, ratio = 0.
5. Compare to threshold.
6. Cite supporting and counter spans.

## Classification rules
- confirmed qualifying event: Documents contain adequate point-in-time evidence of negative operating cash flow and cash reserves such that the computed ratio >= threshold, or an explicit statement of high cash burn. Expected: positive.
- mere proposals or memoranda: Documents contain only a proposal, memorandum, or non-binding intent to increase cash burn or spending, without actual point-in-time operating cash flow and cash facts. Expected: neutral.
- cancellations or denials: Documents explicitly cancel, deny, or contradict a previously reported high cash burn, or report positive operating cash flow and no material cash consumption. Expected: negative.
- below-threshold amounts: Documents contain actual operating cash flow and cash facts, but the computed ratio < threshold. Expected: neutral.
- paraphrases: Documents paraphrase a confirmed qualifying high-burn event with adequate point-in-time facts. Expected: positive.
- lookalikes: Documents mention 'burn rate' or similar terms but refer to non-cash burn (e.g., marketing spend, calorie burn) or otherwise do not measure operating cash outflow relative to cash. Expected: neutral.
- post-cutoff documents: Documents published or available after the as_of are excluded. If only post-cutoff evidence exists, expected: unavailable.
- evidence-insufficient: Documents are vague, lack verbatim operating cash flow and cash facts, or cannot support a point-in-time measurement. Expected: unavailable.

## Output
Return JSON:
{
  'value': 'positive' | 'neutral' | 'negative' | 'unavailable',
  'confidence': float,
  'evidence': [{'ref': '...', 'span': '...', 'source': '...', 'timestamp': '...'}],
  'counter_evidence': [...]
}
