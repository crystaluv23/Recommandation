# Data / Structured

## Status
Started

## Purpose

Normalize source outputs into stable, point-in-time `FeatureRecord` values for scanners, packets, scoring, review, and reports. This module turns raw prices, profile fields, valuation ratios, earnings surprise data, and SEC company facts into auditable features without deciding thesis or score semantics.

## External Interface

The implementation exposes:

- `normalize_price_features()` for daily OHLCV windows, latest close, liquidity, and trailing returns.
- `normalize_alpha_vantage_overview()` for profile, valuation, analyst target, and high-level financial fields from Alpha Vantage overview snapshots.
- `normalize_sec_company_facts()` for selected SEC XBRL company facts using
  filing-date availability, including revenue, profit, cash flow, assets,
  liabilities, equity, and EPS tags when available.
- `company_profile_from_features()` for building `CompanyProfile` from listing metadata and normalized features.

## Responsibilities

- Build structured features used by scanner, research packet construction, scoring, review, and reports.
- Preserve source key, source id when available, retrieval time, feature availability date, optional period end, window size, and data quality.
- Emit explicit missing features when a value, provider field, or required lookback window is unavailable.
- Keep feature names descriptive but non-prescriptive: a feature may inform later scoring, but this module does not score it.

## Dependencies

- Parent spec: [`../data.md`](../data.md).
- Consumes [`sources.md`](sources.md).
- Uses [`../models.md`](../models.md) for `FeatureRecord` and `CompanyProfile`.

## Invariants

- Feature normalization must not inspect observations, facts, or documents unavailable as of the requested date.
- Missing data must be explicit through `DataQuality.MISSING` and `unavailable_reason`.
- SEC fact availability is the filing date, not merely the fiscal period end.
- Earnings surprise features may enter historical packets only when a reported
  date or provider event date is available and on or before the packet
  `as_of_date`; rows without such a date must be ignored rather than guessed.
- Vendor valuation ratios are convenience inputs and do not override SEC authority facts.

## Testing

Use fixture price bars, Alpha Vantage overview payloads, and SEC company facts to verify future-date exclusion, source metadata, missing-value semantics, and profile construction.
