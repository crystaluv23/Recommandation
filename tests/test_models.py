from datetime import date, datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.models import (
    AsOfContext,
    Catalyst,
    CatalystStatus,
    CompanyProfile,
    DataQuality,
    DecisionRecord,
    EvidenceItem,
    EvidenceKind,
    ExperimentRecord,
    ExperimentStatus,
    FeatureRecord,
    RecommendationState,
    ReviewOutcome,
    ReviewRecord,
    ScoreCard,
    SegmentAssessment,
    SignalDefinition,
    Thesis,
    ThesisStatus,
    ThemeMap,
    TickerRef,
    ValidationError,
    ValidationIssue,
    VersionStamp,
    WatchlistEntry,
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


def evidence(kind: EvidenceKind = EvidenceKind.FILING) -> EvidenceItem:
    return EvidenceItem(
        kind=kind,
        summary="Revenue guide was raised.",
        as_of_date=date(2026, 5, 1),
        source_id=None if kind is EvidenceKind.INFERENCE else "filing:10q:1",
        inference=kind is EvidenceKind.INFERENCE,
    )


def feature() -> FeatureRecord:
    return FeatureRecord(
        name="price.latest_close",
        value=125.5,
        as_of_date=date(2026, 5, 1),
        source="stooq",
        retrieved_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        source_id="stooq:NVDA:price.latest_close:2026-05-01",
        period_end_date=date(2026, 5, 1),
    )


def catalyst() -> Catalyst:
    return Catalyst(
        name="Product launch",
        expected_date=date(2026, 6, 1),
        status=CatalystStatus.EXPECTED,
        evidence=[evidence()],
    )


def score_card() -> ScoreCard:
    return ScoreCard(
        score_id="score-1",
        ticker=TickerRef("nvda", exchange="NASDAQ"),
        as_of_date=date(2026, 5, 1),
        theme_transmission_score=0.8,
        segment_timing_score=0.7,
        company_rocket_score=0.9,
        risk_adjustment=0.8,
        upside_potential=0.75,
        launch_probability=0.65,
        final_opportunity_score=0.55,
        component_scores={"fundamental_inflection": 0.8, "valuation_room": 0.6},
        evidence=[evidence()],
        version=version(),
    )


class ModelSerializationTests(TestCase):
    def test_validation_issue_context_cannot_expand_repair_authority(self) -> None:
        issue = ValidationIssue(
            code="example_invalid",
            message="Replace the invalid example.",
            paths=("items[0].value",),
            repair_context={"literal_candidates": ["valid"]},
        )

        self.assertEqual(
            issue.to_dict()["repair_context"],
            {"literal_candidates": ["valid"]},
        )
        with self.assertRaisesRegex(ValueError, "cannot grant repair authority"):
            ValidationIssue(
                code="example_invalid",
                message="Replace the invalid example.",
                paths=("items[0].value",),
                repair_context={"must_change_paths": ["items"]},
            )

    def test_validation_issue_accepts_explicit_stable_item_addition(self) -> None:
        issue = ValidationIssue(
            code="missing_item",
            message="Add the missing runtime-owned item.",
            paths=("items[1]",),
            item_id="item-002",
            item_id_field="item_id",
            allowed_repairs=("add",),
        )

        self.assertEqual(issue.to_dict()["allowed_repairs"], ["add"])

    def test_nested_score_card_round_trips(self) -> None:
        original = score_card()

        restored = ScoreCard.from_dict(original.to_dict())

        self.assertEqual(restored, original)
        self.assertEqual(restored.ticker.symbol, "NVDA")
        self.assertEqual(restored.evidence[0].kind, EvidenceKind.FILING)

    def test_theme_and_segment_records_round_trip(self) -> None:
        segment = SegmentAssessment(
            segment_name="Accelerators",
            timing_score=0.6,
            transmission_score=0.7,
            evidence=[evidence()],
            risks=["Capacity normalizes"],
        )
        theme = ThemeMap(
            theme_id="theme-ai-infra",
            name="AI infrastructure",
            as_of_date=date(2026, 5, 1),
            segments=[segment],
            leading_indicators=["Hyperscaler capex"],
            evidence=[evidence()],
            risks=["Demand pause"],
        )

        self.assertEqual(ThemeMap.from_dict(theme.to_dict()), theme)

    def test_feature_record_round_trips_with_availability_dates(self) -> None:
        original = feature()

        restored = FeatureRecord.from_dict(original.to_dict())

        self.assertEqual(restored, original)
        self.assertEqual(restored.period_end_date, date(2026, 5, 1))

    def test_decision_and_review_records_preserve_versions(self) -> None:
        thesis = Thesis(
            thesis_id="thesis-1",
            ticker=TickerRef("NVDA"),
            as_of_date=date(2026, 5, 1),
            claim="AI infrastructure demand can still surprise expectations.",
            status=ThesisStatus.ACTIVE,
            supporting_evidence=[evidence()],
            contrary_evidence=[evidence(EvidenceKind.INFERENCE)],
            catalysts=[catalyst()],
            disconfirming_conditions=["Revenue revisions turn negative"],
            review_dates=[date(2026, 6, 1)],
            version=version(),
        )
        entry = WatchlistEntry(
            entry_id="entry-1",
            ticker=TickerRef("NVDA"),
            as_of_date=date(2026, 5, 1),
            rank=1,
            state=RecommendationState.HIGH_PRIORITY_WATCHLIST,
            score=score_card(),
            reason="Strong demand evidence with visible catalysts.",
            thesis_id=thesis.thesis_id,
        )
        decision = DecisionRecord(
            decision_id="decision-1",
            as_of_date=date(2026, 5, 1),
            entry=entry,
            thesis=thesis,
            evidence=[evidence()],
            version=version(),
        )
        review = ReviewRecord(
            review_id="review-1",
            decision_id=decision.decision_id,
            as_of_date=decision.as_of_date,
            review_date=date(2026, 8, 1),
            outcome=ReviewOutcome.PARTIAL,
            error_labels=["timing_late"],
            lessons=["Catalyst timing needs tighter evidence."],
            evidence=[evidence()],
            version=version(),
        )

        self.assertEqual(DecisionRecord.from_dict(decision.to_dict()), decision)
        self.assertEqual(ReviewRecord.from_dict(review.to_dict()), review)


class ModelValidationTests(TestCase):
    def test_non_inference_evidence_requires_source(self) -> None:
        with self.assertRaises(ValidationError):
            EvidenceItem(
                kind=EvidenceKind.NEWS,
                summary="Management tone improved.",
                as_of_date=date(2026, 5, 1),
            )

    def test_inference_evidence_can_omit_source(self) -> None:
        item = EvidenceItem(
            kind=EvidenceKind.INFERENCE,
            summary="Narrative appears to be migrating.",
            as_of_date=date(2026, 5, 1),
            inference=True,
        )

        self.assertEqual(item.data_quality, DataQuality.CONFIRMED)

    def test_score_bounds_are_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            ScoreCard(
                score_id="score-1",
                ticker=TickerRef("NVDA"),
                as_of_date=date(2026, 5, 1),
                theme_transmission_score=1.2,
                segment_timing_score=0.7,
                company_rocket_score=0.9,
                risk_adjustment=0.8,
                upside_potential=0.75,
                launch_probability=0.65,
                final_opportunity_score=0.55,
                component_scores={"fundamental_inflection": 0.8},
                evidence=[evidence()],
                version=version(),
            )

    def test_medium_risk_experiment_requires_human_approval(self) -> None:
        with self.assertRaises(ValidationError):
            ExperimentRecord(
                experiment_id="exp-1",
                as_of_date=date(2026, 5, 1),
                hypothesis="New weights improve precision.",
                status=ExperimentStatus.PROPOSED,
                risk_level="medium",
                test_design="Walk-forward comparison.",
                proposed_change="Increase catalyst weight.",
                requires_human_approval=False,
            )


class RequiredRecordCoverageTests(TestCase):
    def test_research_packet_company_profile_and_signal_definition(self) -> None:
        from stock_opportunity_agent.models import ResearchPacket

        packet = ResearchPacket(
            packet_id="packet-1",
            as_of=AsOfContext(as_of_date=date(2026, 5, 1)),
            company=CompanyProfile(
                ticker=TickerRef("NVDA"),
                sector="Semiconductors",
                industry="Accelerators",
                market_cap_usd=1_000_000_000_000,
                average_daily_dollar_volume=5_000_000_000,
            ),
            features=[feature()],
            evidence=[evidence()],
            catalysts=[catalyst()],
            theme_ids=["theme-ai-infra"],
            memory_refs=[],
            version=version(),
        )
        signal = SignalDefinition(
            signal_id="sig-revisions",
            name="Positive revisions",
            description="Analyst estimate revisions are improving.",
            version="signals-v0.1",
            applicable_sectors=["Semiconductors"],
            false_positive_patterns=["Late-cycle extrapolation"],
            evidence=[evidence()],
        )

        self.assertEqual(ResearchPacket.from_dict(packet.to_dict()), packet)
        self.assertEqual(SignalDefinition.from_dict(signal.to_dict()), signal)
