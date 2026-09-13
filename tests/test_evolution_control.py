"""Frozen-contract, transport, and cycle-control tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403
from stock_opportunity_agent.data.acquisition import (
    AlphaVantageNewsAdapter,
    AlphaVantageTranscriptAdapter,
    HistoricalPriceAdapter,
)
from stock_opportunity_agent.data.sources.alpha_vantage import (
    alpha_vantage_json_error,
)
from stock_opportunity_agent.research.evolution_control import (
    apply_slow_history_manifest,
    build_slow_history_manifest,
)
from stock_opportunity_agent.signal_library import SignalLearningEvent


class RunControlTests(TestCase):
    def test_slow_history_preserves_imported_learning_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            registry = SignalRegistry(source / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            signal_ref = registry.freeze().specs[0].ref
            initial_snapshot = registry.freeze()

            def event(event_id: str, *, round_id: int) -> SignalLearningEvent:
                return SignalLearningEvent(
                    event_id=event_id,
                    observation_key=f"observation-{event_id}",
                    signal_ref=signal_ref,
                    round_id=round_id,
                    plan_id=f"plan-{event_id}",
                    case_id=f"case-{event_id}",
                    company_id=f"company-{event_id}",
                    prediction_time="2025-01-10T00:00:00+00:00",
                    selection={
                        "signal_ref": signal_ref,
                        "reason_code": "assess_applicability",
                        "selection_reason": "Exercise committed learning continuity.",
                        "applicability_hypothesis": "The source is comparable.",
                        "expected_role": "coverage",
                        "context_tags": [],
                    },
                    result_value=SignalValue.POSITIVE,
                    coverage=SignalCoverage.SUFFICIENT,
                    document_fingerprint=(f"document-{event_id}",),
                    is_surge=True,
                    realized_max_multiple=2.5,
                    prediction_correct=True,
                )

            imported = event("imported", round_id=1)
            uncommitted = event("uncommitted", round_id=2)
            registry.record_learning_events((imported, uncommitted))
            bootstrap_manifest = {
                "schema_version": "slow-bootstrap-manifest-v2",
                "signal_learning_events": [imported.to_dict()],
            }
            bootstrap_hash = hashlib.sha256(
                json.dumps(
                    bootstrap_manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            (source / "slow_bootstrap").mkdir(parents=True)
            write_json(
                source / "slow_bootstrap" / "manifest.json",
                {"manifest_hash": bootstrap_hash, "manifest": bootstrap_manifest},
            )
            base_contract = make_contract()
            source_contract = replace(
                base_contract,
                cycle_mode="slow_bootstrap",
                slow_bootstrap_manifest_hash=bootstrap_hash,
                initial_signal_registry_hash=initial_snapshot.registry_hash,
                limits={
                    **base_contract.limits,
                    "plan_rounds_per_signal_cycle": 0,
                },
            )
            source_contract.freeze(source / "run_contract.json")
            stable = registry.load_spec(signal_ref)
            registry.register_stable(
                replace(stable, version=2),
                skill=registry.load_skill(signal_ref),
                tests=registry.load_tests(signal_ref),
            )
            registry.bump_version()
            promoted_snapshot = registry.freeze()
            transition_path = source / "signals" / ".transitions" / "cycle-0001.json"
            transition_path.parent.mkdir(parents=True)
            write_json(
                transition_path,
                {"transition_id": "cycle-0001", "status": "applied"},
            )
            write_json(source / "state.json", {"last_completed_round": 0})
            write_json(
                source / "cycle_state.json",
                {
                    "schema_version": "dual-loop-cycle-state-v2",
                    "run_contract_hash": source_contract.contract_hash,
                    "initial_signal_registry_version": 1,
                    "initial_signal_registry_hash": initial_snapshot.registry_hash,
                    "current_signal_registry_version": promoted_snapshot.version,
                    "current_signal_registry_hash": promoted_snapshot.registry_hash,
                    "last_completed_cycle": 1,
                    "active_cycle": None,
                },
            )
            committed_root = source / "experiments" / "cycles" / "cycle-0001"
            committed_root.mkdir(parents=True)
            for name in (
                "slow_input.json",
                "slow_memory.json",
                "slow_experiments.json",
                "slow_loop_validation.json",
                "slow_loop_result.json",
            ):
                write_json(committed_root / name, {"artifact": name})

            build_slow_history_manifest(
                workspace=target,
                source_workspace=source,
                dataset_manifest_hash=source_contract.dataset_manifest_hash,
            )
            envelope = json.loads(
                (target / "slow_history" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                [row["event_id"] for row in envelope["manifest"]["learning_events"]],
                ["imported"],
            )
            self.assertFalse(
                any(
                    row["path"].startswith(".transitions/")
                    for row in envelope["manifest"]["registry_definition_files"]
                )
            )
            apply_slow_history_manifest(
                workspace=target,
                manifest=envelope["manifest"],
            )
            self.assertEqual(
                [
                    item.event_id
                    for item in SignalRegistry(
                        target / "signals"
                    ).load_learning_events(signal_ref)
                ],
                ["imported"],
            )
            self.assertEqual(
                SignalRegistry(target / "signals").freeze().registry_hash,
                promoted_snapshot.registry_hash,
            )
            self.assertFalse((target / "signals" / ".transitions").exists())

    def test_slow_history_import_uses_only_committed_source_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source_registry = SignalRegistry(source / "signals")
            source_registry.install_catalog(
                PROJECT_ROOT / "configs" / "signals_v1.json"
            )
            source.mkdir(parents=True, exist_ok=True)
            source_contract = make_contract()
            source_contract.freeze(source / "run_contract.json")
            write_json(source / "state.json", {"last_completed_round": 0})
            write_json(
                source / "cycle_state.json",
                {
                    "schema_version": "dual-loop-cycle-state-v2",
                    "run_contract_hash": source_contract.contract_hash,
                    "initial_signal_registry_version": 1,
                    "initial_signal_registry_hash": source_registry.freeze().registry_hash,
                    "current_signal_registry_version": 1,
                    "current_signal_registry_hash": source_registry.freeze().registry_hash,
                    "last_completed_cycle": 1,
                    "active_cycle": {
                        "cycle_id": 2,
                        "phase": "slow_loop",
                    },
                },
            )
            committed_root = source / "experiments" / "cycles" / "cycle-0001"
            committed_root.mkdir(parents=True)
            for name in (
                "slow_input.json",
                "slow_memory.json",
                "slow_experiments.json",
                "slow_loop_validation.json",
                "slow_loop_result.json",
            ):
                write_json(committed_root / name, {"artifact": name})
            staged_path = (
                source
                / "experiments"
                / "cycles"
                / "cycle-0002"
                / "slow_input.json"
            )
            staged_path.parent.mkdir(parents=True)
            write_json(staged_path, {"artifact": "must-not-import"})

            manifest_hash = build_slow_history_manifest(
                workspace=target,
                source_workspace=source,
                dataset_manifest_hash=source_contract.dataset_manifest_hash,
            )
            envelope = json.loads(
                (target / "slow_history" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            apply_slow_history_manifest(
                workspace=target,
                manifest=envelope["manifest"],
            )

            self.assertEqual(manifest_hash, envelope["manifest_hash"])
            self.assertEqual(
                {row["cycle_id"] for row in envelope["manifest"]["cycle_artifacts"]},
                {"1"},
            )
            self.assertNotIn(
                str(staged_path.relative_to(source)),
                {row["path"] for row in envelope["manifest"]["cycle_artifacts"]},
            )
            self.assertEqual(
                SignalRegistry(target / "signals").freeze().registry_hash,
                source_registry.freeze().registry_hash,
            )

    def test_historical_controller_output_ceiling_remains_readable(self) -> None:
        raw = make_contract().to_dict()
        raw["limits"]["role_output_tokens"]["controller"] = 2_000
        raw["limits"]["role_output_tokens"]["h1"] = 2_000
        historical = EvolutionRunContract.from_dict(raw)
        self.assertEqual(historical.to_dict()["limits"]["role_output_tokens"]["controller"], 2_000)
        self.assertEqual(historical.to_dict()["limits"]["role_output_tokens"]["h1"], 2_000)
        self.assertEqual(make_contract().limits["role_output_tokens"]["controller"], 8_000)
        self.assertEqual(make_contract().limits["role_output_tokens"]["h1"], 8_000)

    def test_slow_bootstrap_manifest_masks_identity_and_binds_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source_registry = SignalRegistry(source / "signals")
            source_registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            target_registry = SignalRegistry(target / "signals")
            target_registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            snapshot = target_registry.freeze()
            self.assertEqual(source_registry.freeze().registry_hash, snapshot.registry_hash)
            case = evolution_runtime_module.EvolutionCase(
                case_id="case_kgc",
                company_id="issuer_kgc",
                prediction_time=datetime(2025, 9, 30, tzinfo=timezone.utc),
                basic_info={
                    "company_name": "Kinross Gold Corporation",
                    "ticker": "KGC",
                    "identity_aliases": ["Kinross Gold"],
                },
                ground_truth=GroundTruth(2.5),
            )
            dataset = evolution_runtime_module.ApprovedDevelopmentDataset(
                discovery=(),
                anchor=(),
                evolution_validation=(case,),
                locked_test_hash=SHA_B,
                approved_manifest_hash=SHA_A,
            )
            source_contract = EvolutionRunContract(
                **{
                    **make_contract().__dict__,
                    "run_id": "source-run",
                    "initial_signal_registry_version": snapshot.version,
                    "initial_signal_registry_hash": snapshot.registry_hash,
                }
            )
            source.mkdir(parents=True, exist_ok=True)
            source_contract.freeze(source / "run_contract.json")
            write_json(source / "state.json", {"last_completed_round": 0})
            rejected_path = source / "experiments" / "round-0001" / "rejected.json"
            rejected_path.parent.mkdir(parents=True)
            write_json(
                rejected_path,
                {
                    "schema_version": "plan-round-rejected-v1",
                    "round_id": 1,
                    "last_completed_round": 0,
                    "reason": "no fitness-eligible candidate",
                    "attempts": [
                        {
                            "trajectories": [
                                {
                                    "case_id": case.case_id,
                                    "stop_reason": "no_signal_match",
                                    "termination_trigger": "no_signal_match",
                                    "final_state": {
                                        "decision": "continue",
                                        "next_information_needs": [
                                            "What are Kinross Gold's latest analyst estimate revisions?"
                                        ],
                                    },
                                    "prediction": {"is_surge": True},
                                    "ground_truth": {"realized_max_multiple": 2.5},
                                }
                            ]
                        }
                    ],
                },
            )

            manifest_hash = evolution_runtime_module.build_slow_bootstrap_manifest(
                workspace=target,
                source_workspaces=(source,),
                dataset=dataset,
                signal_snapshot=snapshot,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            envelope = json.loads(
                (target / "slow_bootstrap" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            serialized = json.dumps(envelope)
            self.assertIn("[MASKED_COMPANY]", serialized)
            self.assertNotIn("Kinross", serialized)
            self.assertNotIn("case_kgc", serialized)
            self.assertNotIn("ground_truth", serialized)
            self.assertEqual(
                envelope["manifest"]["sources"][0]["rejected_hash"],
                hashlib.sha256(rejected_path.read_bytes()).hexdigest(),
            )
            bootstrap_contract = EvolutionRunContract(
                **{
                    **make_contract().__dict__,
                    "initial_signal_registry_version": snapshot.version,
                    "initial_signal_registry_hash": snapshot.registry_hash,
                    "limits": {
                        **make_contract().limits,
                        "plan_rounds_per_signal_cycle": 0,
                    },
                    "cycle_mode": "slow_bootstrap",
                    "slow_bootstrap_manifest_hash": manifest_hash,
                }
            )
            validated = evolution_runtime_module.validate_slow_bootstrap_manifest(
                workspace=target,
                contract=bootstrap_contract,
                signal_snapshot=snapshot,
            )
            self.assertEqual(validated["schema_version"], "slow-bootstrap-manifest-v1")

    def test_slow_bootstrap_reconstructs_one_committed_fast_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source_registry = SignalRegistry(source / "signals")
            source_registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            target_registry = SignalRegistry(target / "signals")
            target_registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            snapshot = target_registry.freeze()
            source_contract = replace(
                make_contract(),
                run_id="committed-fast-source",
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
            )
            source.mkdir(parents=True, exist_ok=True)
            source_contract.freeze(source / "run_contract.json")
            workspace = EvolutionWorkspace(source)
            workspace.start_or_resume_cycle(
                run_contract_hash=source_contract.contract_hash,
                target_plan_rounds=1,
                cycle_mode="fast_then_slow",
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            selection = SignalSelectionDecision(
                signal_ref="revenue_growth_yoy:v1",
                reason_code="answer_need",
                selection_reason="Measure the answered revenue-growth facet.",
                applicability_hypothesis="Comparable periods are available.",
                expected_role="primary",
                context_tags=("comparable_financials",),
                target_need_indices=(0,),
                answer_scope="partial",
                residual_need="Determine whether growth is durable.",
            )
            signal_result = SignalResult(
                signal_id="revenue_growth_yoy",
                version=1,
                value=SignalValue.POSITIVE,
                confidence=1.0,
                interpretation="Revenue grew year over year.",
                coverage=SignalCoverage.SUFFICIENT,
            )
            final_state = ResearchState(
                decision=ResearchDecision.FINALIZE,
                next_information_needs=(
                    "Determine whether growth remains durable.",
                ),
            )
            trajectory = ExecutionTrajectory(
                case_id="case-1",
                company_id="issuer-1",
                prediction_time=datetime(2025, 1, 15, tzinfo=timezone.utc),
                basic_info={},
                initial_state=final_state,
                signal_rounds=(
                    SignalRound(
                        information_needs=("Measure growth and durability.",),
                        selections=(selection,),
                        batch=SignalBatchResult(
                            results=(signal_result,),
                            signal_calls=1,
                            document_fingerprints={
                                "revenue_growth_yoy:v1": ("doc-hash",)
                            },
                        ),
                    ),
                ),
                final_state=final_state,
                final_context={},
                prediction=BlindPrediction(
                    is_surge=True,
                    candidate_judgment=CandidateJudgment.POSSIBLE,
                    magnitude=MagnitudeClass.TWO_TO_THREE,
                    confidence=ConfidenceLevel.MEDIUM,
                    key_reasons=("Growth is visible.",),
                    uncertainties=(),
                    session_id="session-1",
                ),
                prediction_ref="predictions/case-1.json",
                ground_truth=GroundTruth(2.5),
                self_reflection=PredictionSelfReflection(correct=True),
                stop_reason=RuntimeStopReason.FINALIZED,
                usage=RuntimeUsage(
                    signal_rounds=1,
                    signal_calls=1,
                    model=AgentUsage(),
                ),
            )
            metrics = PlanMetrics(
                binary_precision=1.0,
                binary_recall=1.0,
                binary_f1=1.0,
                magnitude_accuracy=1.0,
                magnitude_macro_f1=1.0,
                true_positive=1,
                false_positive=0,
                true_negative=0,
                false_negative=0,
                sample_count=1,
            )
            plan = default_information_plan()
            record = PlanRecord(
                plan=plan,
                round_id=1,
                embedding=(1.0,),
                metrics=metrics,
                reflection=PlanReflection(
                    successful_patterns=("Revenue evidence was useful.",)
                ),
                signal_usage={"revenue_growth_yoy:v1": {"selected": 1}},
                trajectories=(trajectory,),
            )
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    successful_patterns=("Revenue evidence was useful.",),
                    evidence_refs=(plan.plan_id,),
                ),
                signal_registry_version=snapshot.version,
                signal_registry_hash=snapshot.registry_hash,
                run_contract_hash=source_contract.contract_hash,
            )
            resumed = workspace.start_or_resume_cycle(
                run_contract_hash=source_contract.contract_hash,
                target_plan_rounds=1,
                cycle_mode="fast_then_slow",
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            self.assertEqual(resumed["phase"], "slow_loop")
            dataset = evolution_runtime_module.ApprovedDevelopmentDataset(
                discovery=(),
                anchor=(),
                evolution_validation=(),
                locked_test_hash=SHA_B,
                approved_manifest_hash=SHA_A,
            )

            manifest_hash = evolution_runtime_module.build_slow_bootstrap_manifest(
                workspace=target,
                source_workspaces=(source,),
                dataset=dataset,
                signal_snapshot=snapshot,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            bootstrap_contract = replace(
                make_contract(),
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                limits={
                    **make_contract().limits,
                    "plan_rounds_per_signal_cycle": 0,
                },
                cycle_mode="slow_bootstrap",
                slow_bootstrap_manifest_hash=manifest_hash,
            )
            manifest = evolution_runtime_module.validate_slow_bootstrap_manifest(
                workspace=target,
                contract=bootstrap_contract,
                signal_snapshot=snapshot,
            )
            self.assertEqual(manifest["source_kind"], "committed_fast")
            self.assertEqual(manifest["schema_version"], "slow-bootstrap-manifest-v2")
            self.assertEqual(len(manifest["meta_entries"]), 1)
            self.assertEqual(len(manifest["signal_learning_events"]), 1)
            signal_needs = manifest["capability_backlog_seed"][
                "signal_need_items"
            ]
            self.assertEqual(len(signal_needs), 1)
            self.assertEqual(
                signal_needs[0]["need"],
                "Determine whether growth remains durable.",
            )
            self.assertEqual(signal_needs[0]["source_rounds"], [1])
            self.assertEqual(
                signal_needs[0]["sources"][0]["source_ref"],
                f"{plan.plan_id}:case-1",
            )
            self.assertRegex(
                signal_needs[0]["sources"][0]["source_fingerprint"],
                r"^[0-9a-f]{64}$",
            )
            learning_selection = manifest["signal_learning_events"][0]["selection"]
            self.assertNotIn("answer_scope", learning_selection)
            self.assertNotIn("residual_need", learning_selection)

            for _ in range(2):
                meta_entries = evolution_runtime_module.apply_slow_bootstrap_derivatives(
                    manifest,
                    registry=target_registry,
                )
            self.assertEqual(tuple(entry.round_id for entry in meta_entries), (1,))
            events = target_registry.load_learning_events(
                "revenue_growth_yoy:v1"
            )
            self.assertEqual(len(events), 1)
            self.assertEqual(
                target_registry.load_learning_profile("revenue_growth_yoy:v1")[
                    "unique_observations"
                ],
                1,
            )

    def _seed_candidate(
        self,
        *,
        run_id: str,
        suffix: str,
        binary_f1: float,
        embedding: tuple[float, ...],
        random_prefix: str | None = None,
    ):
        base = default_information_plan()
        plan = InformationPlan(
            plan_id=f"source_{suffix}",
            parent_ids=(),
            basic_info_policy=base.basic_info_policy,
            initial_research_skill=f"{base.initial_research_skill} {suffix}",
            reflection_skill=base.reflection_skill,
            analysis_prompt=base.analysis_prompt,
        )

        def metrics(sample_count: int) -> PlanMetrics:
            return PlanMetrics(
                binary_precision=binary_f1,
                binary_recall=binary_f1,
                binary_f1=binary_f1,
                magnitude_accuracy=0.0,
                magnitude_macro_f1=0.0,
                true_positive=1,
                false_positive=0,
                true_negative=sample_count - 1,
                false_negative=0,
                sample_count=sample_count,
            )

        content_hash = evolution_runtime_module._canonical_hash(
            plan.canonical_dict()
        )
        return evolution_runtime_module.HistoricalPlanSeed(
            source_workspace=run_id,
            source_run_id=run_id,
            source_run_family_id=run_id,
            source_contract_hash=SHA_A,
            source_checkpoint_ref=f"{run_id}/checkpoint.json",
            source_record_hash=SHA_B,
            source_round_id=1,
            source_plan_id=plan.plan_id,
            plan_content_hash=content_hash,
            plan=plan,
            embedding=embedding,
            metrics_by_cohort={
                "anchor": metrics(16),
                "random": metrics(8),
                "combined": metrics(24),
            },
            random_case_ids=tuple(
                f"{random_prefix or run_id}_random_{index}" for index in range(8)
            ),
            source_dataset_snapshot_id=SHA_C,
        )

    def test_historical_seed_selection_requires_source_and_semantic_diversity(self) -> None:
        champion = self._seed_candidate(
            run_id="run-a",
            suffix="champion",
            binary_f1=0.70,
            embedding=(1.0, 0.0),
        )
        same_run = self._seed_candidate(
            run_id="run-a",
            suffix="same-run",
            binary_f1=0.69,
            embedding=(0.0, 1.0),
        )
        near_duplicate = self._seed_candidate(
            run_id="run-c",
            suffix="near-duplicate",
            binary_f1=0.68,
            embedding=(0.999, 0.01),
        )
        diverse = self._seed_candidate(
            run_id="run-b",
            suffix="diverse",
            binary_f1=0.65,
            embedding=(0.0, 1.0),
        )

        selected = evolution_runtime_module._select_historical_plan_seed_candidates(
            (same_run, diverse, near_duplicate, champion)
        )

        self.assertEqual(
            [item.source_plan_id for item in selected],
            [champion.source_plan_id, diverse.source_plan_id],
        )

    def test_historical_seed_selection_underfills_below_quality_floor(self) -> None:
        champion = self._seed_candidate(
            run_id="run-a",
            suffix="champion",
            binary_f1=0.70,
            embedding=(1.0, 0.0),
        )
        weak = self._seed_candidate(
            run_id="run-b",
            suffix="weak",
            binary_f1=0.50,
            embedding=(0.0, 1.0),
        )

        selected = evolution_runtime_module._select_historical_plan_seed_candidates(
            (champion, weak)
        )

        self.assertEqual(selected, (champion,))

    def test_first_workspace_freezes_empty_seed_pool_and_reuses_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "first-run"
            pool = load_or_create_historical_plan_seed_pool(
                workspace=workspace,
                dataset_manifest_hash=SHA_A,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            self.assertEqual(pool.entries, ())
            self.assertTrue((workspace / "seed_pool" / "manifest.json").is_file())

            staged_source = Path(directory) / "staged-run"
            staged_source.mkdir()
            EvolutionRunContract(
                **{**make_contract().__dict__, "run_id": "staged-run"}
            ).freeze(staged_source / "run_contract.json")
            write_json(staged_source / "state.json", {"last_completed_round": 0})
            attempt = staged_source / "experiments" / "round-0001" / "attempts"
            attempt.mkdir(parents=True)
            write_json(attempt / "plan.json", {"metrics": {"binary_f1": 1.0}})

            reused = load_or_create_historical_plan_seed_pool(
                workspace=workspace,
                dataset_manifest_hash=SHA_A,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            self.assertEqual(reused.manifest_hash, pool.manifest_hash)
            self.assertEqual(reused.scanned_workspace_count, 0)

            fresh = build_historical_plan_seed_pool(
                search_root=Path(directory),
                target_workspace=Path(directory) / "second-run",
                dataset_manifest_hash=SHA_A,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            self.assertEqual(fresh.entries, ())
            self.assertEqual(fresh.scanned_workspace_count, 1)
            self.assertEqual(fresh.compatible_workspace_count, 1)

    def test_historical_seed_pool_rejects_manifest_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            pool = HistoricalPlanSeedPool(
                dataset_manifest_hash=SHA_A,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
            )
            pool.freeze(path)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["manifest"]["scan_summary"]["scanned_workspace_count"] = 1
            write_json(path, envelope)
            with self.assertRaisesRegex(ValidationError, "hash mismatch"):
                HistoricalPlanSeedPool.load_frozen(path)

    def test_staged_historical_seed_pool_rejects_currently_invalid_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "target"
            valid_seed = self._seed_candidate(
                run_id="legacy-run",
                suffix="legacy-plan",
                binary_f1=0.70,
                embedding=(1.0, 0.0),
            )
            raw_plan = valid_seed.plan.to_dict()
            raw_plan["basic_info_policy"] = {
                "requests": [
                    {
                        "request_id": "target_news",
                        "description": "Target-company-scoped milestone news.",
                        "source_types": ["company_news"],
                        "lookback_days": 180,
                        "max_documents": 5,
                    },
                    {
                        "request_id": "recent_market_backbone",
                        "description": "Recent point-in-time price and volume.",
                        "source_types": ["market_data"],
                        "lookback_days": 45,
                        "max_documents": 1,
                    },
                ]
            }
            raw_plan["initial_research_skill"] = (
                "Form a hypothesis from the target company's own disclosures and "
                "identify unresolved information needs."
            )
            invalid_plan = InformationPlan.from_dict(raw_plan)
            invalid_seed = replace(
                valid_seed,
                plan=invalid_plan,
                plan_content_hash=evolution_runtime_module._canonical_hash(
                    invalid_plan.canonical_dict()
                ),
            )
            pool = HistoricalPlanSeedPool(
                dataset_manifest_hash=SHA_A,
                evaluation_contract=PlanEvaluationConfig().to_dict(),
                entries=(invalid_seed,),
            )
            pool.freeze(workspace / "seed_pool" / "manifest.json")

            with self.assertRaisesRegex(
                ValidationError,
                "content incompatible with the current proposer contract",
            ):
                load_or_create_historical_plan_seed_pool(
                    workspace=workspace,
                    dataset_manifest_hash=SHA_A,
                    evaluation_contract=PlanEvaluationConfig().to_dict(),
                )

    def test_contract_round_trips_seed_pool_manifest_hash(self) -> None:
        contract = EvolutionRunContract(
            **{**make_contract().__dict__, "seed_pool_manifest_hash": SHA_A}
        )
        value = contract.to_dict()
        self.assertEqual(value["seed_pool_manifest_hash"], SHA_A)
        self.assertEqual(
            EvolutionRunContract.from_dict(value).seed_pool_manifest_hash,
            SHA_A,
        )
        self.assertNotIn("seed_pool_manifest_hash", make_contract().to_dict())

    def test_malformed_paid_json_is_audited_costed_and_not_cached(self) -> None:
        class MalformedClient:
            def complete(self, _messages, **_kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                return ChatResponse(
                    response_id="response-malformed",
                    model="fixture-model",
                    output_text='{"ok":true}\n{"extra":false}',
                    raw={"usage": {"input_tokens": 3, "output_tokens": 2}},
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: MalformedClient(),
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            ledger = ExternalAttemptLedger(
                root / "attempts.json", max_attempts=2, max_total_cost=1.0
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ledger,
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={"FIXTURE_KEY": "test-key"},
            )

            with self.assertRaisesRegex(StructuredOutputInvalid, "invalid structured"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                )

            attempt = json.loads((root / "attempts.json").read_text())["attempts"][0]
            self.assertEqual(attempt["status"], "failed")
            self.assertGreater(attempt["actual_cost"], 0)
            failure_paths = tuple((root / "failed_responses").glob("*.json"))
            self.assertEqual(len(failure_paths), 1)
            failure = json.loads(failure_paths[0].read_text())
            self.assertIn('{"extra":false}', failure["raw_output"])
            self.assertEqual(tuple((root / "cache" / "responses").glob("*.json")), ())

    def test_one_redundant_trailing_brace_is_normalized_and_audited(self) -> None:
        class RedundantBraceClient:
            def complete(self, _messages, **_kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                return ChatResponse(
                    response_id="response-redundant-brace",
                    model="fixture-model",
                    output_text='{"ok":true}}',
                    raw={"usage": {"input_tokens": 3, "output_tokens": 2}},
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: RedundantBraceClient(),
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            ledger = ExternalAttemptLedger(
                root / "attempts.json", max_attempts=2, max_total_cost=1.0
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ledger,
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={"FIXTURE_KEY": "test-key"},
            )

            result, usage = client.complete_json(
                stage="predict",
                system_prompt="Return JSON.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
            )

            self.assertEqual(result, {"ok": True})
            self.assertEqual(usage.llm_calls, 1)
            attempt = json.loads((root / "attempts.json").read_text())["attempts"][0]
            self.assertEqual(attempt["status"], "completed")
            self.assertEqual(tuple((root / "failed_responses").glob("*.json")), ())
            cache_paths = tuple((root / "cache" / "responses").glob("*.json"))
            self.assertEqual(len(cache_paths), 1)
            cache = json.loads(cache_paths[0].read_text())
            self.assertEqual(
                cache["structured_output_normalization"]["kind"],
                "dropped_one_redundant_trailing_closing_brace",
            )
            self.assertRegex(
                cache["structured_output_normalization"]["raw_output_sha256"],
                r"^[0-9a-f]{64}$",
            )

    def test_transport_normalization_rejects_ambiguous_suffixes(self) -> None:
        for raw in (
            '{"ok":true}}}',
            '{"ok":true}]',
            '{"ok":true} trailing text',
            '{"ok":true}{"second":false}',
        ):
            with self.subTest(raw=raw), self.assertRaises(json.JSONDecodeError):
                evolution_runtime_module._parse_json_object_envelope(raw)

    def test_v3_contract_rejects_missing_behavioral_defaults(self) -> None:
        contract = make_contract()
        incomplete_limits = dict(contract.limits)
        incomplete_limits.pop("parent_selection_seed")
        with self.assertRaisesRegex(ValidationError, "parent_selection_seed"):
            EvolutionRunContract(
                **{**contract.__dict__, "limits": incomplete_limits}
            )
        with self.assertRaisesRegex(ValidationError, "code revision"):
            EvolutionRunContract(
                **{**contract.__dict__, "code_revision": ""}
            )

    def test_contract_separates_data_acquisition_from_llm_external_scope(self) -> None:
        contract = EvolutionRunContract(
            **{
                **make_contract().__dict__,
                "data_acquisition": DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("sec_edgar", "alpha_vantage"),
                    allowed_capabilities=("filings", "news"),
                    allowed_source_types=("10-k", "news"),
                    max_requests_per_cycle=10,
                    max_requests_per_run=50,
                ),
            }
        )
        value = contract.to_dict()
        self.assertTrue(value["data_acquisition"]["enabled"])
        self.assertNotIn("allow_external", value["data_acquisition"])
        self.assertIn("initial_signal_registry_hash", value)
        self.assertNotIn("signal_registry_hash", value)
        restored = EvolutionRunContract.from_dict(value)
        self.assertEqual(restored.data_acquisition, contract.data_acquisition)

        legacy_v3 = {
            **value,
            "schema_version": "evolution-run-contract-v3",
            "signal_registry_version": value["initial_signal_registry_version"],
            "signal_registry_hash": value["initial_signal_registry_hash"],
        }
        legacy_v3.pop("initial_signal_registry_version")
        legacy_v3.pop("initial_signal_registry_hash")
        self.assertFalse(EvolutionRunContract.from_dict(legacy_v3).executable)

        legacy = {**value, "schema_version": "evolution-run-contract-v1"}
        legacy.pop("data_acquisition")
        restored_legacy = EvolutionRunContract.from_dict(legacy)
        self.assertFalse(restored_legacy.data_acquisition.enabled)
        self.assertNotIn("data_acquisition", restored_legacy.to_dict())
        self.assertFalse(restored_legacy.executable)
        self.assertTrue(contract.executable)

    def test_runtime_orders_available_price_adapters_by_catalog_priority(self) -> None:
        contract = EvolutionRunContract(
            **{
                **make_contract().__dict__,
                "data_acquisition": DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("massive", "stooq", "alpha_vantage"),
                    allowed_capabilities=("price_daily",),
                    allowed_source_types=("market_data",),
                    max_requests_per_cycle=10,
                    max_requests_per_run=50,
                ),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            resolver = evolution_runtime_module._build_evidence_resolver(
                Path(directory),
                RawInfoStore(),
                contract=contract,
                allow_data_external=True,
                environ={
                    "MASSIVE_API_KEY": "massive-test-key",
                    "STOOQ_API_KEY": "stooq-test-key",
                    "ALPHA_VANTAGE_API_KEY": "alpha-test-key",
                },
                cycle_id=1,
            )

        price_providers = [
            adapter.provider
            for adapter in resolver.adapters
            if "market_data" in adapter.source_types
        ]
        self.assertEqual(
            price_providers,
            ["massive", "stooq", "alpha_vantage"],
        )

    def test_runtime_exposes_authorized_transcript_adapter(self) -> None:
        contract = EvolutionRunContract(
            **{
                **make_contract().__dict__,
                "data_acquisition": DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("alpha_vantage",),
                    allowed_capabilities=("transcripts",),
                    allowed_source_types=("earnings_call",),
                    max_requests_per_cycle=10,
                    max_requests_per_run=50,
                ),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            resolver = evolution_runtime_module._build_evidence_resolver(
                Path(directory),
                RawInfoStore(),
                contract=contract,
                allow_data_external=True,
                environ={"ALPHA_VANTAGE_API_KEY": "alpha-test-key"},
                cycle_id=1,
            )

        self.assertIn("earnings_call", resolver.available_source_types)
        self.assertIn(
            "alpha_vantage",
            [
                adapter.provider
                for adapter in resolver.adapters
                if "earnings_call" in adapter.source_types
            ],
        )

        alpha_adapters = [
            adapter
            for adapter in resolver.adapters
            if adapter.provider == "alpha_vantage"
        ]
        news = next(
            adapter
            for adapter in alpha_adapters
            if isinstance(adapter, AlphaVantageNewsAdapter)
        )
        transcripts = next(
            adapter
            for adapter in alpha_adapters
            if isinstance(adapter, AlphaVantageTranscriptAdapter)
        )
        prices = next(
            adapter
            for adapter in alpha_adapters
            if isinstance(adapter, HistoricalPriceAdapter)
        )
        for client in (news.client, transcripts.client, prices.event_source):
            self.assertIs(
                client.transport.json_error_detector,
                alpha_vantage_json_error,
            )

    def test_frozen_data_policy_stays_disabled_without_invocation_authorization(self) -> None:
        contract = EvolutionRunContract(
            **{
                **make_contract().__dict__,
                "data_acquisition": DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("massive",),
                    allowed_capabilities=("price_daily",),
                    allowed_source_types=("market_data",),
                    max_requests_per_cycle=10,
                    max_requests_per_run=50,
                ),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            resolver = evolution_runtime_module._build_evidence_resolver(
                Path(directory),
                RawInfoStore(),
                contract=contract,
                allow_data_external=False,
                environ={"MASSIVE_API_KEY": "massive-test-key"},
                cycle_id=1,
            )

        self.assertFalse(resolver.policy.enabled)
        self.assertEqual(resolver.policy.allowed_providers, ())
        self.assertEqual(resolver.budget.run_requests, 0)

    def test_enabled_data_contract_pauses_before_snapshot_without_authorization(self) -> None:
        contract = EvolutionRunContract(
            **{
                **make_contract().__dict__,
                "data_acquisition": DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("massive",),
                    allowed_capabilities=("price_daily",),
                    allowed_source_types=("market_data",),
                    max_requests_per_cycle=10,
                    max_requests_per_run=50,
                ),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"

            with self.assertRaises(ExternalExecutionNotReady) as context:
                evolution_runtime_module.run_bounded_evolution_cycle(
                    workspace_path=workspace,
                    raw_info_root=Path(directory) / "raw-info",
                    approved_dataset_manifest=Path(directory) / "dataset.json",
                    contract=contract,
                    allow_external=False,
                    allow_data_external=False,
                )

            self.assertEqual(
                context.exception.status,
                "data_external_approval_required",
            )
            self.assertFalse((workspace / "cycle_state.json").exists())
            self.assertFalse((workspace / "evaluation").exists())

    def test_contract_freeze_is_exact_and_secret_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run_contract.json"
            contract = make_contract()
            contract.freeze(path)
            contract.freeze(path)
            serialized = path.read_text(encoding="utf-8")
            self.assertNotIn("api-key", serialized)
            conflicting = EvolutionRunContract(
                **{**contract.__dict__, "run_id": "other-run"}
            )
            with self.assertRaisesRegex(ValidationError, "conflicting immutable"):
                conflicting.freeze(path)

    def test_attempt_ledger_reserves_before_calls_and_counts_stale_in_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = ExternalAttemptLedger(
                Path(directory) / "attempts.json",
                max_attempts=2,
                max_total_cost=0.5,
            )
            first = ledger.reserve(SHA_A, reserved_cost=0.2)
            self.assertEqual(ledger.summary["in_progress"], 1)
            ledger.finalize(first, status="failed", actual_cost=0.0, error_type="Fixture")
            ledger.reserve(SHA_B, reserved_cost=0.2)
            with self.assertRaisesRegex(ExternalBudgetExhausted, "attempt ceiling"):
                ledger.reserve(SHA_C, reserved_cost=0.01)

    def test_structured_client_preflight_scans_and_never_calls_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: (_ for _ in ()).throw(
                    AssertionError("network client must not be built during preflight")
                ),
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            ledger = ExternalAttemptLedger(
                root / "attempts.json", max_attempts=2, max_total_cost=1.0
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ledger,
                allow_external=False,
                environ={},
            )
            with self.assertRaisesRegex(ValidationError, "outcome field"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"ground_truth": 4.0},
                    allow_outcomes=False,
                )
            with self.assertRaisesRegex(ValidationError, "identity alias"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "AAA has evidence"},
                    allow_outcomes=False,
                    anonymous_aliases=("AAA",),
                )
            with self.assertRaisesRegex(ExternalRequestPending, "requires approval"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "or an artifact with low liquidity"},
                    allow_outcomes=False,
                    anonymous_aliases=("AN", "LOW"),
                )
            with self.assertRaisesRegex(ValidationError, "identity alias"):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "ticker AN identity disclosed"},
                    allow_outcomes=False,
                    anonymous_aliases=("AN",),
                )
            try:
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                    temperature=1.0,
                )
            except ExternalRequestPending as pending:
                self.assertTrue(pending.request_path.is_file())
                request_hash = pending.request_hash
                request_path = pending.request_path
            else:
                self.fail("preview should stop after persisting the exact request")
            self.assertEqual(ledger.summary["attempt_count"], 0)
            request = json.loads(request_path.read_text(encoding="utf-8"))[
                "request"
            ]
            self.assertEqual(request["temperature"], 1.0)
            self.assertEqual(request["response_format"], {"type": "json_object"})
            self.assertIn("JSON", request["messages"][0]["content"])

            ExactResponseCache(root / "cache" / "responses").store(
                request_hash,
                {
                    "json_output": {"ok": True},
                    "usage": {"input_tokens": 3, "output_tokens": 2, "cost": 0.1},
                },
            )
            value, usage = client.complete_json(
                stage="predict",
                system_prompt="Return JSON.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
                temperature=1.0,
            )
            self.assertEqual(value, {"ok": True})
            self.assertEqual(usage.llm_calls, 0)

    def test_request_token_reservation_fails_before_attempt_and_network(self) -> None:
        class NeverCompleteClient:
            called = False

            def complete(self, _messages, **_kwargs):
                self.called = True
                raise AssertionError("token preflight must run before network")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transport = NeverCompleteClient()
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: transport,
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            ledger = ExternalAttemptLedger(
                root / "attempts.json", max_attempts=2, max_total_cost=1.0
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ledger,
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={"FIXTURE_KEY": "test-key"},
            )

            reservation = client.estimate_json_request_tokens(
                system_prompt="Return JSON.",
                payload={"context": "x" * 1_000},
                allow_outcomes=False,
                max_output_tokens=2_000,
            )

            with self.assertRaisesRegex(
                RuntimeBudgetExceeded,
                f"required={reservation}, remaining={reservation - 1}",
            ):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "x" * 1_000},
                    allow_outcomes=False,
                    max_output_tokens=2_000,
                    max_request_tokens=reservation - 1,
                )

            self.assertFalse(transport.called)
            self.assertEqual(ledger.summary["attempt_count"], 0)

    def test_predictor_context_byte_cap_fits_terminal_reserve_on_exact_wire(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests"
                / "fixtures"
                / "evolution_runtime"
                / "v6_predictor_terminal_reserve_overflow.json"
            ).read_text(encoding="utf-8")
        )
        self.assertGreater(fixture["failure"]["required_tokens"], 36_000)
        compact_context = {
            "context_contract": {
                "kind": "bounded_prediction_projection",
                "max_utf8_bytes": 24_000,
                "complete_trajectory_retained_locally": True,
            },
            "basic_info": {"source_index": [], "data_gaps": []},
            "signal_rounds": [],
            "cited_signal_evidence": [],
            "final_research_state": ResearchState(
                decision=ResearchDecision.FINALIZE
            ).to_dict(),
            "analysis_prompt": "a" * 20_000,
        }
        self.assertLessEqual(
            len(
                json.dumps(
                    compact_context,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ),
            24_000,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = StructuredRoleClient(
                registration=get_model("deepseek-v4-flash"),
                contract=make_contract(),
                workspace=root,
                ledger=ExternalAttemptLedger(
                    root / "attempts.json", max_attempts=2, max_total_cost=1.0
                ),
                allow_external=False,
                environ={},
            )
            predictor = LLMBlindPredictor(client)
            predictor.set_request_token_budget(36_000)

            with self.assertRaises(ExternalRequestPending) as pending:
                predictor.predict(compact_context)

            request = json.loads(
                pending.exception.request_path.read_text(encoding="utf-8")
            )["request"]
            self.assertLessEqual(
                request["wire_request"]["body_bytes"]
                + request["max_output_tokens"],
                36_000,
            )

    def test_structured_client_persists_canonical_production_wire_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = StructuredRoleClient(
                registration=get_model("deepseek-v4-flash"),
                contract=make_contract(),
                workspace=root,
                ledger=ExternalAttemptLedger(
                    root / "attempts.json", max_attempts=2, max_total_cost=1.0
                ),
                allow_external=False,
                environ={},
            )
            payload = {"nested": {"b": 2, "a": 1}, "context": "匿名证据"}

            try:
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload=payload,
                    allow_outcomes=False,
                )
            except ExternalRequestPending as pending:
                envelope = json.loads(pending.request_path.read_text(encoding="utf-8"))
            else:
                self.fail("preview should persist an exact production wire request")

            request = envelope["request"]
            self.assertEqual(client.request_hash_trace, [envelope["request_hash"]])
            wire = request["wire_request"]
            body = wire["body_utf8"].encode("utf-8")
            self.assertEqual(wire["body_bytes"], len(body))
            self.assertEqual(wire["body_sha256"], hashlib.sha256(body).hexdigest())
            provider_payload = json.loads(wire["body_utf8"])
            provider_user_text = provider_payload["input"][1]["content"][0]["text"]
            self.assertEqual(provider_user_text, request["messages"][1]["content"])
            self.assertEqual(
                provider_user_text,
                '{"context":"匿名证据","nested":{"a":1,"b":2}}',
            )

    def test_structured_client_rejects_wire_drift_before_attempt_reservation(self) -> None:
        from stock_opportunity_agent.llm.openai import PreparedJsonRequest

        class DriftClient:
            def __init__(self, marker: str) -> None:
                self.marker = marker

            def prepare_request(self, messages, **kwargs):
                return PreparedJsonRequest(
                    "https://api.example.test/responses",
                    {
                        "marker": self.marker,
                        "messages": [message.content for message in messages],
                        "kwargs": dict(kwargs),
                    },
                )

            def complete(self, _messages, **_kwargs):
                raise AssertionError("wire drift must fail before network execution")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration = RegisteredModel(
                alias="drifting-provider",
                provider="openai",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline drift fixture",
                client_factory=lambda settings: DriftClient(
                    "preview" if settings.preview_only else "actual"
                ),
            )
            ledger = ExternalAttemptLedger(
                root / "attempts.json", max_attempts=2, max_total_cost=1.0
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ledger,
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={"FIXTURE_KEY": "test-key"},
            )

            with self.assertRaisesRegex(
                ExternalExecutionNotReady,
                "request bytes changed",
            ):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                )

            self.assertEqual(ledger.summary["attempt_count"], 0)

    def test_missing_api_key_is_control_plane_pause_without_attempt_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: (_ for _ in ()).throw(
                    AssertionError("client must not be built without readiness")
                ),
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            ledger = ExternalAttemptLedger(
                root / "attempts.json", max_attempts=2, max_total_cost=1.0
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ledger,
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={},
            )

            with self.assertRaisesRegex(
                ExternalExecutionNotReady, "API key is unavailable"
            ):
                client.complete_json(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                )

            self.assertEqual(ledger.summary["attempt_count"], 0)

    def test_structured_client_enforces_json_response_format_on_provider_call(self) -> None:
        class RecordingClient:
            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def complete(self, _messages, **kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                self.kwargs = dict(kwargs)
                return ChatResponse(
                    response_id="response-1",
                    model="fixture-model",
                    output_text='{"ok":true}',
                    raw={
                        "usage": {
                            "input_tokens": 3,
                            "output_tokens": 2,
                            "prompt_cache_hit_tokens": 2,
                            "prompt_cache_miss_tokens": 1,
                        }
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording_client = RecordingClient()
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: recording_client,
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ExternalAttemptLedger(
                    root / "attempts.json", max_attempts=2, max_total_cost=1.0
                ),
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={"FIXTURE_KEY": "test-key"},
            )

            value, usage = client.complete_json(
                stage="predict",
                system_prompt="Return JSON.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
            )

            self.assertEqual(value, {"ok": True})
            self.assertEqual(usage.llm_calls, 1)
            self.assertEqual(
                recording_client.kwargs["response_format"],
                {"type": "json_object"},
            )
            cached = json.loads(
                next((root / "cache" / "responses").glob("*.json")).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(cached["usage"]["prompt_cache_hit_tokens"], 2)
            self.assertEqual(cached["usage"]["prompt_cache_miss_tokens"], 1)

    def test_provider_usage_normalizes_responses_cached_tokens(self) -> None:
        usage = evolution_runtime_module._provider_usage_record(
            {
                "input_tokens": 100,
                "output_tokens": 5,
                "input_tokens_details": {"cached_tokens": 64},
            },
            input_tokens=100,
            output_tokens=5,
            cost=0.01,
        )

        self.assertEqual(usage["prompt_cache_hit_tokens"], 64)
        self.assertEqual(usage["prompt_cache_miss_tokens"], 36)

    def test_provider_usage_keeps_conservative_estimate_when_metadata_missing(
        self,
    ) -> None:
        usage = evolution_runtime_module._provider_usage_record(
            {},
            input_tokens=100,
            output_tokens=5,
            cost=0.01,
        )

        self.assertEqual(
            usage,
            {
                "input_tokens": 100,
                "output_tokens": 5,
                "cost": 0.01,
            },
        )

    def test_structured_client_records_optional_binary_token_scores(self) -> None:
        class RecordingClient:
            supports_token_logprobs = True

            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def complete(self, _messages, **kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                self.kwargs = dict(kwargs)
                return ChatResponse(
                    response_id="response-logprobs",
                    model="fixture-model",
                    output_text='{"decision":"YES"}',
                    raw={
                        "choices": [
                            {
                                "logprobs": {
                                    "content": [
                                        {
                                            "token": '"YES"',
                                            "logprob": math.log(0.6),
                                            "top_logprobs": [
                                                {
                                                    "token": '"YES"',
                                                    "logprob": math.log(0.6),
                                                },
                                                {
                                                    "token": '"NO"',
                                                    "logprob": math.log(0.3),
                                                },
                                            ],
                                        }
                                    ]
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording_client = RecordingClient()
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: recording_client,
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ExternalAttemptLedger(
                    root / "attempts.json", max_attempts=2, max_total_cost=1.0
                ),
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={"FIXTURE_KEY": "test-key"},
            )

            value, usage, scores = client.complete_json_with_token_scores(
                stage="predict",
                system_prompt="Return JSON.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
                decision_field="decision",
                decision_tokens=("YES", "NO"),
            )

            self.assertEqual(value, {"decision": "YES"})
            self.assertEqual(usage.llm_calls, 1)
            self.assertIsNotNone(scores)
            assert scores is not None
            self.assertAlmostEqual(scores.yes_token_probability, 0.6)
            self.assertAlmostEqual(scores.no_token_probability, 0.3)
            self.assertAlmostEqual(scores.decision_margin, 2 / 3)
            self.assertTrue(recording_client.kwargs["logprobs"])
            self.assertEqual(recording_client.kwargs["top_logprobs"], 20)

            _value, cached_usage, cached_scores = (
                client.complete_json_with_token_scores(
                    stage="predict",
                    system_prompt="Return JSON.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                    decision_field="decision",
                    decision_tokens=("YES", "NO"),
                )
            )
            self.assertEqual(cached_usage.llm_calls, 0)
            self.assertEqual(cached_scores, scores)

    def test_structured_client_scores_exact_canonical_binary_token(self) -> None:
        class RecordingClient:
            supports_token_logprobs = True

            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def complete(self, _messages, **kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                self.kwargs = dict(kwargs)
                return ChatResponse(
                    response_id="response-binary-token",
                    model="fixture-model",
                    output_text="NO",
                    raw={
                        "choices": [
                            {
                                "logprobs": {
                                    "content": [
                                        {
                                            "token": "NO",
                                            "logprob": -0.2,
                                            "top_logprobs": [
                                                {"token": "NO", "logprob": -0.2},
                                                {"token": "No", "logprob": -9999.0},
                                                {"token": "YES", "logprob": -1.7},
                                                {"token": "yes", "logprob": -9999.0},
                                            ],
                                        }
                                    ]
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording_client = RecordingClient()
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: recording_client,
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ExternalAttemptLedger(
                    root / "attempts.json", max_attempts=2, max_total_cost=1.0
                ),
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={"FIXTURE_KEY": "test-key"},
            )

            token, usage, scores = client.complete_binary_token_with_scores(
                stage="blind_predictor_score",
                system_prompt="Return exactly YES or NO.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
                decision_field="decision",
                decision_tokens=("YES", "NO"),
                temperature=1.0,
            )

            self.assertEqual(token, "NO")
            self.assertEqual(usage.llm_calls, 1)
            self.assertIsNotNone(scores)
            assert scores is not None
            self.assertAlmostEqual(scores.yes_token_probability, math.exp(-1.7))
            self.assertAlmostEqual(scores.no_token_probability, math.exp(-0.2))
            self.assertAlmostEqual(
                scores.decision_margin,
                1.0 / (1.0 + math.exp(1.5)),
            )
            self.assertNotIn("response_format", recording_client.kwargs)

    def test_binary_token_scores_reject_provider_sentinel(self) -> None:
        raw = {
            "choices": [
                {
                    "logprobs": {
                        "content": [
                            {
                                "token": "NO",
                                "logprob": 0.0,
                                "top_logprobs": [
                                    {"token": "NO", "logprob": 0.0},
                                    {"token": "YES", "logprob": -9999.0},
                                ],
                            }
                        ]
                    }
                }
            ]
        }

        scores = evolution_runtime_module._extract_decision_token_scores(
            raw,
            parsed={"decision": "NO"},
            decision_field="decision",
            decision_tokens=("YES", "NO"),
        )

        self.assertIsNone(scores)

    def test_structured_client_degrades_when_provider_has_no_logprobs(self) -> None:
        class RecordingClient:
            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def complete(self, _messages, **kwargs):
                from stock_opportunity_agent.llm.openai import ChatResponse

                self.kwargs = dict(kwargs)
                return ChatResponse(
                    response_id="response-no-logprobs",
                    model="fixture-model",
                    output_text='{"decision":"NO"}',
                    raw={"usage": {"input_tokens": 3, "output_tokens": 2}},
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording_client = RecordingClient()
            registration = RegisteredModel(
                alias="fixture-judge",
                provider="fixture",
                model="fixture-model",
                roles=("judge",),
                api_key_env_var="FIXTURE_KEY",
                description="offline fixture",
                client_factory=lambda _settings: recording_client,
                default_input_cost_per_million_tokens=1.0,
                default_output_cost_per_million_tokens=1.0,
            )
            client = StructuredRoleClient(
                registration=registration,
                contract=make_contract(),
                workspace=root,
                ledger=ExternalAttemptLedger(
                    root / "attempts.json", max_attempts=2, max_total_cost=1.0
                ),
                allow_external=True,
                acknowledged_contract_hash=make_contract().contract_hash,
                environ={"FIXTURE_KEY": "test-key"},
            )

            value, _usage, scores = client.complete_json_with_token_scores(
                stage="predict",
                system_prompt="Return JSON.",
                payload={"context": "anonymous evidence"},
                allow_outcomes=False,
                decision_field="decision",
                decision_tokens=("YES", "NO"),
            )

            self.assertEqual(value, {"decision": "NO"})
            self.assertIsNone(scores)
            self.assertNotIn("logprobs", recording_client.kwargs)
            self.assertNotIn("top_logprobs", recording_client.kwargs)

            token, binary_usage, binary_scores = (
                client.complete_binary_token_with_scores(
                    stage="blind_predictor_score",
                    system_prompt="Return exactly YES or NO.",
                    payload={"context": "anonymous evidence"},
                    allow_outcomes=False,
                    decision_field="decision",
                    decision_tokens=("YES", "NO"),
                    temperature=1.0,
                )
            )
            self.assertEqual(token, "")
            self.assertEqual(binary_usage.llm_calls, 0)
            self.assertIsNone(binary_scores)
