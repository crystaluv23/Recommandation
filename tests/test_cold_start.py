from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from stock_opportunity_agent.cases import (
    CaseOutcomeLabel,
    CaseSlicePlan,
    ControlMatchCriteria,
    HistoricalCase,
    detect_price_inflections,
    OutcomeDefinition,
    default_outcome_definition,
    learn_pre_surge_signal_logic,
    build_historical_cases_from_packets,
    match_controls,
)
from stock_opportunity_agent.config import AgentConfig, StorageConfig
from stock_opportunity_agent.data import PriceBar, SecurityListing, build_research_packet, company_profile_from_features
from stock_opportunity_agent.llm.openai import OpenAIChatClient
from stock_opportunity_agent.models import (
    Catalyst,
    CatalystStatus,
    DataQuality,
    EvidenceItem,
    EvidenceKind,
    FeatureRecord,
    SignalDefinition,
    VersionStamp,
)
from stock_opportunity_agent.memory import FileSignalLibrary
from stock_opportunity_agent.orchestration import run_cold_start_case_learning
from stock_opportunity_agent.research import HeuristicBlindCaseResearcher, OpenAIBlindCaseResearcher
from stock_opportunity_agent.signals import measure_packet_signals


STAMP = datetime(2026, 5, 3, tzinfo=timezone.utc)
AS_OF = date(2026, 5, 3)


class FakeOpenAITransport:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = []

    def post_json(self, url, headers, payload):
        self.calls.append((url, headers, payload))
        return {
            "id": "resp_test",
            "model": "gpt-5.4-mini",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": self.text}],
                }
            ],
        }


def version() -> VersionStamp:
    return VersionStamp(
        prompt_version="prompt-v0.1",
        scoring_version="scoring-v0.1",
        signal_version="signals-v0.1",
        model_version="model-v0.1",
        data_pipeline_version="data-v0.1",
        config_version="config-v0.1",
    )


