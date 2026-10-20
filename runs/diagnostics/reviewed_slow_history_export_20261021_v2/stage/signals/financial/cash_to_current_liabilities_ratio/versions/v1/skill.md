# Skill: cash_to_current_liabilities_ratio

## Purpose
Compute the ratio of latest CashAndCashEquivalentsAtCarryingValue to latest LiabilitiesCurrent for a company as of a point in time, and classify the liquidity signal.

## Inputs
- as_of: ISO-8601 timestamp
- company_id: string
- documents: list of documents, each with source_type, published_at, available_at, content. Content contains SEC company facts as JSON objects with keys accn, end, filed, form, fp, fy, val. Each document also labels the concept: either CashAndCashEquivalentsAtCarryingValue or LiabilitiesCurrent.

## Procedure
1. Filter documents to those with source_type in {company_facts, financials} and available_at <= as_of.
2. From each document, extract the concept label and parse the JSON fact object. The fact's period end is the 'end' field. The value is the 'val' field.
3. For the given company_id, keep only facts whose accn prefix matches company_id (the first 10 digits) OR assume all documents are for the given company_id if no company_id in fact.
4. From the CashAndCashEquivalentsAtCarryingValue facts, select the one with the latest 'end' <= as_of.
5. From the LiabilitiesCurrent facts, select the one with the latest 'end' <= as_of.
6. If either latest fact is missing, return {"value": "unavailable", "confidence": 0.0}.
7. Compute ratio = cash_val / liabilities_val. If liabilities_val is zero, return unavailable.
8. Let positive_min = parameters.positive_min (default 1.0) and negative_max = parameters.negative_max (default 1.0).
9. If ratio >= positive_min, return {"value": "positive", "confidence": 0.9}.
10. Else if ratio <= negative_max, return {"value": "negative", "confidence": 0.9}.
11. Else return {"value": "neutral", "confidence": 0.8}.

## Evidence
Always cite the exact verbatim span of the cash fact and the liabilities fact in the output evidence. Do not use any Discovery labels.
