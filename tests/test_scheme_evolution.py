from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.llm.openai import ChatResponse
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.ralph_loop import BlindPacketSection, BlindSchemePacket
from stock_opportunity_agent.research.scheme_evolution import (
    ArchiveEntry,
    CandidateValidator,
    DataSplitSpec,
    EvaluationContract,
    EvaluationSpec,
    EvolutionStateStore,
    FileSchemeProposer,
    FixedEvolutionSpec,
    LabeledSample,
    MockSchemeFoldEvaluator,
    MockSchemeProposer,
    MutationOperator,
    PredictionRecord,
    SchemeEvaluationResult,
    SchemeEvolutionEngine,
    SchemeGenome,
    TopKArchive,
    build_walk_forward_folds,
    evaluate_predictions,
    realized_max_multiple,
    validate_folds,
)
from stock_opportunity_agent.research.scheme_evolution_ralph import (
    OpenAIGenomeBlindAnalyzer,
    OpenRouterFusionSchemeProposer,
    _packet_identity_findings,
)
from stock_opportunity_agent.research.scheme_evolution_dashboard import (
    write_evolution_dashboard,
    write_evolution_dashboard_index,
)


ROOT = Path(__file__).resolve().parents[1]
INITIAL_PATH = ROOT / "configs/evolution/initial_genome.json"
CANDIDATE_PATH = ROOT / "configs/evolution/codex_candidates_v1.json"