class ColdStartSignalTests(TestCase):
    def test_outcome_definition_labels_surge_control_and_failure_returns(self) -> None:
        definition = default_outcome_definition()

        self.assertEqual(definition.label_return(0.95, trading_days=80), CaseOutcomeLabel.WINNER)
        self.assertEqual(definition.label_return(0.08, trading_days=80), CaseOutcomeLabel.CONTROL)
        self.assertEqual(definition.label_return(-0.25, trading_days=80), CaseOutcomeLabel.FAILURE)
        self.assertEqual(definition.label_return(0.95, trading_days=20), CaseOutcomeLabel.UNLABELED)

    def test_outcome_definition_is_independently_versionable(self) -> None:
        definition = OutcomeDefinition(
            definition_id="surge-close-return-v0.2",
            version="0.2",
            horizon_days=90,
            winner_min_return=0.50,
            control_min_return=-0.05,
            control_max_return=0.10,
            failure_max_return=-0.15,
            min_trading_days=45,
        )

        self.assertEqual(definition.label_return(0.55, trading_days=45), CaseOutcomeLabel.WINNER)
        self.assertEqual(definition.to_dict()["winner_min_return"], 0.50)

    def test_packet_signal_measurement_uses_structured_point_in_time_features(self) -> None:
        case = make_case(
            "winner-1",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.40,
            earnings_growth=0.70,
            margin=0.22,
            return_20d=0.11,
            return_60d=0.25,
            target_upside=0.35,
            catalyst_count=2,
        )

        observations = measure_packet_signals(case.packet)
        observed_ids = {observation.signal_id for observation in observations if observation.observed}

        self.assertIn("sig-fundamental-revenue-acceleration", observed_ids)
        self.assertIn("sig-market-early-confirmation", observed_ids)
        self.assertTrue(all(item.as_of_date <= AS_OF for observation in observations for item in observation.evidence))

    def test_case_learning_promotes_only_signals_that_separate_winners_from_controls(self) -> None:
        cases = [
            make_case(
                "winner-1",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.40,
                earnings_growth=0.70,
                margin=0.22,
                return_20d=0.11,
                return_60d=0.25,
                target_upside=0.35,
                catalyst_count=2,
            ),
            make_case(
                "control-1",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.03,
                earnings_growth=-0.10,
                margin=0.05,
                return_20d=0.00,
                return_60d=0.02,
                target_upside=0.04,
                catalyst_count=0,
            ),
            make_case(
                "failure-1",
                CaseOutcomeLabel.FAILURE,
                revenue_growth=0.06,
                earnings_growth=-0.05,
                margin=0.04,
                return_20d=-0.02,
                return_60d=0.01,
                target_upside=0.05,
                catalyst_count=0,
            ),
        ]

        result = learn_pre_surge_signal_logic(cases)
        promoted = {definition.signal_id for definition in result.signal_definitions}

        self.assertIn("sig-fundamental-revenue-acceleration", promoted)
        self.assertIn("sig-market-early-confirmation", promoted)
        self.assertTrue(all(isinstance(definition, SignalDefinition) for definition in result.signal_definitions))

    def test_control_matching_selects_same_sector_neutral_cases(self) -> None:
        winner = make_case(
            "winner-1",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.40,
            earnings_growth=0.70,
            margin=0.22,
            return_20d=0.11,
            return_60d=0.25,
            target_upside=0.35,
            catalyst_count=2,
            market_cap=12_000_000_000.0,
            sector="Semiconductors",
        )
        control = make_case(
            "control-1",
            CaseOutcomeLabel.CONTROL,
            revenue_growth=0.03,
            earnings_growth=-0.10,
            margin=0.05,
            return_20d=0.00,
            return_60d=0.02,
            target_upside=0.04,
            catalyst_count=0,
            market_cap=10_500_000_000.0,
            sector="Semiconductors",
        )
        wrong_sector = make_case(
            "control-2",
            CaseOutcomeLabel.CONTROL,
            revenue_growth=0.03,
            earnings_growth=-0.10,
            margin=0.05,
            return_20d=0.00,
            return_60d=0.02,
            target_upside=0.04,
            catalyst_count=0,
            market_cap=10_500_000_000.0,
            sector="Retail",
        )

        matches = match_controls(
            [winner, control, wrong_sector],
            ControlMatchCriteria(max_controls_per_winner=2),
        )

        self.assertEqual(matches[0].winner_case_id, "winner-1")
        self.assertEqual(matches[0].control_case_ids, ("control-1",))

    def test_factor_inflection_detection_finds_breakout_before_surge(self) -> None:
        bars = []
        start = date(2026, 1, 1)
        close = 50.0
        for index in range(90):
            if index == 30:
                close *= 1.25
                volume = 4_000_000
            elif index > 30:
                close *= 1.025
                volume = 2_500_000
            else:
                close *= 1.001
                volume = 1_000_000
            bars.append(
                PriceBar(
                    symbol="BRK",
                    as_of_date=start + timedelta(days=index),
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=volume,
                    source="fixture",
                    retrieved_at=STAMP,
                )
            )

        candidates = detect_price_inflections(
            "BRK",
            bars,
            window_start=start,
            window_end=start + timedelta(days=89),
            min_forward_return=0.30,
        )

        self.assertTrue(candidates)
        self.assertEqual(candidates[0].method, "price_volume_factor")

    def test_historical_packet_builder_uses_pre_inflection_slices(self) -> None:
        anchor = date(2026, 7, 1)
        start = anchor - timedelta(days=220)
        bars = []
        close = 50.0
        for index in range(430):
            current_date = start + timedelta(days=index)
            if current_date > anchor:
                close *= 1.006
            bars.append(
                PriceBar(
                    symbol="SLI",
                    as_of_date=current_date,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=1_000_000,
                    source="fixture",
                    retrieved_at=STAMP,
                )
            )
        listing = SecurityListing(
            symbol="SLI",
            name="Slice Corp.",
            exchange="NASDAQ",
            asset_type="common_stock",
            status="active",
            source="fixture",
            retrieved_at=STAMP,
        )
        features = [
            feature("SLI", "profile.sector", "Semiconductors"),
            feature("SLI", "profile.industry", "Accelerators"),
            feature("SLI", "valuation.market_cap_usd", 12_000_000_000.0),
            feature("SLI", "price.average_daily_dollar_volume_20d", 50_000_000.0),
        ]

        cases = build_historical_cases_from_packets(
            listings=[listing],
            bars_by_symbol={"SLI": bars},
            features_by_symbol={"SLI": features},
            version=version(),
            outcome_definition=default_outcome_definition(),
            slice_plan=CaseSlicePlan(),
            inflection_dates_by_symbol={"SLI": anchor},
        )

        self.assertEqual([case.packet.as_of.as_of_date for case in cases], [anchor - timedelta(days=180), anchor - timedelta(days=90), anchor - timedelta(days=30)])
        self.assertTrue(all(case.outcome_start_date > anchor for case in cases))

    def test_heuristic_blind_researcher_does_not_need_future_label(self) -> None:
        case = make_case(
            "winner-1",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.40,
            earnings_growth=0.70,
            margin=0.22,
            return_20d=0.11,
            return_60d=0.25,
            target_upside=0.35,
            catalyst_count=2,
        )

        analysis = HeuristicBlindCaseResearcher().analyze(case)

        self.assertEqual(analysis.case_id, "winner-1")
        self.assertEqual(analysis.as_of_date, AS_OF.isoformat())
        self.assertTrue(analysis.pre_surge_signals)

    def test_openai_blind_researcher_masks_company_identity_and_uses_no_tools(self) -> None:
        case = make_case(
            "winner-1",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.40,
            earnings_growth=0.70,
            margin=0.22,
            return_20d=0.11,
            return_60d=0.25,
            target_upside=0.35,
            catalyst_count=2,
        )
        transport = FakeOpenAITransport(
            "{\"expectation_gap\":\"gap\",\"pre_surge_signals\":[\"signal\"],"
            "\"contrary_evidence\":[\"risk\"],\"catalyst_watch\":[\"watch\"],\"confidence\":0.4}"
        )
        client = OpenAIChatClient("gpt-5.4-mini", "test-key", transport=transport)

        OpenAIBlindCaseResearcher(client).analyze(case)

        payload = transport.calls[0][2]
        prompt_text = payload["input"][1]["content"][0]["text"]
        self.assertNotIn("tools", payload)
        self.assertIn("\"symbol\": \"MASKED\"", prompt_text)
        self.assertNotIn("WINNER", prompt_text)

    def test_cold_start_orchestration_writes_manifest_and_signal_logic(self) -> None:
        cases = [
            make_case(
                "winner-1",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.40,
                earnings_growth=0.70,
                margin=0.22,
                return_20d=0.11,
                return_60d=0.25,
                target_upside=0.35,
                catalyst_count=2,
            ),
            make_case(
                "control-1",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.03,
                earnings_growth=-0.10,
                margin=0.05,
                return_20d=0.00,
                return_60d=0.02,
                target_upside=0.04,
                catalyst_count=0,
            ),
        ]
        with TemporaryDirectory() as tmp:
            config = AgentConfig(storage=StorageConfig(reports_dir=tmp))
            library = FileSignalLibrary(Path(tmp) / "memory" / "signals")
            progress_messages = []
            output = run_cold_start_case_learning(
                cases,
                config=config,
                run_id="test-cold-start",
                created_at=STAMP,
                signal_library=library,
                control_match_criteria=ControlMatchCriteria(max_controls_per_winner=1),
                progress=progress_messages.append,
            )

            self.assertTrue(output.manifest_path.exists())
            self.assertTrue(output.signal_logic_path.exists())
            self.assertTrue(output.signal_definitions_path.exists())
            self.assertTrue(output.blind_analysis_path.exists())
            self.assertTrue(output.inflection_analysis_path.exists())
            self.assertTrue(library.definitions_path.exists())
            self.assertIn("sig-fundamental-revenue-acceleration", output.signal_logic_path.read_text())
            self.assertIn("inflection_analyses", output.manifest_path.read_text())
            self.assertIn("matched_control_sets", output.manifest_path.read_text())
            self.assertTrue(library.read_definitions())
            self.assertTrue(any("discovering inflections" in message for message in progress_messages))
            self.assertTrue(any("complete:" in message for message in progress_messages))


