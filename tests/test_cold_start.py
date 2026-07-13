import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.cases import (
    CaseOutcomeLabel,
    CaseSlicePlan,
    ControlMatchCriteria,
    HistoricalCandidate,
    HistoricalCase,
    detect_price_inflections,
    OutcomeDefinition,
    default_outcome_definition,
    eligible_common_stock_listings,
    learn_pre_surge_signal_logic,
    build_historical_cases_from_packets,
    match_controls,
)
from stock_opportunity_agent.config import AgentConfig, StorageConfig
from stock_opportunity_agent.data import (
    DocumentContentScope,
    DocumentRecord,
    FilingMetadata,
    PriceBar,
    SecurityListing,
    build_research_packet,
    company_profile_from_features,
)
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
from stock_opportunity_agent.memory import FilePlaybookLibrary, FileSignalLibrary, FileThemeLibrary
from stock_opportunity_agent.orchestration import run_cold_start_case_learning
from stock_opportunity_agent.research import (
    EvidenceAcquisitionRequest,
    EvidenceAcquisitionResult,
    CachedRalphBlindResearcher,
    HeuristicBlindCaseResearcher,
    HeuristicRalphBlindResearcher,
    HeuristicSurgePlaybookSynthesizer,
    OpenAIRalphBlindResearcher,
    OpenAIBlindCaseResearcher,
    OpenAISurgePlaybookSynthesizer,
    OpenAIWebEvidenceResearcher,
    RalphBlindAnalysis,
    apply_context_coverage_gate,
    assess_context_coverage,
    audit_point_in_time_documents,
    build_requirement_coverage_ledger,
    build_raw_source_blind_packet,
    default_information_requirements,
    document_content_readiness,
    evaluate_information_plan_experiment,
    extract_atomic_evidence_by_case,
    prepare_information_plan_experiment,
    point_in_time_document_identity_tokens,
    write_information_plan_experiment_artifacts,
)
from stock_opportunity_agent.research.ralph_loop import (
    InformationSection,
    InformationScheme,
    analyze_scheme_errors,
    build_blind_scheme_packet,
    evaluate_scheme_performance,
    run_ralph_experiment,
    propose_next_information_scheme,
    run_ralph_loop,
    synthesize_information_scheme,
    write_ralph_experiment_artifacts,
    write_ralph_loop_artifacts,
)
from stock_opportunity_agent.research.inflection_discovery import (
    CachedInflectionResearcher,
    CompositeInflectionResearcher,
    HeuristicInflectionResearcher,
)
from stock_opportunity_agent.signals import measure_packet_signals
from stock_opportunity_agent.themes import build_cold_start_theme_maps
from scripts.run_cold_start_formal import (
    _alpha_earnings_features,
    _catalyst_from_news_document,
    _fetch_context_documents,
    _filing_documents_for_candidate,
    _finnhub_earnings_features,
    _finnhub_news_document,
    _news_documents_for_candidate,
    _provider_profile_features,
    _provider_theme_news_documents_for_candidate,
    _theme_context_documents_for_candidate,
)
from scripts.run_ralph_loop_experiment import (
    _augment_alpha_vantage_news_for_cases,
    _augment_sec_submission_documents_for_cases,
    _enrich_cases_with_documents,
    _leakage_report,
    _load_documents_by_symbol,
    _refresh_sec_filing_documents_for_cases,
    _select_cases,
    _write_imported_response_artifacts,
    _write_preflight_artifacts,
)


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


class SequencedOpenAITransport:
    def __init__(self, texts) -> None:
        self.texts = list(texts)
        self.calls = []

    def post_json(self, url, headers, payload):
        self.calls.append((url, headers, payload))
        index = min(len(self.calls) - 1, len(self.texts) - 1)
        return {
            "id": "resp_test",
            "model": "gpt-5.4-mini",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": self.texts[index]}],
                }
            ],
        }


class FailingInflectionResearcher:
    def discover(self, case):
        raise RuntimeError("provider unavailable")


class CountingInflectionResearcher:
    def __init__(self) -> None:
        self.calls = 0

    def discover(self, case):
        self.calls += 1
        return HeuristicInflectionResearcher().discover(case)


class FakeAlphaEarningsClient:
    def earnings(self, symbol):
        return {
            "quarterlyEarnings": [
                {
                    "fiscalDateEnding": "2026-03-31",
                    "reportedDate": "2026-04-20",
                    "reportedEPS": "1.20",
                    "estimatedEPS": "1.00",
                    "surprise": "0.20",
                    "surprisePercentage": "20.0",
                },
                {
                    "fiscalDateEnding": "2026-06-30",
                    "reportedDate": "2026-07-20",
                    "reportedEPS": "2.00",
                },
            ]
        }


class FakeAlphaProfileClient:
    def company_overview(self, symbol):
        return {"Sector": "Technology", "Industry": "Semiconductors"}


class FakeAlphaNewsClient:
    def __init__(self):
        self.calls = []

    def news_sentiment(self, symbol, **kwargs):
        self.calls.append((symbol, kwargs))
        return {
            "feed": [
                {
                    "time_published": "20251115T120000",
                    "title": "ABC wins AI customer contract",
                    "summary": "The customer order includes execution risk.",
                    "url": "https://example.com/alpha-news",
                    "source": "Example Wire",
                }
            ]
        }

    def topic_news_sentiment(self, topics, **kwargs):
        self.calls.append((topics, kwargs))
        return {
            "feed": [
                {
                    "time_published": "20251120T120000",
                    "title": "AI infrastructure demand lifts semiconductor suppliers",
                    "summary": "Industry demand is tied to data center investment and manufacturing capacity.",
                    "url": "https://example.com/theme-news",
                    "source": "Example Wire",
                }
            ]
        }


class FakeFinnhubEarningsClient:
    def earnings_surprises(self, symbol):
        return [
            {
                "period": "2026-03-31",
                "date": "2026-04-21",
                "actual": 1.1,
                "estimate": 1.0,
                "surprise": 0.1,
                "surprisePercent": 10.0,
            },
            {
                "period": "2026-03-31",
                "actual": 9.9,
            },
        ]


class FakeContextSecClient:
    def recent_filings_as_of(self, cik, as_of_date):
        return []


class FakeContextFinnhubClient:
    def company_news(self, symbol, from_date, to_date):
        return [
            {
                "id": 7,
                "datetime": int(datetime(2026, 4, 15, tzinfo=timezone.utc).timestamp()),
                "headline": "ABC wins AI infrastructure contract",
                "summary": "The company disclosed a customer order and related execution risk.",
                "url": "https://example.com/contract",
            }
        ]

    def transcript_list(self, symbol):
        return []


class FakeContextAlphaClient:
    def __init__(self):
        self.calls = []

    def news_sentiment(self, symbol, **kwargs):
        self.calls.append("news")
        return {
            "feed": [
                {
                    "time_published": "20260410T120000",
                    "title": "ABC signs semiconductor supply agreement",
                    "summary": "The company announced an order linked to AI infrastructure demand.",
                    "url": "https://example.com/alpha-contract",
                }
            ]
        }

    def topic_news_sentiment(self, topics, **kwargs):
        self.calls.append("topic")
        return {
            "feed": [
                {
                    "time_published": "20260401T120000",
                    "title": "AI infrastructure capex supports semiconductor demand",
                    "summary": "Provider topic news links data center buildouts to chip suppliers.",
                    "url": "https://example.com/alpha-theme",
                }
            ]
        }


