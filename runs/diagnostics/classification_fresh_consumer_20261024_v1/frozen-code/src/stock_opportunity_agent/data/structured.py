"""Structured feature normalization for point-in-time data packets."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.data.sources.core import PriceBar, SecurityListing
from stock_opportunity_agent.models import (
    CompanyProfile,
    DataQuality,
    FeatureRecord,
    TickerRef,
    ValidationError,
)


PRICE_FEATURE_WINDOWS = (20, 60, 120)

ALPHA_VANTAGE_OVERVIEW_FEATURES: dict[str, tuple[str, str]] = {
    "Sector": ("profile.sector", "text"),
    "Industry": ("profile.industry", "text"),
    "Exchange": ("profile.exchange", "text"),
    "MarketCapitalization": ("valuation.market_cap_usd", "number"),
    "PERatio": ("valuation.pe_ratio", "number"),
    "PEGRatio": ("valuation.peg_ratio", "number"),
    "PriceToSalesRatioTTM": ("valuation.price_to_sales_ttm", "number"),
    "PriceToBookRatio": ("valuation.price_to_book", "number"),
    "EVToRevenue": ("valuation.ev_to_revenue", "number"),
    "EVToEBITDA": ("valuation.ev_to_ebitda", "number"),
    "ProfitMargin": ("financial.profit_margin", "number"),
    "OperatingMarginTTM": ("financial.operating_margin_ttm", "number"),
    "QuarterlyRevenueGrowthYOY": ("financial.revenue_growth_yoy", "number"),
    "QuarterlyEarningsGrowthYOY": ("financial.earnings_growth_yoy", "number"),
    "AnalystTargetPrice": ("analyst.target_price", "number"),
}

SEC_COMPANY_FACT_FEATURE_TAGS: dict[str, tuple[str, ...]] = {
    "financial.revenue_usd": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "financial.gross_profit_usd": ("GrossProfit",),
    "financial.net_income_usd": ("NetIncomeLoss",),
    "financial.operating_income_usd": ("OperatingIncomeLoss",),
    "financial.operating_cash_flow_usd": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "financial.capex_usd": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "financial.cash_and_equivalents_usd": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "financial.total_debt_usd": (
        "LongTermDebtAndFinanceLeaseObligations",
        "LongTermDebt",
        "LongTermDebtNoncurrent",
    ),
    "financial.assets_usd": ("Assets",),
    "financial.liabilities_usd": ("Liabilities",),
    "financial.stockholders_equity_usd": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "financial.diluted_eps": ("EarningsPerShareDiluted",),
    "financial.basic_eps": ("EarningsPerShareBasic",),
}


def normalize_price_features(
    bars: Iterable[PriceBar],
    as_of_date: date,
    *,
    windows: Iterable[int] = PRICE_FEATURE_WINDOWS,
    retrieved_at: datetime | None = None,
) -> list[FeatureRecord]:
    """Normalize daily bars into latest price, liquidity, and return features.

    Future bars are ignored. Windowed features are explicit missing records when
    there are not enough point-in-time observations.
    """

    ordered = sorted((bar for bar in bars if bar.as_of_date <= as_of_date), key=lambda bar: bar.as_of_date)
    stamp = retrieved_at or _latest_retrieved_at(ordered) or _default_retrieved_at(as_of_date)
    source = _source_from_bars(ordered)
    features: list[FeatureRecord] = []

    if not ordered:
        for name in ("price.latest_close", "price.latest_volume"):
            features.append(_missing_feature(name, as_of_date, source, stamp, "no price bars available as of date"))
        for window in windows:
            _validate_window(window)
            features.append(
                _missing_feature(
                    f"price.average_daily_dollar_volume_{window}d",
                    as_of_date,
                    source,
                    stamp,
                    f"no price bars available for {window}-day window",
                    window_days=window,
                )
            )
            features.append(
                _missing_feature(
                    f"price.return_{window}d",
                    as_of_date,
                    source,
                    stamp,
                    f"no price bars available for {window}-day return",
                    window_days=window,
                )
            )
        return features

    latest = ordered[-1]
    latest_source = latest.source
    features.extend(
        [
            FeatureRecord(
                name="price.latest_close",
                value=latest.close,
                as_of_date=latest.as_of_date,
                source=latest_source,
                retrieved_at=latest.retrieved_at,
                source_id=f"{latest_source}:{latest.symbol}:price.latest_close:{latest.as_of_date.isoformat()}",
                period_end_date=latest.as_of_date,
            ),
            FeatureRecord(
                name="price.latest_volume",
                value=latest.volume,
                as_of_date=latest.as_of_date,
                source=latest_source,
                retrieved_at=latest.retrieved_at,
                source_id=f"{latest_source}:{latest.symbol}:price.latest_volume:{latest.as_of_date.isoformat()}",
                period_end_date=latest.as_of_date,
            ),
        ]
    )

    for window in windows:
        _validate_window(window)
        if len(ordered) >= window:
            window_bars = ordered[-window:]
            average_dollar_volume = sum(bar.close * bar.volume for bar in window_bars) / window
            features.append(
                FeatureRecord(
                    name=f"price.average_daily_dollar_volume_{window}d",
                    value=average_dollar_volume,
                    as_of_date=latest.as_of_date,
                    source=source,
                    retrieved_at=stamp,
                    source_id=f"{source}:{latest.symbol}:price.average_daily_dollar_volume_{window}d:{latest.as_of_date.isoformat()}",
                    period_end_date=latest.as_of_date,
                    window_days=window,
                )
            )
        else:
            features.append(
                _missing_feature(
                    f"price.average_daily_dollar_volume_{window}d",
                    as_of_date,
                    source,
                    stamp,
                    f"only {len(ordered)} price bars available for {window}-day window",
                    window_days=window,
                )
            )

        if len(ordered) > window:
            base = ordered[-window - 1]
            if base.close == 0:
                features.append(
                    _missing_feature(
                        f"price.return_{window}d",
                        as_of_date,
                        source,
                        stamp,
                        "base close is zero",
                        window_days=window,
                    )
                )
            else:
                features.append(
                    FeatureRecord(
                        name=f"price.return_{window}d",
                        value=(latest.close / base.close) - 1,
                        as_of_date=latest.as_of_date,
                        source=source,
                        retrieved_at=stamp,
                        source_id=f"{source}:{latest.symbol}:price.return_{window}d:{latest.as_of_date.isoformat()}",
                        period_end_date=latest.as_of_date,
                        window_days=window,
                    )
                )
        else:
            features.append(
                _missing_feature(
                    f"price.return_{window}d",
                    as_of_date,
                    source,
                    stamp,
                    f"only {len(ordered)} price bars available for {window}-day return",
                    window_days=window,
                )
            )

    return features


def normalize_alpha_vantage_overview(
    overview: Mapping[str, Any],
    as_of_date: date,
    retrieved_at: datetime,
) -> list[FeatureRecord]:
    """Normalize Alpha Vantage ``OVERVIEW`` fields into profile and valuation features."""

    symbol = str(overview.get("Symbol") or "UNKNOWN").upper()
    features: list[FeatureRecord] = []
    for raw_field, (feature_name, value_kind) in ALPHA_VANTAGE_OVERVIEW_FEATURES.items():
        raw_value = overview.get(raw_field)
        if value_kind == "number":
            value = _optional_number(raw_value, raw_field)
        else:
            value = _optional_text(raw_value)
        if value is None:
            features.append(
                _missing_feature(
                    feature_name,
                    as_of_date,
                    "alpha_vantage",
                    retrieved_at,
                    f"{raw_field} unavailable",
                    source_id=f"alpha_vantage:{symbol}:OVERVIEW:{raw_field}",
                )
            )
            continue
        features.append(
            FeatureRecord(
                name=feature_name,
                value=value,
                as_of_date=as_of_date,
                source="alpha_vantage",
                retrieved_at=retrieved_at,
                source_id=f"alpha_vantage:{symbol}:OVERVIEW:{raw_field}",
            )
        )
    return features


def normalize_sec_company_facts(
    company_facts: Mapping[str, Any],
    as_of_date: date,
    retrieved_at: datetime,
    *,
    feature_tags: Mapping[str, tuple[str, ...]] = SEC_COMPANY_FACT_FEATURE_TAGS,
) -> list[FeatureRecord]:
    """Normalize selected SEC XBRL company facts using filing-date availability."""

    cik = str(company_facts.get("cik") or "unknown")
    facts = company_facts.get("facts")
    us_gaap = facts.get("us-gaap") if isinstance(facts, Mapping) else None
    if not isinstance(us_gaap, Mapping):
        return [
            _missing_feature(name, as_of_date, "sec_edgar", retrieved_at, "SEC company facts missing us-gaap facts")
            for name in feature_tags
        ]

    features: list[FeatureRecord] = []
    for feature_name, tags in feature_tags.items():
        selected = _select_sec_fact(us_gaap, tags, as_of_date)
        if selected is None:
            features.append(
                _missing_feature(
                    feature_name,
                    as_of_date,
                    "sec_edgar",
                    retrieved_at,
                    "no SEC fact filed by as_of_date",
                )
            )
            continue
        tag, row, value, filed_date, end_date = selected
        accession = str(row.get("accn") or "unknown")
        features.append(
            FeatureRecord(
                name=feature_name,
                value=value,
                as_of_date=filed_date,
                source="sec_edgar",
                retrieved_at=retrieved_at,
                source_id=f"sec:{cik}:{accession}:{tag}",
                period_end_date=end_date,
            )
        )
    return features


def company_profile_from_features(
    listing: SecurityListing,
    features: Iterable[FeatureRecord],
    as_of_date: date,
) -> CompanyProfile:
    """Build a domain company profile from listing metadata and normalized features."""

    available = _latest_available_features(features, as_of_date)
    sector = _text_feature(available.get("profile.sector")) or "Unknown"
    industry = _text_feature(available.get("profile.industry")) or "Unknown"
    market_cap = _float_feature(available.get("valuation.market_cap_usd"))
    average_dollar_volume = _float_feature(available.get("price.average_daily_dollar_volume_20d"))
    quality = DataQuality.CONFIRMED
    if sector == "Unknown" or industry == "Unknown":
        quality = DataQuality.MISSING

    return CompanyProfile(
        ticker=TickerRef(
            listing.symbol,
            exchange=listing.exchange,
            company_name=listing.name,
        ),
        sector=sector,
        industry=industry,
        market_cap_usd=market_cap,
        average_daily_dollar_volume=average_dollar_volume,
        data_quality=quality,
    )


def _select_sec_fact(
    us_gaap: Mapping[str, Any],
    tags: tuple[str, ...],
    as_of_date: date,
) -> tuple[str, Mapping[str, Any], float | int, date, date | None] | None:
    candidates: list[tuple[date, date, int, int, str, Mapping[str, Any], float | int, date | None]] = []
    for tag_order, tag in enumerate(tags):
        fact = us_gaap.get(tag)
        units = fact.get("units") if isinstance(fact, Mapping) else None
        unit_row_groups = _fact_unit_rows(units)
        if not unit_row_groups:
            continue
        for unit_rows in unit_row_groups:
            for row_index, row in enumerate(unit_rows):
                if not isinstance(row, Mapping):
                    continue
                filed_date = _date_from(row.get("filed"))
                if filed_date is None or filed_date > as_of_date:
                    continue
                end_date = _date_from(row.get("end"))
                if end_date is not None and end_date > as_of_date:
                    continue
                value = row.get("val")
                if not isinstance(value, (int, float)):
                    continue
                candidates.append((filed_date, end_date or date.min, -tag_order, row_index, tag, row, value, end_date))
    if not candidates:
        return None
    filed_date, _end_sort, _tag_rank, _row_index, tag, row, value, end_date = max(candidates)
    return tag, row, value, filed_date, end_date


def _fact_unit_rows(units: Any) -> list[list[Any]]:
    if not isinstance(units, Mapping):
        return []
    preferred = units.get("USD")
    if isinstance(preferred, list):
        return [preferred]
    return [rows for rows in units.values() if isinstance(rows, list)]


def _latest_available_features(
    features: Iterable[FeatureRecord],
    as_of_date: date,
) -> dict[str, FeatureRecord]:
    selected: dict[str, FeatureRecord] = {}
    for feature in features:
        if feature.as_of_date > as_of_date or feature.data_quality is DataQuality.MISSING:
            continue
        current = selected.get(feature.name)
        if current is None or feature.as_of_date > current.as_of_date:
            selected[feature.name] = feature
    return selected


def _missing_feature(
    name: str,
    as_of_date: date,
    source: str,
    retrieved_at: datetime,
    reason: str,
    *,
    source_id: str | None = None,
    window_days: int | None = None,
) -> FeatureRecord:
    return FeatureRecord(
        name=name,
        value=None,
        as_of_date=as_of_date,
        source=source,
        retrieved_at=retrieved_at,
        data_quality=DataQuality.MISSING,
        source_id=source_id,
        window_days=window_days,
        unavailable_reason=reason,
    )


def _source_from_bars(bars: list[PriceBar]) -> str:
    if not bars:
        return "unavailable"
    sources = {bar.source for bar in bars}
    if len(sources) == 1:
        return bars[-1].source
    return "mixed"


def _latest_retrieved_at(bars: list[PriceBar]) -> datetime | None:
    if not bars:
        return None
    return max(bar.retrieved_at for bar in bars)


def _default_retrieved_at(as_of_date: date) -> datetime:
    return datetime.combine(as_of_date, time.min, tzinfo=timezone.utc)


def _optional_number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan", "-", "n/a"}:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be numeric when present") from exc


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan", "-", "n/a"}:
        return None
    return text


def _text_feature(feature: FeatureRecord | None) -> str | None:
    if feature is None or feature.value is None:
        return None
    return str(feature.value)


def _float_feature(feature: FeatureRecord | None) -> float | None:
    if feature is None or feature.value is None:
        return None
    if not isinstance(feature.value, (int, float)):
        return None
    return float(feature.value)


def _date_from(value: Any) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value))


def _validate_window(window: int) -> None:
    if window < 1:
        raise ValidationError("price feature windows must be positive")
