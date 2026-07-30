from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.llm.openai import ChatResponse
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.ralph_loop import (
    BlindPacketSection,
    BlindSchemePacket,
)
from stock_opportunity_agent.research.scheme_evolution import (
    AdmissionDecision,
    CandidateValidator,
    DataSplitSpec,
    EvaluationSpec,
    EvolutionStateStore,
    FileSchemeProposer,
    FixedEvolutionSpec,
    LabelSpec,
    LabeledSample,
    MockSchemeFoldEvaluator,
    MockSchemeProposer,
    QualityDiversityArchive,
    SchemeEvaluationResult,
    SchemeEvolutionEngine,
    SchemeGenome,
    build_walk_forward_folds,
    genome_recipe_hash,
)
from stock_opportunity_agent.research.scheme_evolution_ralph import (
    OpenAIGenomeBlindAnalyzer,
    _packet_identity_findings,
)


ROOT = Path(__file__).resolve().parents[1]
INITIAL_PATH = ROOT / "configs/evolution/initial_genome.json"
CANDIDATE_PATH = ROOT / "configs/evolution/codex_candidates_v1.json"


class SchemeEvolutionTests(TestCase):
    def test_future_document_is_rejected_at_sample_boundary(self) -> None:
        prediction_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValidationError, "after prediction_time"):
            _sample(
                "future-source",
                company="company-a",
                prediction_time=prediction_time,
                label=1,
                available_date=prediction_time.date() + timedelta(days=1),
            )

    def test_walk_forward_purges_overlapping_label_windows_and_issuers(self) -> None:
        fixed = _fixed_spec()
        admission_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        eligible = _sample(
            "eligible",
            company="old-company",
            prediction_time=admission_start - timedelta(days=121),
            label=1,
        )
        overlapping = _sample(
            "overlapping",
            company="near-company",
            prediction_time=admission_start - timedelta(days=119),
            label=0,
        )
        same_issuer = _sample(
            "same-issuer-history",
            company="admission-company",
            prediction_time=admission_start - timedelta(days=200),
            label=0,
        )
        admission = _sample(
            "admission",
            company="admission-company",
            prediction_time=admission_start + timedelta(days=1),
            label=1,
        )
        folds = build_walk_forward_folds(
            (eligible, overlapping, same_issuer, admission),
            (admission_start,),
            fixed_spec=fixed,
            admission_window_days=10,
        )
        self.assertEqual(len(folds), 1)
        self.assertEqual(
            [sample.sample_id for sample in folds[0].discovery_samples],
            ["eligible"],
        )

    def test_blind_evaluator_never_receives_label_or_identity(self) -> None:
        initial, candidates = _genomes()
        fixed = _fixed_spec()
        folds = _four_folds(fixed)
        evaluator = MockSchemeFoldEvaluator()
        with tempfile.TemporaryDirectory() as tmp:
            engine = SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=evaluator,
                fixed_spec=fixed,
                state_store=EvolutionStateStore(tmp),
            )
            engine.run(initial, folds, candidate_count=1)
        self.assertTrue(evaluator.observed_blind_inputs)
        for payload in evaluator.observed_blind_inputs:
            self.assertNotIn("label", payload)
            self.assertNotIn("outcome", json.dumps(payload).lower())
            self.assertTrue(payload["company_key"].startswith("anon_"))
            self.assertNotIn("company-", payload["company_key"])

    def test_sealed_sample_is_not_serialized_into_engine_state(self) -> None:
        initial, candidates = _genomes()
        fixed = _fixed_spec()
        sealed_id = "sealed-company-do-not-touch"
        _sealed = _sample(
            sealed_id,
            company=sealed_id,
            prediction_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            label=1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            engine = SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=MockSchemeFoldEvaluator(),
                fixed_spec=fixed,
                state_store=EvolutionStateStore(tmp),
            )
            result = engine.run(initial, _four_folds(fixed), candidate_count=1)
            artifact_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in Path(tmp).rglob("*.json")
            )
            state = json.loads(
                result.artifact_paths["state"].read_text(encoding="utf-8")
            )
        self.assertNotIn(sealed_id, artifact_text)
        self.assertFalse(state["sealed_test_included"])

    def test_file_proposer_rejects_invalid_candidate_json(self) -> None:
        initial, _candidates = _genomes()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidates.json"
            path.write_text('{"candidates": [{"genome_id": "broken"}]}', encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "invalid scheme candidate"):
                FileSchemeProposer(path).propose([initial], [], [], 1)

    def test_blind_prompt_label_variable_is_rejected(self) -> None:
        initial, candidates = _genomes()
        leaking_prompt = replace(
            candidates[0].blind_analysis_prompt,
            variables=candidates[0].blind_analysis_prompt.variables + ["label"],
            content_hash="",
        )
        leaking = replace(
            candidates[0],
            genome_id="leaking-candidate",
            blind_analysis_prompt=leaking_prompt,
        )
        reasons = CandidateValidator().validate(
            leaking,
            parents=[initial],
            accepted=[],
        )
        self.assertTrue(any("forbidden variables" in reason for reason in reasons))

    def test_exact_and_near_duplicate_candidates_are_filtered(self) -> None:
        initial, candidates = _genomes()
        exact = replace(candidates[0], genome_id="exact-copy")
        reasons = CandidateValidator().validate(
            exact,
            parents=[initial],
            accepted=[candidates[0]],
        )
        self.assertTrue(any("exact recipe duplicate" in reason for reason in reasons))
        self.assertEqual(genome_recipe_hash(exact), genome_recipe_hash(candidates[0]))

    def test_predictions_must_exist_before_evaluation_artifact(self) -> None:
        evaluation = _evaluation("candidate", pr_auc=0.5)
        with tempfile.TemporaryDirectory() as tmp:
            store = EvolutionStateStore(tmp)
            with self.assertRaisesRegex(ValidationError, "predictions must be persisted"):
                store.write_evaluation("context", evaluation, context={})

    def test_resume_reuses_predictions_without_calling_evaluator(self) -> None:
        initial, candidates = _genomes()
        fixed = _fixed_spec()
        folds = _four_folds(fixed)
        with tempfile.TemporaryDirectory() as tmp:
            first_evaluator = MockSchemeFoldEvaluator()
            first_engine = SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=first_evaluator,
                fixed_spec=fixed,
                state_store=EvolutionStateStore(tmp),
            )
            first_engine.run(initial, folds, candidate_count=1)
            self.assertTrue(first_evaluator.observed_blind_inputs)

            second_evaluator = MockSchemeFoldEvaluator()
            second_engine = SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=second_evaluator,
                fixed_spec=fixed,
                state_store=EvolutionStateStore(tmp),
            )
            resumed = second_engine.run(initial, folds, candidate_count=1, resume=True)
            self.assertEqual(second_evaluator.observed_blind_inputs, [])
            self.assertEqual(resumed.incumbent.genome_id, candidates[0].genome_id)

    def test_resume_invalidates_same_fold_id_when_fold_content_changes(self) -> None:
        initial, candidates = _genomes()
        fixed = _fixed_spec()
        folds = _four_folds(fixed)
        with tempfile.TemporaryDirectory() as tmp:
            SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=MockSchemeFoldEvaluator(),
                fixed_spec=fixed,
                state_store=EvolutionStateStore(tmp),
            ).run(initial, folds, candidate_count=1)
            changed_first = replace(
                folds[0],
                admission_samples=[
                    replace(
                        sample,
                        features={**sample.features, "signal_strength": 0.99},
                    )
                    for sample in folds[0].admission_samples
                ],
            )
            evaluator = MockSchemeFoldEvaluator()
            SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=evaluator,
                fixed_spec=fixed,
                state_store=EvolutionStateStore(tmp),
            ).run(
                initial,
                [changed_first, *folds[1:]],
                candidate_count=1,
                resume=True,
            )
        self.assertTrue(evaluator.observed_blind_inputs)

    def test_insufficient_blocks_never_promote_candidate(self) -> None:
        initial, candidates = _genomes()
        fixed = _fixed_spec()
        one_fold = _four_folds(fixed)[:1]
        with tempfile.TemporaryDirectory() as tmp:
            result = SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=MockSchemeFoldEvaluator(),
                fixed_spec=fixed,
                state_store=EvolutionStateStore(tmp),
            ).run(initial, one_fold, candidate_count=1)
        decision = result.experiments[0].admission_decision
        self.assertFalse(decision.admitted)
        self.assertEqual(decision.status, "insufficient_evidence")
        self.assertEqual(result.incumbent.genome_id, initial.genome_id)

    def test_archive_preserves_distinct_niches(self) -> None:
        initial, candidates = _genomes()
        archive = QualityDiversityArchive()
        archive.update(initial, _evaluation(initial.genome_id, pr_auc=0.4), admitted=True)
        archive.update(candidates[0], _evaluation(candidates[0].genome_id, pr_auc=0.6), admitted=False)
        archive.update(candidates[1], _evaluation(candidates[1].genome_id, pr_auc=0.5), admitted=False)
        self.assertEqual(len(archive.entries), 3)
        self.assertEqual(len({entry.niche for entry in archive.entries}), 3)

    def test_mock_end_to_end_is_network_free_secret_safe_and_resumable(self) -> None:
        initial, candidates = _genomes()
        fixed = _fixed_spec()
        with tempfile.TemporaryDirectory() as tmp:
            result = SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates),
                evaluator=MockSchemeFoldEvaluator(),
                fixed_spec=fixed,
                state_store=EvolutionStateStore(tmp),
            ).run(initial, _four_folds(fixed), candidate_count=2)
            state = json.loads(result.artifact_paths["state"].read_text(encoding="utf-8"))
            all_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in Path(tmp).rglob("*.json")
            )
            lesson_artifact = json.loads(
                result.artifact_paths["meta_lessons"].read_text(encoding="utf-8")
            )
        self.assertEqual(result.incumbent.genome_id, "info-genome-event-evidence-v2")
        self.assertEqual(len(result.experiments), 2)
        self.assertEqual(len(result.archive.entries), 3)
        self.assertTrue(result.meta_lessons)
        self.assertTrue(result.mutation_requests)
        self.assertEqual(state["proposal_status"], "proposal_only_pending_human_review")
        self.assertFalse(lesson_artifact["contains_per_sample_labels"])
        self.assertNotIn("admission-1-positive", json.dumps(lesson_artifact))
        self.assertNotIn("OPENROUTER_API_KEY", all_text)
        self.assertNotIn("sk-", all_text)

    def test_invalid_model_json_is_rejected(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(
            initial,
            _four_folds(_fixed_spec())[0],
        )
        with tempfile.TemporaryDirectory() as tmp:
            analyzer = OpenAIGenomeBlindAnalyzer(
                _FakeChatClient("not-json"),
                tmp,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
            )
            with self.assertRaisesRegex(ValidationError, "not valid JSON"):
                analyzer.analyze(initial, materialized, _blind_packet())

    def test_model_output_with_unexpected_fields_is_rejected(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(
            initial,
            _four_folds(_fixed_spec())[0],
        )
        output = json.dumps(
            {
                "probability_of_surge": 0.5,
                "decision": "abstain",
                "confidence": "low",
                "supporting_signals": [],
                "contradicting_signals": [],
                "missing_critical_information": ["missing evidence"],
                "difficulty_codes": ["insufficient_information"],
                "evidence_source_ids": [],
                "hidden_label_guess": "winner",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            analyzer = OpenAIGenomeBlindAnalyzer(
                _FakeChatClient(output),
                tmp,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
            )
            with self.assertRaisesRegex(ValidationError, "unexpected fields"):
                analyzer.analyze(initial, materialized, _blind_packet())

    def test_same_genome_request_hits_secret_safe_cache(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(
            initial,
            _four_folds(_fixed_spec())[0],
        )
        output = json.dumps(
            {
                "probability_of_surge": 0.7,
                "decision": "positive",
                "confidence": "medium",
                "supporting_signals": ["confirmed event"],
                "contradicting_signals": [],
                "missing_critical_information": [],
                "difficulty_codes": [],
                "evidence_source_ids": ["opaque-ref-1"],
            }
        )
        client = _FakeChatClient(output)
        with tempfile.TemporaryDirectory() as tmp:
            analyzer = OpenAIGenomeBlindAnalyzer(
                client,
                tmp,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
            )
            first = analyzer.analyze(initial, materialized, _blind_packet())
            second = analyzer.analyze(initial, materialized, _blind_packet())
            cache_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in Path(tmp).glob("*.json")
            )
        self.assertEqual(first["probability_of_surge"], 0.7)
        self.assertEqual(second["probability_of_surge"], 0.7)
        self.assertEqual(client.calls, 1)
        self.assertEqual(analyzer.external_call_count, 1)
        self.assertEqual(analyzer.cache_hit_count, 1)
        self.assertTrue(first["_metadata"]["external_call_performed"])
        self.assertFalse(second["_metadata"]["external_call_performed"])
        self.assertNotIn("secret-key", cache_text)

    def test_provider_cost_budget_fails_closed_before_request(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(
            initial,
            _four_folds(_fixed_spec())[0],
        )
        client = _FakeChatClient("{}")
        with tempfile.TemporaryDirectory() as tmp:
            analyzer = OpenAIGenomeBlindAnalyzer(
                client,
                tmp,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                input_cost_per_million_tokens=1000.0,
                output_cost_per_million_tokens=1000.0,
                max_cost_usd=0.01,
            )
            with self.assertRaisesRegex(ValidationError, "cost budget"):
                analyzer.analyze(initial, materialized, _blind_packet())
        self.assertEqual(client.calls, 0)

    def test_packet_identity_scan_ignores_fixed_short_word_but_checks_evidence(self) -> None:
        packet = BlindSchemePacket(
            source_case_id="source-case",
            anonymous_case_id="anonymous-case",
            as_of_date="2025-01-01",
            scheme_id="scheme",
            scheme_version="scheme-v1",
            sections=(
                BlindPacketSection(
                    name="Evidence",
                    priority=1,
                    token_budget=100,
                    compression_rule="Judge evidence in this section.",
                    items=({"summary": "Ordinary evidence remains available."},),
                    estimated_tokens=4,
                ),
            ),
        )
        self.assertEqual(
            _packet_identity_findings(
                packet,
                own_identity_terms=("IN",),
                cross_identity_terms=("AI",),
            ),
            [],
        )
        leaking = replace(
            packet,
            sections=(
                replace(
                    packet.sections[0],
                    items=({"summary": "ACME announced a contract."},),
                ),
            ),
        )
        self.assertEqual(
            _packet_identity_findings(
                leaking,
                own_identity_terms=("IN",),
                cross_identity_terms=("ACME",),
            ),
            ["ACME"],
        )


def _genomes() -> tuple[SchemeGenome, list[SchemeGenome]]:
    initial = SchemeGenome.from_dict(json.loads(INITIAL_PATH.read_text(encoding="utf-8")))
    candidates = FileSchemeProposer(CANDIDATE_PATH).propose([initial], [], [], 8)
    return initial, candidates


def _fixed_spec() -> FixedEvolutionSpec:
    return FixedEvolutionSpec(
        label_spec=LabelSpec(version="test-label-v1", horizon_days=90),
        split_spec=DataSplitSpec(
            version="test-split-v1",
            purge_days=15,
            embargo_days=15,
        ),
        evaluation_spec=EvaluationSpec(
            version="test-evaluation-v1",
            top_k=2,
            bootstrap_replicates=80,
            minimum_paired_blocks=4,
        ),
    )


def _four_folds(fixed: FixedEvolutionSpec):
    discovery_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    samples = [
        _sample(
            f"discovery-{index}",
            company=f"discovery-company-{index}",
            prediction_time=discovery_time + timedelta(days=index * 10),
            label=index % 2,
            strength=0.7 if index % 2 else 0.25,
            period="2023-H1",
        )
        for index in range(6)
    ]
    starts = [
        datetime(2024, 6, 1, tzinfo=timezone.utc),
        datetime(2024, 10, 1, tzinfo=timezone.utc),
        datetime(2025, 2, 1, tzinfo=timezone.utc),
        datetime(2025, 6, 1, tzinfo=timezone.utc),
    ]
    for fold_index, start in enumerate(starts, start=1):
        samples.extend(
            [
                _sample(
                    f"admission-{fold_index}-positive",
                    company=f"admission-{fold_index}-positive",
                    prediction_time=start + timedelta(days=1),
                    label=1,
                    strength=0.7,
                    period=start.strftime("%Y-%m"),
                ),
                _sample(
                    f"admission-{fold_index}-negative",
                    company=f"admission-{fold_index}-negative",
                    prediction_time=start + timedelta(days=2),
                    label=0,
                    strength=0.25,
                    period=start.strftime("%Y-%m"),
                ),
            ]
        )
    return build_walk_forward_folds(
        samples,
        starts,
        fixed_spec=fixed,
        admission_window_days=10,
    )


def _sample(
    sample_id: str,
    *,
    company: str,
    prediction_time: datetime,
    label: int,
    strength: float = 0.5,
    period: str = "test-period",
    available_date=None,
) -> LabeledSample:
    return LabeledSample(
        sample_id=sample_id,
        company_key=company,
        prediction_time=prediction_time,
        label=label,
        sector="technology",
        market_cap_bucket="small",
        period=period,
        features={"signal_strength": strength},
        evidence_source_ids=[f"source:{sample_id}"],
        document_available_dates=[
            available_date or prediction_time.date() - timedelta(days=1)
        ],
    )


def _evaluation(genome_id: str, *, pr_auc: float) -> SchemeEvaluationResult:
    return SchemeEvaluationResult(
        genome_id=genome_id,
        sample_count=10,
        confusion_matrix={"tp": 2, "fp": 1, "tn": 5, "fn": 2},
        precision=2 / 3,
        recall=0.5,
        f1=0.57,
        pr_auc=pr_auc,
        roc_auc=0.6,
        brier_score=0.2,
        log_loss=0.6,
        precision_at_k=0.5,
        recall_at_k=0.5,
        coverage_rate=1.0,
        abstention_rate=0.0,
        metrics_by_time_period={},
        metrics_by_sector={},
        metrics_by_market_cap_bucket={},
        model_provider_sensitivity={},
        data_cost_usd=0.0,
        token_cost_usd=0.0,
        latency_ms=0.0,
        confidence_intervals={},
        worst_period_f1=0.5,
        primary_utility=pr_auc,
    )


def _blind_packet() -> BlindSchemePacket:
    return BlindSchemePacket(
        source_case_id="internal-case-id",
        anonymous_case_id="anonymous-001",
        as_of_date="2025-01-01",
        scheme_id="test-scheme",
        scheme_version="test-scheme-v1",
        sections=(
            BlindPacketSection(
                name="Catalyst/Event Ledger",
                priority=1,
                token_budget=100,
                compression_rule="fixture",
                items=(
                    {
                        "evidence_ref": "opaque-ref-1",
                        "summary": "Confirmed source-linked event.",
                    },
                ),
                estimated_tokens=10,
            ),
        ),
    )


class _FakeChatClient:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        assert kwargs["response_format"]["type"] == "json_schema"
        assert all(message.role != "tool" for message in messages)
        return ChatResponse(
            response_id=f"response-{self.calls}",
            model="fake-model",
            output_text=self.output_text,
            raw={"usage": {"input_tokens": 10, "output_tokens": 10}},
        )