class FakeContextWebResearcher:
    def __init__(self, client, *, max_documents, max_theme_documents):
        self.max_documents = max_documents
        self.max_theme_documents = max_theme_documents

    def collect(self, request, retrieved_at):
        return EvidenceAcquisitionResult(
            documents=(
                DocumentRecord(
                    document_id="theme-doc",
                    symbol=request.symbol,
                    kind=EvidenceKind.THEME_CONTEXT,
                    title="AI infrastructure trend",
                    text="Theme context linked data center capex to supplier demand and valuation risk.",
                    source_id="web:theme",
                    source_url="https://example.com/theme",
                    published_date=date(2026, 4, 1),
                    available_date=date(2026, 4, 1),
                    retrieved_at=retrieved_at,
                ),
            ),
            catalysts=(
                Catalyst(
                    name="AI product launch",
                    expected_date=date(2026, 6, 1),
                    status=CatalystStatus.EXPECTED,
                    evidence=[
                        EvidenceItem(
                            kind=EvidenceKind.NEWS,
                            summary="Launch was reported before the inflection cutoff.",
                            as_of_date=date(2026, 4, 2),
                            source_id="web:catalyst",
                            source_url="https://example.com/launch",
                            published_date=date(2026, 4, 2),
                        )
                    ],
                ),
            ),
            queries=("ABC query before 2026-05-01",),
        )


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

    def test_common_stock_filter_excludes_warrants_units_and_rights(self) -> None:
        listings = [
            SecurityListing("ABCD", "ABCD Corp Common Stock", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("ABCDW", "ABCD Corp Warrant", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("ABCDU", "ABCD Corp Unit", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("ABCDR", "ABCD Corp Right", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("ABCDN", "ABCD Corp 6.50% Notes due 2029", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("ABCDP", "ABCD Corp Preferred Series A", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("ABCDT", "ABCD Trust Structured Securities", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("OPTXW", "Syntec Optics Holdings Inc Wt Exp", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("CHSCL", "CHS Inc", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("IFED", "ETRACS IFED Invest with the Fed TR Index ETN", "NYSE", "Stock", "Active", "test", STAMP),
            SecurityListing("NMAI", "Nuveen Multi-Asset Income Fund", "NYSE", "Stock", "Active", "test", STAMP),
            SecurityListing("ZWZZT", "NASDAQ TEST STOCK", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("FUND", "Sprott Focus Trust Inc", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("BIP", "Brookfield Infrastructure Partners L.P", "NYSE", "Stock", "Active", "test", STAMP),
            SecurityListing("AGNC", "AGNC Investment Corp Common Stock", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("AGNCN", "AGNC Investment Corp", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("OXSQ", "Oxford Square Capital Corp Common Stock", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("OXSQG", "Oxford Square Capital Corp", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("SAR", "Saratoga Investment Corp Common Stock", "NYSE", "Stock", "Active", "test", STAMP),
            SecurityListing("SAJ", "Saratoga Investment Corp", "NYSE", "Stock", "Active", "test", STAMP),
            SecurityListing("SAT", "Saratoga Investment Corp", "NYSE", "Stock", "Active", "test", STAMP),
            SecurityListing("SACH", "Sachem Capital Corp Common Stock", "NYSE", "Stock", "Active", "test", STAMP),
            SecurityListing("SCCC", "Sachem Capital Corp", "NYSE", "Stock", "Active", "test", STAMP),
            SecurityListing("SO", "Southern Company Common Stock", "NYSE", "Stock", "Active", "test", STAMP),
            SecurityListing("SOJF", "Southern Company", "NYSE", "Stock", "Active", "test", STAMP),
            SecurityListing("GOOG", "Alphabet Inc Class C", "NASDAQ", "Stock", "Active", "test", STAMP),
            SecurityListing("GOOGL", "Alphabet Inc Class A", "NASDAQ", "Stock", "Active", "test", STAMP),
        ]

        eligible = eligible_common_stock_listings(listings)

        self.assertEqual(
            [listing.symbol for listing in eligible],
            ["ABCD", "AGNC", "GOOG", "GOOGL", "OXSQ", "SACH", "SAR", "SO"],
        )

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

        self.assertEqual(
            [case.packet.as_of.as_of_date for case in cases],
            [
                anchor - timedelta(days=180),
                anchor - timedelta(days=120),
                anchor - timedelta(days=90),
                anchor - timedelta(days=60),
                anchor - timedelta(days=30),
            ],
        )
        self.assertTrue(all(case.outcome_start_date > anchor for case in cases))

    def test_formal_earnings_features_use_report_dates_as_cutoff(self) -> None:
        as_of_dates = (date(2026, 4, 19), date(2026, 4, 21))

        alpha_features = _alpha_earnings_features("ABC", as_of_dates, FakeAlphaEarningsClient(), STAMP)
        finnhub_features = _finnhub_earnings_features("ABC", as_of_dates, FakeFinnhubEarningsClient(), STAMP)

        self.assertTrue(all(feature.as_of_date <= max(as_of_dates) for feature in alpha_features + finnhub_features))
        self.assertEqual(
            {feature.name for feature in alpha_features},
            {
                "financial.reported_eps",
                "analyst.estimated_eps",
                "analyst.earnings_surprise",
                "analyst.earnings_surprise_pct",
            },
        )
        self.assertNotIn(9.9, [feature.value for feature in finnhub_features])

    def test_provider_profile_features_add_industry_context_without_current_valuation(self) -> None:
        as_of_dates = (date(2026, 1, 1), date(2026, 2, 1))

        features = _provider_profile_features("abc", as_of_dates, FakeAlphaProfileClient(), None, STAMP)
        theme_docs = _theme_context_documents_for_candidate(
            HistoricalCandidate(
                symbol="ABC",
                company_name="ABC Corp.",
                label=CaseOutcomeLabel.WINNER,
                outcome_anchor_date=date(2026, 5, 1),
                inflection_date=date(2026, 5, 1),
                inflection_method="fixture",
                inflection_score=1.0,
                outcome_end_date=date(2026, 8, 1),
                forward_return=1.0,
                max_forward_return=1.2,
                max_drawdown_from_start=-0.1,
                trading_days=65,
                selection_rank=1,
            ),
            features,
            earliest_as_of=as_of_dates[0],
            created_at=STAMP,
        )

        self.assertEqual({feature.name for feature in features}, {"profile.sector", "profile.industry"})
        self.assertTrue(all(feature.data_quality is DataQuality.STALE for feature in features))
        self.assertEqual(theme_docs[0].kind, EvidenceKind.THEME_CONTEXT)
        self.assertIn("Semiconductors", theme_docs[0].text)

    def test_alpha_news_context_uses_historical_window(self) -> None:
        candidate = HistoricalCandidate(
            symbol="ABC",
            company_name="ABC Corp.",
            label=CaseOutcomeLabel.WINNER,
            outcome_anchor_date=date(2026, 5, 1),
            inflection_date=date(2026, 5, 1),
            inflection_method="fixture",
            inflection_score=1.0,
            outcome_end_date=date(2026, 8, 1),
            forward_return=1.0,
            max_forward_return=1.2,
            max_drawdown_from_start=-0.1,
            trading_days=65,
            selection_rank=1,
        )
        client = FakeAlphaNewsClient()

        documents = _news_documents_for_candidate(
            SimpleNamespace(news_lookback_days=365, max_news_per_symbol=4),
            candidate,
            context_start=date(2025, 11, 1),
            created_at=STAMP,
            finnhub_client=None,
            alpha_client=client,
            warnings=[],
        )

        self.assertEqual(documents[0].kind, EvidenceKind.NEWS)
        kwargs = client.calls[0][1]
        self.assertEqual(kwargs["time_from"], datetime(2025, 11, 1, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(kwargs["time_to"], datetime(2026, 5, 1, 23, 59, 59, 999999, tzinfo=timezone.utc))

    def test_provider_theme_news_uses_alpha_vantage_topic_api(self) -> None:
        candidate = HistoricalCandidate(
            symbol="ABC",
            company_name="ABC Corp.",
            label=CaseOutcomeLabel.WINNER,
            outcome_anchor_date=date(2026, 5, 1),
            inflection_date=date(2026, 5, 1),
            inflection_method="fixture",
            inflection_score=1.0,
            outcome_end_date=date(2026, 8, 1),
            forward_return=1.0,
            max_forward_return=1.2,
            max_drawdown_from_start=-0.1,
            trading_days=65,
            selection_rank=1,
        )
        client = FakeAlphaNewsClient()
        features = _provider_profile_features(
            "ABC",
            (date(2025, 11, 1),),
            FakeAlphaProfileClient(),
            None,
            STAMP,
        )

        documents = _provider_theme_news_documents_for_candidate(
            SimpleNamespace(news_lookback_days=365, max_theme_documents_per_symbol=4),
            candidate,
            features,
            context_start=date(2025, 11, 1),
            latest_as_of=date(2026, 4, 1),
            created_at=STAMP,
            alpha_client=client,
            warnings=[],
        )

        self.assertEqual(documents[0].kind, EvidenceKind.THEME_CONTEXT)
        self.assertIn("AI infrastructure", documents[0].text)
        topics, kwargs = client.calls[0]
        self.assertEqual(topics, ("technology", "manufacturing"))
        self.assertEqual(kwargs["time_to"], datetime(2026, 4, 1, 23, 59, 59, 999999, tzinfo=timezone.utc))

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
            "{\"surge_candidate\":\"possible\",\"surge_candidate_reason\":\"reason\","
            "\"expectation_gap\":\"gap\",\"pre_surge_signals\":[\"signal\"],"
            "\"contrary_evidence\":[\"risk\"],\"catalyst_watch\":[\"watch\"],\"confidence\":0.4}"
        )
        client = OpenAIChatClient("gpt-5.4-mini", "test-key", transport=transport)

        OpenAIBlindCaseResearcher(client).analyze(case)

        payload = transport.calls[0][2]
        prompt_text = payload["input"][1]["content"][0]["text"]
        self.assertNotIn("tools", payload)
        self.assertIn("\"symbol\": \"MASKED\"", prompt_text)
        self.assertIn("\"packet_id\": \"MASKED\"", prompt_text)
        self.assertNotIn("winner-1:packet", prompt_text)
        self.assertNotIn("WINNER", prompt_text)
        self.assertNotIn("WINNER Corp.", prompt_text)

    def test_openai_blind_researcher_masks_document_identity_text(self) -> None:
        case = make_case(
            "apple-1",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.40,
            earnings_growth=0.70,
            margin=0.22,
            return_20d=0.11,
            return_60d=0.25,
            target_upside=0.35,
            catalyst_count=0,
            company_name="Apple Inc.",
            extra_documents=[
                DocumentRecord(
                    document_id="aapl-10k",
                    symbol="AAPL",
                    kind=EvidenceKind.FILING,
                    title="Apple Inc. 10-K",
                    text="Apple Inc. disclosed new customer orders.",
                    source_id="sec:Apple",
                    source_url="https://www.sec.gov/apple",
                    published_date=AS_OF,
                    retrieved_at=STAMP,
                )
            ],
        )
        transport = FakeOpenAITransport(
            "{\"surge_candidate\":\"possible\",\"surge_candidate_reason\":\"reason\","
            "\"expectation_gap\":\"gap\",\"pre_surge_signals\":[\"signal\"],"
            "\"contrary_evidence\":[\"risk\"],\"catalyst_watch\":[\"watch\"],\"confidence\":0.4}"
        )
        client = OpenAIChatClient("gpt-5.4-mini", "test-key", transport=transport)

        OpenAIBlindCaseResearcher(client).analyze(case)

        prompt_text = transport.calls[0][2]["input"][1]["content"][0]["text"]
        self.assertNotIn("AAPL", prompt_text)
        self.assertNotIn("Apple", prompt_text)
        self.assertNotIn("sec:Apple", prompt_text)

    def test_openai_playbook_synthesizer_uses_anonymized_cross_case_prompt_without_tools(self) -> None:
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
        learning = learn_pre_surge_signal_logic(cases)
        themes = build_cold_start_theme_maps(cases, learning)
        blind = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in cases)
        transport = FakeOpenAITransport(
            json.dumps(
                {
                    "schema_version": "surge-playbook-v0.1",
                    "playbooks": [
                        {
                            "playbook_id": "pb-test-v0.1",
                            "name": "Test playbook",
                            "purpose": "Find surge candidates with multiple confirmations.",
                            "version": "playbook-v0.1",
                            "applies_when": ["news", "price_volume"],
                            "core_questions": [
                                {
                                    "question_id": "q-test",
                                    "prompt": "What changed and how is it confirmed?",
                                    "evidence_types": ["news"],
                                    "positive_indicators": ["confirmed order"],
                                    "negative_indicators": ["theme mention only"],
                                    "linked_signal_ids": ["sig-market-early-confirmation"],
                                }
                            ],
                            "reasoning_steps": [
                                {
                                    "step_id": "step-test",
                                    "name": "Triangulate",
                                    "question": "Do sources agree?",
                                    "inputs": ["blind_case_analyses"],
                                    "output": "triangulation",
                                    "common_failure_mode": "single-source story",
                                }
                            ],
                            "positive_patterns": ["winner setup had multiple confirmations"],
                            "counter_patterns": ["control setup lacked confirmation"],
                            "false_positive_traps": ["headline-only catalyst"],
                            "linked_signal_ids": ["sig-market-early-confirmation"],
                            "linked_theme_ids": ["semiconductors"],
                            "evidence_case_refs": {"positive": ["case_001"], "counterexamples": ["case_002"]},
                            "confidence": 0.5,
                            "promotion_status": "candidate",
                            "hindsight_risk_notes": ["retrospective synthesis"],
                        }
                    ],
                    "warnings": [],
                }
            )
        )
        client = OpenAIChatClient("gpt-5.4-mini", "test-key", transport=transport)

        result = OpenAISurgePlaybookSynthesizer(client).synthesize(cases, blind, learning, themes)

        payload = transport.calls[0][2]
        prompt_text = payload["input"][1]["content"][0]["text"]
        self.assertNotIn("tools", payload)
        self.assertIn("\"label\": \"winner\"", prompt_text)
        self.assertNotIn("winner-1", prompt_text)
        self.assertNotIn("WINNER", prompt_text)
        self.assertNotIn("WINNER Corp.", prompt_text)
        self.assertEqual(result.generated_by, "OpenAISurgePlaybookSynthesizer")
        self.assertEqual(result.playbooks[0].playbook_id, "pb-test-v0.1")

    def test_openai_playbook_synthesizer_falls_back_after_invalid_json(self) -> None:
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
        learning = learn_pre_surge_signal_logic(cases)
        themes = build_cold_start_theme_maps(cases, learning)
        blind = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in cases)
        transport = SequencedOpenAITransport(["{", "{\"playbooks\": ["])
        client = OpenAIChatClient("gpt-5.4-mini", "test-key", transport=transport)

        result = OpenAISurgePlaybookSynthesizer(client, max_attempts=2).synthesize(cases, blind, learning, themes)

        self.assertEqual(len(transport.calls), 2)
        self.assertIn("fallback=HeuristicSurgePlaybookSynthesizer", result.generated_by)
        self.assertTrue(result.playbooks)
        self.assertTrue(any("LLM playbook synthesis failed" in warning for warning in result.warnings))

    def test_ralph_scheme_and_packets_hide_labels_identity_and_forward_return(self) -> None:
        cases = [
            make_case(
                "winner-apple",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.40,
                earnings_growth=0.70,
                margin=0.22,
                return_20d=0.11,
                return_60d=0.25,
                target_upside=0.35,
                catalyst_count=2,
                company_name="Apple Inc.",
                extra_documents=[
                    DocumentRecord(
                        document_id="aapl-contract",
                        symbol="AAPL",
                        kind=EvidenceKind.NEWS,
                        title="Apple order",
                        text="Apple Inc. announced a customer order and execution risk.",
                        source_id="wire:Apple",
                        source_url="https://example.com/apple",
                        published_date=AS_OF,
                        retrieved_at=STAMP,
                    )
                ],
            ),
            make_case(
                "control-apple",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.03,
                earnings_growth=-0.10,
                margin=0.05,
                return_20d=0.00,
                return_60d=0.02,
                target_upside=0.04,
                catalyst_count=0,
                company_name="Apple Inc.",
            ),
        ]
        learning = learn_pre_surge_signal_logic(cases)
        themes = build_cold_start_theme_maps(cases, learning)
        blind = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(cases, blind, learning, themes)

        scheme, diagnostic = synthesize_information_scheme(
            cases,
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
            coverage_reports={
                "winner-apple": {
                    "sufficient_context": False,
                    "missing_buckets": ["catalyst_event_context"],
                }
            },
        )
        packet = build_blind_scheme_packet(cases[0], scheme, anonymous_case_id="case_001")

        self.assertEqual(diagnostic.stage_boundary, "retrospective_label_aware")
        self.assertTrue(diagnostic.coverage_summary["provided"])
        self.assertEqual(diagnostic.coverage_summary["missing_bucket_counts"]["catalyst_event_context"], 1)
        scheme_text = json.dumps(scheme.to_dict())
        packet_text = json.dumps(packet.to_dict())
        for forbidden in ("winner", "control", "AAPL", "Apple", "winner-apple", "control-apple", "1.0"):
            self.assertNotIn(forbidden, scheme_text)
            self.assertNotIn(forbidden, packet_text)
        self.assertIn("MASKED", packet_text)
        self.assertNotIn("source_url", packet_text)
        self.assertNotIn("source_id", packet_text)

    def test_ralph_packet_prioritizes_catalyst_theme_expectation_and_compresses_tables(self) -> None:
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
        learning = learn_pre_surge_signal_logic([case])
        themes = build_cold_start_theme_maps([case], learning)
        blind = (HeuristicBlindCaseResearcher().analyze(case),)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize([case], blind, learning, themes)
        scheme, _diagnostic = synthesize_information_scheme(
            [case],
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )

        packet = build_blind_scheme_packet(case, scheme, anonymous_case_id="case_001")

        section_names = [section.name for section in packet.sections]
        self.assertEqual(
            section_names[:5],
            [
                "Catalyst/Event Ledger",
                "Expectation Gap Summary",
                "Theme/Industry Transmission",
                "Materiality and Timing",
                "Contrary/Risk Evidence",
            ],
        )
        budget_by_section = {section.name: section.token_budget for section in scheme.sections}
        compressed_budget = sum(
            budget_by_section[name]
            for name in ("Compressed Fundamentals", "Compressed Market Confirmation")
        )
        self.assertLessEqual(compressed_budget / scheme.total_token_budget, scheme.max_compressed_context_share)
        fundamentals = next(section for section in packet.sections if section.name == "Compressed Fundamentals")
        market = next(section for section in packet.sections if section.name == "Compressed Market Confirmation")
        catalyst = next(section for section in packet.sections if section.name == "Catalyst/Event Ledger")
        self.assertLessEqual(len(fundamentals.items), 3)
        self.assertLessEqual(len(market.items), 3)
        self.assertGreaterEqual(catalyst.priority, 1)
        self.assertLess(catalyst.priority, fundamentals.priority)

        recent_confirmed = Catalyst(
            name="Recent financing close",
            expected_date=AS_OF - timedelta(days=15),
            status=CatalystStatus.CONFIRMED,
            evidence=[
                EvidenceItem(
                    kind=EvidenceKind.NEWS,
                    summary="Financing became effective before as-of.",
                    as_of_date=AS_OF,
                    source_id="fixture:recent-financing",
                    published_date=AS_OF - timedelta(days=15),
                )
            ],
        )
        recent_case = replace(
            case,
            packet=replace(case.packet, catalysts=[recent_confirmed]),
        )
        recent_packet = build_blind_scheme_packet(recent_case, scheme, anonymous_case_id="case_002")
        recent_catalyst = next(section for section in recent_packet.sections if section.name == "Catalyst/Event Ledger")
        recent_timing = next(section for section in recent_packet.sections if section.name == "Materiality and Timing")
        self.assertTrue(
            any(
                item.get("summary") == "Recent financing close"
                and item.get("relative_timing_days") == -15
                for item in recent_catalyst.items
            )
        )
        self.assertTrue(
            any("observed 15 days before as-of" in item.get("summary", "") for item in recent_timing.items)
        )

        event_case = make_case(
            "winner-event",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.10,
            earnings_growth=0.10,
            margin=0.05,
            return_20d=-0.20,
            return_60d=-0.40,
            target_upside=0.10,
            catalyst_count=0,
            extra_documents=[
                DocumentRecord(
                    document_id="trading-resumption",
                    symbol="WINNER",
                    kind=EvidenceKind.NEWS,
                    title="NYSE removal of trading suspension",
                    text="The NYSE removal of trading suspension became effective after a compliance plan.",
                    source_id="wire:trading-resumption",
                    source_url="https://example.com/trading-resumption",
                    published_date=AS_OF,
                    retrieved_at=STAMP,
                )
            ],
        )
        event_packet = build_blind_scheme_packet(event_case, scheme, anonymous_case_id="case_003")
        event_expectation = next(
            section for section in event_packet.sections if section.name == "Expectation Gap Summary"
        )
        event_materiality = next(
            section for section in event_packet.sections if section.name == "Materiality and Timing"
        )
        self.assertTrue(
            any("Depressed market setup" in item.get("summary", "") for item in event_expectation.items)
        )
        self.assertTrue(
            any(item.get("item_type") == "materiality_timing" for item in event_materiality.items)
        )

    def test_ralph_packet_refreshes_source_detail_and_ai_chain_transmission(self) -> None:
        case = make_case(
            "winner-ai",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.30,
            earnings_growth=0.50,
            margin=0.18,
            return_20d=-0.18,
            return_60d=-0.32,
            target_upside=0.25,
            catalyst_count=0,
            extra_documents=[
                DocumentRecord(
                    document_id="stale-filing",
                    symbol="WINNER",
                    kind=EvidenceKind.FILING,
                    title="Winner Corp. 8-K",
                    text=(
                        "<?xml version='1.0'?><html>"
                        "<!-- Field: Set; Name: xdx; ID: xdx_06D_USDPShares -->"
                        "<body><p>Item 1.01 Entry into a Material Definitive Agreement.</p>"
                        "<p>The company signed a customer order for AI data center liquid cooling systems.</p>"
                        "<p>Management described proprietary high density cooling and gross margin leverage.</p>"
                        "</body></html>"
                    ),
                    source_id="sec:winner:8k",
                    source_url="https://www.sec.gov/example",
                    published_date=AS_OF - timedelta(days=2),
                    retrieved_at=STAMP,
                )
            ],
        )
        learning = learn_pre_surge_signal_logic([case])
        themes = build_cold_start_theme_maps([case], learning)
        blind = (HeuristicBlindCaseResearcher().analyze(case),)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize([case], blind, learning, themes)
        scheme, _diagnostic = synthesize_information_scheme(
            [case],
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )

        packet = build_blind_scheme_packet(case, scheme, anonymous_case_id="case_004")

        catalyst = next(section for section in packet.sections if section.name == "Catalyst/Event Ledger")
        theme = next(section for section in packet.sections if section.name == "Theme/Industry Transmission")
        materiality = next(section for section in packet.sections if section.name == "Materiality and Timing")
        packet_text = json.dumps(packet.to_dict())
        self.assertTrue(
            any(
                item.get("item_type") == "source_detail"
                and "customer order" in item.get("summary", "")
                and item.get("relative_timing_days") == -2
                for item in catalyst.items
            )
        )
        self.assertTrue(
            any(item.get("item_type") == "ai_chain_transmission" for item in theme.items)
        )
        self.assertTrue(
            any(
                item.get("item_type") == "ai_chain_stage_map"
                and item.get("directness_level") == "company_level"
                and item.get("bottleneck_position") == "bottleneck_candidate"
                and "cooling/thermal management" in item.get("matched_stages", ())
                and "customer capex and order pull-through" in item.get("matched_stages", ())
                and "specialized integration" in item.get("irreplaceability_markers", ())
                and "margin/EBITDA leverage" in item.get("operating_leverage_markers", ())
                and "Map upstream and downstream bottleneck layers." in item.get("methodology", ())
                for item in theme.items
            )
        )
        self.assertTrue(
            any("liquid cooling" in item.get("summary", "") for item in materiality.items)
        )
        self.assertNotIn("Field: Set", packet_text)
        self.assertNotIn("Winner Corp", packet_text)
        self.assertNotIn("https://", packet_text)

    def test_ralph_packet_marks_ai_theme_without_direct_pullthrough_as_caution(self) -> None:
        case = make_case(
            "control-ai-theme-only",
            CaseOutcomeLabel.CONTROL,
            revenue_growth=0.04,
            earnings_growth=-0.05,
            margin=0.02,
            return_20d=0.03,
            return_60d=0.08,
            target_upside=0.05,
            catalyst_count=0,
            extra_documents=[
                DocumentRecord(
                    document_id="ai-theme",
                    symbol="THEME",
                    kind=EvidenceKind.RESEARCH_REPORT,
                    title="AI strategy overview",
                    text=(
                        "The company discussed artificial intelligence strategy and machine learning "
                        "initiatives but disclosed no customer orders, capacity expansion, funding, "
                        "or data center deployment."
                    ),
                    source_id="research:theme:ai",
                    source_url="https://example.com/ai-theme",
                    published_date=AS_OF - timedelta(days=5),
                    retrieved_at=STAMP,
                )
            ],
        )
        learning = learn_pre_surge_signal_logic([case])
        themes = build_cold_start_theme_maps([case], learning)
        blind = (HeuristicBlindCaseResearcher().analyze(case),)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize([case], blind, learning, themes)
        scheme, _diagnostic = synthesize_information_scheme(
            [case],
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )

        packet = build_blind_scheme_packet(case, scheme, anonymous_case_id="case_ai_theme_only")

        theme = next(section for section in packet.sections if section.name == "Theme/Industry Transmission")
        packet_text = json.dumps(packet.to_dict())
        self.assertTrue(
            any(
                item.get("item_type") == "ai_chain_stage_map"
                and item.get("directness_level") == "theme_only"
                and item.get("bottleneck_position") == "theme_adjacent"
                for item in theme.items
            )
        )
        self.assertTrue(
            any(item.get("item_type") == "ai_chain_theme_caution" for item in theme.items)
        )
        self.assertNotIn("https://example.com", packet_text)

    def test_ralph_packet_distills_event_polarity_materiality_and_risk(self) -> None:
        ai_order_case = make_case(
            "winner-ai-order",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.25,
            earnings_growth=0.35,
            margin=0.16,
            return_20d=-0.22,
            return_60d=-0.34,
            target_upside=0.20,
            catalyst_count=0,
            extra_documents=[
                DocumentRecord(
                    document_id="ai-order",
                    symbol="WINNER",
                    kind=EvidenceKind.FILING,
                    title="8-K material agreement",
                    text=(
                        "Item 1.01 Entry into a Material Definitive Agreement. "
                        "The company signed a customer order for AI data center liquid cooling "
                        "systems with expected shipments and capacity expansion."
                    ),
                    source_id="sec:winner:8k",
                    source_url="https://www.sec.gov/example",
                    published_date=AS_OF - timedelta(days=3),
                    retrieved_at=STAMP,
                )
            ],
        )
        delisting_case = make_case(
            "control-listing-risk",
            CaseOutcomeLabel.CONTROL,
            revenue_growth=-0.05,
            earnings_growth=-0.20,
            margin=-0.03,
            return_20d=-0.18,
            return_60d=-0.28,
            target_upside=0.05,
            catalyst_count=0,
            extra_documents=[
                DocumentRecord(
                    document_id="listing-risk",
                    symbol="RISK",
                    kind=EvidenceKind.FILING,
                    title="Nasdaq listing notice",
                    text=(
                        "Item 3.01 Notice of Delisting or Failure to Satisfy a Continued "
                        "Listing Rule. Nasdaq notified the company of minimum bid "
                        "non-compliance and potential delisting risk."
                    ),
                    source_id="sec:risk:8k",
                    source_url="https://www.sec.gov/example-risk",
                    published_date=AS_OF - timedelta(days=4),
                    retrieved_at=STAMP,
                )
            ],
        )
        cases = [ai_order_case, delisting_case]
        learning = learn_pre_surge_signal_logic(cases)
        themes = build_cold_start_theme_maps(cases, learning)
        blind = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(cases, blind, learning, themes)
        scheme, _diagnostic = synthesize_information_scheme(
            cases,
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )

        ai_packet = build_blind_scheme_packet(ai_order_case, scheme, anonymous_case_id="case_ai")
        risk_packet = build_blind_scheme_packet(delisting_case, scheme, anonymous_case_id="case_risk")

        ai_catalyst = next(section for section in ai_packet.sections if section.name == "Catalyst/Event Ledger")
        ai_materiality = next(section for section in ai_packet.sections if section.name == "Materiality and Timing")
        ai_expectation = next(section for section in ai_packet.sections if section.name == "Expectation Gap Summary")
        self.assertTrue(
            any(
                item.get("item_type") == "event_distillation"
                and item.get("event_family") == "ai_chain_bottleneck_transmission"
                and item.get("event_polarity") == "positive"
                for item in ai_catalyst.items
            )
        )
        self.assertTrue(
            any(
                item.get("item_type") == "event_materiality"
                and item.get("event_polarity") == "positive"
                and "AI-chain directness" in item.get("summary", "")
                for item in ai_materiality.items
            )
        )
        self.assertTrue(
            any(
                item.get("item_type") == "expectation_gap_lens"
                and item.get("event_polarity_counts", {}).get("positive") == 1
                for item in ai_expectation.items
            )
        )

        risk_section = next(section for section in risk_packet.sections if section.name == "Contrary/Risk Evidence")
        risk_expectation = next(
            section for section in risk_packet.sections if section.name == "Expectation Gap Summary"
        )
        self.assertTrue(
            any(
                item.get("item_type") == "event_risk"
                and item.get("event_family") == "listing_compliance"
                and item.get("event_polarity") == "risk"
                for item in risk_section.items
            )
        )
        self.assertTrue(
            any(
                item.get("item_type") == "expectation_gap_caution"
                and "do not treat price weakness" in item.get("summary", "")
                for item in risk_expectation.items
            )
        )

    def test_ralph_packet_marks_generic_market_sources_as_caution_not_catalyst(self) -> None:
        case = make_case(
            "generic-news",
            CaseOutcomeLabel.CONTROL,
            revenue_growth=0.02,
            earnings_growth=-0.05,
            margin=0.01,
            return_20d=-0.12,
            return_60d=-0.22,
            target_upside=0.05,
            catalyst_count=0,
            sector="Unknown",
            extra_documents=[
                DocumentRecord(
                    document_id="generic-it-movers",
                    symbol="GEN",
                    kind=EvidenceKind.NEWS,
                    title="12 Information Technology Stocks Moving In Tuesday's Intraday Session",
                    text=(
                        "12 Information Technology Stocks Moving In Tuesday's Intraday Session. "
                        "AMC, Cisco Set To Report Earnings As Investors Watch Out For Core CPI."
                    ),
                    source_id="wire:generic",
                    source_url="https://example.com/generic",
                    published_date=AS_OF - timedelta(days=2),
                    retrieved_at=STAMP,
                )
            ],
        )
        learning = learn_pre_surge_signal_logic([case])
        themes = build_cold_start_theme_maps([case], learning)
        blind = (HeuristicBlindCaseResearcher().analyze(case),)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize([case], blind, learning, themes)
        scheme, _diagnostic = synthesize_information_scheme(
            [case],
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )

        packet = build_blind_scheme_packet(case, scheme, anonymous_case_id="case_generic")

        catalyst = next(section for section in packet.sections if section.name == "Catalyst/Event Ledger")
        theme = next(section for section in packet.sections if section.name == "Theme/Industry Transmission")
        risk = next(section for section in packet.sections if section.name == "Contrary/Risk Evidence")
        self.assertFalse(
            any(item.get("item_type") == "event_distillation" for item in catalyst.items)
        )
        self.assertTrue(
            any(
                item.get("item_type") == "identity_safe_business_context"
                and item.get("sector") == "Information Technology"
                for item in theme.items
            )
        )
        self.assertTrue(
            any(item.get("item_type") == "source_quality_caution" for item in risk.items)
        )

    def test_ralph_document_enrichment_adds_source_fact_digest(self) -> None:
        case = make_case(
            "abc-filing-digest",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.02,
            earnings_growth=-0.10,
            margin=-0.04,
            return_20d=-0.18,
            return_60d=-0.30,
            target_upside=0.15,
            catalyst_count=0,
            sector="Unknown",
            company_name="ABC Digest Corp",
        )
        document = DocumentRecord(
            document_id="abc-10q",
            symbol="ABC",
            kind=EvidenceKind.FILING,
            title="ABC Digest Corp 10-Q",
            text=(
                "<html><body><p>ABC Digest Corp generated sales volumes of 12,989 Boe/d.</p>"
                "<p>Cash and cash equivalents totaled $10.5 million.</p>"
                "<p>Total debt outstanding was $200 million.</p>"
                "<p>Item 3.01 Notice of Delisting or Failure to Satisfy a Continued "
                "Listing Rule. The exchange notice referenced a minimum bid price of at least "
                "$1.00 per share and stockholders' equity requirements.</p>"
                "<p>The company reported stockholders' equity of $(1.8) million.</p>"
                "<p>The company must submit a plan of compliance by June 30, 2025.</p>"
                "<p>The company borrowed approximately $121.3 million under the revolving credit "
                "facility, and aggregate principal amount of borrowings was $175.0 million.</p>"
                "</body></html>"
            ),
            source_id="sec:abc:10q",
            source_url="https://www.sec.gov/Archives/edgar/data/1/2/abc-10q.htm",
            published_date=AS_OF - timedelta(days=4),
            retrieved_at=STAMP,
        )
        enriched = _enrich_cases_with_documents((case,), {"ABC": (document,)})
        learning = learn_pre_surge_signal_logic(enriched)
        themes = build_cold_start_theme_maps(enriched, learning)
        blind = tuple(HeuristicBlindCaseResearcher().analyze(item) for item in enriched)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(enriched, blind, learning, themes)
        scheme, _diagnostic = synthesize_information_scheme(
            enriched,
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )

        packet = build_blind_scheme_packet(enriched[0], scheme, anonymous_case_id="case_digest")

        fundamentals = next(section for section in packet.sections if section.name == "Compressed Fundamentals")
        risk = next(section for section in packet.sections if section.name == "Contrary/Risk Evidence")
        packet_text = json.dumps(packet.to_dict())
        self.assertTrue(
            any(
                item.get("item_type") == "source_fact_digest"
                and "cash: 10.5 million" in item.get("summary", "")
                and "total debt: 200 million" in item.get("summary", "")
                and "production volume: 12,989 Boe/d" in item.get("summary", "")
                and "revolver draw: 121.3 million" in item.get("summary", "")
                for item in fundamentals.items
            )
        )
        self.assertTrue(
            any(
                item.get("item_type") == "source_fact_digest"
                and "listing risk" in item.get("summary", "")
                and "minimum bid 1.00 per share" in item.get("summary", "")
                and "reported stockholders' equity: -1.8 million" in item.get("summary", "")
                and "compliance plan due June 30, 2025" in item.get("summary", "")
                for item in risk.items
            )
        )
        self.assertNotIn("ABC Digest", packet_text)
        self.assertNotIn("https://www.sec.gov", packet_text)

    def test_ralph_document_enrichment_adds_deal_status_and_chain_digest(self) -> None:
        case = make_case(
            "spac-deal-digest",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.02,
            earnings_growth=-0.10,
            margin=-0.04,
            return_20d=-0.18,
            return_60d=-0.30,
            target_upside=0.15,
            catalyst_count=0,
            sector="Unknown",
            company_name="Acquirer Shell Corp",
        )
        document = DocumentRecord(
            document_id="spac-deal-news",
            symbol="SPAC",
            kind=EvidenceKind.NEWS,
            title="TargetOps and Acquirer Shell Corp File Form F-4/A Ahead of Proposed Nasdaq Listing",
            text=(
                "TargetOps and Acquirer Shell Corp filed a Form F-4/A registration statement "
                "in connection with their proposed Business Combination. TargetOps reported "
                "revenue reaching $219.8 million, up 36.4% year-over-year, and Adjusted "
                "EBITDA increasing by 178.4% to $14.0 million. The company is actively "
                "pursuing a Nasdaq listing and provided positive guidance. Management cited "
                "digital transformation, cybersecurity, AI solutions, cloud partnerships, "
                "and customer demand. The merger deadline was extended to July 31, 2024, "
                "with potential further extensions to October 31, 2024 after shareholder "
                "approval, though some Class A ordinary shares were redeemed. The company "
                "was later dropped from Nasdaq Composite Index and auditor going concern "
                "language appeared. Hidden Issuer, Inc. (the \"Company\") held an annual meeting."
            ),
            source_id="wire:spac:deal",
            source_url="https://example.com/spac-deal",
            published_date=AS_OF - timedelta(days=30),
            retrieved_at=STAMP,
        )
        enriched = _enrich_cases_with_documents((case,), {"SPAC": (document,)})
        learning = learn_pre_surge_signal_logic(enriched)
        themes = build_cold_start_theme_maps(enriched, learning)
        blind = tuple(HeuristicBlindCaseResearcher().analyze(item) for item in enriched)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(enriched, blind, learning, themes)
        scheme, _diagnostic = synthesize_information_scheme(
            enriched,
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )

        packet = build_blind_scheme_packet(enriched[0], scheme, anonymous_case_id="case_deal_chain")

        catalyst = next(section for section in packet.sections if section.name == "Catalyst/Event Ledger")
        theme = next(section for section in packet.sections if section.name == "Theme/Industry Transmission")
        materiality = next(section for section in packet.sections if section.name == "Materiality and Timing")
        risk = next(section for section in packet.sections if section.name == "Contrary/Risk Evidence")
        packet_text = json.dumps(packet.to_dict())
        self.assertTrue(
            any(
                item.get("item_type") == "event_distillation"
                and item.get("event_family") == "ai_chain_bottleneck_transmission"
                for item in catalyst.items
            )
        )
        self.assertTrue(
            any(
                item.get("item_type") == "source_fact_digest"
                and "industry-chain lens" in item.get("summary", "")
                and "company-level pull-through" in item.get("summary", "")
                for item in theme.items
            )
        )
        self.assertTrue(
            any(
                item.get("item_type") == "source_fact_digest"
                and "deal status: Form F-4 registration statement" in item.get("summary", "")
                and "deal timing: merger deadline extended to July 31, 2024" in item.get("summary", "")
                and "revenue/sales: 219.8 million" in item.get("summary", "")
                and "adjusted EBITDA: 14.0 million" in item.get("summary", "")
                for item in materiality.items
            )
        )
        self.assertTrue(
            any(
                item.get("item_type") == "source_fact_digest"
                and "deal/capital risk: shareholder redemption" in item.get("summary", "")
                and "listing/tradability risk" in item.get("summary", "")
                and "liquidity risk" in item.get("summary", "")
                for item in risk.items
            )
        )
        self.assertNotIn("Acquirer Shell", packet_text)
        self.assertNotIn("TargetOps", packet_text)
        self.assertNotIn("Hidden Issuer", packet_text)
        self.assertNotIn("https://example.com", packet_text)

    def test_ralph_experiment_rehydrates_saved_documents_for_current_packets(self) -> None:
        stale_case = make_case(
            "abc-1",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.10,
            earnings_growth=0.20,
            margin=0.08,
            return_20d=-0.10,
            return_60d=-0.30,
            target_upside=0.20,
            catalyst_count=0,
        )
        stale_evidence = EvidenceItem(
            kind=EvidenceKind.FILING,
            summary="filing document available: ABC 8-K. Excerpt: <!-- Field: Set; Name: xdx; ID: xdx_06D -->",
            as_of_date=AS_OF,
            source_id="sec:abc:8k",
            source_url="https://www.sec.gov/example",
            published_date=AS_OF - timedelta(days=1),
        )
        stale_case = replace(
            stale_case,
            packet=replace(stale_case.packet, evidence=stale_case.packet.evidence + [stale_evidence]),
        )
        with TemporaryDirectory() as tmp:
            documents_path = Path(tmp) / "documents_and_catalysts.json"
            documents_path.write_text(
                json.dumps(
                    {
                        "documents_by_symbol": {
                            "ABC": [
                                {
                                    "document_id": "abc-8k",
                                    "symbol": "ABC",
                                    "kind": "filing",
                                    "title": "ABC 8-K",
                                    "text": (
                                        "<html><body><p>Item 1.01 Entry into a Material Definitive Agreement.</p>"
                                        "<p>The issuer signed a customer order for AI power infrastructure.</p>"
                                        "</body></html>"
                                    ),
                                    "source_id": "sec:abc:8k",
                                    "source_url": "https://www.sec.gov/example",
                                    "published_date": (AS_OF - timedelta(days=1)).isoformat(),
                                    "retrieved_at": STAMP.isoformat(),
                                    "available_date": (AS_OF - timedelta(days=1)).isoformat(),
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            documents = _load_documents_by_symbol(documents_path)
            enriched = _enrich_cases_with_documents((stale_case,), documents)

        summaries = [item.summary for item in enriched[0].packet.evidence]
        self.assertTrue(any("customer order for AI power infrastructure" in summary for summary in summaries))
        self.assertFalse(any("Field: Set" in summary for summary in summaries))

    def test_ralph_experiment_refreshes_selected_sec_filing_text(self) -> None:
        class FakeSecTextTransport:
            def __init__(self) -> None:
                self.urls: list[str] = []

            def get_text(self, url, headers):
                self.urls.append(url)
                return (
                    "<?xml version='1.0'?><html><head><title></title></head><body>"
                    "<p>Item 1.01 Entry into a Material Definitive Agreement.</p>"
                    "<p>The issuer secured a material financing backstop before the deadline.</p>"
                    "</body></html>"
                )

        case = make_case(
            "abc-filing-refresh",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.10,
            earnings_growth=0.20,
            margin=0.08,
            return_20d=-0.10,
            return_60d=-0.30,
            target_upside=0.20,
            catalyst_count=0,
        )
        documents = {
            "ABC": (
                DocumentRecord(
                    document_id="abc-sec-8k",
                    symbol="ABC",
                    kind=EvidenceKind.FILING,
                    title="ABC 8-K",
                    text="<?xml version='1.0'?><html xmlns:xbrli='xbrl'><head></head>",
                    source_id="sec:abc:8k",
                    source_url="https://www.sec.gov/Archives/edgar/data/1/2/form8-k.htm",
                    published_date=AS_OF - timedelta(days=1),
                    retrieved_at=STAMP,
                ),
            )
        }
        transport = FakeSecTextTransport()

        refreshed, warnings = _refresh_sec_filing_documents_for_cases(
            documents,
            (case,),
            user_agent="test-agent",
            transport=transport,
        )
        enriched = _enrich_cases_with_documents((case,), refreshed)

        self.assertEqual(warnings, ())
        self.assertEqual(transport.urls, ["https://www.sec.gov/Archives/edgar/data/1/2/form8-k.htm"])
        summaries = [item.summary for item in enriched[0].packet.evidence]
        self.assertTrue(any("material financing backstop" in summary for summary in summaries))
        self.assertFalse(any("xmlns:xbrli" in summary for summary in summaries))

    def test_ralph_refresh_skips_cross_case_identity_contamination(self) -> None:
        class ContaminatedSecTextTransport:
            def get_text(self, url, headers):
                return (
                    "<html><body><p>Item 5.02 Departure of Directors.</p>"
                    "<p>SRM Entertainment, Inc. granted options to its chief executive officer.</p>"
                    "</body></html>"
                )

        target_case = make_case(
            "abc-filing-refresh",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.10,
            earnings_growth=0.20,
            margin=0.08,
            return_20d=-0.10,
            return_60d=-0.30,
            target_upside=0.20,
            catalyst_count=0,
        )
        other_case = make_case(
            "srm-other",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.10,
            earnings_growth=0.20,
            margin=0.08,
            return_20d=-0.10,
            return_60d=-0.30,
            target_upside=0.20,
            catalyst_count=0,
            company_name="SRM Entertainment Inc",
        )
        original_text = "8-K filed on the as-of date."
        documents = {
            "ABC": (
                DocumentRecord(
                    document_id="abc-sec-8k",
                    symbol="ABC",
                    kind=EvidenceKind.FILING,
                    title="ABC 8-K",
                    text=original_text,
                    source_id="sec:abc:8k",
                    source_url="https://www.sec.gov/Archives/edgar/data/1/2/form8-k.htm",
                    published_date=AS_OF - timedelta(days=1),
                    retrieved_at=STAMP,
                ),
            )
        }

        refreshed, warnings = _refresh_sec_filing_documents_for_cases(
            documents,
            (target_case, other_case),
            user_agent="test-agent",
            transport=ContaminatedSecTextTransport(),
        )

        self.assertIn("cross-case identity terms", warnings[0])
        self.assertEqual(refreshed["ABC"][0].text, original_text)

    def test_ralph_refresh_skips_sec_declared_identity_conflict(self) -> None:
        class MismatchedSecTextTransport:
            def get_text(self, url, headers):
                return (
                    "<html><body><p>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</p>"
                    "<p>FORM 8-K</p>"
                    "<p>Date of Report (Date of earliest event reported): January 6, 2025</p>"
                    "<p>SRM ENTERTAINMENT, INC.</p>"
                    "<p>(Exact name of registrant as specified in charter)</p>"
                    "<p>Title of each class Trading Symbol(s) Name of each exchange on which registered</p>"
                    "<p>Common Stock SRM The Nasdaq Stock Market LLC</p>"
                    "<p>Item 5.02 Departure of Directors or Principal Officers.</p>"
                    "</body></html>"
                )

        target_case = make_case(
            "abc-filing-refresh",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.10,
            earnings_growth=0.20,
            margin=0.08,
            return_20d=-0.10,
            return_60d=-0.30,
            target_upside=0.20,
            catalyst_count=0,
        )
        original_text = "8-K filed on the as-of date."
        documents = {
            "ABC": (
                DocumentRecord(
                    document_id="abc-sec-8k",
                    symbol="ABC",
                    kind=EvidenceKind.FILING,
                    title="ABC 8-K",
                    text=original_text,
                    source_id="sec:abc:8k",
                    source_url="https://www.sec.gov/Archives/edgar/data/1/2/form8-k.htm",
                    published_date=AS_OF - timedelta(days=1),
                    retrieved_at=STAMP,
                ),
            )
        }

        refreshed, warnings = _refresh_sec_filing_documents_for_cases(
            documents,
            (target_case,),
            user_agent="test-agent",
            transport=MismatchedSecTextTransport(),
        )

        self.assertIn("declared identity conflicts", warnings[0])
        self.assertIn("trading symbols SRM", warnings[0])
        self.assertEqual(refreshed["ABC"][0].text, original_text)

    def test_ralph_sec_augmentation_allows_same_cik_former_name_and_masks_it(self) -> None:
        class SameCikSecTransport:
            def get_json(self, url, headers):
                if url.endswith("/files/company_tickers_exchange.json"):
                    return {"fields": ["cik", "name", "ticker", "exchange"], "data": []}
                return {
                    "name": "Tron Inc.",
                    "tickers": ["TRON"],
                    "formerNames": [{"name": "SRM Entertainment, Inc."}],
                    "filings": {
                        "recent": {
                            "accessionNumber": [
                                "0001493152-25-001960",
                                "0001493152-25-999999",
                            ],
                            "filingDate": [
                                (AS_OF - timedelta(days=2)).isoformat(),
                                (AS_OF + timedelta(days=1)).isoformat(),
                            ],
                            "form": ["8-K", "8-K"],
                            "primaryDocument": ["form8-k.htm", "future.htm"],
                            "reportDate": [
                                (AS_OF - timedelta(days=2)).isoformat(),
                                (AS_OF + timedelta(days=1)).isoformat(),
                            ],
                        }
                    },
                }

            def get_text(self, url, headers):
                return (
                    "<html><body><p>SRM ENTERTAINMENT, INC.</p>"
                    "<p>(Exact name of registrant as specified in charter)</p>"
                    "<p>Title of each class Trading Symbol(s) Name of each exchange on which registered</p>"
                    "<p>Common Stock SRM The Nasdaq Stock Market LLC</p>"
                    "<p>Item 1.01 Entry into a Material Definitive Agreement.</p>"
                    "<p>The issuer entered into a credit agreement and reported cash and cash equivalents "
                    "of $12.3 million.</p></body></html>"
                )

        case = make_case(
            "tron-same-cik",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.10,
            earnings_growth=0.20,
            margin=0.08,
            return_20d=-0.10,
            return_60d=-0.30,
            target_upside=0.20,
            catalyst_count=0,
            company_name="Corner Growth Acquisition Corp 2 - Class A / Tron Inc.",
        )
        documents = {
            "TRON": (
                DocumentRecord(
                    document_id="old-sec",
                    symbol="TRON",
                    kind=EvidenceKind.FILING,
                    title="Existing SEC filing",
                    text="Existing SEC filing.",
                    source_id="sec:0001956744:0000000000-25-000000",
                    source_url="https://www.sec.gov/Archives/edgar/data/1956744/000000000025000000/form8-k.htm",
                    published_date=AS_OF - timedelta(days=5),
                    retrieved_at=STAMP,
                ),
            )
        }

        augmented, warnings = _augment_sec_submission_documents_for_cases(
            documents,
            (case,),
            user_agent="test-agent",
            forms=("8-K",),
            lookback_days=30,
            max_filings_per_symbol=5,
            transport=SameCikSecTransport(),
        )
        enriched = _enrich_cases_with_documents((case,), augmented)
        learning = learn_pre_surge_signal_logic(enriched)
        themes = build_cold_start_theme_maps(enriched, learning)
        blind = (HeuristicBlindCaseResearcher().analyze(enriched[0]),)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(enriched, blind, learning, themes)
        scheme, _diagnostic = synthesize_information_scheme(
            enriched,
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )
        packet = build_blind_scheme_packet(enriched[0], scheme, anonymous_case_id="case_same_cik")
        packet_text = json.dumps(packet.to_dict())

        self.assertEqual(warnings, ())
        self.assertIn("0001493152-25-001960", {document.source_id.split(":")[-1] for document in augmented["TRON"]})
        self.assertIn("credit agreement", packet_text)
        self.assertIn("cash", packet_text)
        self.assertNotIn("SRM", packet_text)
        self.assertNotIn("SRM Entertainment", packet_text)
        self.assertNotIn("TRON", packet_text)
        self.assertNotIn("Corner Growth", packet_text)

    def test_ralph_alpha_vantage_news_augmentation_is_bounded_and_point_in_time(self) -> None:
        class FakeAlphaVantageClient:
            def __init__(self) -> None:
                self.calls = []

            def news_sentiment(self, symbol, **kwargs):
                self.calls.append((symbol, kwargs))
                return {
                    "feed": [
                        {
                            "time_published": "20260415T120000",
                            "title": "Company secures public contract",
                            "summary": "The company secured a $10.9 million federal defense contract.",
                            "url": "https://example.com/contract",
                        },
                        {
                            "time_published": "20260504T120000",
                            "title": "Future article",
                            "summary": "This was published after the case cutoff.",
                            "url": "https://example.com/future",
                        },
                        {
                            "time_published": "20260420T120000",
                            "title": "Low relevance industry article",
                            "summary": "Another issuer signed a contract.",
                            "url": "https://example.com/low-relevance",
                            "ticker_sentiment": [
                                {"ticker": "NEWS", "relevance_score": "0.05"}
                            ],
                        },
                    ]
                }

        case = make_case(
            "news-winner",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.10,
            earnings_growth=0.20,
            margin=0.08,
            return_20d=-0.10,
            return_60d=-0.30,
            target_upside=0.20,
            catalyst_count=0,
        )
        client = FakeAlphaVantageClient()

        augmented, warnings = _augment_alpha_vantage_news_for_cases(
            {},
            (case,),
            lookback_days=90,
            max_news_per_symbol=25,
            client=client,
        )

        self.assertEqual(warnings, ())
        self.assertEqual(len(augmented["NEWS"]), 1)
        document = augmented["NEWS"][0]
        self.assertEqual(document.content_scope, DocumentContentScope.SUMMARY_ONLY)
        self.assertEqual(document.published_date, date(2026, 4, 15))
        self.assertIn("federal defense contract", document.text)
        self.assertNotIn("Future article", document.text)
        self.assertEqual(client.calls[0][0], "NEWS")
        self.assertEqual(client.calls[0][1]["limit"], 25)

    def test_ralph_preflight_leakage_report_scans_cross_case_identities(self) -> None:
        class FakePacket:
            anonymous_case_id = "case_001"

            def to_prompt_dict(self):
                return {"text": "SRM Entertainment Inc appeared in a mismapped source document."}

        case = make_case(
            "abc-packet",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.10,
            earnings_growth=0.20,
            margin=0.08,
            return_20d=-0.10,
            return_60d=-0.30,
            target_upside=0.20,
            catalyst_count=0,
        )
        other_case = make_case(
            "srm-other",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.10,
            earnings_growth=0.20,
            margin=0.08,
            return_20d=-0.10,
            return_60d=-0.30,
            target_upside=0.20,
            catalyst_count=0,
            company_name="SRM Entertainment Inc",
        )

        report = _leakage_report([(FakePacket(), case), (FakePacket(), other_case)])

        self.assertFalse(report["passed"])
        findings = report["case_reports"][0]["findings"]
        self.assertTrue(any(item["kind"].startswith("cross_case_") for item in findings))

    def test_ralph_evaluation_metrics_and_feedback_proposal(self) -> None:
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
        analyses = [
            RalphBlindAnalysis(
                source_case_id="winner-1",
                anonymous_case_id="case_001",
                as_of_date=AS_OF.isoformat(),
                scheme_version="information-scheme-v0.1",
                surge_candidate="possible",
                surge_candidate_reason="thin packet",
                expectation_gap="thin",
                pre_surge_signals=("signal",),
                contrary_evidence=("risk",),
                catalyst_watch=("watch",),
                missing_context=(
                    "Current status of the proposed business combination is missing.",
                    "Latest filings, financing arrangements, float, and liquidity are missing.",
                ),
                confidence=0.30,
                raw_text="{}",
            ),
            RalphBlindAnalysis(
                source_case_id="control-1",
                anonymous_case_id="case_002",
                as_of_date=AS_OF.isoformat(),
                scheme_version="information-scheme-v0.1",
                surge_candidate="possible",
                surge_candidate_reason="looks similar",
                expectation_gap="thin",
                pre_surge_signals=("signal",),
                contrary_evidence=("risk",),
                catalyst_watch=("watch",),
                confidence=0.70,
                raw_text="{}",
            ),
        ]
        evaluation = evaluate_scheme_performance(cases, analyses, scheme_version="information-scheme-v0.1")
        learning = learn_pre_surge_signal_logic(cases)
        themes = build_cold_start_theme_maps(cases, learning)
        blind = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(cases, blind, learning, themes)
        scheme, diagnostic = synthesize_information_scheme(
            cases,
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )

        error_analysis = analyze_scheme_errors(evaluation, diagnostic)
        proposal = propose_next_information_scheme(scheme, error_analysis)

        self.assertEqual(evaluation.confidence_gap, -0.4)
        self.assertEqual(evaluation.positive_confidence_gap, -0.4)
        self.assertEqual(evaluation.false_positive_controls, ("control-1",))
        self.assertEqual(evaluation.false_negative_winners, ("winner-1",))
        self.assertEqual(evaluation.false_positive_rate, 1.0)
        self.assertEqual(evaluation.false_negative_rate, 1.0)
        self.assertIn("business combination", " ".join(evaluation.unable_to_judge_reasons))
        self.assertFalse(evaluation.separation_passed)
        self.assertIn("deal_status_timing", error_analysis.missing_evidence_families)
        self.assertIn("capital_structure_liquidity", error_analysis.missing_evidence_families)
        self.assertEqual(proposal.version, "information-scheme-v0.2")
        self.assertIn("proposal_only", proposal.proposal_status)
        self.assertNotEqual(proposal.to_dict()["proposal_status"], "production_default")

    def test_ralph_positive_confidence_gap_ignores_confident_negative_judgments(self) -> None:
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
        analyses = [
            RalphBlindAnalysis(
                source_case_id="winner-1",
                anonymous_case_id="case_001",
                as_of_date=AS_OF.isoformat(),
                scheme_version="information-scheme-v0.1",
                surge_candidate="unlikely",
                surge_candidate_reason="confidently negative",
                expectation_gap="none",
                pre_surge_signals=(),
                contrary_evidence=("risk",),
                catalyst_watch=(),
                confidence=0.90,
                raw_text="{}",
            ),
            RalphBlindAnalysis(
                source_case_id="control-1",
                anonymous_case_id="case_002",
                as_of_date=AS_OF.isoformat(),
                scheme_version="information-scheme-v0.1",
                surge_candidate="insufficient_information",
                surge_candidate_reason="thin",
                expectation_gap="none",
                pre_surge_signals=(),
                contrary_evidence=(),
                catalyst_watch=(),
                confidence=0.20,
                raw_text="{}",
            ),
        ]

        evaluation = evaluate_scheme_performance(cases, analyses, scheme_version="information-scheme-v0.1")

        self.assertEqual(evaluation.confidence_gap, 0.7)
        self.assertEqual(evaluation.positive_confidence_gap, 0.0)
        self.assertEqual(evaluation.false_negative_rate, 1.0)
        self.assertFalse(evaluation.separation_passed)

    def test_ralph_feedback_iterations_apply_prior_proposal_cumulatively(self) -> None:
        class AlwaysFalseNegativeResearcher:
            def analyze(self, packet):
                return RalphBlindAnalysis(
                    source_case_id=packet.source_case_id,
                    anonymous_case_id=packet.anonymous_case_id,
                    as_of_date=packet.as_of_date,
                    scheme_version=packet.scheme_version,
                    surge_candidate="insufficient_information",
                    surge_candidate_reason="still missing decisive catalyst context",
                    expectation_gap="missing",
                    pre_surge_signals=(),
                    contrary_evidence=("risk",),
                    catalyst_watch=(),
                    missing_context=("orders/contracts", "theme transmission"),
                    confidence=0.20,
                    raw_text="{}",
                )

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
                catalyst_count=1,
            ),
            make_case(
                "control-1",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.02,
                earnings_growth=-0.03,
                margin=0.03,
                return_20d=0.00,
                return_60d=0.01,
                target_upside=0.02,
                catalyst_count=0,
            ),
        ]
        learning = learn_pre_surge_signal_logic(cases)
        themes = build_cold_start_theme_maps(cases, learning)
        baseline = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(cases, baseline, learning, themes)

        result = run_ralph_loop(
            cases,
            baseline_blind_analyses=baseline,
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
            run_id="ralph-cumulative-feedback-test",
            blind_researcher=AlwaysFalseNegativeResearcher(),
            max_iterations=3,
        )

        catalyst_budgets = [
            next(
                section.token_budget
                for section in iteration.scheme.sections
                if section.name == "Catalyst/Event Ledger"
            )
            for iteration in result.iterations
        ]
        self.assertEqual(catalyst_budgets, [900, 1000, 1100])
        self.assertEqual(result.next_scheme_proposal.version, "information-scheme-v0.4")
        self.assertNotEqual(result.next_scheme_proposal.proposal_status, "production_default")

    def test_openai_ralph_blind_researcher_uses_no_tools_and_anonymous_prompt(self) -> None:
        case = make_case(
            "winner-apple",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.40,
            earnings_growth=0.70,
            margin=0.22,
            return_20d=0.11,
            return_60d=0.25,
            target_upside=0.35,
            catalyst_count=1,
            company_name="Apple Inc.",
            extra_documents=[
                DocumentRecord(
                    document_id="aapl-risk",
                    symbol="AAPL",
                    kind=EvidenceKind.NEWS,
                    title="Apple risk",
                    text="Apple Inc. reported an order with execution risk.",
                    source_id="wire:Apple",
                    source_url="https://example.com/apple",
                    published_date=AS_OF,
                    retrieved_at=STAMP,
                )
            ],
        )
        learning = learn_pre_surge_signal_logic([case])
        themes = build_cold_start_theme_maps([case], learning)
        blind = (HeuristicBlindCaseResearcher().analyze(case),)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize([case], blind, learning, themes)
        scheme, _diagnostic = synthesize_information_scheme(
            [case],
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )
        packet = build_blind_scheme_packet(case, scheme, anonymous_case_id="case_001")
        transport = FakeOpenAITransport(
            "{\"surge_candidate\":\"possible\",\"surge_candidate_reason\":\"reason\","
            "\"expectation_gap\":\"gap\",\"pre_surge_signals\":[\"signal\"],"
            "\"contrary_evidence\":[\"risk\"],\"catalyst_watch\":[\"watch\"],\"confidence\":0.4}"
        )
        client = OpenAIChatClient("gpt-5.4-mini", "test-key", transport=transport)

        OpenAIRalphBlindResearcher(client).analyze(packet)

        payload = transport.calls[0][2]
        developer_text = payload["input"][0]["content"][0]["text"]
        prompt_text = payload["input"][1]["content"][0]["text"]
        self.assertNotIn("tools", payload)
        self.assertIn("\"web_tools_allowed\": false", prompt_text)
        self.assertIn("never list missing ticker or unmasked company name", developer_text)
        self.assertIn("possible means a source-backed positive setup with confidence >= 0.45", developer_text)
        self.assertIn("intentionally hidden", prompt_text)
        self.assertIn("possible only when", prompt_text)
        for forbidden in ("AAPL", "Apple", "winner-apple", "winner", "control", "https://example.com"):
            self.assertNotIn(forbidden, prompt_text)

    def test_cached_ralph_blind_researcher_resumes_without_identity_leakage(self) -> None:
        class CountingRalphResearcher:
            def __init__(self) -> None:
                self.calls = 0

            def analyze(self, packet):
                self.calls += 1
                return RalphBlindAnalysis(
                    source_case_id=packet.source_case_id,
                    anonymous_case_id=packet.anonymous_case_id,
                    as_of_date=packet.as_of_date,
                    scheme_version=packet.scheme_version,
                    surge_candidate="possible",
                    surge_candidate_reason="Source-backed catalyst and expectation gap are present.",
                    expectation_gap="Expectations lag source-backed catalyst evidence.",
                    pre_surge_signals=("Catalyst ledger has a dated event.",),
                    contrary_evidence=("Execution risk remains.",),
                    catalyst_watch=("Watch catalyst follow-through.",),
                    missing_context=("Funding terms are incomplete.",),
                    confidence=0.61,
                    raw_text='{"surge_candidate":"possible"}',
                )

        class FailingRalphResearcher:
            def analyze(self, packet):
                raise AssertionError("cache miss")

        case = make_case(
            "cache-winner",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.30,
            earnings_growth=0.40,
            margin=0.20,
            return_20d=0.08,
            return_60d=0.16,
            target_upside=0.25,
            catalyst_count=1,
            company_name="Hidden Identity Inc",
        )
        scheme = InformationScheme(
            scheme_id="ralph-information-scheme",
            version="information-scheme-cache-test",
            sections=(
                InformationSection(
                    "Catalyst/Event Ledger",
                    1,
                    500,
                    ("catalyst_event",),
                    "List dated catalysts.",
                ),
            ),
            total_token_budget=500,
            max_compressed_context_share=0.30,
            contrary_evidence_required=True,
            compression_rules=("Cache test.",),
        )
        packet = build_blind_scheme_packet(case, scheme, anonymous_case_id="case_001")

        with TemporaryDirectory() as tmp:
            inner = CountingRalphResearcher()
            first = CachedRalphBlindResearcher(inner, tmp).analyze(packet)
            second = CachedRalphBlindResearcher(FailingRalphResearcher(), tmp).analyze(packet)
            cache_text = "\n".join(path.read_text(encoding="utf-8") for path in Path(tmp).glob("*.json"))

        self.assertEqual(inner.calls, 1)
        self.assertEqual(first.confidence, 0.61)
        self.assertEqual(second.confidence, 0.61)
        self.assertEqual(second.source_case_id, case.case_id)
        self.assertNotIn(case.case_id, cache_text)
        self.assertNotIn("Hidden Identity", cache_text)

    def test_ralph_loop_writes_artifacts_with_fake_blind_researcher(self) -> None:
        class FakeRalphResearcher:
            def analyze(self, packet):
                confidence = 0.80 if packet.anonymous_case_id == "case_001" else 0.35
                judgment = "likely" if packet.anonymous_case_id == "case_001" else "unlikely"
                return RalphBlindAnalysis(
                    source_case_id=packet.source_case_id,
                    anonymous_case_id=packet.anonymous_case_id,
                    as_of_date=packet.as_of_date,
                    scheme_version=packet.scheme_version,
                    surge_candidate=judgment,
                    surge_candidate_reason="fake",
                    expectation_gap="fake",
                    pre_surge_signals=("signal",),
                    contrary_evidence=("risk",),
                    catalyst_watch=("watch",),
                    confidence=confidence,
                    raw_text="fake",
                )

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
        learning = learn_pre_surge_signal_logic(cases)
        themes = build_cold_start_theme_maps(cases, learning)
        baseline = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(cases, baseline, learning, themes)

        with TemporaryDirectory() as tmp:
            result = run_ralph_loop(
                cases,
                baseline_blind_analyses=baseline,
                learning_result=learning,
                theme_maps=themes,
                playbook_synthesis=playbooks,
                run_id="ralph-test",
                blind_researcher=FakeRalphResearcher(),
            )
            paths = write_ralph_loop_artifacts(
                result,
                tmp,
                created_at=STAMP,
                proposal_memory_dir=Path(tmp) / "memory" / "ralph",
            )

            self.assertTrue(paths["information_scheme"].exists())
            self.assertTrue(paths["blind_scheme_evaluation"].exists())
            self.assertTrue(paths["ralph_error_analysis"].exists())
            self.assertTrue(paths["information_scheme_proposal_memory"].exists())
            self.assertTrue(result.latest_evaluation.separation_passed)
            packets_text = paths["blind_packets_by_scheme"].read_text()
            self.assertNotIn("winner-1", packets_text)
            self.assertNotIn("control-1", packets_text)

    def test_ralph_experiment_uses_holdout_and_writes_final_status(self) -> None:
        class FakeRalphResearcher:
            def analyze(self, packet):
                is_winner = packet.source_case_id.startswith("winner")
                return RalphBlindAnalysis(
                    source_case_id=packet.source_case_id,
                    anonymous_case_id=packet.anonymous_case_id,
                    as_of_date=packet.as_of_date,
                    scheme_version=packet.scheme_version,
                    surge_candidate="likely" if is_winner else "unlikely",
                    surge_candidate_reason="fake holdout separation",
                    expectation_gap="fake",
                    pre_surge_signals=("signal",),
                    contrary_evidence=("risk",),
                    catalyst_watch=("watch",),
                    confidence=0.82 if is_winner else 0.22,
                    raw_text="fake",
                )

        cases = [
            make_case(
                "winner-refine",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.35,
                earnings_growth=0.70,
                margin=0.22,
                return_20d=0.10,
                return_60d=0.25,
                target_upside=0.35,
                catalyst_count=2,
            ),
            make_case(
                "control-refine",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.04,
                earnings_growth=-0.05,
                margin=0.05,
                return_20d=0.00,
                return_60d=0.03,
                target_upside=0.04,
                catalyst_count=0,
            ),
            make_case(
                "winner-holdout",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.32,
                earnings_growth=0.50,
                margin=0.20,
                return_20d=0.08,
                return_60d=0.20,
                target_upside=0.28,
                catalyst_count=1,
            ),
            make_case(
                "control-holdout",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.02,
                earnings_growth=-0.02,
                margin=0.04,
                return_20d=0.00,
                return_60d=0.01,
                target_upside=0.02,
                catalyst_count=0,
            ),
        ]
        refinement_cases = tuple(cases[:2])
        holdout_cases = tuple(cases[2:])
        learning = learn_pre_surge_signal_logic(refinement_cases)
        themes = build_cold_start_theme_maps(refinement_cases, learning)
        baseline = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in refinement_cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(
            refinement_cases,
            baseline,
            learning,
            themes,
        )

        with TemporaryDirectory() as tmp:
            result = run_ralph_experiment(
                refinement_cases,
                holdout_cases,
                baseline_refinement_blind_analyses=baseline,
                learning_result=learning,
                theme_maps=themes,
                playbook_synthesis=playbooks,
                run_id="ralph-experiment-test",
                blind_researcher=FakeRalphResearcher(),
                max_iterations=2,
            )
            paths = write_ralph_experiment_artifacts(result, tmp, created_at=STAMP)

            self.assertEqual(result.final_status, "holdout_separated")
            self.assertTrue(result.holdout_evaluation.separation_passed)
            self.assertEqual(result.holdout_evaluation.false_positive_rate, 0.0)
            self.assertTrue(paths["ralph_experiment_summary"].exists())
            self.assertTrue(paths["holdout_blind_scheme_evaluation"].exists())
            self.assertIn("holdout_separated", paths["manifest"].read_text())
            packets_text = paths["holdout_blind_packets_by_scheme"].read_text()
            self.assertNotIn("winner-holdout", packets_text)
            self.assertNotIn("control-holdout", packets_text)

    def test_ralph_experiment_can_iterate_holdout_feedback_without_promotion(self) -> None:
        class FeedbackRalphResearcher:
            def analyze(self, packet):
                is_winner = packet.source_case_id.startswith("winner")
                feedback_scheme = packet.scheme_version == "information-scheme-v0.2"
                judgment = "likely" if is_winner and feedback_scheme else "possible"
                confidence = 0.82 if is_winner and feedback_scheme else 0.35
                if not is_winner:
                    judgment = "unlikely"
                    confidence = 0.20
                return RalphBlindAnalysis(
                    source_case_id=packet.source_case_id,
                    anonymous_case_id=packet.anonymous_case_id,
                    as_of_date=packet.as_of_date,
                    scheme_version=packet.scheme_version,
                    surge_candidate=judgment,
                    surge_candidate_reason="fake feedback separation",
                    expectation_gap="fake",
                    pre_surge_signals=("signal",),
                    contrary_evidence=("risk",),
                    catalyst_watch=("watch",),
                    missing_context=("missing catalyst specificity",) if is_winner and not feedback_scheme else (),
                    confidence=confidence,
                    raw_text="fake",
                )

        cases = [
            make_case(
                "winner-refine",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.35,
                earnings_growth=0.70,
                margin=0.22,
                return_20d=0.10,
                return_60d=0.25,
                target_upside=0.35,
                catalyst_count=2,
            ),
            make_case(
                "control-refine",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.04,
                earnings_growth=-0.05,
                margin=0.05,
                return_20d=0.00,
                return_60d=0.03,
                target_upside=0.04,
                catalyst_count=0,
            ),
            make_case(
                "winner-holdout",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.32,
                earnings_growth=0.50,
                margin=0.20,
                return_20d=0.08,
                return_60d=0.20,
                target_upside=0.28,
                catalyst_count=1,
            ),
            make_case(
                "control-holdout",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.02,
                earnings_growth=-0.02,
                margin=0.04,
                return_20d=0.00,
                return_60d=0.01,
                target_upside=0.02,
                catalyst_count=0,
            ),
        ]
        refinement_cases = tuple(cases[:2])
        holdout_cases = tuple(cases[2:])
        learning = learn_pre_surge_signal_logic(refinement_cases)
        themes = build_cold_start_theme_maps(refinement_cases, learning)
        baseline = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in refinement_cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(
            refinement_cases,
            baseline,
            learning,
            themes,
        )

        with TemporaryDirectory() as tmp:
            result = run_ralph_experiment(
                refinement_cases,
                holdout_cases,
                baseline_refinement_blind_analyses=baseline,
                learning_result=learning,
                theme_maps=themes,
                playbook_synthesis=playbooks,
                run_id="ralph-feedback-test",
                blind_researcher=FeedbackRalphResearcher(),
                max_iterations=1,
                holdout_feedback_iterations=1,
            )
            paths = write_ralph_experiment_artifacts(result, tmp, created_at=STAMP)

            self.assertFalse(result.initial_holdout_evaluation.separation_passed)
            self.assertEqual(len(result.holdout_feedback_iterations), 1)
            self.assertEqual(result.final_status, "holdout_separated")
            self.assertEqual(result.final_information_scheme.version, "information-scheme-v0.2")
            self.assertEqual(result.final_information_scheme.proposal_status, "proposal_only_pending_review")
            self.assertTrue(paths["holdout_feedback_iterations"].exists())
            self.assertIn("holdout_feedback_iteration_count", paths["manifest"].read_text())

    def test_ralph_preflight_exports_anonymous_packet_review(self) -> None:
        refinement_cases = (
            make_case(
                "winner-refine",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.35,
                earnings_growth=0.70,
                margin=0.22,
                return_20d=0.10,
                return_60d=0.25,
                target_upside=0.35,
                catalyst_count=2,
                company_name="Corner Growth Acquisition Corp 2 - Class A / Tron Inc.",
                extra_documents=[
                    DocumentRecord(
                        document_id="corner-growth-merger",
                        symbol="WINNER",
                        kind=EvidenceKind.NEWS,
                        title="Corner Growth Acquisition Corp. extends merger deadline",
                        text="Corner Growth Acquisition Corp. and Tron Inc. filed updated merger materials.",
                        source_id="wire:corner-growth",
                        source_url="https://example.com/corner-growth",
                        published_date=AS_OF,
                        retrieved_at=STAMP,
                    )
                ],
            ),
        )
        holdout_cases = (
            make_case(
                "control-holdout",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.02,
                earnings_growth=-0.02,
                margin=0.04,
                return_20d=0.00,
                return_60d=0.01,
                target_upside=0.02,
                catalyst_count=0,
                company_name="Microsoft Corporation",
            ),
        )
        learning = learn_pre_surge_signal_logic(refinement_cases)
        themes = build_cold_start_theme_maps(refinement_cases, learning)
        baseline = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in refinement_cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(
            refinement_cases,
            baseline,
            learning,
            themes,
        )

        with TemporaryDirectory() as tmp:
            paths = _write_preflight_artifacts(
                Path(tmp),
                run_id="ralph-preflight-test",
                created_at=STAMP,
                refinement_cases=refinement_cases,
                holdout_cases=holdout_cases,
                learning_result=learning,
                theme_maps=themes,
                playbook_synthesis=playbooks,
            )

            request_text = paths["preflight_blind_llm_requests"].read_text()
            leakage = json.loads(paths["preflight_leakage_report"].read_text())
            self.assertTrue(leakage["passed"])
            self.assertIn("packet_sha256", request_text)
            for forbidden in (
                "winner-refine",
                "control-holdout",
                "Corner Growth",
                "Tron",
                "Microsoft",
                "AAPL",
                "https://example.com",
                '"label"',
                '"outcome_return"',
            ):
                self.assertNotIn(forbidden, request_text)

    def test_ralph_selection_policy_prioritizes_rich_evidence(self) -> None:
        cases = [
            make_case(
                "aaa-winner-thin",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.10,
                earnings_growth=0.10,
                margin=0.10,
                return_20d=0.01,
                return_60d=0.02,
                target_upside=0.01,
                catalyst_count=0,
            ),
            make_case(
                "zzz-winner-rich",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.35,
                earnings_growth=0.70,
                margin=0.22,
                return_20d=0.10,
                return_60d=0.25,
                target_upside=0.35,
                catalyst_count=2,
                extra_documents=[
                    DocumentRecord(
                        document_id="rich-order",
                        symbol="ZZZ",
                        kind=EvidenceKind.NEWS,
                        title="Customer contract",
                        text="A large customer order added capacity demand and execution risk.",
                        source_id="fixture:rich-order",
                        source_url="https://example.com/rich-order",
                        published_date=AS_OF,
                        retrieved_at=STAMP,
                    )
                ],
            ),
            make_case(
                "bbb-winner-holdout",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.20,
                earnings_growth=0.30,
                margin=0.15,
                return_20d=0.05,
                return_60d=0.10,
                target_upside=0.10,
                catalyst_count=1,
            ),
            make_case(
                "aaa-control-thin",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.02,
                earnings_growth=0.01,
                margin=0.03,
                return_20d=0.00,
                return_60d=0.01,
                target_upside=0.01,
                catalyst_count=0,
            ),
            make_case(
                "zzz-control-rich",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.12,
                earnings_growth=0.05,
                margin=0.08,
                return_20d=0.03,
                return_60d=0.05,
                target_upside=0.02,
                catalyst_count=2,
            ),
            make_case(
                "bbb-control-holdout",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.03,
                earnings_growth=0.02,
                margin=0.04,
                return_20d=0.01,
                return_60d=0.02,
                target_upside=0.01,
                catalyst_count=1,
            ),
        ]

        selected = _select_cases(
            cases,
            winner_symbol_count=2,
            control_symbol_count=2,
            refinement_per_label=1,
            selection_policy="evidence-rich",
        )

        self.assertEqual(selected["refinement"][0].case_id, "zzz-winner-rich")
        self.assertEqual(selected["refinement"][1].case_id, "zzz-control-rich")

        pinned = _select_cases(
            cases,
            winner_symbol_count=2,
            control_symbol_count=2,
            refinement_per_label=1,
            selection_policy="evidence-rich",
            holdout_symbols=frozenset({"ZZZ"}),
        )

        self.assertEqual(pinned["refinement"][0].case_id, "bbb-winner-holdout")
        self.assertIn("zzz-winner-rich", {case.case_id for case in pinned["holdout"]})
        self.assertIn("zzz-control-rich", {case.case_id for case in pinned["holdout"]})

    def test_ralph_imported_responses_score_holdout_without_provider_call(self) -> None:
        cases = [
            make_case(
                "winner-refine",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.35,
                earnings_growth=0.70,
                margin=0.22,
                return_20d=0.10,
                return_60d=0.25,
                target_upside=0.35,
                catalyst_count=2,
            ),
            make_case(
                "control-refine",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.04,
                earnings_growth=-0.05,
                margin=0.05,
                return_20d=0.00,
                return_60d=0.03,
                target_upside=0.04,
                catalyst_count=0,
            ),
            make_case(
                "winner-holdout",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.32,
                earnings_growth=0.50,
                margin=0.20,
                return_20d=0.08,
                return_60d=0.20,
                target_upside=0.28,
                catalyst_count=1,
            ),
            make_case(
                "control-holdout",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.02,
                earnings_growth=-0.02,
                margin=0.04,
                return_20d=0.00,
                return_60d=0.01,
                target_upside=0.02,
                catalyst_count=0,
            ),
        ]
        refinement_cases = tuple(cases[:2])
        holdout_cases = tuple(cases[2:])
        learning = learn_pre_surge_signal_logic(refinement_cases)
        themes = build_cold_start_theme_maps(refinement_cases, learning)
        baseline = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in refinement_cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(
            refinement_cases,
            baseline,
            learning,
            themes,
        )

        response_payload = {
            "responses": [
                _external_response("case_001", "likely", 0.82),
                _external_response("case_002", "unlikely", 0.22),
                _external_response("holdout_001", "likely", 0.80),
                _external_response("holdout_002", "unlikely", 0.20),
            ]
        }
        with TemporaryDirectory() as tmp:
            response_path = Path(tmp) / "external_responses.json"
            response_path.write_text(json.dumps(response_payload), encoding="utf-8")
            paths = _write_imported_response_artifacts(
                Path(tmp),
                run_id="ralph-import-test",
                created_at=STAMP,
                refinement_cases=refinement_cases,
                holdout_cases=holdout_cases,
                learning_result=learning,
                theme_maps=themes,
                playbook_synthesis=playbooks,
                responses_path=response_path,
            )

            manifest = json.loads(paths["imported_response_manifest"].read_text())
            evaluation = json.loads(paths["imported_blind_scheme_evaluation"].read_text())
            proposal = json.loads(paths["imported_next_scheme_proposal"].read_text())
            responses_text = paths["imported_blind_responses"].read_text()
            self.assertEqual(manifest["final_status"], "holdout_separated")
            self.assertEqual(manifest["holdout_false_positive_rate"], 0.0)
            self.assertEqual(manifest["holdout_false_negative_rate"], 0.0)
            self.assertTrue(evaluation["holdout_evaluation"]["separation_passed"])
            self.assertIsNone(proposal["next_scheme_proposal"])
            self.assertFalse(proposal["can_enter_long_running_default"])
            self.assertNotIn("winner-holdout", responses_text)
            self.assertNotIn("control-holdout", responses_text)

    def test_information_plan_atomic_extraction_rejects_keyword_false_positives(self) -> None:
        case = make_case(
            "atom-winner",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.20,
            earnings_growth=0.30,
            margin=0.12,
            return_20d=-0.05,
            return_60d=-0.20,
            target_upside=0.30,
            catalyst_count=0,
            extra_documents=[
                DocumentRecord(
                    document_id="atom-governance",
                    symbol="ATOM",
                    kind=EvidenceKind.FILING,
                    title="ATOM 8-K",
                    text=(
                        "Item 5.02 Departure of Directors or Principal Officers. "
                        "The board appointed a new director. "
                        "The issuer was dropped from Nasdaq Composite Index. "
                        "The company may enter into contracts in the ordinary course. "
                        "Artificial intelligence and customer contracts were discussed as risk factors. "
                        "Identify the previous filing by registration statement number. "
                        "A director was awarded 1,200 shares of restricted stock. "
                        "Tariffs could materially affect the business. "
                        "Customers may request extended payment terms and manufacturers may not "
                        "have capacity to increase production."
                    ),
                    source_id="sec:atom:governance",
                    source_url="https://www.sec.gov/example/atom-governance",
                    published_date=AS_OF - timedelta(days=2),
                    retrieved_at=STAMP,
                ),
                DocumentRecord(
                    document_id="atom-order",
                    symbol="ATOM",
                    kind=EvidenceKind.NEWS,
                    title="ATOM customer order",
                    text=(
                        "The company received a purchase order with a customer for $12.3 million. "
                        "The company has no orders from artificial intelligence customers."
                    ),
                    source_id="news:atom:order",
                    source_url="https://example.com/atom-order",
                    published_date=AS_OF - timedelta(days=1),
                    retrieved_at=STAMP,
                ),
                DocumentRecord(
                    document_id="atom-bank-boilerplate",
                    symbol="ATOM",
                    kind=EvidenceKind.FILING,
                    title="ATOM banking boilerplate",
                    text=(
                        "The Company has entered into agreements with certain customers to extend "
                        "credit or provide payment on drafts under credit documents. "
                        "Under a commercial letter of credit, the underlying transaction is "
                        "consummated between the customer and a third party. "
                        "Crowe provided audit services that were pre-approved. "
                        "We could remain an emerging growth company if annual gross revenues "
                        "remain below $1.24 billion. Under ASC 606, revenues are recognized when "
                        "control transfers. Proceeds on sales of available for sale securities "
                        "were $14.8 million. We may sell securities from time to time in a public "
                        "offering. We may face product liability lawsuits. The related consolidated "
                        "statements of cash flows for the two-year period are financial statements. "
                        "Options and warrants are not considered in the diluted loss-per-share "
                        "calculations. The company is committed to helping its customers. "
                        "The warning letter template uses required legal wording. The company "
                        "entered into a customer refundable deposit agreement for financing. "
                        "Authoritative guidance for pensions permits a calculated value."
                    ),
                    source_id="sec:atom:bank-boilerplate",
                    source_url="https://www.sec.gov/example/atom-bank-boilerplate",
                    published_date=AS_OF - timedelta(days=1),
                    retrieved_at=STAMP,
                ),
                DocumentRecord(
                    document_id="atom-unrelated-theme-context",
                    symbol="ATOM",
                    kind=EvidenceKind.THEME_CONTEXT,
                    title="Industry financing context",
                    text=(
                        "Another company closed a public offering for gross proceeds of "
                        "$184 million."
                    ),
                    source_id="theme:atom:unrelated-offering",
                    source_url="https://example.com/atom-unrelated-theme",
                    published_date=AS_OF - timedelta(days=1),
                    retrieved_at=STAMP,
                ),
                DocumentRecord(
                    document_id="atom-designed-agreement",
                    symbol="ATOM",
                    kind=EvidenceKind.NEWS,
                    title="ATOM interconnection dispute",
                    text=(
                        "A regulator rejected an interconnection service agreement designed "
                        "to increase power supply to a third-party data center."
                    ),
                    source_id="news:atom:designed-agreement",
                    source_url="https://example.com/atom-designed-agreement",
                    published_date=AS_OF - timedelta(days=1),
                    retrieved_at=STAMP,
                ),
                DocumentRecord(
                    document_id="atom-unrelated-provider-news",
                    symbol="ATOM",
                    kind=EvidenceKind.NEWS,
                    title="Another issuer signs customer agreement",
                    text="Another issuer signed a customer agreement for cloud services.",
                    source_id="alpha_vantage:ATOM:unrelated",
                    source_url="https://example.com/atom-unrelated",
                    published_date=AS_OF - timedelta(days=1),
                    retrieved_at=STAMP,
                ),
            ],
        )

        facts = extract_atomic_evidence_by_case((case,))[case.case_id]

        event_types = {fact.event_type for fact in facts}
        self.assertIn("governance_routine", event_types)
        self.assertIn("market_index_membership", event_types)
        self.assertNotIn("strategic_transaction", event_types)
        self.assertNotIn("capital_or_liquidity", event_types)
        order_facts = [fact for fact in facts if fact.family == "orders_contracts"]
        self.assertEqual(len(order_facts), 2)
        positive = next(fact for fact in order_facts if not fact.negated)
        negative = next(fact for fact in order_facts if fact.negated)
        self.assertEqual(positive.amount, 12_300_000.0)
        self.assertEqual(positive.unit, "USD")
        self.assertEqual(negative.status.value, "contradicted")
        self.assertTrue(all(fact.source_span for fact in facts))
        self.assertFalse(any(fact.family == "theme_industry_transmission" for fact in facts))
        self.assertFalse(any(fact.family == "customer_capacity" for fact in facts))
        self.assertFalse(any(fact.family == "policy_regulatory" for fact in facts))
        self.assertFalse(
            any(
                fact.family == "business_identity"
                and fact.source_id == "sec:atom:bank-boilerplate"
                for fact in facts
            )
        )
        self.assertFalse(
            any(
                fact.family
                in {
                    "fundamentals",
                    "capital_structure_liquidity",
                    "contrary_risk",
                    "expectation_gap",
                }
                and fact.source_id == "sec:atom:bank-boilerplate"
                for fact in facts
            )
        )
        self.assertFalse(
            any(
                fact.family == "capital_structure_liquidity"
                and fact.source_id == "theme:atom:unrelated-offering"
                for fact in facts
            )
        )

    def test_information_plan_preserves_multifamily_facts_and_qualifies_coverage(self) -> None:
        factual_case = make_case(
            "factmulti-winner",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.20,
            earnings_growth=0.30,
            margin=0.12,
            return_20d=-0.05,
            return_60d=-0.20,
            target_upside=0.30,
            catalyst_count=0,
            extra_documents=[
                DocumentRecord(
                    document_id="factmulti-agreement",
                    symbol="FACTMULTI",
                    kind=EvidenceKind.NEWS,
                    title="Annual services agreement",
                    text=(
                        "The company announced the signing of a $25 million annual services "
                        "agreement with a client for AI-driven compliance services. "
                        "Its AI compliance platform is currently deployed by leading European banks. "
                        "Amazon sales surged 417% in three months, driven by strong customer demand. "
                        "The company is set to receive $750 million in CHIPS and Science Act "
                        "funding and will boost manufacturing capacity. The company closed a "
                        "public offering of common stock, no par value, for gross proceeds of "
                        "$20 million."
                    ),
                    source_id="news:factmulti:agreement",
                    source_url="https://example.com/factmulti-agreement",
                    published_date=AS_OF - timedelta(days=1),
                    retrieved_at=STAMP,
                )
            ],
        )
        planned_case = make_case(
            "planned-control",
            CaseOutcomeLabel.CONTROL,
            revenue_growth=0.02,
            earnings_growth=0.01,
            margin=0.04,
            return_20d=0.00,
            return_60d=0.01,
            target_upside=0.01,
            catalyst_count=0,
            extra_documents=[
                DocumentRecord(
                    document_id="planned-proposal",
                    symbol="PLANNED",
                    kind=EvidenceKind.NEWS,
                    title="Proposed pilot",
                    text=(
                        "The company was invited to submit a full proposal for a potential DoD "
                        "pilot award. It plans an FDA submission and approval in 2026."
                    ),
                    source_id="news:planned:proposal",
                    source_url="https://example.com/planned-proposal",
                    published_date=AS_OF - timedelta(days=1),
                    retrieved_at=STAMP,
                )
            ],
        )
        cases = (factual_case, planned_case)

        facts_by_case = extract_atomic_evidence_by_case(cases)
        factual_families = {fact.family for fact in facts_by_case[factual_case.case_id]}
        self.assertTrue(
            {
                "orders_contracts",
                "customer_capacity",
                "capital_structure_liquidity",
                "policy_regulatory",
                "theme_industry_transmission",
            }
            <= factual_families
        )
        policy_fact = next(
            fact
            for fact in facts_by_case[factual_case.case_id]
            if fact.family == "policy_regulatory"
        )
        self.assertEqual(policy_fact.status.value, "expected")
        capital_fact = next(
            fact
            for fact in facts_by_case[factual_case.case_id]
            if fact.family == "capital_structure_liquidity"
            and "no par value" in fact.source_span
        )
        self.assertEqual(capital_fact.status.value, "completed")
        self.assertFalse(capital_fact.negated)
        self.assertFalse(
            any(
                fact.family in {"orders_contracts", "policy_regulatory"}
                for fact in facts_by_case[planned_case.case_id]
            )
        )

        coverage = build_requirement_coverage_ledger(
            cases,
            default_information_requirements(),
            facts_by_case,
        )
        factual_states = {
            entry.family: entry.state
            for entry in coverage
            if entry.source_case_id == factual_case.case_id
        }
        planned_states = {
            entry.family: entry.state
            for entry in coverage
            if entry.source_case_id == planned_case.case_id
        }
        for family in (
            "orders_contracts",
            "customer_capacity",
            "policy_regulatory",
            "theme_industry_transmission",
        ):
            self.assertEqual(factual_states[family].value, "confirmed")
        self.assertEqual(planned_states["orders_contracts"].value, "not_found")
        self.assertEqual(planned_states["policy_regulatory"].value, "not_found")

    def test_information_plan_masks_source_aliases_and_interleaves_raw_documents(self) -> None:
        case = make_case(
            "tron-winner",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.20,
            earnings_growth=0.30,
            margin=0.12,
            return_20d=-0.05,
            return_60d=-0.20,
            target_upside=0.30,
            catalyst_count=0,
            company_name="Corner Growth Acquisition Corp 2 - Class A / Tron Inc.",
        )
        documents = (
            DocumentRecord(
                document_id="tron-alias-one",
                symbol="TRON",
                kind=EvidenceKind.NEWS,
                title="Noventiq Holdings PLC update",
                text=(
                    "Noventiq Holdings PLC and Corner Growth Acquisition Corp. announced an update. "
                    "Noventiq CEO discussed the transaction under the former ticker (NASDAQ:COOL). "
                    "Jupiter distributed shares. "
                    + "first-source-word " * 240
                ),
                source_id="news:tron:alias-one",
                source_url="https://example.com/tron-alias-one",
                published_date=AS_OF - timedelta(days=1),
                retrieved_at=STAMP,
                content_scope=DocumentContentScope.SUMMARY_ONLY,
            ),
            DocumentRecord(
                document_id="tron-alias-two",
                symbol="TRON",
                kind=EvidenceKind.FILING,
                title="SRM Entertainment, Inc. filing",
                text="second-source-word " * 240,
                source_id="sec:tron:alias-two",
                source_url="https://www.sec.gov/tron-alias-two",
                published_date=AS_OF - timedelta(days=2),
                retrieved_at=STAMP,
                content_scope=DocumentContentScope.COMPLETE_BODY,
            ),
        )

        identity_tokens = point_in_time_document_identity_tokens(documents)
        raw_packet = build_raw_source_blind_packet(
            case,
            anonymous_case_id="holdout_001",
            context_budget=1200,
            documents=documents,
        )
        prompt = json.dumps(raw_packet.to_prompt_dict())
        for identity in (
            "Noventiq",
            "Corner Growth",
            "COOL",
            "Jupiter",
            "SRM Entertainment",
        ):
            self.assertNotIn(identity.lower(), prompt.lower())
        source_items = raw_packet.sections[0].items
        self.assertEqual([item["chunk_index"] for item in source_items[:2]], [1, 1])
        self.assertNotEqual(source_items[0]["evidence_ref"], source_items[1]["evidence_ref"])
        leakage = _leakage_report(
            [(raw_packet, case)],
            extra_identity_terms_by_case={case.case_id: identity_tokens},
        )
        self.assertTrue(leakage["passed"])

    def test_information_plan_identity_tokens_reject_generic_news_words(self) -> None:
        document = DocumentRecord(
            document_id="generic-news-identity",
            symbol="FCAP",
            kind=EvidenceKind.NEWS,
            title="First Capital, Inc. Reports Quarterly Earnings",
            text=(
                "First Capital reported results. Power reported strong demand while Energy "
                "announced a project in New York. Biden announced a federal initiative."
            ),
            source_id="news:generic-identity",
            source_url="https://example.com/generic-identity",
            published_date=AS_OF - timedelta(days=1),
            retrieved_at=STAMP,
        )

        tokens = point_in_time_document_identity_tokens((document,))

        self.assertIn("First Capital", tokens)
        for generic in ("Capital", "Power", "Energy", "York", "Biden"):
            self.assertNotIn(generic, tokens)

    def test_information_plan_prepares_raw_organized_coverage_and_family_variants(self) -> None:
        discovery_cases = (
            make_case(
                "discwin-winner",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.35,
                earnings_growth=0.55,
                margin=0.20,
                return_20d=-0.10,
                return_60d=-0.25,
                target_upside=0.35,
                catalyst_count=1,
            ),
            make_case(
                "discctl-control",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.03,
                earnings_growth=0.01,
                margin=0.05,
                return_20d=0.01,
                return_60d=0.02,
                target_upside=0.02,
                catalyst_count=0,
            ),
        )
        holdout_cases = (
            make_case(
                "holdwin-winner",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.28,
                earnings_growth=0.40,
                margin=0.18,
                return_20d=-0.08,
                return_60d=-0.20,
                target_upside=0.30,
                catalyst_count=0,
                extra_documents=[
                    DocumentRecord(
                        document_id="holdwin-order",
                        symbol="HOLDWIN",
                        kind=EvidenceKind.NEWS,
                        title="HOLDWIN order",
                        text="The company was awarded a customer contract for $25 million.",
                        source_id="news:holdwin:order",
                        source_url="https://example.com/holdwin-order",
                        published_date=AS_OF - timedelta(days=3),
                        retrieved_at=STAMP,
                    )
                ],
            ),
            make_case(
                "holdctl-control",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.02,
                earnings_growth=-0.02,
                margin=0.04,
                return_20d=0.00,
                return_60d=0.01,
                target_upside=0.01,
                catalyst_count=0,
            ),
        )
        learning = learn_pre_surge_signal_logic(discovery_cases)
        themes = build_cold_start_theme_maps(discovery_cases, learning)
        baseline = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in discovery_cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(
            discovery_cases,
            baseline,
            learning,
            themes,
        )
        scheme, _diagnostic = synthesize_information_scheme(
            discovery_cases,
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )

        prepared = prepare_information_plan_experiment(
            discovery_cases,
            holdout_cases,
            active_scheme=scheme,
            run_id="information-plan-test",
            context_budget=1200,
        )

        self.assertFalse(prepared.plan.to_dict()["gold_packet_available"])
        self.assertIn(
            "other_or_unclassified",
            {requirement.family for requirement in prepared.plan.requirements},
        )
        self.assertEqual(len(prepared.raw_packets), 2)
        self.assertEqual(len(prepared.organized_packets), 2)
        self.assertEqual(prepared.active_scheme.total_token_budget, 1200)
        self.assertEqual(sum(section.token_budget for section in prepared.raw_packets[0].sections), 1200)
        self.assertEqual(
            sum(section.token_budget for section in prepared.organized_packets[0].sections),
            1200,
        )
        self.assertTrue(
            all(
                section.estimated_tokens <= section.token_budget
                for packet in prepared.raw_packets + prepared.organized_packets
                for section in packet.sections
            )
        )
        self.assertIn("news:holdwin:order", prepared.source_pool_by_case["holdwin-winner"])
        order_experiment = next(
            item for item in prepared.family_experiments if item.family == "orders_contracts"
        )
        self.assertEqual(order_experiment.status, "packet_variants_ready")
        self.assertGreater(order_experiment.available_fact_count, 0)
        organized_text = json.dumps(prepared.organized_packets[0].to_dict())
        raw_text = json.dumps(prepared.raw_packets[0].to_dict())
        self.assertNotIn("news:holdwin:order", organized_text)
        self.assertNotIn("https://example.com", organized_text)
        self.assertNotIn("HOLDWIN", organized_text)
        self.assertNotIn("HOLDWIN", raw_text)
        self.assertIn("fact_", organized_text)
        order_coverage = next(
            entry
            for entry in prepared.coverage_entries
            if entry.source_case_id == "holdwin-winner"
            and entry.family == "orders_contracts"
        )
        self.assertEqual(order_coverage.state.value, "confirmed")

    def test_information_plan_full_document_pool_is_shared_and_identity_masked(self) -> None:
        discovery_cases = (
            make_case(
                "pooltrain-winner",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.20,
                earnings_growth=0.30,
                margin=0.15,
                return_20d=0.02,
                return_60d=0.08,
                target_upside=0.20,
                catalyst_count=1,
            ),
            make_case(
                "poolctl-control",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.02,
                earnings_growth=0.01,
                margin=0.04,
                return_20d=0.00,
                return_60d=0.01,
                target_upside=0.01,
                catalyst_count=0,
            ),
        )
        holdout = make_case(
            "poolhold-winner",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.25,
            earnings_growth=0.35,
            margin=0.16,
            return_20d=-0.04,
            return_60d=-0.12,
            target_upside=0.25,
            catalyst_count=0,
            company_name="Pool Hold Corp.",
        )
        control = make_case(
            "poolfresh-control",
            CaseOutcomeLabel.CONTROL,
            revenue_growth=0.01,
            earnings_growth=-0.01,
            margin=0.03,
            return_20d=0.00,
            return_60d=0.01,
            target_upside=0.01,
            catalyst_count=0,
        )
        document = DocumentRecord(
            document_id="poolhold-full",
            symbol="POOLHOLD",
            kind=EvidenceKind.FILING,
            title="Pool Hold Corp. transaction filing",
            text=(
                "Pool Hold Corp. (the Company) entered into a business combination agreement "
                "with Secret Target Inc. (the Company). The target received a purchase order "
                "for $18 million. As of the quarter end, the company reported cash and cash "
                "equivalents of $12 million."
            ),
            source_id="sec:poolhold:full",
            source_url="https://www.sec.gov/poolhold/full",
            published_date=AS_OF - timedelta(days=2),
            retrieved_at=STAMP,
            content_scope=DocumentContentScope.COMPLETE_BODY,
        )
        generic_control_document = DocumentRecord(
            document_id="poolfresh-generic",
            symbol="POOLFRESH",
            kind=EvidenceKind.FILING,
            title="Pool Fresh Corp. risk factors",
            text="Risk factors include the possibility that customer orders may never materialize.",
            source_id="sec:poolfresh:generic",
            source_url="https://www.sec.gov/poolfresh/generic",
            published_date=AS_OF - timedelta(days=2),
            retrieved_at=STAMP,
            content_scope=DocumentContentScope.SUMMARY_ONLY,
        )
        learning = learn_pre_surge_signal_logic(discovery_cases)
        themes = build_cold_start_theme_maps(discovery_cases, learning)
        baseline = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in discovery_cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(
            discovery_cases,
            baseline,
            learning,
            themes,
        )
        scheme, _diagnostic = synthesize_information_scheme(
            discovery_cases,
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )

        prepared = prepare_information_plan_experiment(
            discovery_cases,
            (holdout, control),
            active_scheme=scheme,
            run_id="source-pool-test",
            context_budget=1000,
            documents_by_symbol={
                "POOLHOLD": (document,),
                "POOLFRESH": (generic_control_document,),
            },
        )

        raw_text = json.dumps(prepared.raw_packets[0].to_dict())
        organized_text = json.dumps(prepared.organized_packets[0].to_dict())
        self.assertIn("sec:poolhold:full", prepared.source_pool_by_case[holdout.case_id])
        self.assertNotIn("Pool Hold", raw_text)
        self.assertNotIn("Secret Target", raw_text)
        self.assertNotIn("Pool Hold", organized_text)
        self.assertNotIn("Secret Target", organized_text)
        self.assertIn("purchase order", raw_text)
        self.assertIn("purchase order", organized_text)
        materiality_section = next(
            section
            for section in prepared.organized_packets[0].sections
            if section.name == "Materiality and Timing"
        )
        materiality_families = {item.get("family") for item in materiality_section.items}
        self.assertIn("deal_status_timing", materiality_families)
        self.assertIn("capital_structure_liquidity", materiality_families)
        control_order_coverage = next(
            entry
            for entry in prepared.coverage_entries
            if entry.source_case_id == control.case_id
            and entry.family == "orders_contracts"
        )
        self.assertEqual(control_order_coverage.state.value, "not_found")
        self.assertTrue(document_content_readiness(prepared)["passed"])

        result = evaluate_information_plan_experiment(
            prepared,
            (holdout, control),
            blind_researcher=HeuristicRalphBlindResearcher(),
            family_experiment_mode="both",
            evaluation_method="heuristic",
        )
        order_evaluation = next(
            item
            for item in result.family_evaluations
            if item.family == "orders_contracts"
        )
        self.assertIsNotNone(order_evaluation.add_back_baseline_evaluation)
        self.assertIsNotNone(order_evaluation.add_back_delta)
        self.assertIsNotNone(order_evaluation.ablation_baseline_evaluation)
        self.assertIsNotNone(order_evaluation.ablation_delta)

    def test_information_plan_audits_legacy_truncated_source_bodies(self) -> None:
        case = make_case(
            "truncated-winner",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.20,
            earnings_growth=0.30,
            margin=0.15,
            return_20d=0.02,
            return_60d=0.08,
            target_upside=0.20,
            catalyst_count=0,
        )
        document = DocumentRecord(
            document_id="truncated-filing",
            symbol="TRUNCATED",
            kind=EvidenceKind.FILING,
            title="Truncated filing",
            text="Inline XBRL header " + "x" * 1478 + "...",
            source_id="sec:truncated:filing",
            source_url="https://www.sec.gov/truncated",
            published_date=AS_OF - timedelta(days=1),
            retrieved_at=STAMP,
        )
        news_summary = DocumentRecord(
            document_id="truncated-news-summary",
            symbol="TRUNCATED",
            kind=EvidenceKind.NEWS,
            title="Provider news summary",
            text="The provider supplied a source-linked company news summary that naturally ends...",
            source_id="news:truncated:summary",
            source_url="https://example.com/news",
            published_date=AS_OF - timedelta(days=1),
            retrieved_at=STAMP,
        )

        audits = audit_point_in_time_documents(
            (case,),
            {"TRUNCATED": (document, news_summary)},
        )

        by_source = {audit.source_id: audit for audit in audits}
        self.assertEqual(by_source[document.source_id].state.value, "likely_truncated")
        self.assertTrue(
            any("ellipsis" in reason for reason in by_source[document.source_id].reasons)
        )
        self.assertEqual(by_source[news_summary.source_id].state.value, "summary_only")

    def test_information_plan_evaluates_and_writes_required_artifacts(self) -> None:
        discovery_cases = (
            make_case(
                "trainwin-winner",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.30,
                earnings_growth=0.45,
                margin=0.18,
                return_20d=-0.08,
                return_60d=-0.20,
                target_upside=0.30,
                catalyst_count=1,
            ),
            make_case(
                "trainctl-control",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.02,
                earnings_growth=0.01,
                margin=0.04,
                return_20d=0.01,
                return_60d=0.02,
                target_upside=0.01,
                catalyst_count=0,
            ),
        )
        holdout_cases = (
            make_case(
                "freshwin-winner",
                CaseOutcomeLabel.WINNER,
                revenue_growth=0.32,
                earnings_growth=0.48,
                margin=0.19,
                return_20d=0.05,
                return_60d=0.12,
                target_upside=0.32,
                catalyst_count=2,
            ),
            make_case(
                "freshctl-control",
                CaseOutcomeLabel.CONTROL,
                revenue_growth=0.01,
                earnings_growth=-0.03,
                margin=0.03,
                return_20d=0.00,
                return_60d=0.01,
                target_upside=0.01,
                catalyst_count=0,
            ),
        )
        learning = learn_pre_surge_signal_logic(discovery_cases)
        themes = build_cold_start_theme_maps(discovery_cases, learning)
        baseline = tuple(HeuristicBlindCaseResearcher().analyze(case) for case in discovery_cases)
        playbooks = HeuristicSurgePlaybookSynthesizer().synthesize(
            discovery_cases,
            baseline,
            learning,
            themes,
        )
        scheme, _diagnostic = synthesize_information_scheme(
            discovery_cases,
            learning_result=learning,
            theme_maps=themes,
            playbook_synthesis=playbooks,
        )
        prepared = prepare_information_plan_experiment(
            discovery_cases,
            holdout_cases,
            active_scheme=scheme,
            run_id="information-plan-artifact-test",
            context_budget=1200,
        )
        result = evaluate_information_plan_experiment(
            prepared,
            holdout_cases,
            blind_researcher=HeuristicRalphBlindResearcher(),
            family_experiment_mode="both",
            evaluation_method="heuristic",
        )

        with TemporaryDirectory() as tmp:
            paths = write_information_plan_experiment_artifacts(
                result,
                tmp,
                created_at=STAMP,
                leakage_report={"passed": True, "case_reports": []},
            )
            required = {
                "research_information_plan",
                "information_requirements",
                "evidence_coverage_ledger",
                "atomic_evidence_by_case",
                "point_in_time_source_documents",
                "document_content_audit",
                "raw_source_blind_packets",
                "raw_vs_organized_evaluation",
                "information_family_experiments",
                "layered_failure_attribution",
            }
            self.assertTrue(required.issubset(paths))
            self.assertTrue(all(paths[name].exists() for name in required))
            manifest = json.loads(paths["manifest"].read_text())
            comparison = json.loads(paths["raw_vs_organized_evaluation"].read_text())
            family = json.loads(paths["information_family_experiments"].read_text())
            self.assertEqual(manifest["pipeline"], "ralph_information_plan_experiment")
            self.assertEqual(manifest["evaluation_method"], "heuristic")
            self.assertFalse(manifest["effectiveness_claim_allowed"])
            summary = json.loads(paths["ralph_experiment_summary"].read_text())
            self.assertEqual(summary["final_status"], "pipeline_diagnostic_only")
            self.assertFalse(comparison["comparison_contract"]["gold_packet_available"])
            self.assertEqual(comparison["comparison_contract"]["source_pool_case_count"], 2)
            self.assertEqual(len(family["experiments"]), 7)
            self.assertTrue(result.failure_attributions)

    def test_web_evidence_researcher_collects_as_of_bounded_documents(self) -> None:
        transport = FakeOpenAITransport(
            json.dumps(
                {
                    "documents": [
                        {
                            "kind": "research_report",
                            "title": "Analyst note sees AI server demand",
                            "summary": "Analysts discussed AI infrastructure demand before the cutoff.",
                            "source_url": "https://example.com/research",
                            "published_date": "2026-04-01",
                        },
                        {
                            "kind": "theme_context",
                            "title": "AI infrastructure capex trend",
                            "summary": "Data center capex was accelerating across the supply chain.",
                            "source_url": "https://example.com/theme",
                            "published_date": "2026-04-02",
                        },
                        {
                            "kind": "news",
                            "title": "Future order",
                            "summary": "This should be excluded because it is after cutoff.",
                            "source_url": "https://example.com/future",
                            "published_date": "2026-05-10",
                        },
                    ],
                    "catalysts": [
                        {
                            "name": "AI product launch",
                            "expected_date": "2026-06-15",
                            "source_title": "Launch preview",
                            "source_url": "https://example.com/launch",
                            "published_date": "2026-04-03",
                        }
                    ],
                    "warnings": [],
                }
            )
        )
        client = OpenAIChatClient("gpt-5.4-mini", "test-key", transport=transport)
        request = EvidenceAcquisitionRequest(
            symbol="AAPL",
            company_name="Apple Inc.",
            inflection_date=date(2026, 5, 1),
            as_of_dates=(date(2026, 3, 1), date(2026, 4, 1)),
            sector="AI Infrastructure",
            industry="Devices",
            priority_themes=("AI Infrastructure",),
        )

        result = OpenAIWebEvidenceResearcher(client).collect(request, STAMP)

        payload = transport.calls[0][2]
        prompt_text = payload["input"][1]["content"][0]["text"]
        self.assertIn("\"cutoff_date\": \"2026-05-01\"", prompt_text)
        self.assertIn("\"packet_as_of_dates\"", prompt_text)
        self.assertNotIn("winner", prompt_text.lower())
        self.assertNotIn("forward_return", prompt_text)
        self.assertEqual(payload["tools"], [{"type": "web_search"}])
        self.assertEqual([document.kind for document in result.documents], [EvidenceKind.RESEARCH_REPORT, EvidenceKind.THEME_CONTEXT])
        self.assertEqual(result.catalysts[0].name, "AI product launch")

    def test_context_coverage_gate_warns_or_excludes_thin_packets(self) -> None:
        rich = make_case(
            "winner-1",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.40,
            earnings_growth=0.70,
            margin=0.22,
            return_20d=0.11,
            return_60d=0.25,
            target_upside=0.35,
            catalyst_count=1,
            extra_documents=[
                DocumentRecord(
                    document_id="winner-theme",
                    symbol="WINNER",
                    kind=EvidenceKind.THEME_CONTEXT,
                    title="AI infrastructure trend",
                    text="AI capex trend supports demand but dilution risk remains.",
                    source_id="web:theme",
                    source_url="https://example.com/theme",
                    published_date=AS_OF,
                    retrieved_at=STAMP,
                )
            ],
        )
        thin = make_thin_case("thin-1", CaseOutcomeLabel.CONTROL)
        financial_only = make_case(
            "financial-1",
            CaseOutcomeLabel.CONTROL,
            revenue_growth=0.20,
            earnings_growth=0.30,
            margin=0.10,
            return_20d=0.02,
            return_60d=0.03,
            target_upside=0.10,
            catalyst_count=0,
        )
        no_event = make_case(
            "no-event-1",
            CaseOutcomeLabel.CONTROL,
            revenue_growth=0.20,
            earnings_growth=0.30,
            margin=0.10,
            return_20d=0.02,
            return_60d=0.03,
            target_upside=0.10,
            catalyst_count=0,
            extra_documents=[
                DocumentRecord(
                    document_id="industry-theme",
                    symbol="WINNER",
                    kind=EvidenceKind.THEME_CONTEXT,
                    title="Industry context",
                    text="Provider profile places the company in semiconductors.",
                    source_id="provider:theme",
                    source_url="urn:provider:theme",
                    published_date=AS_OF,
                    retrieved_at=STAMP,
                )
            ],
        )

        rich_report = assess_context_coverage(rich)
        financial_report = assess_context_coverage(financial_only)
        no_event_report = assess_context_coverage(no_event)
        warn_result = apply_context_coverage_gate([rich, thin], mode="warn")
        enforce_result = apply_context_coverage_gate([rich, thin], mode="enforce")

        self.assertTrue(rich_report.sufficient_context)
        self.assertFalse(financial_report.buckets["catalyst_event_context"])
        self.assertFalse(financial_report.sufficient_context)
        self.assertFalse(no_event_report.sufficient_context)
        self.assertIn("catalyst_event_context", no_event_report.missing_buckets)
        self.assertEqual([case.case_id for case in warn_result.cases], ["winner-1", "thin-1"])
        self.assertEqual(warn_result.excluded_case_ids, ())
        self.assertEqual(enforce_result.excluded_case_ids, ("thin-1",))
        self.assertEqual([case.case_id for case in enforce_result.cases], ["winner-1"])

    def test_formal_context_fetch_merges_provider_and_web_evidence(self) -> None:
        args = SimpleNamespace(
            web_context_mode="cached",
            max_web_documents_per_symbol=8,
            max_theme_documents_per_symbol=4,
            filing_forms="10-K,10-Q,8-K",
            filing_lookback_days=540,
            news_lookback_days=365,
            max_filings_per_symbol=3,
            max_news_per_symbol=4,
            max_transcripts_per_symbol=1,
            skip_filing_text=True,
            document_excerpt_chars=500,
            quiet=True,
        )
        candidate = HistoricalCandidate(
            symbol="ABC",
            company_name="ABC Corp.",
            label=CaseOutcomeLabel.WINNER,
            outcome_anchor_date=date(2026, 5, 1),
            inflection_date=date(2026, 5, 1),
            inflection_method="fixture",
            inflection_score=1.0,
            outcome_end_date=date(2026, 8, 1),
            forward_return=1.0,
            max_forward_return=1.2,
            max_drawdown_from_start=-0.1,
            trading_days=65,
            selection_rank=1,
        )
        listing = SecurityListing(
            symbol="ABC",
            name="ABC Corp.",
            exchange="NASDAQ",
            asset_type="common_stock",
            status="active",
            source="fixture",
            retrieved_at=STAMP,
            cik="0000000001",
        )
        features = _provider_profile_features(
            "ABC",
            (date(2026, 1, 1),),
            FakeAlphaProfileClient(),
            None,
            STAMP,
        ) + [feature("ABC", "financial.revenue_usd", 100.0)]
        alpha_client = FakeContextAlphaClient()

        with patch("scripts.run_cold_start_formal.SecEdgarClient.from_config", return_value=FakeContextSecClient()):
            with patch("scripts.run_cold_start_formal._optional_finnhub_client", return_value=FakeContextFinnhubClient()):
                with patch("scripts.run_cold_start_formal._optional_alpha_client", return_value=alpha_client):
                    with patch("scripts.run_cold_start_formal.OpenAIWebEvidenceResearcher", FakeContextWebResearcher):
                        result = _fetch_context_documents(
                            args,
                            [candidate],
                            [listing],
                            {"ABC": features},
                            AgentConfig(),
                            object(),
                            STAMP,
                        )

        documents = result.documents_by_symbol["ABC"]
        catalysts = result.catalysts_by_symbol["ABC"]

        self.assertIn(EvidenceKind.NEWS, {document.kind for document in documents})
        self.assertIn(EvidenceKind.THEME_CONTEXT, {document.kind for document in documents})
        self.assertEqual(alpha_client.calls, ["news", "topic"])
        self.assertEqual(result.web_queries_by_symbol["ABC"], ("ABC query before 2026-05-01",))
        self.assertTrue(any(catalyst.name == "AI product launch" for catalyst in catalysts))
        self.assertTrue(any(catalyst.status is CatalystStatus.CONFIRMED for catalyst in catalysts))

    def test_formal_filing_acquisition_preserves_complete_source_body(self) -> None:
        body = (
            "<html><body><p>Item 1.01 Entry into a Material Definitive Agreement.</p>"
            + "<p>The issuer signed a customer supply agreement.</p>" * 120
            + "</body></html>"
        )
        filing = FilingMetadata(
            cik="0000000001",
            accession_number="0000000001-26-000001",
            filing_date=date(2026, 4, 15),
            report_date=None,
            form="8-K",
            primary_document="form8-k.htm",
            source_url="https://www.sec.gov/Archives/edgar/data/1/form8-k.htm",
            retrieved_at=STAMP,
        )

        class FullBodySecClient:
            def recent_filings_as_of(self, cik, as_of_date):
                return [filing]

            def filing_document_text(self, selected_filing):
                self.selected_filing = selected_filing
                return body

        candidate = HistoricalCandidate(
            symbol="ABC",
            company_name="ABC Corp.",
            label=CaseOutcomeLabel.WINNER,
            outcome_anchor_date=AS_OF,
            inflection_date=AS_OF,
            inflection_method="fixture",
            inflection_score=1.0,
            outcome_end_date=AS_OF + timedelta(days=90),
            forward_return=1.0,
            max_forward_return=1.2,
            max_drawdown_from_start=-0.1,
            trading_days=65,
            selection_rank=1,
        )
        warnings: list[str] = []
        documents = _filing_documents_for_candidate(
            SimpleNamespace(
                max_filings_per_symbol=2,
                skip_filing_text=False,
                document_excerpt_chars=100,
            ),
            FullBodySecClient(),
            candidate,
            "0000000001",
            context_start=date(2026, 1, 1),
            filing_forms=("8-K",),
            created_at=STAMP,
            warnings=warnings,
        )

        self.assertEqual(documents[0].text, body)
        self.assertGreater(len(documents[0].text), 1500)
        self.assertEqual(documents[0].content_scope, DocumentContentScope.COMPLETE_BODY)
        self.assertEqual(warnings, [])

    def test_formal_news_context_turns_order_news_into_document_and_catalyst(self) -> None:
        document = _finnhub_news_document(
            "ABC",
            {
                "id": 123,
                "datetime": int(STAMP.timestamp()),
                "headline": "ABC wins new customer order",
                "summary": "The company announced a multi-year supply agreement.",
                "url": "https://example.com/order",
            },
            STAMP,
        )

        self.assertIsNotNone(document)
        assert document is not None
        self.assertEqual(document.kind, EvidenceKind.NEWS)
        catalyst = _catalyst_from_news_document(document)
        self.assertIsNotNone(catalyst)
        assert catalyst is not None
        self.assertEqual(catalyst.status, CatalystStatus.CONFIRMED)
        broad_customer_document = _finnhub_news_document(
            "ABC",
            {
                "id": 124,
                "datetime": int(STAMP.timestamp()),
                "headline": "ABC discusses customer costs",
                "summary": "The update mentioned customer bills and operational service quality.",
                "url": "https://example.com/customer-costs",
            },
            STAMP,
        )
        assert broad_customer_document is not None
        self.assertIsNone(_catalyst_from_news_document(broad_customer_document))

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
            theme_library = FileThemeLibrary(Path(tmp) / "memory" / "themes")
            playbook_library = FilePlaybookLibrary(Path(tmp) / "memory" / "playbooks")
            progress_messages = []
            output = run_cold_start_case_learning(
                cases,
                config=config,
                run_id="test-cold-start",
                created_at=STAMP,
                signal_library=library,
                theme_library=theme_library,
                playbook_library=playbook_library,
                control_match_criteria=ControlMatchCriteria(max_controls_per_winner=1),
                progress=progress_messages.append,
            )

            self.assertTrue(output.manifest_path.exists())
            self.assertTrue(output.signal_logic_path.exists())
            self.assertTrue(output.signal_definitions_path.exists())
            self.assertTrue(output.blind_analysis_path.exists())
            self.assertTrue(output.inflection_analysis_path.exists())
            self.assertTrue(output.theme_maps_path.exists())
            self.assertTrue(output.playbooks_path.exists())
            self.assertTrue(output.information_scheme_path.exists())
            self.assertTrue(output.ralph_iterations_path.exists())
            self.assertTrue(output.ralph_blind_packets_path.exists())
            self.assertTrue(output.ralph_evaluation_path.exists())
            self.assertTrue(output.ralph_error_analysis_path.exists())
            self.assertTrue(library.definitions_path.exists())
            self.assertTrue(theme_library.theme_maps_path.exists())
            self.assertTrue(playbook_library.playbooks_path.exists())
            self.assertIn("sig-fundamental-revenue-acceleration", output.signal_logic_path.read_text())
            self.assertIn("inflection_analyses", output.manifest_path.read_text())
            self.assertIn("theme_maps", output.manifest_path.read_text())
            self.assertIn("surge_research_playbooks", output.manifest_path.read_text())
            self.assertIn("information_scheme", output.manifest_path.read_text())
            self.assertIn("ralph_scheme_version", output.manifest_path.read_text())
            self.assertIn("matched_control_sets", output.manifest_path.read_text())
            self.assertTrue(library.read_definitions())
            self.assertTrue(theme_library.read_theme_maps())
            self.assertTrue(playbook_library.read_playbooks())
            self.assertTrue(output.theme_maps.theme_maps)
            self.assertTrue(output.playbook_synthesis.playbooks)
            self.assertTrue(output.ralph_loop.iterations)
            self.assertTrue(any("discovering inflections" in message for message in progress_messages))
            self.assertTrue(any("theme maps" in message for message in progress_messages))
            self.assertTrue(any("research playbooks" in message for message in progress_messages))
            self.assertTrue(any("Ralph scheme" in message for message in progress_messages))
            self.assertTrue(any("complete:" in message for message in progress_messages))

    def test_composite_inflection_keeps_factor_candidate_when_web_research_fails(self) -> None:
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
        researcher = CompositeInflectionResearcher((HeuristicInflectionResearcher(), FailingInflectionResearcher()))

        result = researcher.discover(case)

        self.assertEqual(len(result.candidates), 1)
        self.assertIn("FailingInflectionResearcher failed: provider unavailable", result.raw_text)

    def test_cached_inflection_research_reuses_symbol_outcome_window(self) -> None:
        first = make_case(
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
        second = make_case(
            "winner-2",
            CaseOutcomeLabel.WINNER,
            revenue_growth=0.35,
            earnings_growth=0.60,
            margin=0.20,
            return_20d=0.08,
            return_60d=0.18,
            target_upside=0.25,
            catalyst_count=1,
        )
        researcher = CountingInflectionResearcher()
        cached = CachedInflectionResearcher(researcher)

        first_result = cached.discover(first)
        second_result = cached.discover(second)

        self.assertEqual(researcher.calls, 1)
        self.assertEqual(first_result.case_id, "winner-1")
        self.assertEqual(second_result.case_id, "winner-2")

    def test_cold_start_theme_maps_group_cases_by_theme_and_segment(self) -> None:
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
        learning = learn_pre_surge_signal_logic(cases)

        result = build_cold_start_theme_maps(cases, learning)

        self.assertEqual(len(result.theme_maps), 1)
        theme = result.theme_maps[0]
        self.assertEqual(theme.theme_id, "semiconductors")
        self.assertIn("WINNER", theme.candidate_symbols)
        self.assertIn("Accelerators", [segment.segment_name for segment in theme.segments])
        self.assertTrue(theme.validation_state["data_evidence"])
        self.assertTrue(any(segment.transmission_stage >= 3 for segment in theme.segments))


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
    company_name: str | None = None,
    extra_documents: list[DocumentRecord] | None = None,
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
        name=company_name or f"{symbol} Corp.",
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
        documents=extra_documents or [],
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


def _external_response(request_id: str, judgment: str, confidence: float) -> dict[str, object]:
    return {
        "request_id": request_id,
        "output": {
            "surge_candidate": judgment,
            "surge_candidate_reason": "external blind response fixture",
            "expectation_gap": "fixture expectation gap",
            "pre_surge_signals": ["fixture signal"],
            "contrary_evidence": ["fixture risk"],
            "catalyst_watch": ["fixture catalyst"],
            "missing_context": [],
            "confidence": confidence,
        },
    }


def make_thin_case(case_id: str, label: CaseOutcomeLabel) -> HistoricalCase:
    symbol = case_id.split("-")[0].upper()
    features = [
        feature(symbol, "price.latest_close", 10.0),
        feature(symbol, "price.return_20d", 0.01),
        feature(symbol, "price.average_daily_dollar_volume_20d", 1_000_000.0),
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
    packet = build_research_packet(
        symbol=symbol,
        as_of_date=AS_OF,
        company=company_profile_from_features(listing, features, AS_OF),
        features=features,
        version=version(),
        packet_id=f"{case_id}:packet",
        created_at=STAMP,
    )
    return HistoricalCase(
        case_id=case_id,
        label=label,
        packet=packet,
        outcome_start_date=AS_OF + timedelta(days=1),
        outcome_end_date=AS_OF + timedelta(days=181),
        outcome_return=0.0,
        matched_group_id="fixture-thin",
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
