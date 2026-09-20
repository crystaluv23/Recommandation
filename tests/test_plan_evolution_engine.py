"""Plan archive, workspace recovery, and Fast-loop engine tests."""

from tests.scheme_evolution_test_support import *  # noqa: F403


class PlanArchiveAndWorkspaceTests(TestCase):
    def test_slow_only_cumulative_limit_survives_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            snapshot = registry.freeze()
            workspace = EvolutionWorkspace(root / "workspace")
            cycle = workspace.start_or_resume_cycle(
                run_contract_hash="contract",
                target_plan_rounds=0,
                cycle_mode="slow_only",
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
                max_slow_cycles=1,
            )
            result = {
                "input_registry_version": snapshot.version,
                "input_registry_hash": snapshot.registry_hash,
                "output_registry_version": snapshot.version,
                "output_registry_hash": snapshot.registry_hash,
            }
            workspace.stage_slow_result(cycle_id=1, result=result)
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )

            with self.assertRaisesRegex(ValidationError, "cumulative cycle limit"):
                workspace.start_or_resume_cycle(
                    run_contract_hash="contract",
                    target_plan_rounds=0,
                    cycle_mode="slow_only",
                    initial_signal_registry_version=snapshot.version,
                    initial_signal_registry_hash=snapshot.registry_hash,
                    observed_signal_registry_version=snapshot.version,
                    observed_signal_registry_hash=snapshot.registry_hash,
                    max_slow_cycles=1,
                )

    def test_meta_model_view_keeps_every_complete_round_even_over_48k(self) -> None:
        memory = PlanMetaMemory(
            entries=tuple(
                RoundMetaEntry(
                    round_id=round_id,
                    successful_patterns=("x" * 10_000,),
                    failed_patterns=("y" * 10_000,),
                    search_implications=("z" * 10_000,),
                    evidence_refs=(f"plan_{round_id}",),
                )
                for round_id in range(1, 11)
            )
        )

        view = memory.model_view()

        self.assertEqual([item["round_id"] for item in view], list(range(1, 11)))
        self.assertEqual(view, tuple(entry.to_dict() for entry in memory.entries))
        self.assertGreater(
            len(json.dumps(view, ensure_ascii=False, sort_keys=True)), 48_000
        )

    def test_meta_view_keeps_all_whole_items_without_sampling(self) -> None:
        first = "A long complete reflection. " * 100
        second = "Another complete reflection. " * 100
        memory = PlanMetaMemory(entries=(RoundMetaEntry(
            round_id=1, successful_patterns=(first, second), evidence_refs=("plan_1",),
        ),))
        view = memory.model_view(max_chars=4000)[0]
        self.assertEqual(
            view["plan_level"]["successful_patterns"], [first, second]
        )
        self.assertEqual(memory._entries[0].successful_patterns, (first, second))

    def test_meta_model_view_keeps_every_original_case_reflection(self) -> None:
        def prediction(judgment: CandidateJudgment) -> BlindPrediction:
            positive = judgment in {
                CandidateJudgment.LIKELY,
                CandidateJudgment.POSSIBLE,
            }
            return BlindPrediction(
                is_surge=positive,
                candidate_judgment=judgment,
                magnitude=(MagnitudeClass.TWO_TO_THREE if positive else None),
                confidence=ConfidenceLevel.LOW,
                key_reasons=("fixture",),
                uncertainties=(),
                session_id="anonymous-session",
            )

        false_negative = prediction(CandidateJudgment.UNLIKELY)
        false_positive = prediction(CandidateJudgment.POSSIBLE)
        correct_negative = prediction(CandidateJudgment.UNLIKELY)
        reflections = (
            CaseReflectionEvidence(
                1,
                RuntimeStopReason.FINALIZED,
                None,
                candidate_judgment_feedback(false_negative, GroundTruth(2.2)),
                PredictionSelfReflection(correct=False),
            ),
            CaseReflectionEvidence(
                2,
                RuntimeStopReason.FINALIZED,
                None,
                candidate_judgment_feedback(false_negative, GroundTruth(2.2)),
                PredictionSelfReflection(
                    correct=False,
                    why_prediction_failed=(
                        "Concrete catalyst evidence was underweighted.",
                    ),
                    ignored_evidence=("Binding customer order was ignored.",),
                ),
            ),
            CaseReflectionEvidence(
                3,
                RuntimeStopReason.FINALIZED,
                None,
                candidate_judgment_feedback(false_positive, GroundTruth(1.2)),
                PredictionSelfReflection(
                    correct=False,
                    why_prediction_failed=("Narrative news was overweighted.",),
                ),
            ),
            CaseReflectionEvidence(
                4,
                RuntimeStopReason.FINALIZED,
                None,
                candidate_judgment_feedback(correct_negative, GroundTruth(1.2)),
                PredictionSelfReflection(
                    correct=True,
                    missing_information=("No forward guidance was available.",),
                ),
            ),
        )
        metrics = PlanMetrics(
            binary_precision=0.0,
            binary_recall=0.0,
            binary_f1=0.0,
            magnitude_accuracy=0.0,
            magnitude_macro_f1=0.0,
            true_positive=0,
            false_positive=1,
            true_negative=1,
            false_negative=2,
            sample_count=4,
        )
        plan_reflection = PlanMetaReflection(
            plan=default_information_plan(),
            metrics=metrics,
            metrics_by_cohort={},
            evaluation_snapshot_ids=(),
            fitness=FitnessEligibility(
                eligible=True,
                reasons=(),
                expected_case_count=4,
                valid_case_count=4,
                evidence_covered_count=4,
                predicted_positive_count=1,
                true_positive_count=0,
            ),
            signal_usage={},
            original_case_reflections=reflections,
            vertical_plan_reflection=PlanReflection(),
        )
        memory = PlanMetaMemory(
            entries=(
                RoundMetaEntry(
                    round_id=1,
                    plan_reflections=(plan_reflection,),
                    evidence_refs=(plan_reflection.plan_id,),
                ),
            )
        )

        cases = memory.model_view()[0]["plan_reflections"][0][
            "original_case_reflections"
        ]
        self.assertEqual([item["case_index"] for item in cases], [1, 2, 3, 4])
        severe = cases[1]
        self.assertEqual(
            severe["self_reflection"]["why_prediction_failed"],
            ["Concrete catalyst evidence was underweighted."],
        )

    def test_durable_attempt_trajectories_do_not_become_formal_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            trajectory = replace(
                make_trajectory("issuer_gap", 1.2, False, None),
                basic_info={
                    "requests": [
                        {
                            "data_gap": {
                                "request_id": "recent_news",
                                "reason": "adapter_missing",
                                "message": "missing",
                                "source_types": ["news"],
                                "provider": None,
                            }
                        }
                    ]
                },
            )
            attempt = PlanEvaluationAttempt(
                plan=default_information_plan(),
                expected_case_ids=(trajectory.case_id,),
                trajectories=(trajectory,),
            )

            path = workspace.stage_evaluation_attempt(
                round_id=1,
                attempt=attempt,
                available_source_types=("news",),
            )

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["trajectories"][0]["case_id"], trajectory.case_id)
            backlog = json.loads(
                (workspace.root / "capability_backlog.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(backlog["items"], [])
            self.assertEqual(backlog["signal_need_items"], [])

    def test_committed_backlog_retains_all_118_needs_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            needs = tuple(f"Investigate unresolved item {index}" for index in range(118))
            trajectory = replace(
                make_trajectory(
                    "issuer_needs", 2.5, True, MagnitudeClass.TWO_TO_THREE
                ),
                final_state=ResearchState(
                    decision=ResearchDecision.FINALIZE,
                    next_information_needs=needs,
                ),
                stop_reason=RuntimeStopReason.NO_SIGNAL_MATCH,
            )
            record = replace(
                make_record("plan_needs", 1.0, (1.0, 0.0)),
                trajectories=(trajectory,),
                evaluation=None,
                fitness=None,
            )
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=RoundMetaEntry(
                    round_id=1, evidence_refs=(record.plan_id,)
                ),
                signal_registry_version=1,
                signal_registry_hash="registry-hash",
            )

            workspace.refresh_capability_backlog()
            backlog = json.loads(
                (workspace.root / "capability_backlog.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(backlog["schema_version"], "capability-gap-report-v3")
            self.assertEqual(len(backlog["signal_need_items"]), 118)
            self.assertEqual(
                {item["sources"][0]["stop_reason"] for item in backlog["signal_need_items"]},
                {"no_signal_match"},
            )
            self.assertTrue(
                all(item["source_rounds"] == [1] for item in backlog["signal_need_items"])
            )

    def test_quality_diverse_topk_then_random_exploration(self) -> None:
        archive = PlanArchive(
            (
                make_record("plan_a", 0.90, (1.0, 0.0)),
                make_record("plan_b", 0.80, (0.99, 0.01)),
                make_record("plan_c", 0.70, (0.0, 1.0)),
                make_record("plan_d", 0.60, (-1.0, 0.0)),
            )
        )
        selection = archive.select_parents(
            top_k=2,
            random_k=1,
            similarity_threshold=0.95,
            rng=random.Random(7),
        )
        self.assertEqual([record.plan_id for record in selection.top], ["plan_a", "plan_c"])
        self.assertEqual(len(selection.random), 1)
        self.assertNotIn(selection.random[0].plan_id, {"plan_a", "plan_c"})

    def test_workspace_restores_only_records_reachable_from_completed_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            record = make_record("plan_committed", 0.8, (1.0, 0.0), round_id=1)
            meta = RoundMetaEntry(
                round_id=1,
                successful_patterns=("evidence weighting",),
                evidence_refs=("plan_committed",),
            )
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=meta,
                signal_registry_version=1,
                signal_registry_hash="registry-hash",
            )
            staged = make_record("plan_staged", 0.9, (0.0, 1.0), round_id=2)
            staged_path = Path(directory) / "plans" / "plan_staged" / "record.json"
            staged_path.parent.mkdir(parents=True)
            staged_path.write_text(json.dumps(staged.to_dict()), encoding="utf-8")
            self.assertEqual(workspace.last_completed_round, 1)
            self.assertEqual(
                [record.plan_id for record in workspace.restore_archive().records],
                ["plan_committed"],
            )
            self.assertEqual(
                [entry.round_id for entry in workspace.restore_meta().entries],
                [1],
            )

    def test_workspace_rejects_checkpoint_record_cross_link_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            record = make_record("plan_committed", 0.8, (1.0, 0.0), round_id=1)
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=("plan_committed",),
                ),
                signal_registry_version=1,
                signal_registry_hash="registry-hash",
            )
            record_path = workspace.plans_root / "plan_committed" / "record.json"
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            payload["round_id"] = 2
            record_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValidationError, "cross-links"):
                workspace.restore_archive()

    def test_workspace_accepts_equivalent_checkpoint_path_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            record = make_record("plan_committed", 0.8, (1.0, 0.0), round_id=1)
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=("plan_committed",),
                ),
                signal_registry_version=1,
                signal_registry_hash="registry-hash",
            )
            state = json.loads(workspace.state_path.read_text(encoding="utf-8"))
            checkpoint_path = Path(state["checkpoint_ref"])
            state["checkpoint_ref"] = str(
                checkpoint_path.parent
                / ".."
                / checkpoint_path.parent.name
                / checkpoint_path.name
            )
            workspace.state_path.write_text(json.dumps(state), encoding="utf-8")

            self.assertEqual(
                [item.plan_id for item in workspace.restore_archive().records],
                ["plan_committed"],
            )

    def test_round_commit_reuses_only_exact_crash_staged_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            record = make_record("plan_recovered", 0.8, (1.0, 0.0), round_id=1)
            meta = RoundMetaEntry(round_id=1, evidence_refs=("plan_recovered",))
            staged_path = workspace.plans_root / "plan_recovered" / "record.json"
            staged_path.parent.mkdir(parents=True)
            staged_path.write_text(json.dumps(record.to_dict()), encoding="utf-8")
            workspace.commit_round(
                round_id=1,
                records=(record,),
                meta_entry=meta,
                signal_registry_version=1,
                signal_registry_hash="registry-hash",
            )
            self.assertEqual(workspace.last_completed_round, 1)

        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            record = make_record("plan_conflict", 0.8, (1.0, 0.0), round_id=1)
            meta = RoundMetaEntry(round_id=1, evidence_refs=("plan_conflict",))
            staged_path = workspace.plans_root / "plan_conflict" / "record.json"
            staged_path.parent.mkdir(parents=True)
            staged_path.write_text('{"wrong": true}', encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "conflicting staged"):
                workspace.commit_round(
                    round_id=1,
                    records=(record,),
                    meta_entry=meta,
                    signal_registry_version=1,
                    signal_registry_hash="registry-hash",
                )
            self.assertEqual(workspace.last_completed_round, 0)

    def test_meta_memory_is_fifo_and_requires_monotonic_grounded_entries(self) -> None:
        memory = PlanMetaMemory(maxlen=2)
        plan_reflection = PlanMetaReflection.from_record(
            make_record("plan_meta_fifo", 0.8, (1.0, 0.0))
        )
        for round_id in (1, 2, 3):
            memory.append(
                RoundMetaEntry(
                    round_id=round_id,
                    plan_reflections=(plan_reflection,),
                    evidence_refs=(plan_reflection.plan_id,),
                )
            )
        self.assertEqual([entry.round_id for entry in memory.entries], [2, 3])
        self.assertTrue(
            all(
                entry.plan_reflections == (plan_reflection,)
                for entry in memory.entries
            )
        )
        with self.assertRaisesRegex(ValidationError, "monotonically"):
            memory.append(
                RoundMetaEntry(
                    round_id=3,
                    evidence_refs=("plan_meta_fifo",),
                )
            )

    def test_imported_history_prefix_survives_multi_round_commit_restart_cycles(
        self,
    ) -> None:
        """Replay the successor control-layer construction across three rounds.

        Mirrors the production sequence that crashed V129: an imported
        slow-history meta prefix, a local round commit, process restarts that
        rebuild meta memory from durable state, and further commits. The
        rebased negative prefix must never collide with local round ids, the
        proposer must see prior-round reflections each round, and definition-
        only registry stats must initialize lazily on first observation.
        """
        from stock_opportunity_agent.research.evolution_control import (
            _rebased_history_meta_entries,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_root = root / "signals"
            registry = SignalRegistry(registry_root)
            registry.install_catalog(SEED_CATALOG)
            for stats_path in registry_root.rglob("stats.json"):
                stats_path.unlink()
            workspace = EvolutionWorkspace(root / "workspace")
            imported = RoundMetaEntry(
                round_id=1,
                evidence_refs=("imported-plan",),
                missing_capabilities=("Imported unresolved Fast need.",),
            )
            proposers: list[CountingProposer] = []
            plan_counter = [0]

            class UniqueCountingProposer(CountingProposer):
                def propose(
                    self,
                    *,
                    round_id,
                    candidate_index,
                    candidate_count,
                    proposal_attempt,
                    forbidden_plan_ids,
                    parents,
                    meta_info,
                    prior,
                ):
                    self.calls.append(
                        {
                            "round_id": round_id,
                            "candidate_index": candidate_index,
                            "candidate_count": candidate_count,
                            "proposal_attempt": proposal_attempt,
                            "forbidden_plan_ids": forbidden_plan_ids,
                            "parents": tuple(
                                plan.plan_id for plan in parents
                            ),
                            "meta_rounds": tuple(
                                entry.round_id for entry in meta_info
                            ),
                            "prior": prior,
                        }
                    )
                    plan_counter[0] += 1
                    base = default_information_plan()
                    return InformationPlan(
                        plan_id=f"plan_child_{plan_counter[0]}",
                        parent_ids=tuple(
                            plan.plan_id for plan in parents
                        ),
                        basic_info_policy=base.basic_info_policy,
                        initial_research_skill=(
                            f"{base.initial_research_skill} Variant "
                            f"{plan_counter[0]}."
                        ),
                        reflection_skill=base.reflection_skill,
                        analysis_prompt=base.analysis_prompt,
                    )

            def build_engine() -> PlanEvolutionEngine:
                local_meta = workspace.restore_meta()
                imports = _rebased_history_meta_entries((imported,))
                proposers.append(UniqueCountingProposer())
                return PlanEvolutionEngine(
                    archive=workspace.restore_archive(),
                    meta_memory=PlanMetaMemory(
                        entries=(*imports, *local_meta.entries)
                    ),
                    signal_registry=registry,
                    evaluator=SyntheticPlanEvaluator(),
                    proposer=proposers[-1],
                    critic=SimpleCritic(),
                    round_reflector=SimpleRoundReflector(),
                    workspace=workspace,
                    seed_plans=(default_information_plan(),),
                    candidates_per_round=1,
                )

            events_after_rounds = []
            for round_id in (1, 2, 3):
                build_engine().run_round(
                    round_id=round_id,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )
                self.assertEqual(workspace.last_completed_round, round_id)
                events_after_rounds.append(
                    len(registry.load_learning_events("revenue_growth_yoy:v1"))
                )

            self.assertEqual(
                [entry.round_id for entry in workspace.restore_meta().entries],
                [1, 2, 3],
            )
            self.assertTrue(
                (registry_root / "financial" / "revenue_growth_yoy" / "stats.json")
                .exists()
            )
            self.assertEqual(
                events_after_rounds[0] > 0,
                True,
            )
            self.assertGreater(events_after_rounds[2], events_after_rounds[0])
            self.assertEqual(
                proposers[0].calls[0]["meta_rounds"], (-1,)
            )
            self.assertEqual(
                proposers[1].calls[0]["meta_rounds"], (-1, 1)
            )
            self.assertEqual(
                proposers[2].calls[0]["meta_rounds"], (-1, 1, 2)
            )

    def test_rebased_prefix_evicts_first_and_serializes_for_consumers(self) -> None:
        """FIFO recency and model-view serialization for the rebased prefix."""
        from stock_opportunity_agent.research.evolution_control import (
            _rebased_history_meta_entries,
        )

        imported = tuple(
            RoundMetaEntry(
                round_id=round_id,
                evidence_refs=(f"imported-plan-{round_id}",),
                missing_capabilities=(f"Imported need {round_id}.",),
            )
            for round_id in (1, 2)
        )
        rebased = _rebased_history_meta_entries(imported)
        self.assertEqual([entry.round_id for entry in rebased], [-2, -1])
        memory = PlanMetaMemory(maxlen=3, entries=rebased)
        for round_id in (1, 2, 3):
            memory.append(
                RoundMetaEntry(round_id=round_id, evidence_refs=(f"p{round_id}",))
            )
        self.assertEqual(
            [entry.round_id for entry in memory.entries], [1, 2, 3]
        )
        # The proposer-context projection (evolution_plan_roles) consumes the
        # combined list through the same model_view and must serialize the
        # reserved negative ids without assertions.
        combined = (*rebased, *memory.entries)
        view = PlanMetaMemory(
            maxlen=max(1, len(combined)), entries=combined
        ).model_view()
        self.assertEqual(
            [row["round_id"] for row in view], [-2, -1, 1, 2, 3]
        )

    def test_additive_round_meta_round_trips_and_reads_legacy_horizontal_only(
        self,
    ) -> None:
        record = make_record("plan_meta_roundtrip", 0.8, (1.0, 0.0))
        plan_reflection = PlanMetaReflection.from_record(record)
        entry = RoundMetaEntry(
            round_id=1,
            successful_patterns=("preserve exact evidence",),
            search_implications=("restore annual filings",),
            evidence_refs=(record.plan_id,),
        ).append_plan_reflections((plan_reflection,))

        serialized = entry.to_dict()
        restored = RoundMetaEntry.from_dict(serialized)

        self.assertEqual(restored, entry)
        self.assertEqual(
            restored.plan_reflections[0].original_case_reflections[0].self_reflection,
            record.trajectories[0].self_reflection,
        )
        self.assertEqual(
            restored.plan_reflections[0].vertical_plan_reflection,
            record.reflection,
        )
        rendered = json.dumps(serialized)
        self.assertNotIn('"case_id"', rendered)
        self.assertNotIn('"company_id"', rendered)
        self.assertNotIn('"final_context"', rendered)
        legacy = dict(serialized)
        legacy.pop("plan_reflections")
        self.assertEqual(
            RoundMetaEntry.from_dict(legacy).plan_reflections,
            (),
        )

        unsafe_case = plan_reflection.original_case_reflections[0].to_dict()
        unsafe_case["company_id"] = "must-not-persist"
        with self.assertRaisesRegex(ValidationError, "fields are invalid"):
            CaseReflectionEvidence.from_dict(unsafe_case)

    def test_cycle_state_and_debug_events_resume_from_committed_round_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            started = workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=2,
                initial_signal_registry_version=1,
                initial_signal_registry_hash="registry-hash-v1",
                observed_signal_registry_version=1,
                observed_signal_registry_hash="registry-hash-v1",
            )
            self.assertFalse(started["resumed"])
            self.assertEqual(started["completed_plan_rounds"], 0)
            first_event = workspace.append_event(
                "cycle_started",
                {"cycle_id": 1, "sequence": 99, "event_type": "spoofed"},
            )
            self.assertEqual(first_event["sequence"], 1)
            self.assertEqual(first_event["event_type"], "cycle_started")
            with workspace.trajectory_events_path.open("ab") as handle:
                handle.write(b'{"truncated":')
            recovered_event = EvolutionWorkspace(directory).append_event(
                "recovered_after_truncated_log",
            )
            self.assertEqual(recovered_event["sequence"], 2)

            for round_id in (1, 2):
                plan_id = f"plan_cycle_{round_id}"
                workspace.commit_round(
                    round_id=round_id,
                    records=(
                        make_record(
                            plan_id,
                            0.5 + round_id / 10,
                            (1.0, float(round_id)),
                            round_id=round_id,
                        ),
                    ),
                    meta_entry=RoundMetaEntry(
                        round_id=round_id,
                        evidence_refs=(plan_id,),
                    ),
                    signal_registry_version=1,
                    signal_registry_hash="registry-hash",
                    run_contract_hash="contract-hash",
                )
                resumed = EvolutionWorkspace(directory).start_or_resume_cycle(
                    run_contract_hash="contract-hash",
                    target_plan_rounds=2,
                    initial_signal_registry_version=1,
                    initial_signal_registry_hash="registry-hash-v1",
                    observed_signal_registry_version=1,
                    observed_signal_registry_hash="registry-hash-v1",
                )
                self.assertEqual(resumed["completed_plan_rounds"], round_id)

            workspace = EvolutionWorkspace(directory)
            self.assertEqual(
                [event["event_type"] for event in workspace.load_events()],
                ["cycle_started", "recovered_after_truncated_log"],
            )
            validation = {
                "mined_candidates": [],
                "updated_candidates": [],
                "validated_candidates": {},
                "rejected": {},
                "input_registry_version": 1,
                "input_registry_hash": "registry-hash-v1",
                "input_signal_refs": ["fixture:v1"],
            }
            workspace.stage_slow_validation(cycle_id=1, validation=validation)
            result = {
                **validation,
                "promoted": [],
                "output_registry_version": 1,
                "output_registry_hash": "registry-hash-v1",
            }
            staged = workspace.stage_slow_result(
                cycle_id=1,
                result=result,
            )
            self.assertTrue(staged.is_file())
            self.assertEqual(
                workspace.staged_slow_result(1),
                result,
            )
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=1,
                observed_signal_registry_hash="registry-hash-v1",
            )
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=1,
                observed_signal_registry_hash="registry-hash-v1",
            )
            self.assertEqual(workspace.last_completed_cycle, 1)
            self.assertIsNone(
                json.loads(workspace.cycle_state_path.read_text())["active_cycle"]
            )

    def test_cycle_pointer_recovers_fault_before_or_after_atomic_replace(self) -> None:
        for fault_stage in ("before_cycle_pointer", "after_cycle_pointer"):
            with self.subTest(fault_stage=fault_stage), tempfile.TemporaryDirectory() as directory:
                workspace = EvolutionWorkspace(directory)
                workspace.start_or_resume_cycle(
                    run_contract_hash="contract-hash",
                    target_plan_rounds=1,
                    initial_signal_registry_version=1,
                    initial_signal_registry_hash="registry-hash-v1",
                    observed_signal_registry_version=1,
                    observed_signal_registry_hash="registry-hash-v1",
                )
                record = make_record(
                    "cycle_pointer_plan",
                    0.6,
                    (1.0, 0.0),
                    round_id=1,
                )
                workspace.commit_round(
                    round_id=1,
                    records=(record,),
                    meta_entry=RoundMetaEntry(
                        round_id=1,
                        evidence_refs=(record.plan_id,),
                    ),
                    signal_registry_version=1,
                    signal_registry_hash="registry-hash-v1",
                    run_contract_hash="contract-hash",
                )
                workspace.stage_slow_result(
                    cycle_id=1,
                    result={
                        "input_registry_version": 1,
                        "input_registry_hash": "registry-hash-v1",
                        "output_registry_version": 1,
                        "output_registry_hash": "registry-hash-v1",
                    },
                )

                def inject(stage):
                    if stage == fault_stage:
                        raise RuntimeError(f"fault at {fault_stage}")

                workspace._fault_injector = inject
                with self.assertRaisesRegex(RuntimeError, "fault at"):
                    workspace.complete_cycle(
                        cycle_id=1,
                        observed_signal_registry_version=1,
                        observed_signal_registry_hash="registry-hash-v1",
                    )
                workspace._fault_injector = None
                workspace.complete_cycle(
                    cycle_id=1,
                    observed_signal_registry_version=1,
                    observed_signal_registry_hash="registry-hash-v1",
                )
                self.assertEqual(workspace.last_completed_cycle, 1)

    def test_workspace_execution_lock_rejects_concurrent_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            with workspace.execution_lock():
                with self.assertRaisesRegex(ValidationError, "active cycle executor"):
                    with EvolutionWorkspace(directory).execution_lock():
                        self.fail("concurrent workspace lock unexpectedly succeeded")
            with EvolutionWorkspace(directory).execution_lock():
                pass


