"""Run a deterministic local cold-start seed case set."""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from stock_opportunity_agent.cases import ControlMatchCriteria, HistoricalCase, OutcomeDefinition, default_outcome_definition
from stock_opportunity_agent.config import AgentConfig, PromptConfig
from stock_opportunity_agent.data import PriceBar, SecurityListing, build_research_packet, company_profile_from_features
from stock_opportunity_agent.memory import FileSignalLibrary, FileThemeLibrary
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
from stock_opportunity_agent.llm.openai import OpenAIChatClient
from stock_opportunity_agent.llm.openrouter import OpenRouterChatClient
from stock_opportunity_agent.research import (
    CompositeInflectionResearcher,
    FactorInflectionResearcher,
    OpenAIBlindCaseResearcher,
    OpenAIWebInflectionResearcher,
)


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

    args = _parse_args()
    _load_local_env()
    config = _config_for_args(args)
    researcher = None
    factor_researcher = FactorInflectionResearcher(_seed_bars_by_symbol(), min_forward_return=0.50)
    inflection_researcher = factor_researcher
    if args.openai:
        client = OpenAIChatClient.from_config(config.prompts)
        researcher = OpenAIBlindCaseResearcher(client)
        inflection_researcher = CompositeInflectionResearcher((factor_researcher, OpenAIWebInflectionResearcher(client)))
    elif args.openrouter:
        client = OpenRouterChatClient(args.openrouter_model, _required_env("OPENROUTER_API_KEY"))
        researcher = OpenAIBlindCaseResearcher(client)
        inflection_researcher = CompositeInflectionResearcher((factor_researcher, OpenAIWebInflectionResearcher(client)))
    elif args.openai_inflection:
        inflection_researcher = CompositeInflectionResearcher(
            (factor_researcher, OpenAIWebInflectionResearcher(OpenAIChatClient.from_config(config.prompts)))
        )
    elif args.openrouter_inflection:
        inflection_researcher = CompositeInflectionResearcher(
            (
                factor_researcher,
                OpenAIWebInflectionResearcher(
                    OpenRouterChatClient(args.openrouter_model, _required_env("OPENROUTER_API_KEY"))
                ),
            )
        )
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
        config=config,
        output_dir=Path(args.output_dir),
        run_id=args.run_id,
        created_at=STAMP,
        signal_library=FileSignalLibrary(".agent_state/memory/signals"),
        theme_library=FileThemeLibrary(".agent_state/memory/themes"),
        control_match_criteria=ControlMatchCriteria(max_controls_per_winner=2),
        blind_researcher=researcher,
        inflection_researcher=inflection_researcher,
        progress=print if not args.quiet else None,
    )
    if args.quiet:
        print(output.signal_logic_path)


def _parse_args():
    parser = argparse.ArgumentParser(description="Run the deterministic cold-start seed case set.")
    parser.add_argument(
        "--openai",
        action="store_true",
        help="Use OpenAI for both web-enabled inflection discovery and web-disabled blind analysis.",
    )
    parser.add_argument(
        "--openai-inflection",
        action="store_true",
        help="Use OpenAI web search for retrospective inflection discovery only.",
    )
    parser.add_argument(
        "--openrouter",
        action="store_true",
        help="Use OpenRouter for both web-enabled inflection discovery and web-disabled blind analysis.",
    )
    parser.add_argument(
        "--openrouter-inflection",
        action="store_true",
        help="Use OpenRouter web search for retrospective inflection discovery only.",
    )
    parser.add_argument(
        "--openrouter-model",
        default="openai/gpt-5.5",
        help="OpenRouter model id used when --openrouter or --openrouter-inflection is set.",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/cold_start/seed-2026-05-03",
        help="Directory for cold-start report artifacts.",
    )
    parser.add_argument(
        "--run-id",
        default="cold-start-seed-2026-05-03",
        help="Run identifier written into manifests and artifacts.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the final signal-logic path.",
    )
    return parser.parse_args()


def _config_for_args(args) -> AgentConfig:
    if args.openrouter or args.openrouter_inflection:
        return AgentConfig(
            prompts=PromptConfig(
                model_version=args.openrouter_model,
                openai_api_key_env_var="OPENROUTER_API_KEY",
                openai_base_url="https://openrouter.ai/api/v1",
            )
        )
    return AgentConfig()


def _load_local_env(path: str = ".env.local") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


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


def _seed_bars_by_symbol() -> dict[str, tuple[PriceBar, ...]]:
    return {
        symbol: tuple(_seed_bars(symbol, base_close=base, surge=surge))
        for symbol, base, surge in (
            ("AIX1", 42.0, True),
            ("PWR1", 31.0, True),
            ("AIC1", 50.0, False),
            ("PWF1", 29.0, False),
        )
    }


def _seed_bars(symbol: str, *, base_close: float, surge: bool) -> list[PriceBar]:
    bars: list[PriceBar] = []
    close = base_close
    start = AS_OF
    for index in range(181):
        if surge and index == 30:
            close *= 1.22
            volume = 4_000_000
        elif surge and index > 30:
            close *= 1.010
            volume = 2_400_000
        elif not surge and index > 30:
            close *= 0.999
            volume = 900_000
        else:
            close *= 1.001
            volume = 1_000_000
        bars.append(
            PriceBar(
                symbol=symbol,
                as_of_date=start + timedelta(days=index),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=volume,
                source="seed",
                retrieved_at=STAMP,
            )
        )
    return bars


if __name__ == "__main__":
    main()