def make_case(
    case_id: str,
    label: CaseOutcomeLabel,
    *,
    revenue_growth: float,
    earnings_growth: float,
    margin: float,
    return_20d: float,
    return_60d: float,
    target_upside: float,
    catalyst_count: int,
    market_cap: float = 15_000_000_000.0,
    sector: str = "Semiconductors",
) -> HistoricalCase:
    symbol = case_id.split("-")[0].upper()
    close = 100.0
    features = [
        feature(symbol, "financial.revenue_growth_yoy", revenue_growth),
        feature(symbol, "financial.earnings_growth_yoy", earnings_growth),
        feature(symbol, "financial.operating_margin_ttm", margin),
        feature(symbol, "price.latest_close", close),
        feature(symbol, "price.return_20d", return_20d),
        feature(symbol, "price.return_60d", return_60d),
        feature(symbol, "price.return_120d", return_60d / 2),
        feature(symbol, "price.average_daily_dollar_volume_20d", 120_000_000.0),
        feature(symbol, "price.average_daily_dollar_volume_60d", 90_000_000.0),
        feature(symbol, "valuation.pe_ratio", 25.0),
        feature(symbol, "valuation.price_to_sales_ttm", 5.0),
        feature(symbol, "valuation.market_cap_usd", market_cap),
        feature(symbol, "analyst.target_price", close * (1 + target_upside)),
        feature(symbol, "profile.sector", sector),
        feature(symbol, "profile.industry", "Accelerators"),
    ]
    listing = SecurityListing(
        symbol=symbol,
        name=f"{symbol} Corp.",
        exchange="NASDAQ",
        asset_type="common_stock",
        status="active",
        source="fixture",
        retrieved_at=STAMP,
    )
    company = company_profile_from_features(listing, features, AS_OF)
    catalysts = [
        Catalyst(
            name=f"Catalyst {index}",
            expected_date=AS_OF + timedelta(days=30 + index),
            status=CatalystStatus.EXPECTED,
            evidence=[
                EvidenceItem(
                    kind=EvidenceKind.NEWS,
                    summary="Catalyst was known before the outcome window.",
                    as_of_date=AS_OF,
                    source_id=f"fixture:{symbol}:catalyst:{index}",
                    published_date=AS_OF,
                )
            ],
        )
        for index in range(catalyst_count)
    ]
    packet = build_research_packet(
        symbol=symbol,
        as_of_date=AS_OF,
        company=company,
        features=features,
        version=version(),
        catalysts=catalysts,
        packet_id=f"{case_id}:packet",
        created_at=STAMP,
    )
    return HistoricalCase(
        case_id=case_id,
        label=label,
        packet=packet,
        outcome_start_date=AS_OF + timedelta(days=1),
        outcome_end_date=AS_OF + timedelta(days=181),
        outcome_return=1.0 if label is CaseOutcomeLabel.WINNER else 0.0,
        matched_group_id="fixture-group",
        hidden_outcome_summary="Outcome was hidden from packet construction.",
        outcome_definition_id=default_outcome_definition().definition_id,
    )


def feature(symbol: str, name: str, value: float | str) -> FeatureRecord:
    return FeatureRecord(
        name=name,
        value=value,
        as_of_date=AS_OF,
        source="fixture",
        retrieved_at=STAMP,
        data_quality=DataQuality.CONFIRMED,
        source_id=f"fixture:{symbol}:{name}",
        period_end_date=AS_OF,
    )
