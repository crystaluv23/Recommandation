import json
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
    DocumentRecord,
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
    HeuristicBlindCaseResearcher,
    OpenAIBlindCaseResearcher,
    OpenAISurgePlaybookSynthesizer,
    OpenAIWebEvidenceResearcher,
    apply_context_coverage_gate,
    assess_context_coverage,
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
    _finnhub_earnings_features,
    _finnhub_news_document,
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

        rich_report = assess_context_coverage(rich)
        warn_result = apply_context_coverage_gate([rich, thin], mode="warn")
        enforce_result = apply_context_coverage_gate([rich, thin], mode="enforce")

        self.assertTrue(rich_report.sufficient_context)
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
        features = [
            feature("ABC", "profile.sector", "Technology"),
            feature("ABC", "financial.revenue_usd", 100.0),
        ]

        with patch("scripts.run_cold_start_formal.SecEdgarClient.from_config", return_value=FakeContextSecClient()):
            with patch("scripts.run_cold_start_formal._optional_finnhub_client", return_value=FakeContextFinnhubClient()):
                with patch("scripts.run_cold_start_formal._optional_alpha_client", return_value=None):
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
        self.assertEqual(result.web_queries_by_symbol["ABC"], ("ABC query before 2026-05-01",))
        self.assertTrue(any(catalyst.name == "AI product launch" for catalyst in catalysts))
        self.assertTrue(any(catalyst.status is CatalystStatus.CONFIRMED for catalyst in catalysts))

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
            self.assertTrue(library.definitions_path.exists())
            self.assertTrue(theme_library.theme_maps_path.exists())
            self.assertTrue(playbook_library.playbooks_path.exists())
            self.assertIn("sig-fundamental-revenue-acceleration", output.signal_logic_path.read_text())
            self.assertIn("inflection_analyses", output.manifest_path.read_text())
            self.assertIn("theme_maps", output.manifest_path.read_text())
            self.assertIn("surge_research_playbooks", output.manifest_path.read_text())
            self.assertIn("matched_control_sets", output.manifest_path.read_text())
            self.assertTrue(library.read_definitions())
            self.assertTrue(theme_library.read_theme_maps())
            self.assertTrue(playbook_library.read_playbooks())
            self.assertTrue(output.theme_maps.theme_maps)
            self.assertTrue(output.playbook_synthesis.playbooks)
            self.assertTrue(any("discovering inflections" in message for message in progress_messages))
            self.assertTrue(any("theme maps" in message for message in progress_messages))
            self.assertTrue(any("research playbooks" in message for message in progress_messages))
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