class SchemeEvolutionTests(TestCase):
    def test_genome_schema_round_trip_and_fixed_output_contract(self) -> None:
        initial, candidates = _genomes()
        restored = SchemeGenome.from_dict(initial.to_dict())
        self.assertEqual(restored, initial)
        self.assertEqual(len(candidates), 2)
        self.assertNotIn("probability_of_surge", restored.blind_analysis_prompt.output_json_schema)
        self.assertEqual(
            set(restored.blind_analysis_prompt.output_json_schema),
            {
                "predicted_class",
                "confidence_level",
                "difficulty_level",
                "difficulty_reasons",
                "decisive_signals",
                "conflicting_signals",
                "missing_information",
                "flip_conditions",
                "evidence_source_ids",
            },
        )

    def test_evaluation_contract_is_frozen_across_resume(self) -> None:
        fixed = _fixed_spec()
        with tempfile.TemporaryDirectory() as tmp:
            store = EvolutionStateStore(tmp, run_id="frozen")
            store.initialize(fixed)
            with self.assertRaisesRegex(ValidationError, "frozen evaluation contract"):
                store.initialize(
                    replace(
                        fixed,
                        evaluation_contract=EvaluationContract(version="different-version"),
                    )
                )
            self.assertFalse((Path(tmp) / "evaluation_contract.json.tmp").exists())

    def test_realized_multiple_uses_five_day_smoothing_and_maps_classes(self) -> None:
        contract = EvaluationContract()
        multiple = realized_max_multiple(10.0, [10.0, 10.0, 100.0, 10.0, 10.0])
        self.assertEqual(multiple, 2.8)
        self.assertEqual(contract.classify(1.99), "A")
        self.assertEqual(contract.classify(2.0), "B")
        self.assertEqual(contract.classify(2.99), "B")
        self.assertEqual(contract.classify(3.0), "C")

    def test_binary_mapping_is_derived_from_abc(self) -> None:
        contract = EvaluationContract()
        self.assertFalse(contract.is_positive("A"))
        self.assertTrue(contract.is_positive("B"))
        self.assertTrue(contract.is_positive("C"))
        with self.assertRaisesRegex(ValidationError, "true_class"):
            replace(_sample("bad", outcome_class="A", strength=0.1), is_surge=True)

    def test_binary_multiclass_and_ordinal_metrics(self) -> None:
        initial, _candidates = _genomes()
        samples = {
            "a": _sample("a", outcome_class="A", strength=0.1),
            "b": _sample("b", outcome_class="B", strength=0.6),
            "c": _sample("c", outcome_class="C", strength=0.9),
        }
        predictions = [
            _prediction(initial, "a", "A"),
            _prediction(initial, "b", "B"),
            _prediction(initial, "c", "A"),
        ]
        result = evaluate_predictions(initial, predictions, samples)
        self.assertAlmostEqual(result.binary_f1, 2 / 3, places=7)
        self.assertAlmostEqual(result.multiclass_macro_f1, 5 / 9, places=7)
        self.assertEqual(result.class_c_recall, 0.0)
        self.assertAlmostEqual(result.ordinal_distance, 2 / 3, places=7)
        self.assertEqual(result.error_cases[0]["ordinal_error"], 2)
        self.assertEqual(result.error_cases[0]["realized_max_multiple"], 3.4)

    def test_future_document_and_walk_forward_overlap_are_rejected(self) -> None:
        prediction_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValidationError, "after prediction_time"):
            _sample(
                "future-source",
                outcome_class="A",
                strength=0.1,
                prediction_time=prediction_time,
                available_date=prediction_time.date() + timedelta(days=1),
            )
        fixed = _fixed_spec()
        samples = [
            _sample(
                "too-recent",
                outcome_class="A",
                strength=0.1,
                prediction_time=datetime(2024, 12, 1, tzinfo=timezone.utc),
            ),
            _sample(
                "validation",
                outcome_class="B",
                strength=0.6,
                prediction_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
            ),
        ]
        folds = build_walk_forward_folds(
            samples,
            [datetime(2025, 1, 1, tzinfo=timezone.utc)],
            fixed_spec=fixed,
            admission_window_days=10,
        )
        self.assertEqual(folds, [])

    def test_fold_requires_both_binary_classes_on_each_side(self) -> None:
        fixed = _fixed_spec()
        fold = _folds(fixed)[0]
        unsupported = replace(
            fold,
            admission_samples=tuple(
                sample for sample in fold.admission_samples if not sample.is_surge
            ),
        )
        with self.assertRaisesRegex(
            ValidationError,
            "development validation requires both A and B/C classes",
        ):
            validate_folds([unsupported], fixed)

    def test_atomic_state_checkpoint_and_append_only_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = EvolutionStateStore(tmp, run_id="atomic")
            store.initialize(_fixed_spec())
            store.begin_iteration(1, resume=False)
            store.checkpoint_task("task-1", status="running", context_hash="context")
            store.checkpoint_task("task-1", status="completed", context_hash="context")
            state = store.load_state()
            event_lines = (Path(tmp) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(state["current_tasks"][0]["status"], "completed")
            self.assertGreaterEqual(len(event_lines), 4)
            self.assertFalse(any(Path(tmp).rglob("*.tmp")))
            for line in event_lines:
                self.assertIsInstance(json.loads(line), dict)

    def test_progress_reports_candidate_summary_and_round_top_k_metrics(self) -> None:
        initial, candidates = _genomes()
        messages: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            result = SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=MockSchemeFoldEvaluator(),
                fixed_spec=_fixed_spec(),
                state_store=EvolutionStateStore(tmp, run_id="progress"),
                progress=messages.append,
            ).run(initial, _folds(_fixed_spec())[:1], candidate_count=1)
        output = "\n".join(messages)
        self.assertTrue(result.top_k)
        self.assertIn(f"candidate={candidates[0].genome_id}", output)
        self.assertIn(f"candidate-summary={candidates[0].genome_id}", output)
        self.assertIn("changed=", output)
        self.assertIn("falsification=", output)
        self.assertIn("top-k round=1 rank=1", output)
        self.assertIn("tp=", output)
        self.assertIn("binary_f1=", output)
        self.assertIn("class_c_recall=", output)
        self.assertIn("ordinal_distance=", output)
        self.assertIn("scope=development proposal_only=true", output)

    def test_empty_dashboard_opens_from_local_data_script_without_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = EvolutionStateStore(tmp, run_id="empty-dashboard")
            store.initialize(_fixed_spec())
            paths = write_evolution_dashboard(tmp)
            history = json.loads(paths["history"].read_text(encoding="utf-8"))
            html = paths["dashboard"].read_text(encoding="utf-8")
            data_script = paths["data"].read_text(encoding="utf-8")
        self.assertEqual(history["rounds"], [])
        self.assertFalse(history["contains_final_test_metrics"])
        self.assertIn('src="evolution_dashboard_data.js"', html)
        self.assertNotIn("fetch(", html)
        self.assertIn("window.__SCHEME_EVOLUTION_DASHBOARD__", data_script)

    def test_unified_dashboard_indexes_runs_and_defaults_to_latest(self) -> None:
        initial, candidates = _genomes()
        fixed = _fixed_spec()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evolution"
            for run_id in ("run-one", "run-two"):
                SchemeEvolutionEngine(
                    proposer=MockSchemeProposer(candidates[:1]),
                    evaluator=MockSchemeFoldEvaluator(),
                    fixed_spec=fixed,
                    state_store=EvolutionStateStore(root / run_id, run_id=run_id),
                ).run(initial, _folds(fixed)[:1], candidate_count=1)
            invalid = root / "invalid-run"
            invalid.mkdir()
            (invalid / "state.json").write_text("{}\n", encoding="utf-8")
            (invalid / "evolution_history.json").write_text(
                json.dumps({"schema_version": "wrong"}),
                encoding="utf-8",
            )
            paths = write_evolution_dashboard_index(root)
            index = json.loads(paths["index"].read_text(encoding="utf-8"))
            html = paths["dashboard"].read_text(encoding="utf-8")
            data_script = paths["data"].read_text(encoding="utf-8")
        self.assertEqual([run["run_id"] for run in index["runs"]], ["run-two", "run-one"])
        self.assertEqual(index["skipped_runs"][0]["run_directory"], "invalid-run")
        self.assertFalse(index["contains_final_test_metrics"])
        self.assertIn('id="run-select"', html)
        self.assertIn("window.__SCHEME_EVOLUTION_DASHBOARD__", data_script)
        self.assertNotIn("fetch(", html)

    def test_interruption_resume_reuses_completed_per_sample_predictions(self) -> None:
        initial, candidates = _genomes()
        folds = _folds(_fixed_spec())[:1]
        sample_count = len(folds[0].admission_samples)
        with tempfile.TemporaryDirectory() as tmp:
            store = EvolutionStateStore(tmp, run_id="interrupt-resume")
            interrupted = MockSchemeFoldEvaluator(interrupt_after=2)
            engine = SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=interrupted,
                fixed_spec=_fixed_spec(),
                state_store=store,
            )
            with self.assertRaises(KeyboardInterrupt):
                engine.run(initial, folds, candidate_count=1)
            completed_before_resume = list(Path(tmp).glob("experiments/*/predictions/*.json"))
            self.assertEqual(len(completed_before_resume), 2)
            self.assertEqual(store.load_state()["status"], "paused")

            resumed_evaluator = MockSchemeFoldEvaluator()
            result = SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=resumed_evaluator,
                fixed_spec=_fixed_spec(),
                state_store=store,
            ).run(initial, folds, candidate_count=1, resume=True)
            self.assertEqual(
                resumed_evaluator.predict_call_count,
                sample_count * 2 - len(completed_before_resume),
            )
            self.assertEqual(store.load_state()["status"], "completed")
            self.assertTrue(result.top_k)

    def test_blind_analyzer_never_receives_validation_labels(self) -> None:
        initial, candidates = _genomes()
        evaluator = MockSchemeFoldEvaluator()
        with tempfile.TemporaryDirectory() as tmp:
            SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=evaluator,
                fixed_spec=_fixed_spec(),
                state_store=EvolutionStateStore(tmp),
            ).run(initial, _folds(_fixed_spec())[:1], candidate_count=1)
        forbidden = {
            "realized_max_multiple",
            "true_class",
            "is_surge",
            "label",
            "future_price",
        }
        self.assertTrue(evaluator.observed_blind_inputs)
        self.assertTrue(
            all(not forbidden.intersection(payload) for payload in evaluator.observed_blind_inputs)
        )

    def test_invalid_json_retries_then_succeeds(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(initial, _folds(_fixed_spec())[0])
        client = _FakeChatClient(["not-json", json.dumps(_valid_model_output())])
        with tempfile.TemporaryDirectory() as tmp:
            output = OpenAIGenomeBlindAnalyzer(
                client,
                tmp,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=2,
            ).analyze(initial, materialized, _blind_packet())
            attempt_audits = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in Path(tmp).glob("_attempts/*/*.json")
            ]
        self.assertEqual(output["predicted_class"], "B")
        self.assertEqual(client.calls, 2)
        self.assertEqual(
            sorted(row["status"] for row in attempt_audits),
            ["failed_validation", "validated"],
        )
        self.assertTrue(
            any(row["raw_output"] == "not-json" for row in attempt_audits)
        )

    def test_external_attempt_ledger_survives_provider_error_and_enforces_cap(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(
            initial,
            _folds(_fixed_spec())[0],
        )
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "external_attempts.json"
            cache_path = Path(tmp) / "cache"
            failed_client = _FailingChatClient(
                RuntimeError("provider returned HTTP 429 for api_key=secret-key")
            )
            failed = OpenAIGenomeBlindAnalyzer(
                failed_client,
                cache_path,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
                input_cost_per_million_tokens=2.0,
                output_cost_per_million_tokens=8.0,
                max_cost_usd=2.0,
                attempt_ledger_path=ledger_path,
                attempt_scope_fingerprint="reviewed-preflight",
                authorized_max_external_attempts=1,
            )
            with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
                failed.analyze(initial, materialized, _blind_packet())

            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual(ledger["authorized_max_attempts"], 1)
            self.assertEqual(len(ledger["attempts"]), 1)
            self.assertEqual(ledger["attempts"][0]["status"], "provider_error")
            self.assertGreater(ledger["attempts"][0]["cost_usd"], 0.0)
            self.assertFalse(ledger["attempts"][0]["cost_observed"])
            self.assertNotIn("secret-key", ledger_path.read_text(encoding="utf-8"))

            blocked_client = _FakeChatClient([json.dumps(_valid_model_output())])
            blocked = OpenAIGenomeBlindAnalyzer(
                blocked_client,
                cache_path,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
                input_cost_per_million_tokens=2.0,
                output_cost_per_million_tokens=8.0,
                max_cost_usd=2.0,
                attempt_ledger_path=ledger_path,
                attempt_scope_fingerprint="reviewed-preflight",
                authorized_max_external_attempts=1,
            )
            request = blocked.preview_request(initial, materialized, _blind_packet())
            with self.assertRaisesRegex(
                ValidationError,
                "uncached blind requests exceed the remaining authorized",
            ):
                blocked.assert_authorized_capacity([request])
            self.assertEqual(blocked_client.calls, 0)

            resumed_client = _FakeChatClient([json.dumps(_valid_model_output())])
            resumed = OpenAIGenomeBlindAnalyzer(
                resumed_client,
                cache_path,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
                input_cost_per_million_tokens=2.0,
                output_cost_per_million_tokens=8.0,
                max_cost_usd=2.0,
                attempt_ledger_path=ledger_path,
                attempt_scope_fingerprint="reviewed-preflight",
                authorized_max_external_attempts=2,
            )
            capacity = resumed.assert_authorized_capacity([request])
            output = resumed.analyze(initial, materialized, _blind_packet())
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

        self.assertEqual(output["predicted_class"], "B")
        self.assertEqual(capacity["outstanding_request_count"], 1)
        self.assertEqual(capacity["remaining_authorized_attempts"], 1)
        self.assertEqual(resumed.cumulative_external_call_count, 2)
        self.assertEqual(len(ledger["attempts"]), 2)
        self.assertEqual(ledger["attempts"][1]["status"], "completed")
        self.assertGreater(ledger["attempts"][1]["cost_usd"], 0.0)
        self.assertEqual(
            ledger["authorization_changes"][0]["authorized_max_attempts"],
            2,
        )

    def test_request_preview_is_exact_label_free_and_performs_no_call(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(
            initial,
            _folds(_fixed_spec())[0],
        )
        client = _FakeChatClient([json.dumps(_valid_model_output())])
        with tempfile.TemporaryDirectory() as tmp:
            analyzer = OpenAIGenomeBlindAnalyzer(
                client,
                tmp,
                provider="openrouter:openai",
                model="openai/gpt-4.1",
                temperature=0.0,
                max_attempts=1,
                input_cost_per_million_tokens=2.0,
                output_cost_per_million_tokens=8.0,
                max_cost_usd=2.0,
            )
            preview = analyzer.preview_request(
                initial,
                materialized,
                _blind_packet(),
            )
        serialized_payload = json.dumps(preview["input_payload"], sort_keys=True)
        self.assertEqual(client.calls, 0)
        self.assertEqual(analyzer.external_call_count, 0)
        self.assertFalse(preview["external_call_performed"])
        self.assertEqual(preview["model"], "openai/gpt-4.1")
        self.assertGreater(preview["maximum_request_cost_usd"], 0)
        developer_prompt = preview["messages"][0]["content"]
        self.assertIn("class A means below 2.0", developer_prompt)
        self.assertIn("class B means at least 2.0 and below 3.0", developer_prompt)
        self.assertIn("class C means at least 3.0", developer_prompt)
        self.assertIn("A negative or unsupported setup must map to A, never C", developer_prompt)
        self.assertEqual(
            preview["prompt_hash"],
            hashlib.sha256(developer_prompt.encode("utf-8")).hexdigest(),
        )
        for forbidden in (
            "source_case_id",
            "realized_max_multiple",
            "true_class",
            "is_surge",
        ):
            self.assertNotIn(forbidden, serialized_payload)
        self.assertEqual(
            json.loads(preview["messages"][1]["content"]),
            preview["input_payload"],
        )

    def test_effective_blind_prompt_changes_cache_identity(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(
            initial,
            _folds(_fixed_spec())[0],
        )
        changed_prompt = replace(
            initial.blind_analysis_prompt,
            template=initial.blind_analysis_prompt.template + " Preserve abstention.",
            content_hash="",
        )
        changed = replace(initial, blind_analysis_prompt=changed_prompt)
        client = _FakeChatClient([])
        with tempfile.TemporaryDirectory() as tmp:
            analyzer = OpenAIGenomeBlindAnalyzer(
                client,
                tmp,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
            )
            original = analyzer.preview_request(initial, materialized, _blind_packet())
            modified = analyzer.preview_request(changed, materialized, _blind_packet())

        self.assertEqual(original["input_hash"], modified["input_hash"])
        self.assertNotEqual(original["prompt_hash"], modified["prompt_hash"])
        self.assertNotEqual(original["cache_key"], modified["cache_key"])
        self.assertEqual(client.calls, 0)

    def test_fusion_proposer_previews_and_caches_one_valid_candidate(self) -> None:
        initial, candidates = _genomes()
        response = json.dumps({"candidates": [candidates[0].to_dict()]})
        client = _FakeChatClient([response])
        with tempfile.TemporaryDirectory() as tmp:
            proposer = OpenRouterFusionSchemeProposer(
                client,
                tmp,
                objective_text="Keep the exam fixed and mutate one information scheme.",
                max_cost_usd=2.0,
            )
            preview = proposer.preview_request([initial], [], [], 1)
            first = proposer.propose([initial], [], [], 1)
            second = proposer.propose([initial], [], [], 1)
        self.assertFalse(preview["external_call_performed"])
        self.assertEqual(preview["model"], "openrouter/fusion")
        self.assertEqual(preview["plugins"][0]["preset"], "general-high")
        self.assertLess(preview["pricing_snapshot_estimated_cost_usd"], 2.0)
        self.assertEqual(first, second)
        self.assertEqual(first[0].genome_id, candidates[0].genome_id)
        self.assertEqual(client.calls, 1)
        self.assertEqual(proposer.external_call_count, 1)
        self.assertEqual(proposer.cache_hit_count, 1)

    def test_fusion_proposer_persists_invalid_response_without_retry(self) -> None:
        initial, _candidates = _genomes()
        client = _FakeChatClient(["not-json"])
        with tempfile.TemporaryDirectory() as tmp:
            proposer = OpenRouterFusionSchemeProposer(
                client,
                tmp,
                objective_text="Keep the exam fixed.",
                max_cost_usd=2.0,
            )
            with self.assertRaisesRegex(ValidationError, "JSON object"):
                proposer.propose([initial], [], [], 1)
            cache = json.loads(next(Path(tmp).glob("*.json")).read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValidationError, "automatic retry is disabled"):
                proposer.propose([initial], [], [], 1)
        self.assertEqual(client.calls, 1)
        self.assertEqual(cache["status"], "failed_validation")
        self.assertEqual(cache["raw_output"], "not-json")

    def test_model_probability_field_is_rejected(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(initial, _folds(_fixed_spec())[0])
        output = {**_valid_model_output(), "probability_of_surge": 0.7}
        with tempfile.TemporaryDirectory() as tmp:
            analyzer = OpenAIGenomeBlindAnalyzer(
                _FakeChatClient([json.dumps(output)]),
                tmp,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
            )
            with self.assertRaisesRegex(ValidationError, "unexpected fields"):
                analyzer.analyze(initial, materialized, _blind_packet())

    def test_packet_fact_refs_are_valid_citations_and_external_refs_are_rejected(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(
            initial,
            _folds(_fixed_spec())[0],
        )
        packet = _blind_packet()
        packet = replace(
            packet,
            sections=(
                replace(
                    packet.sections[0],
                    items=(
                        {
                            "fact_ref": "fact_visible_in_packet",
                            "derived_from_fact_refs": ["fact_visible_lineage"],
                            "summary": "Point-in-time source-backed fact.",
                        },
                    ),
                ),
            ),
        )
        valid_output = {
            **_valid_model_output(),
            "evidence_source_ids": [
                "fact_visible_in_packet",
                "fact_visible_lineage",
            ],
        }
        invalid_output = {
            **_valid_model_output(),
            "evidence_source_ids": ["fact_outside_packet"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            valid_dir = Path(tmp) / "valid"
            valid = OpenAIGenomeBlindAnalyzer(
                _FakeChatClient([json.dumps(valid_output)]),
                valid_dir,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
            ).analyze(initial, materialized, packet)
            valid_audit = json.loads(
                next(valid_dir.glob("_attempts/*/*.json")).read_text(encoding="utf-8")
            )

            invalid_dir = Path(tmp) / "invalid"
            invalid_analyzer = OpenAIGenomeBlindAnalyzer(
                _FakeChatClient([json.dumps(invalid_output)]),
                invalid_dir,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
            )
            with self.assertRaisesRegex(ValidationError, "outside the packet"):
                invalid_analyzer.analyze(initial, materialized, packet)
            invalid_audit = json.loads(
                next(invalid_dir.glob("_attempts/*/*.json")).read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(
            valid["evidence_source_ids"],
            ["fact_visible_in_packet", "fact_visible_lineage"],
        )
        self.assertEqual(valid_audit["status"], "validated")
        self.assertIn("fact_visible_in_packet", valid_audit["raw_output"])
        self.assertEqual(invalid_audit["status"], "failed_validation")
        self.assertIn("fact_outside_packet", invalid_audit["validation_error"])

    def test_failed_validation_audit_is_revalidated_without_http(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(
            initial,
            _folds(_fixed_spec())[0],
        )
        packet = replace(
            _blind_packet(),
            sections=(
                replace(
                    _blind_packet().sections[0],
                    items=(
                        {
                            "fact_ref": "derived_fact",
                            "derived_from_fact_refs": ["lineage_fact"],
                            "summary": "Derived point-in-time fact.",
                        },
                    ),
                ),
            ),
        )
        output = {
            **_valid_model_output(),
            "evidence_source_ids": ["lineage_fact"],
        }
        client = _FakeChatClient([])
        with tempfile.TemporaryDirectory() as tmp:
            analyzer = OpenAIGenomeBlindAnalyzer(
                client,
                tmp,
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_attempts=1,
            )
            request = analyzer.preview_request(initial, materialized, packet)
            audit_path = (
                Path(tmp)
                / "_attempts"
                / request["cache_key"]
                / "attempt-0001.json"
            )
            audit_path.parent.mkdir(parents=True)
            raw_output = json.dumps(output)
            audit_path.write_text(
                json.dumps(
                    {
                        "schema_version": "genome-blind-response-attempt-v0.1",
                        "status": "failed_validation",
                        "cache_key": request["cache_key"],
                        "input_hash": request["input_hash"],
                        "settings_fingerprint": analyzer.settings_fingerprint,
                        "prompt_hash": request["prompt_hash"],
                        "response_id": "response-paid-before-fix",
                        "response_model": "fake-model",
                        "response_hash": hashlib.sha256(raw_output.encode()).hexdigest(),
                        "raw_output": raw_output,
                        "usage": {"total_tokens": 10},
                        "cost_usd": 0.01,
                        "cost_observed": True,
                        "received_at": "2026-08-02T00:00:00+00:00",
                        "validation_error": "old validator rejected lineage_fact",
                    }
                ),
                encoding="utf-8",
            )
            recovered = analyzer.analyze(initial, materialized, packet)
            cache = json.loads(
                (Path(tmp) / f'{request["cache_key"]}.json').read_text(encoding="utf-8")
            )
            audit = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertEqual(client.calls, 0)
        self.assertEqual(recovered["evidence_source_ids"], ["lineage_fact"])
        self.assertTrue(recovered["_metadata"]["revalidated_from_attempt_audit"])
        self.assertEqual(cache["prediction"]["predicted_class"], "B")
        self.assertEqual(audit["status"], "validated")
        self.assertIn("old validator", audit["prior_validation_error"])

    def test_identical_input_hits_secret_safe_openrouter_cache(self) -> None:
        initial, _candidates = _genomes()
        materialized = MockSchemeFoldEvaluator().materialize(initial, _folds(_fixed_spec())[0])
        client = _FakeChatClient([json.dumps(_valid_model_output())])
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
                path.read_text(encoding="utf-8") for path in Path(tmp).glob("*.json")
            )
        self.assertEqual(first["predicted_class"], "B")
        self.assertEqual(second["predicted_class"], "B")
        self.assertEqual(client.calls, 1)
        self.assertEqual(analyzer.cache_hit_count, 1)
        self.assertNotIn("secret-key", cache_text)

    def test_top_k_uses_binary_f1_ties_and_behavior_dedup(self) -> None:
        initial, candidates = _genomes()
        common_vector = {"a": False, "b": True}
        archive = TopKArchive()
        selected = archive.select(
            [
                ArchiveEntry(initial, _evaluation(initial.genome_id, f1=0.8, c_recall=0.2), common_vector),
                ArchiveEntry(candidates[0], _evaluation(candidates[0].genome_id, f1=0.8, c_recall=0.9), common_vector),
                ArchiveEntry(candidates[1], _evaluation(candidates[1].genome_id, f1=0.6, c_recall=1.0), {"a": True, "b": False}),
            ],
            top_k=2,
            similarity_threshold=0.95,
            maximum_cost_usd=20.0,
        )
        self.assertEqual(
            [entry.genome.genome_id for entry in selected],
            [candidates[0].genome_id, candidates[1].genome_id],
        )

    def test_mock_provider_runs_two_generations_and_keeps_final_test_sealed(self) -> None:
        initial, candidates = _genomes()
        fixed = _fixed_spec()
        folds = _folds(fixed)
        with tempfile.TemporaryDirectory() as tmp:
            store = EvolutionStateStore(tmp, run_id="two-generations")
            first = SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates),
                evaluator=MockSchemeFoldEvaluator(),
                fixed_spec=fixed,
                state_store=store,
            ).run(initial, folds, candidate_count=2)
            store.write_run_artifacts(first, fixed_spec=fixed, rejections=first.rejections)
            first_history = json.loads(
                (Path(tmp) / "evolution_history.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(first_history["rounds"]), 1)
            parent = first.incumbent
            child = replace(
                parent,
                genome_id="second-generation-local-refine",
                parent_ids=[parent.genome_id],
                generation=parent.generation + 1,
                mutation_operator=MutationOperator.LOCAL_REFINE,
                hypothesis_of_change="Test stricter class-C materiality.",
                changed_fields=["metadata.ordinal_shift_min_strength"],
                expected_benefit="Reduce B-to-C errors.",
                possible_side_effects=["May miss marginal C cases."],
                falsification_test="Reject if class-C recall falls.",
                metadata={**parent.metadata, "ordinal_shift_min_strength": 0.75},
            )
            second = SchemeEvolutionEngine(
                proposer=MockSchemeProposer([child]),
                evaluator=MockSchemeFoldEvaluator(),
                fixed_spec=fixed,
                state_store=store,
                archive=first.archive,
                validator=CandidateValidator(near_duplicate_threshold=1.0),
            ).run(parent, folds, candidate_count=1, resume=True)
            state = store.load_state()
            dashboard_paths = write_evolution_dashboard(tmp)
            history = json.loads(
                dashboard_paths["history"].read_text(encoding="utf-8")
            )
            all_artifacts = "\n".join(
                path.read_text(encoding="utf-8")
                for path in Path(tmp).rglob("*.json")
            )
        self.assertEqual(state["current_iteration"], 2)
        self.assertEqual(state["status"], "completed")
        self.assertFalse(state["final_test_accessed"])
        self.assertEqual(len(second.experiments), 1)
        self.assertEqual([row["iteration"] for row in history["rounds"]], [1, 2])
        self.assertTrue(all("archive_best_metrics" in row for row in history["rounds"]))
        self.assertTrue(all("candidates" in row for row in history["rounds"]))
        self.assertNotIn("final-test-company-do-not-touch", all_artifacts)
        self.assertTrue(second.meta_lessons)

    def test_dashboard_recovers_only_latest_legacy_development_round(self) -> None:
        initial, candidates = _genomes()
        fixed = _fixed_spec()
        with tempfile.TemporaryDirectory() as tmp:
            store = EvolutionStateStore(tmp, run_id="legacy-dashboard")
            SchemeEvolutionEngine(
                proposer=MockSchemeProposer(candidates[:1]),
                evaluator=MockSchemeFoldEvaluator(),
                fixed_spec=fixed,
                state_store=store,
            ).run(initial, _folds(fixed)[:1], candidate_count=1)
            history_path = Path(tmp) / "evolution_history.json"
            history_path.unlink()
            final_test_dir = Path(tmp) / "final_test"
            final_test_dir.mkdir()
            (final_test_dir / "evaluation.json").write_text(
                json.dumps({"binary_f1": 0.123456789}),
                encoding="utf-8",
            )
            paths = write_evolution_dashboard(tmp)
            history = json.loads(paths["history"].read_text(encoding="utf-8"))
            combined = json.dumps(history, sort_keys=True)
        self.assertEqual(len(history["rounds"]), 1)
        self.assertEqual(history["rounds"][0]["source"], "legacy_latest_only")
        self.assertFalse(history["contains_final_test_metrics"])
        self.assertNotIn("0.123456789", combined)

    def test_identity_preflight_still_checks_packet_evidence(self) -> None:
        packet = _blind_packet()
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
                    items=({"evidence_ref": "opaque-ref-1", "summary": "ACME contract."},),
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
        evaluation_contract=EvaluationContract(),
        split_spec=DataSplitSpec(
            version="test-company-disjoint-walk-forward-v2",
            purge_days=5,
            embargo_days=5,
        ),
        evaluation_spec=EvaluationSpec(
            version="test-binary-f1-top-k-v2",
            top_k=3,
            prediction_similarity_threshold=0.95,
            maximum_cost_usd=20.0,
        ),
    )


def _folds(fixed: FixedEvolutionSpec):
    samples: list[LabeledSample] = []
    discovery_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    discovery_classes = ("A", "B", "C", "A", "B", "C")
    for index, outcome_class in enumerate(discovery_classes):
        samples.append(
            _sample(
                f"discovery-{index}",
                outcome_class=outcome_class,
                strength={"A": 0.2, "B": 0.6, "C": 0.8}[outcome_class],
                prediction_time=discovery_time + timedelta(days=index * 10),
            )
        )
    starts = [
        datetime(2024, 6, 1, tzinfo=timezone.utc),
        datetime(2024, 10, 1, tzinfo=timezone.utc),
    ]
    for fold_index, start in enumerate(starts, start=1):
        for offset, (outcome_class, strength) in enumerate(
            (("C", 0.72), ("A", 0.24), ("B", 0.68), ("A", 0.28)),
            start=1,
        ):
            samples.append(
                _sample(
                    f"validation-{fold_index}-{offset}",
                    outcome_class=outcome_class,
                    strength=strength,
                    prediction_time=start + timedelta(days=offset),
                    period=start.strftime("%Y-%m"),
                )
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
    outcome_class: str,
    strength: float,
    prediction_time: datetime | None = None,
    period: str = "test-period",
    available_date=None,
) -> LabeledSample:
    prediction_time = prediction_time or datetime(2025, 1, 1, tzinfo=timezone.utc)
    multiple = {"A": 1.4, "B": 2.4, "C": 3.4}[outcome_class]
    return LabeledSample(
        sample_id=sample_id,
        company_key=f"company:{sample_id}",
        prediction_time=prediction_time,
        realized_max_multiple=multiple,
        true_class=outcome_class,
        is_surge=outcome_class in {"B", "C"},
        sector="technology",
        market_cap_bucket="small",
        period=period,
        features={"signal_strength": strength},
        evidence_source_ids=[f"source:{sample_id}"],
        document_available_dates=[
            available_date or prediction_time.date() - timedelta(days=1)
        ],
    )


def _prediction(genome: SchemeGenome, sample_id: str, predicted_class: str) -> PredictionRecord:
    return PredictionRecord(
        genome_id=genome.genome_id,
        materialized_scheme_id="materialized",
        fold_id="fold",
        sample_id=sample_id,
        prediction_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        predicted_class=predicted_class,
        is_surge=predicted_class in {"B", "C"},
        confidence_level="medium",
        difficulty_level="medium",
        difficulty_reasons=["fixture"],
        decisive_signals=[],
        conflicting_signals=[],
        missing_information=[],
        flip_conditions=[],
        evidence_source_ids=[],
        model_metadata={},
        input_hash=f"hash-{sample_id}",
        raw_response_location=None,
    )


def _evaluation(genome_id: str, *, f1: float, c_recall: float) -> SchemeEvaluationResult:
    return SchemeEvaluationResult(
        genome_id=genome_id,
        sample_count=2,
        confusion_matrix={"tp": 1, "fp": 0, "tn": 1, "fn": 0},
        binary_precision=f1,
        binary_recall=f1,
        binary_f1=f1,
        multiclass_confusion_matrix={
            actual: {predicted: 0 for predicted in ("A", "B", "C")}
            for actual in ("A", "B", "C")
        },
        per_class_recall={"A": 1.0, "B": 1.0, "C": c_recall},
        multiclass_macro_f1=(2 + c_recall) / 3,
        class_c_recall=c_recall,
        ordinal_distance=1 - c_recall,
        error_cases=[],
        reflection_summary={},
        predictions_by_sample={},
        binary_predictions_by_sample={},
        metrics_by_time_period={},
        metrics_by_sector={},
        metrics_by_market_cap_bucket={},
        data_cost_usd=0.0,
        token_cost_usd=0.0,
        latency_ms=0.0,
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


def _valid_model_output() -> dict[str, object]:
    return {
        "predicted_class": "B",
        "confidence_level": "medium",
        "difficulty_level": "medium",
        "difficulty_reasons": ["materiality is bounded"],
        "decisive_signals": ["confirmed event"],
        "conflicting_signals": [],
        "missing_information": [],
        "flip_conditions": ["event is cancelled"],
        "evidence_source_ids": ["opaque-ref-1"],
    }


class _FakeChatClient:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.calls = 0
        self.api_key = "secret-key"

    def complete(self, messages, **kwargs):
        self.calls += 1
        if "response_format" in kwargs:
            assert kwargs["response_format"]["type"] == "json_schema"
        assert all(message.role != "tool" for message in messages)
        output = self.outputs[min(self.calls - 1, len(self.outputs) - 1)]
        return ChatResponse(
            response_id=f"response-{self.calls}",
            model="fake-model",
            output_text=output,
            raw={"usage": {"input_tokens": 10, "output_tokens": 10}},
        )


class _FailingChatClient:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0
        self.api_key = "secret-key"

    def complete(self, messages, **kwargs):
        del messages, kwargs
        self.calls += 1
        raise self.error
