"""Run a deterministic local cold-start seed case set."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from stock_opportunity_agent.cases import HistoricalCase, OutcomeDefinition, default_outcome_definition
from stock_opportunity_agent.config import AgentConfig
from stock_opportunity_agent.data import SecurityListing, build_research_packet, company_profile_from_features
from stock_opportunity_agent.models import (
    Catalyst,
    CatalystStatus,
    DataQuality,
    EvidenceItem,
    EvidenceKind,
    FeatureRecord,
    VersionStamp,
)
from stock_opportunity_agent.orchestration import run_cold_start_case_learning


STAMP = datetime(2026, 5, 3, tzinfo=timezone.utc)
AS_OF = date(2026, 5, 3)
VERSION = VersionStamp(
    prompt_version="prompt-v0.1",
    scoring_version="scoring-v0.1",
    signal_version="signals-v0.1",
    model_version="seed-offline",
    data_pipeline_version="data-pipeline-v0.1",
    config_version="config-v0.1",
)


def main() -> None:
    """Execute the local seed cold-start run."""

    definition = default_outcome_definition()
    cases = [
        _case(
            "winner-accelerator-1",
            "AIX1",
            "AI Infrastructure Co.",
            "Semiconductors",
            "Accelerators",
            "ai-accelerator-cycle",
            outcome_return=1.45,
            feature_values={
                "financial.revenue_growth_yoy": 0.42,
                "financial.earnings_growth_yoy": 0.78,
                "financial.operating_margin_ttm": 0.24,
                "price.latest_close": 48.0,
                "price.return_20d": 0.12,
                "price.return_60d": 0.31,
                "price.return_120d": 0.28,
                "price.average_daily_dollar_volume_20d": 180_000_000.0,
                "price.average_daily_dollar_volume_60d": 112_000_000.0,
                "valuation.pe_ratio": 27.0,
                "valuation.price_to_sales_ttm": 6.4,
                "analyst.target_price": 66.0,
            },
            catalyst_names=("Capacity expansion update", "Major customer product cycle"),
            definition=definition,
        ),
        _case(
            "winner-power-1",
            "PWR1",
            "Grid Equipment Co.",
            "Power Equipment",
            "Electrical Equipment",
            "power-grid-cycle",
            outcome_return=0.88,
            feature_values={
                "financial.revenue_growth_yoy": 0.33,
                "financial.earnings_growth_yoy": 0.55,
                "financial.operating_margin_ttm": 0.18,
                "price.latest_close": 36.0,
                "price.return_20d": 0.09,
                "price.return_60d": 0.22,
                "price.return_120d": 0.18,
                "price.average_daily_dollar_volume_20d": 92_000_000.0,
                "price.average_daily_dollar_volume_60d": 70_000_000.0,
                "valuation.pe_ratio": 24.0,
                "valuation.price_to_sales_ttm": 3.1,
                "analyst.target_price": 48.0,
            },
            catalyst_names=("Backlog disclosure",),
            definition=definition,
        ),
        _case(
            "control-accelerator-1",
            "AIC1",
            "Legacy Compute Co.",
            "Semiconductors",
            "Processors",
            "ai-accelerator-cycle",
            outcome_return=0.08,
            feature_values={
                "financial.revenue_growth_yoy": 0.07,
                "financial.earnings_growth_yoy": -0.04,
                "financial.operating_margin_ttm": 0.08,
                "price.latest_close": 52.0,
                "price.return_20d": 0.01,
                "price.return_60d": 0.04,
                "price.return_120d": -0.03,
                "price.average_daily_dollar_volume_20d": 85_000_000.0,
                "price.average_daily_dollar_volume_60d": 83_000_000.0,
                "valuation.pe_ratio": 38.0,
                "valuation.price_to_sales_ttm": 8.8,
                "analyst.target_price": 55.0,
            },
            catalyst_names=(),
            definition=definition,
        ),
        _case(
            "failure-power-1",
            "PWF1",
            "Slow Grid Supplier Co.",
            "Power Equipment",
            "Electrical Equipment",
            "power-grid-cycle",
            outcome_return=-0.25,
            feature_values={
                "financial.revenue_growth_yoy": 0.04,
                "financial.earnings_growth_yoy": -0.12,
                "financial.operating_margin_ttm": 0.05,
                "price.latest_close": 29.0,
                "price.return_20d": -0.02,
                "price.return_60d": 0.03,
                "price.return_120d": -0.08,
                "price.average_daily_dollar_volume_20d": 41_000_000.0,
                "price.average_daily_dollar_volume_60d": 45_000_000.0,
                "valuation.pe_ratio": 44.0,
                "valuation.price_to_sales_ttm": 4.9,
                "analyst.target_price": 31.0,
            },
            catalyst_names=("Industry conference",),
            definition=definition,
        ),
    ]
    output = run_cold_start_case_learning(
        cases,
        config=AgentConfig(),
        output_dir=Path("reports/cold_start/seed-2026-05-03"),
        run_id="cold-start-seed-2026-05-03",
        created_at=STAMP,
    )
    print(output.signal_logic_path)


def _case(
    case_id: str,
    symbol: str,
    company_name: str,
    sector: str,
    industry: str,
    matched_group_id: str,
    *,
    outcome_return: float,
    feature_values: dict[str, float],
    catalyst_names: tuple[str, ...],
    definition: OutcomeDefinition,
) -> HistoricalCase:
    label = definition.label_return(outcome_return, trading_days=definition.min_trading_days)
    features = [_feature(symbol, name, value) for name, value in feature_values.items()]
    features.extend(
        [
            _feature(symbol, "profile.sector", sector),
            _feature(symbol, "profile.industry", industry),
            _feature(symbol, "valuation.market_cap_usd", 12_000_000_000.0),
        ]
    )
    listing = SecurityListing(
        symbol=symbol,
        name=company_name,
        exchange="NASDAQ",
        asset_type="common_stock",
        status="active",
        source="seed",
        retrieved_at=STAMP,
    )
    company = company_profile_from_features(listing, features, AS_OF)
    catalysts = [
        Catalyst(
            name=name,
            expected_date=AS_OF + timedelta(days=45 + index * 30),
            status=CatalystStatus.EXPECTED,
            evidence=[
                EvidenceItem(
                    kind=EvidenceKind.NEWS,
                    summary=f"{name} was known before the outcome window.",
                    as_of_date=AS_OF,
                    source_id=f"seed:{symbol}:catalyst:{index}",
                    published_date=AS_OF,
                )
            ],
        )
        for index, name in enumerate(catalyst_names)
    ]
    packet = build_research_packet(
        symbol=symbol,
        as_of_date=AS_OF,
        company=company,
        features=features,
        version=VERSION,
        catalysts=catalysts,
        theme_ids=[matched_group_id],
        packet_id=f"{case_id}:packet",
        created_at=STAMP,
    )
    return HistoricalCase(
        case_id=case_id,
        label=label,
        packet=packet,
        outcome_start_date=AS_OF + timedelta(days=1),
        outcome_end_date=AS_OF + timedelta(days=181),
        outcome_return=outcome_return,
        matched_group_id=matched_group_id,
        hidden_outcome_summary="Outcome label hidden from as-of packet and signal measurement.",
        outcome_definition_id=definition.definition_id,
    )


def _feature(symbol: str, name: str, value: float | str) -> FeatureRecord:
    quality = DataQuality.CONFIRMED
    return FeatureRecord(
        name=name,
        value=value,
        as_of_date=AS_OF,
        source="seed",
        retrieved_at=STAMP,
        data_quality=quality,
        source_id=f"seed:{symbol}:{name}",
        period_end_date=AS_OF,
    )


if __name__ == "__main__":
    main()