class PlanEvolutionEngineTests(TestCase):
    def test_parent_comparison_only_deltas_metrics_on_exact_snapshot(self) -> None:
        def metrics(tp: int, fp: int, tn: int, fn: int) -> PlanMetrics:
            precision = tp / (tp + fp)
            recall = tp / (tp + fn)
            return PlanMetrics(
                binary_precision=precision,
                binary_recall=recall,
                binary_f1=2 * precision * recall / (precision + recall),
                magnitude_accuracy=0.0,
                magnitude_macro_f1=0.0,
                true_positive=tp,
                false_positive=fp,
                true_negative=tn,
                false_negative=fn,
                sample_count=tp + fp + tn + fn,
            )

        base = default_information_plan()
        parent_plan = replace(base, plan_id="parent_plan")
        child_plan = replace(
            base,
            plan_id="child_plan",
            parent_ids=(parent_plan.plan_id,),
            basic_info_policy=BasicInfoPolicy(
                requests=tuple(
                    request
                    for request in base.basic_info_policy.requests
                    if request.request_id
                    in {"recent_company_news", "recent_market_backbone"}
                )
            ),
        )
        parent_metrics = metrics(8, 1, 9, 6)
        child_metrics = metrics(5, 1, 9, 9)
        snapshot_id = "a" * 64
        evidence = ParentPlanReflectionEvidence(
            plan=parent_plan,
            source_scope="historical_seed",
            evaluation_snapshot_ids=(snapshot_id,),
            metrics_by_cohort={
                "anchor": parent_metrics,
                "random": parent_metrics,
                "combined": parent_metrics,
            },
        )

        comparison = build_parent_plan_comparison(
            parent=evidence,
            child_plan=child_plan,
            child_metrics=child_metrics,
            child_snapshot_id=snapshot_id,
        )

        self.assertTrue(comparison["same_evaluation_snapshot"])
        self.assertEqual(comparison["metric_delta"]["confusion"]["true_positive"], -3)
        self.assertEqual(comparison["metric_delta"]["confusion"]["false_negative"], 3)
        removed_ids = {
            item["request_id"]
            for item in comparison["plan_diff"]["basic_info_requests_removed"]
        }
        self.assertEqual(
            removed_ids,
            {"recent_annual_filing", "reported_financial_facts"},
        )

        cross_snapshot = build_parent_plan_comparison(
            parent=evidence,
            child_plan=child_plan,
            child_metrics=child_metrics,
            child_snapshot_id="b" * 64,
        )
        self.assertFalse(cross_snapshot["same_evaluation_snapshot"])
        self.assertIsNone(cross_snapshot["metric_delta"])

    def test_historical_warm_start_replaces_manual_cold_start_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            proposer = CountingProposer()
            base = default_information_plan()
            historical = InformationPlan(
                plan_id="historical_seed_fixture",
                parent_ids=(),
                basic_info_policy=base.basic_info_policy,
                initial_research_skill=(
                    f"{base.initial_research_skill} Historical warm start."
                ),
                reflection_skill=base.reflection_skill,
                analysis_prompt=base.analysis_prompt,
            )
            events: list[Mapping[str, Any]] = []
            critic = SimpleCritic()
            round_reflector = SimpleRoundReflector()
            dataset_manager = EvaluationDatasetManager(
                workspace.evaluation_root,
                make_evaluation_pool(),
                make_anchor_pool(),
            )
            snapshot = dataset_manager.get_or_create_round_dataset(1)
            parent_trajectories = SyntheticPlanEvaluator().evaluate(
                historical,
                dataset_manager.resolve_cases(snapshot.case_ids),
                registry.freeze(),
            )
            anchor_ids = set(snapshot.anchor_case_ids)
            parent_metrics_by_cohort = {
                "anchor": score_predictions(
                    tuple(
                        item
                        for item in parent_trajectories
                        if item.case_id in anchor_ids
                    )
                ),
                "random": score_predictions(
                    tuple(
                        item
                        for item in parent_trajectories
                        if item.case_id not in anchor_ids
                    )
                ),
                "combined": score_predictions(parent_trajectories),
            }
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=proposer,
                critic=critic,
                round_reflector=round_reflector,
                workspace=workspace,
                seed_plans=(base,),
                warm_start_plans=(historical,),
                warm_start_parent_evidence=(
                    ParentPlanReflectionEvidence(
                        plan=historical,
                        source_scope="historical_seed",
                        evaluation_snapshot_ids=(snapshot.snapshot_id,),
                        metrics_by_cohort=parent_metrics_by_cohort,
                    ),
                ),
                candidates_per_round=1,
                on_progress=events.append,
            )

            engine.run_round(
                round_id=1,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )

            self.assertEqual(proposer.calls[0]["parents"], (historical.plan_id,))
            parent_event = next(
                item for item in events if item["event_type"] == "parents_selected"
            )
            self.assertEqual(parent_event["seed_parent_ids"], [historical.plan_id])
            comparison = critic.parent_comparisons[0][0]
            self.assertTrue(comparison["same_evaluation_snapshot"])
            self.assertIsNotNone(comparison["metric_delta"])
            self.assertEqual(
                round_reflector.parent_comparisons_by_plan_id[0][
                    "plan_child_1"
                ],
                critic.parent_comparisons[0],
            )
            committed_meta = workspace.restore_meta().entries[0]
            self.assertEqual(
                committed_meta.plan_reflections[0].parent_comparisons,
                critic.parent_comparisons[0],
            )
            self.assertEqual(
                committed_meta.plan_reflections[
                    0
                ].vertical_plan_reflection.successful_patterns,
                ("correct binary separation",),
            )

    def test_current_top_k_displaces_historical_warm_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            current = make_record("current_plan", 1.0, (1.0, 0.0))
            base = default_information_plan()
            historical = InformationPlan(
                plan_id="historical_seed_fixture",
                parent_ids=(),
                basic_info_policy=base.basic_info_policy,
                initial_research_skill=(
                    f"{base.initial_research_skill} Historical warm start."
                ),
                reflection_skill=base.reflection_skill,
                analysis_prompt=base.analysis_prompt,
            )
            proposer = CountingProposer()
            engine = PlanEvolutionEngine(
                archive=PlanArchive((current,)),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(base,),
                warm_start_plans=(historical,),
                candidates_per_round=1,
                top_k=1,
            )

            engine.run_round(
                round_id=1,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )

            self.assertEqual(proposer.calls[0]["parents"], (current.plan_id,))

    def test_one_stage_shares_exact_round_snapshot_and_keeps_diagnostics(self) -> None:
        class StageAwareEvaluator:
            def __init__(self) -> None:
                self.calls: dict[str, list[tuple[str, ...]]] = {}

            def evaluate(self, plan, cases, signal_registry):
                prior_calls = self.calls.setdefault(plan.plan_id, [])
                prior_calls.append(tuple(case.case_id for case in cases))
                rows = []
                for case in cases:
                    if plan.plan_id == "plan_child_1":
                        predicted = True
                    elif plan.plan_id == "plan_child_2":
                        predicted = case.ground_truth.is_surge
                    else:
                        predicted = False
                    rows.append(
                        make_trajectory(
                            case.company_id,
                            case.ground_truth.realized_max_multiple,
                            predicted,
                            (
                                case.ground_truth.magnitude
                                if predicted and case.ground_truth.is_surge
                                else (
                                    MagnitudeClass.TWO_TO_THREE
                                    if predicted
                                    else None
                                )
                            ),
                            case_id=case.case_id,
                        )
                    )
                return tuple(rows)

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            evaluator = StageAwareEvaluator()
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=evaluator,
                proposer=CountingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=3,
            )
            result = engine.run_round(
                round_id=1,
                validation_cases=make_evaluation_pool(),
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )

            round_ids = evaluator.calls["plan_child_1"][0]
            self.assertEqual(evaluator.calls["plan_child_2"][0], round_ids)
            self.assertEqual(evaluator.calls["plan_child_3"][0], round_ids)
            self.assertTrue(all(len(calls) == 1 for calls in evaluator.calls.values()))

            records = {record.plan_id: record for record in result.records}
            self.assertEqual(
                records["plan_child_3"].evaluation.evaluation_stage,
                "round",
            )
            self.assertEqual(records["plan_child_3"].evaluation.n_cases, 24)
            self.assertFalse(records["plan_child_3"].fitness.eligible)
            self.assertIn("no_positive_prediction", records["plan_child_3"].fitness.reasons)
            self.assertEqual(records["plan_child_3"].metrics.predicted_positive_count, 0)
            self.assertFalse(records["plan_child_3"].metrics.precision_defined)
            evaluated = records["plan_child_1"]
            self.assertEqual(evaluated.evaluation.evaluation_stage, "round")
            self.assertEqual(evaluated.evaluation.n_cases, 24)
            self.assertEqual(evaluated.metrics, score_predictions(evaluated.trajectories))
            self.assertEqual(
                set(evaluated.evaluation.metrics_by_cohort),
                {"anchor", "random", "combined"},
            )
            self.assertEqual(
                evaluated.evaluation.metrics_by_cohort["combined"],
                evaluated.metrics,
            )
            anchor_metrics = score_predictions(evaluated.trajectories[:16])
            random_metrics = score_predictions(evaluated.trajectories[16:])
            self.assertEqual(
                evaluated.evaluation.metrics_by_cohort["anchor"],
                anchor_metrics,
            )
            self.assertEqual(
                evaluated.evaluation.metrics_by_cohort["random"],
                random_metrics,
            )
            self.assertNotEqual(
                evaluated.metrics.binary_f1,
                (anchor_metrics.binary_f1 + random_metrics.binary_f1) / 2,
            )
            saved = json.loads(
                (
                    workspace.plans_root
                    / "plan_child_1"
                    / "record.json"
                ).read_text()
            )
            self.assertEqual(saved["evaluation_stage"], "round")
            self.assertEqual(saved["n_cases"], 24)
            self.assertEqual(len(saved["dataset_snapshot_ids"]), 1)

    def test_non_content_pause_is_not_converted_to_candidate_rejection(self) -> None:
        class PendingApproval(ValidationError):
            pass

        class PausingProposer:
            def propose(self, **kwargs):
                raise PendingApproval("external approval pending")

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            events = []
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=PausingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
                on_progress=events.append,
            )
            with self.assertRaisesRegex(PendingApproval, "approval pending"):
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )
            self.assertEqual(workspace.last_completed_round, 0)
            self.assertNotIn(
                "candidate_proposal_rejected",
                [item["event_type"] for item in events],
            )

    def test_all_rejected_candidates_leave_round_uncommitted(self) -> None:
        class RejectingProposer:
            def propose(self, **kwargs):
                raise CandidateProposalRejected(
                    "invalid Plan content after correction"
                )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            events = []
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=RejectingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=2,
                on_progress=events.append,
            )
            with self.assertRaisesRegex(RoundPaused, "all_candidate"):
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )
            self.assertEqual(workspace.last_completed_round, 0)
            self.assertEqual(
                [item["event_type"] for item in events].count(
                    "candidate_proposal_rejected"
                ),
                6,
            )

    def test_shared_anchor_data_pause_precedes_plan_calls_and_is_not_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            proposer = CountingProposer()
            anchors = make_anchor_pool()
            blocked_case_id = anchors[0].case_id

            def readiness(case: EvolutionCase) -> EvaluationCaseReadiness:
                if case.case_id == blocked_case_id:
                    return EvaluationCaseReadiness(
                        case.case_id,
                        False,
                        "provider_error",
                        retryable=True,
                    )
                return EvaluationCaseReadiness(case.case_id, True)

            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
                case_readiness=readiness,
            )

            with self.assertRaises(SharedEvaluationDataUnavailable) as context:
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=anchors,
                    signal_snapshot=registry.freeze(),
                )

            self.assertTrue(context.exception.retryable)
            self.assertEqual(proposer.calls, [])
            round_root = workspace.experiments_root / "round-0001"
            self.assertTrue((round_root / "shared-data-pause.json").is_file())
            self.assertFalse((round_root / "rejected.json").exists())
            self.assertEqual(workspace.last_completed_round, 0)

    def test_common_post_evaluation_evidence_gap_is_not_plan_rejection(self) -> None:
        class OneSharedGapEvaluator(SyntheticPlanEvaluator):
            def evaluate(self, plan, cases, signal_registry):
                rows = super().evaluate(plan, cases, signal_registry)
                return (
                    *rows[:-1],
                    replace(
                        rows[-1],
                        basic_info={"requests": []},
                        signal_rounds=(),
                    ),
                )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            critic = SimpleCritic()
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=OneSharedGapEvaluator(),
                proposer=CountingProposer(),
                critic=critic,
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=2,
            )

            with self.assertRaises(SharedEvaluationDataUnavailable) as context:
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )

            self.assertFalse(context.exception.retryable)
            self.assertEqual(len(context.exception.case_reasons), 1)
            self.assertEqual(critic.parent_comparisons, [])
            round_root = workspace.experiments_root / "round-0001"
            self.assertTrue((round_root / "shared-data-pause.json").is_file())
            self.assertFalse((round_root / "rejected.json").exists())
            self.assertEqual(workspace.last_completed_round, 0)

    def test_fast_loop_calls_proposer_independently_and_commits_s_e_j_r_u_t(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            proposer = CountingProposer()
            reflector = SimpleRoundReflector()
            evaluator = SyntheticPlanEvaluator()
            archive = PlanArchive()
            meta = PlanMetaMemory()
            progress_events = []
            engine = PlanEvolutionEngine(
                archive=archive,
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=reflector,
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=2,
                top_k=2,
                random_k=1,
                rng=random.Random(3),
                on_progress=progress_events.append,
            )
            cases = make_evaluation_pool()
            result = engine.run_round(
                round_id=1,
                validation_cases=cases,
                anchor_cases=make_anchor_pool(),
                signal_snapshot=registry.freeze(),
            )
            self.assertEqual(len(proposer.calls), 2)
            self.assertEqual(proposer.calls[0]["parents"], ("plan_manual_v1",))
            self.assertEqual(proposer.calls[0]["prior"], DEFAULT_EVOLUTION_PRIORS.propose_plan)
            self.assertEqual(proposer.calls[0]["candidate_index"], 1)
            self.assertEqual(proposer.calls[0]["candidate_count"], 2)
            self.assertEqual(proposer.calls[0]["forbidden_plan_ids"], ())
            self.assertEqual(proposer.calls[1]["candidate_index"], 2)
            self.assertEqual(
                proposer.calls[1]["forbidden_plan_ids"], ("plan_child_1",)
            )
            self.assertEqual(len(result.records), 2)
            for record in result.records:
                self.assertTrue(record.embedding)
                self.assertEqual(record.metrics.binary_f1, 1.0)
                self.assertTrue(record.reflection.successful_patterns)
                self.assertIn("revenue_growth_yoy:v1", record.signal_usage)
                self.assertEqual(len(record.trajectories), 24)
            self.assertEqual(workspace.last_completed_round, 1)
            self.assertEqual(len(workspace.restore_archive().records), 2)
            self.assertEqual(meta.entries[0].evidence_refs, ("plan_child_1", "plan_child_2"))
            self.assertEqual(
                tuple(
                    item.plan_id for item in meta.entries[0].plan_reflections
                ),
                ("plan_child_1", "plan_child_2"),
            )
            for plan_reflection, record in zip(
                meta.entries[0].plan_reflections,
                result.records,
            ):
                self.assertEqual(len(plan_reflection.original_case_reflections), 24)
                self.assertEqual(
                    plan_reflection.vertical_plan_reflection,
                    record.reflection,
                )
            self.assertEqual(workspace.restore_meta().entries, meta.entries)
            event_types = [event["event_type"] for event in progress_events]
            self.assertIn("candidate_proposed", event_types)
            self.assertIn("candidate_scored", event_types)
            self.assertEqual(event_types[-1], "round_committed")
            committed_event = progress_events[-1]
            self.assertEqual(committed_event["round_id"], 1)
            self.assertEqual(len(committed_event["top_k"]), 1)
            proposed = next(
                event
                for event in progress_events
                if event["event_type"] == "candidate_proposed"
            )
            self.assertIn("basic_info_requests", proposed["plan_summary"])
            stats = registry.load_stats("revenue_growth_yoy")
            self.assertEqual(stats.retrieved, 48)
            self.assertEqual(stats.executed, 48)
            PlanEvolutionEngine(
                archive=workspace.restore_archive(),
                meta_memory=workspace.restore_meta(),
                signal_registry=registry,
                evaluator=evaluator,
                proposer=CountingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            reconciled = registry.load_stats("revenue_growth_yoy")
            self.assertEqual(reconciled.retrieved, 48)
            self.assertEqual(reconciled.executed, 48)

    def test_post_pointer_learning_failure_reconciles_scoped_selection(
        self,
    ) -> None:
        class FailFirstLearningRegistry(SignalRegistry):
            def __init__(self, root):
                super().__init__(root)
                self.fail_learning = True

            def record_learning_events(self, events):
                materialized = tuple(events)
                if self.fail_learning and materialized:
                    self.fail_learning = False
                    raise RuntimeError("simulated post-pointer learning failure")
                return super().record_learning_events(materialized)

        scoped_selection = SignalSelectionDecision(
            signal_ref="revenue_growth_yoy:v1",
            reason_code="answer_need",
            selection_reason="Measure the answered revenue-growth facet.",
            applicability_hypothesis="Comparable annual periods are available.",
            expected_role="primary",
            context_tags=("comparable_financials",),
            target_need_indices=(0,),
            answer_scope="partial",
            residual_need="Determine whether the growth is durable.",
        )
        self.assertEqual(
            set(scoped_selection.to_dict())
            - set(scoped_selection.to_learning_dict()),
            {"answer_scope", "residual_need"},
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_root = root / "signals"
            registry = FailFirstLearningRegistry(registry_root)
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            evaluator = SyntheticPlanEvaluator(signal_selection=scoped_selection)
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=evaluator,
                proposer=CountingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )

            with self.assertRaisesRegex(
                RuntimeError, "simulated post-pointer learning failure"
            ):
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )

            self.assertEqual(workspace.last_completed_round, 1)
            self.assertEqual(
                registry.load_learning_events("revenue_growth_yoy:v1"), ()
            )
            restored_archive = workspace.restore_archive()
            raw_selection = (
                restored_archive.records[0]
                .trajectories[0]
                .signal_rounds[0]
                .selections[0]
                .to_dict()
            )
            self.assertEqual(raw_selection["answer_scope"], "partial")
            self.assertEqual(
                raw_selection["residual_need"],
                "Determine whether the growth is durable.",
            )

            resumed_registry = SignalRegistry(registry_root)
            for _ in range(2):
                PlanEvolutionEngine(
                    archive=restored_archive,
                    meta_memory=workspace.restore_meta(),
                    signal_registry=resumed_registry,
                    evaluator=evaluator,
                    proposer=CountingProposer(),
                    critic=SimpleCritic(),
                    round_reflector=SimpleRoundReflector(),
                    workspace=workspace,
                    seed_plans=(default_information_plan(),),
                    candidates_per_round=1,
                )

            events = resumed_registry.load_learning_events(
                "revenue_growth_yoy:v1"
            )
            self.assertEqual(len(events), 24)
            self.assertNotIn("answer_scope", events[0].selection)
            self.assertNotIn("residual_need", events[0].selection)
            stats = resumed_registry.load_stats("revenue_growth_yoy")
            self.assertEqual(stats.retrieved, 24)
            self.assertEqual(stats.executed, 24)

    def test_fast_loop_reuses_staged_candidate_after_interrupted_evaluation(
        self,
    ) -> None:
        class InterruptedEvaluator:
            def evaluate(self, plan, cases, signal_registry):
                raise RuntimeError("simulated evaluator interruption")

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            first_proposer = CountingProposer()
            first_engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=InterruptedEvaluator(),
                proposer=first_proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
                run_contract_hash="contract-hash",
            )
            cases = make_evaluation_pool()
            anchors = make_anchor_pool()

            with self.assertRaisesRegex(RuntimeError, "simulated evaluator"):
                first_engine.run_round(
                    round_id=1,
                    validation_cases=cases,
                    anchor_cases=anchors,
                    signal_snapshot=registry.freeze(),
                )

            candidate_path = (
                workspace.experiments_root
                / "round-0001"
                / "candidates"
                / "slot-01.json"
            )
            self.assertTrue(candidate_path.is_file())
            self.assertEqual(len(first_proposer.calls), 1)
            self.assertEqual(workspace.last_completed_round, 0)

            resumed_proposer = CountingProposer()
            events = []
            resumed = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(),
                proposer=resumed_proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
                run_contract_hash="contract-hash",
                on_progress=events.append,
            ).run_round(
                round_id=1,
                validation_cases=cases,
                anchor_cases=anchors,
                signal_snapshot=registry.freeze(),
            )

            self.assertEqual(resumed_proposer.calls, [])
            self.assertEqual(resumed.records[0].plan.plan_id, "plan_child_1")
            self.assertEqual(workspace.last_completed_round, 1)
            self.assertIn(
                "candidate_proposal_reused",
                [event["event_type"] for event in events],
            )

    def test_round_meta_cannot_cite_old_or_unrelated_experiment(self) -> None:
        class BadReflector(SimpleRoundReflector):
            def reflect(
                self,
                *,
                round_id,
                records,
                prior,
                parent_comparisons_by_plan_id=None,
            ):
                return RoundMetaEntry(round_id=round_id, evidence_refs=("old_plan",))

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(Path(directory) / "workspace")
            engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=PlanMetaMemory(),
                signal_registry=registry,
                evaluator=SyntheticPlanEvaluator(include_signal=False),
                proposer=CountingProposer(),
                critic=SimpleCritic(),
                round_reflector=BadReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            with self.assertRaisesRegex(ValidationError, "outside new experiments"):
                engine.run_round(
                    round_id=1,
                    validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(),
                    signal_snapshot=registry.freeze(),
                )
            self.assertEqual(workspace.last_completed_round, 0)
