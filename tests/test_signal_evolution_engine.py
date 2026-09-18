"""Slow Signal and dual-loop evolution tests."""

from tests.scheme_evolution_test_support import *  # noqa: F403
from stock_opportunity_agent.research.signal_evolution import (
    SIGNAL_UPDATE_MUTABLE_PATHS,
    SlowLoopValidation,
    _exploration_comparison_concepts,
    _prioritize_reflection_feedback,
    _signal_effectiveness_counts,
    signal_effectiveness_measurement_contract,
    signal_research_objective,
    signal_candidate_execution_contract,
    build_slow_sampling_manifest,
    project_slow_method_memory,
    read_slow_sources,
    validate_slow_memory,
)
from stock_opportunity_agent.data.resolution import AcquisitionResult
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.llm.openai import OpenAIClientError


class SignalEvolutionTests(TestCase):
    def test_effectiveness_contract_explains_available_neutral_results(self) -> None:
        counts = _signal_effectiveness_counts((
            (SignalValue.POSITIVE, True, SignalExecutionStatus.SUCCESS),
            (SignalValue.NEUTRAL, False, SignalExecutionStatus.SUCCESS),
            (SignalValue.UNAVAILABLE, False, SignalExecutionStatus.DOMAIN_UNAVAILABLE),
        ))
        self.assertEqual(counts, (2, 1, 1, 0, 0))
        contract = signal_effectiveness_measurement_contract()
        self.assertIn("NEUTRAL", contract["available"])
        self.assertIn("NEUTRAL", contract["decisive"])
        self.assertIn("same frozen case pool", contract["paired_population"])

    def test_imported_committed_slow_history_becomes_namespaced_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = EvolutionWorkspace(root / "workspace")
            namespace = "source-0123456789abcdef"
            relative = Path(
                "experiments/cycles/cycle-0001/slow_loop_result.json"
            )
            artifact = {
                "schema_version": "dual-loop-slow-result-v2",
                "result": {"signal_goal_status": "unmet"},
            }
            artifact_path = workspace.root / "slow_history" / namespace / relative
            artifact_path.parent.mkdir(parents=True)
            artifact_path.write_text(
                json.dumps(artifact, sort_keys=True), encoding="utf-8"
            )
            manifest = {
                "schema_version": "slow-history-manifest-v1",
                "source_namespace": namespace,
                "committed_slow_cycle": 1,
                "cycle_artifacts": [
                    {
                        "cycle_id": "1",
                        "path": str(relative),
                        "sha256": hashlib.sha256(
                            artifact_path.read_bytes()
                        ).hexdigest(),
                    }
                ],
            }
            manifest_path = workspace.root / "slow_history" / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "manifest_hash": canonical_json_hash(manifest),
                        "manifest": manifest,
                    }
                ),
                encoding="utf-8",
            )
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("history_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )

            rows, sources = engine._committed_slow_feedback()

            self.assertEqual(engine._imported_slow_history_cutoff(), 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["kind"], "search_result")
            self.assertIn(namespace, rows[0]["feedback_ref"])
            self.assertEqual(
                sources[0]["content_hash"],
                canonical_json_hash(artifact["result"]),
            )

    def test_monolithic_slow_validation_splits_at_complete_work_boundaries(self) -> None:
        units = SignalEvolutionEngine._imported_artifact_units(
            "slow_loop_validation.json",
            {
                "validation": {
                    "mined_candidates": [],
                    "candidate_evaluations": {"candidate:v1": {"accepted": False}},
                    "candidate_effectiveness": {
                        "candidate:v1": {"disposition": "rejected"}
                    },
                    "agent_audits": {
                        "mining_pipeline": {
                            "track": "hypothesis_then_exploration_fallback",
                            "hypothesis": {"status": "no_testable_hypothesis"},
                            "exploration": {"status": "completed"},
                        },
                        "update_pipeline": {
                            "status": "completed",
                            "targets": [{"signal_ref": "stable:v1"}],
                        },
                    },
                }
            },
        )

        suffixes = {item[0] for item in units}
        self.assertIn("summary", suffixes)
        self.assertIn("mining-hypothesis", suffixes)
        self.assertIn("mining-exploration", suffixes)
        self.assertIn("update-target-001", suffixes)
        self.assertTrue(all(item[2].startswith("/") for item in units))

    def test_large_mining_track_retains_complete_decision_in_reflection_budget(self) -> None:
        decision = {"hypothesis_id": "e2-proposal", "rationale": "Observed contrast.",
                    "candidate": {"spec": {"signal_id": "cash_state"},
                                  "skill": "Source grounded measurement.", "tests": [{"expected": "positive"}]}}
        raw = {"validation": {"agent_audits": {"mining_pipeline": {
            "exploration": {"stages": {
                "E1": {"signatures": ["x" * 70000]},
                "E2": {"decisions": [decision]},
            }},
        }}}}
        units = SignalEvolutionEngine._imported_artifact_units("slow_loop_validation.json", raw)
        rows = [{"feedback_ref": "slow:1:slow_loop_validation:" + suffix,
                 "subject_ref": "cycle-0001", "artifact": unit}
                for suffix, _kind, _locator, unit in units]
        ordered = _prioritize_reflection_feedback(rows)
        catalog = {row["feedback_ref"]: {"visible_to": ["reflection"], "content": row} for row in ordered}
        selected, manifest = read_slow_sources(
            catalog, role_scope="reflection", source_catalog=catalog,
            budget_bytes=64000, max_items=12,
        )
        ref = "slow:1:slow_loop_validation:mining-decision-E2-001"
        self.assertIn(ref, [item["ref"] for item in selected])
        self.assertEqual(catalog[ref]["content"]["artifact"], decision)
        self.assertIn({"ref": "slow:1:slow_loop_validation:mining-exploration",
                       "reason": "whole_entry_budget"}, manifest["deferred"])
        unit = next(unit for unit in units if unit[0] == "mining-decision-E2-001")
        located = raw
        for part in unit[2].strip("/").split("/"):
            located = located[int(part)] if isinstance(located, list) else located[part]
        self.assertEqual(located, decision)
        raw["validation"]["agent_audits"]["mining_pipeline"]["exploration"]["stages"]["E2"] = {
            "decisions": [], "no_candidate": {"reason": "No supported business contrast."},
        }
        empty_units = SignalEvolutionEngine._imported_artifact_units("slow_loop_validation.json", raw)
        empty = next(unit for unit in empty_units if unit[0] == "mining-decision-E2-empty")
        self.assertEqual(empty[3]["no_candidate"]["reason"], "No supported business contrast.")

    def test_slow_sampling_is_order_invariant_and_issuer_disjoint(self) -> None:
        cases = tuple(
            make_case(f"slow_sample_{index}", 2.5 if index % 2 else 1.2)
            for index in range(1, 13)
        )

        first = build_slow_sampling_manifest(
            cases,
            cycle_id=2,
            base_seed="fixture-contract",
            dev_limit=6,
            check_limit=4,
        )
        replay = build_slow_sampling_manifest(
            reversed(cases),
            cycle_id=2,
            base_seed="fixture-contract",
            dev_limit=6,
            check_limit=4,
        )

        self.assertEqual(first, replay)
        groups = first["issuer_groups"]
        self.assertFalse(
            {groups[item] for item in first["dev_case_ids"]}
            & {groups[item] for item in first["check_case_ids"]}
        )

    def test_slow_sampling_rotates_cohorts_across_cycles(self) -> None:
        cases = tuple(
            make_case(f"slow_rotate_{index}", 2.5 if index % 2 else 1.2)
            for index in range(1, 25)
        )

        first = build_slow_sampling_manifest(
            cases,
            cycle_id=1,
            base_seed="fixture-contract",
            dev_limit=6,
            check_limit=4,
        )
        second = build_slow_sampling_manifest(
            cases,
            cycle_id=2,
            base_seed="fixture-contract",
            dev_limit=6,
            check_limit=4,
        )

        # Each cycle is a fresh permutation of the same population: roles may
        # repeat across cycles (evaluation hygiene is enforced per candidate
        # at the effectiveness gate), while within a cycle dev and check stay
        # issuer-disjoint.
        self.assertNotEqual(first["dev_case_ids"], second["dev_case_ids"])
        self.assertNotEqual(first["check_case_ids"], second["check_case_ids"])
        for manifest in (first, second):
            groups = manifest["issuer_groups"]
            self.assertFalse(
                {groups[item] for item in manifest["dev_case_ids"]}
                & {groups[item] for item in manifest["check_case_ids"]}
            )

    def test_pooled_provisional_decision_zones(self) -> None:
        from stock_opportunity_agent.research.signal_evolution import (
            pooled_provisional_decision,
        )

        def record(decisive, correct, wrong, tp=None, fn=None):
            confusion = {}
            if tp is not None and fn is not None:
                confusion = {"tp": tp, "fn": fn}
            return {
                "candidate_decisive": decisive,
                "candidate_correct": correct,
                "candidate_wrong": wrong,
                "candidate_confusion": confusion,
            }

        promote = pooled_provisional_decision(
            [
                record(4, 3, 1, tp=2, fn=0),
                record(4, 4, 0, tp=2, fn=0),
                record(5, 5, 0, tp=2, fn=0),
            ]
        )
        self.assertEqual(promote["action"], "promote")

        recall_starved = pooled_provisional_decision(
            [
                record(4, 3, 1, tp=1, fn=3),
                record(4, 4, 0, tp=1, fn=3),
                record(5, 5, 0, tp=2, fn=2),
            ]
        )
        self.assertEqual(recall_starved["action"], "continue")

        tie_keep = pooled_provisional_decision(
            [record(4, 2, 2), record(4, 3, 1)]
        )
        self.assertEqual(tie_keep["action"], "continue")

        eliminate = pooled_provisional_decision(
            [
                record(4, 2, 2),
                record(4, 2, 2),
                record(4, 1, 3),
                record(4, 1, 3),
                record(4, 2, 2),
            ]
        )
        self.assertEqual(eliminate["action"], "eliminate")

        recall_eliminate = pooled_provisional_decision(
            [
                record(4, 4, 0, tp=1, fn=3),
                record(4, 4, 0, tp=1, fn=3),
                record(4, 4, 0, tp=1, fn=3),
                record(4, 4, 0, tp=1, fn=3),
                record(4, 4, 0, tp=1, fn=3),
            ]
        )
        self.assertEqual(recall_eliminate["action"], "eliminate")

        starved = pooled_provisional_decision(
            [record(0, 0, 0)] * 5
        )
        self.assertEqual(starved["action"], "eliminate")

    def test_candidate_evaluation_exclusions_pool_generation_and_prior_cases(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals", candidate_root=root / "cand")
            registry.install_catalog(SEED_CATALOG)
            current = registry.latest_spec("revenue_growth_yoy")
            spec = SignalSpec(
                **{
                    **current.__dict__,
                    "signal_id": "exclusion_measurement",
                    "version": 1,
                    "description": "Exclusion cohort fixture.",
                }
            )
            ref = registry.stage_candidate(spec, origin="test")
            candidate_hash = registry.candidate_hash(ref)
            identity_fields = (
                "baseline_hash",
                "cohort_hash",
                "source_manifest_hash",
                "projection_hash",
                "validator_hash",
                "model_hash",
                "sampling_hash",
            )

            def evaluate_once(case_ids, generation, seed):
                identity = {
                    field: hashlib.sha256(
                        f"{field}-{seed}".encode("utf-8")
                    ).hexdigest()
                    for field in identity_fields
                }
                return registry.record_candidate_validation(
                    ref,
                    candidate_hash=candidate_hash,
                    evaluation_identity=identity,
                    accepted=False,
                    reasons=("fixture",),
                    effectiveness={
                        "disposition": "provisional",
                        "case_ids": list(case_ids),
                        "generation_case_ids": list(generation),
                    },
                )

            evaluate_once(["check_a", "check_b"], ["dev_1", "dev_2"], 1)
            evaluate_once(["check_c"], ["dev_1", "dev_2"], 2)

            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("exclusion_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )

            excluded = engine._candidate_evaluation_exclusions(ref)

            self.assertEqual(
                excluded,
                ("check_a", "check_b", "check_c", "dev_1", "dev_2"),
            )

    def test_slow_source_read_keeps_whole_entries_and_enforces_scope(self) -> None:
        catalog = {
            "feedback-1": {
                "visible_to": ["reflection", "H1"],
                "content": {"detail": "specific evidence" * 20},
            },
            "feedback-2": {
                "visible_to": ["reflection"],
                "content": {"detail": "counterexample" * 20},
            },
        }

        included, manifest = read_slow_sources(
            ("feedback-1", "feedback-2"),
            role_scope="reflection",
            source_catalog=catalog,
            budget_bytes=500,
        )

        self.assertEqual(manifest["available_count"], 2)
        self.assertEqual(
            manifest["included_count"] + manifest["deferred_count"], 2
        )
        self.assertTrue(all(item["content"] for item in included))
        with self.assertRaisesRegex(ValidationError, "outside the role scope"):
            read_slow_sources(
                ("feedback-2",),
                role_scope="H1",
                source_catalog=catalog,
                budget_bytes=2_000,
            )

    def test_slow_source_read_preserves_whole_entries_beyond_item_limit(self) -> None:
        catalog = {
            f"feedback-{index}": {
                "visible_to": ["reflection"],
                "content": {"detail": f"complete-{index}"},
            }
            for index in range(1, 4)
        }

        included, manifest = read_slow_sources(
            catalog,
            role_scope="reflection",
            source_catalog=catalog,
            budget_bytes=2_000,
            max_items=2,
        )

        self.assertEqual(
            [item["ref"] for item in included],
            ["feedback-1", "feedback-2"],
        )
        self.assertEqual(manifest["max_items"], 2)
        self.assertEqual(
            manifest["deferred"],
            [{"ref": "feedback-3", "reason": "item_limit"}],
        )

    def test_reflection_prioritizes_terminal_evidence_within_each_cycle(self) -> None:
        prefix = "slow-history:source-abc:1:"
        rows = [
            {
                "feedback_ref": prefix + f"slow_experiments:attempt-{index:03d}",
                "subject_ref": "source-abc:cycle-0001",
            }
            for index in range(1, 12)
        ]
        rows.extend(
            [
                {
                    "feedback_ref": prefix + "slow_loop_validation:effect-candidate",
                    "subject_ref": "source-abc:cycle-0001",
                },
                {
                    "feedback_ref": prefix + "slow_loop_validation:summary",
                    "subject_ref": "source-abc:cycle-0001",
                },
                {
                    "feedback_ref": prefix + "slow_loop_result:summary",
                    "subject_ref": "source-abc:cycle-0001",
                },
                {
                    "feedback_ref": (
                        "slow-history:source-abc:2:slow_loop_result:summary"
                    ),
                    "subject_ref": "source-abc:cycle-0002",
                },
            ]
        )

        prioritized = _prioritize_reflection_feedback(rows)
        selected = [row["feedback_ref"] for row in prioritized[:12]]

        self.assertEqual(
            selected[0],
            "slow-history:source-abc:2:slow_loop_result:summary",
        )
        self.assertEqual(
            selected[1:4],
            [
                prefix + "slow_loop_result:summary",
                prefix + "slow_loop_validation:summary",
                prefix + "slow_loop_validation:effect-candidate",
            ],
        )
        self.assertNotIn(prefix + "slow_experiments:attempt-011", selected)

    def test_signal_mining_production_defaults_bound_reflection_and_induction(self) -> None:
        config = SignalMiningConfig()

        self.assertEqual(config.reflection_feedback_limit, 12)
        self.assertEqual(config.induction_cases_per_class, 4)
        self.assertEqual(config.validation_cases_per_class, 8)

    def test_slow_method_memory_is_bounded_by_complete_recent_entries(self) -> None:
        deltas = [
            {
                "cycle_id": 1,
                "status": "appended",
                "failure_ref": None,
                "episode_reflections": [
                    {"episode_ref": "old-episode", "reflection": "o" * 900}
                ],
                "lesson_additions": [
                    {"lesson_id": "old-lesson", "guidance": "p" * 900}
                ],
            },
            {
                "cycle_id": 2,
                "status": "appended",
                "failure_ref": None,
                "episode_reflections": [
                    {"episode_ref": "new-episode", "reflection": "n" * 900}
                ],
                "lesson_additions": [
                    {"lesson_id": "new-lesson", "guidance": "l" * 900}
                ],
            },
        ]

        view = project_slow_method_memory(deltas, budget_bytes=3_500)

        manifest = view["memory_view_manifest"]
        self.assertLessEqual(manifest["bytes"], 3_500)
        self.assertEqual(
            manifest["included_refs"][:2],
            [
                "slow-memory:2:episode:new-episode",
                "slow-memory:2:lesson:new-lesson",
            ],
        )
        self.assertTrue(manifest["deferred"])
        current = view["memory_deltas"][1]
        self.assertEqual(
            current["episode_reflections"][0]["reflection"], "n" * 900
        )
        self.assertEqual(current["lesson_additions"][0]["guidance"], "l" * 900)

    def test_typed_slow_source_read_replaces_view_once_and_keeps_pending(self) -> None:
        class Reader:
            def __init__(self) -> None:
                self.payloads = []

            def request_slow_sources(self, payload):
                self.payloads.append(payload)
                return AgentStep(
                    ("feedback-2",),
                    metadata={"request_refs": ("read-request",)},
                )

        catalog = {
            "feedback-1": {
                "visible_to": ["reflection"],
                "content": {"detail": "a" * 350},
            },
            "feedback-2": {
                "visible_to": ["reflection"],
                "content": {"detail": "b" * 550},
            },
        }
        selected, manifest = read_slow_sources(
            catalog,
            role_scope="reflection",
            source_catalog=catalog,
            budget_bytes=700,
        )
        self.assertEqual([item["ref"] for item in selected], ["feedback-1"])
        engine = object.__new__(SignalEvolutionEngine)
        reader = Reader()

        replacement, final_manifest = engine._optional_slow_source_read(
            model=reader,
            role_scope="reflection",
            source_catalog=catalog,
            selected=selected,
            manifest=manifest,
        )

        self.assertEqual([item["ref"] for item in replacement], ["feedback-2"])
        self.assertEqual(
            final_manifest["source_read_request_refs"], ["read-request"]
        )
        self.assertEqual(
            final_manifest["deferred"],
            [{"ref": "feedback-1", "reason": "source_read_not_selected"}],
        )
        self.assertEqual(len(reader.payloads), 1)

    def test_typed_slow_source_read_cannot_evict_required_recent_frontier(self) -> None:
        class Reader:
            def request_slow_sources(self, payload):
                self.payload = payload
                return AgentStep(("historical-2",))

        catalog = {
            "recent-1": {
                "visible_to": ["reflection"],
                "content": {"detail": "recent" * 20},
            },
            "historical-1": {
                "visible_to": ["reflection"],
                "content": {"detail": "old-a" * 100},
            },
            "historical-2": {
                "visible_to": ["reflection"],
                "content": {"detail": "old-b" * 20},
            },
        }
        selected, manifest = read_slow_sources(
            catalog,
            role_scope="reflection",
            source_catalog=catalog,
            budget_bytes=900,
        )
        engine = object.__new__(SignalEvolutionEngine)
        reader = Reader()

        replacement, final_manifest = engine._optional_slow_source_read(
            model=reader,
            role_scope="reflection",
            source_catalog=catalog,
            selected=selected,
            manifest=manifest,
            required_refs=("recent-1",),
        )

        self.assertEqual(
            [item["ref"] for item in replacement],
            ["recent-1", "historical-2"],
        )
        self.assertEqual(
            reader.payload["current_view"]["required_refs"], ["recent-1"]
        )
        self.assertEqual(final_manifest["required_refs"], ["recent-1"])

    def test_slow_experiments_seal_role_granular_request_chains(self) -> None:
        engine = object.__new__(SignalEvolutionEngine)
        engine.workspace = mock.Mock()
        engine.workspace.load_slow_experiments.return_value = None
        engine.registry = mock.Mock()
        validation = SlowLoopValidation(
            mined_candidates=(),
            updated_candidates=(),
            validated_candidates={},
            provisional_candidates={},
            rejected={},
            refined_hypotheses={},
            input_registry_version=1,
            input_registry_hash="registry",
            input_signal_refs=(),
            agent_audits={
                "mining_pipeline": {
                    "hypothesis": {
                        "track": "hypothesis",
                        "status": "completed",
                        "stages": {
                            "H1": {"status": "completed", "request_refs": ["h1-a", "h1-b"]},
                            "H3": {"status": "completed", "request_refs": ["h3-a"]},
                        },
                    },
                    "exploration": {
                        "track": "exploration",
                        "status": "completed",
                        "stages": {
                            "E1": {
                                "microbatches": [
                                    {"status": "completed", "request_refs": ["e1-a"]},
                                    {"status": "technical_failure", "request_refs": ["e1-b", "e1-c"]},
                                ]
                            },
                            "E2": {"status": "completed", "request_refs": ["e2-a"]},
                        },
                    },
                },
                "update_pipeline": {
                    "status": "completed",
                    "targets": [
                        {
                            "status": "completed",
                            "disposition": "defer",
                            "target": {"signal_ref": "cash_reserves:v1"},
                            "request_refs": ["update-a", "update-b"],
                        }
                    ],
                },
            },
        )

        sealed = engine._seal_slow_experiments(
            cycle_id=1,
            slow_input={"contract_hash": "contract"},
            slow_memory={"status": "reused"},
            validation=validation,
        )

        by_id = {item["work_id"]: item for item in sealed["attempts"]}
        self.assertEqual(
            set(by_id),
            {
                "cycle-0001:H1",
                "cycle-0001:H3",
                "cycle-0001:E1:001",
                "cycle-0001:E1:002",
                "cycle-0001:E2",
                "cycle-0001:Update:001",
            },
        )
        self.assertEqual(by_id["cycle-0001:H1"]["usage_ref"], "h1-b")
        self.assertEqual(
            by_id["cycle-0001:E1:002"]["request_refs"], ["e1-b", "e1-c"]
        )
        self.assertEqual(by_id["cycle-0001:E1:002"]["failure_ref"], "E1:002")
        self.assertEqual(
            by_id["cycle-0001:Update:001"]["parent_signal_ref"],
            "cash_reserves:v1",
        )

    def test_failed_slow_memory_cannot_consume_feedback(self) -> None:
        value = {
            "schema_version": "slow-memory-v1",
            "cycle_id": 1,
            "contract_hash": "contract",
            "input_hash": "input",
            "parent_memory_hash": "",
            "reflection_work_hash": "work",
            "status": "failed",
            "processed_feedback_refs": ["feedback-1"],
            "pending_feedback_refs": [],
            "episode_reflections": [],
            "lesson_additions": [],
            "model_view_manifest": {},
            "usage_ref": None,
            "failure_ref": "failed",
        }

        with self.assertRaisesRegex(ValidationError, "cannot consume"):
            validate_slow_memory(
                value,
                available_feedback_refs=("feedback-1",),
                available_source_refs=("feedback-1",),
            )

    def test_update_target_selection_rotates_recently_worked_signals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)

            def install_profile(signal_ref: str, misleading: int) -> None:
                spec = registry.latest_spec(
                    signal_ref.rsplit(":v", 1)[0]
                )
                profile_dir = (
                    registry._manifest_for(spec.signal_id).parent
                    / "versions"
                    / f"v{spec.version}"
                    / "learning"
                )
                profile_dir.mkdir(parents=True, exist_ok=True)
                (profile_dir / "profile.json").write_text(
                    json.dumps(
                        {
                            "schema_version": "signal-learning-profile-v1",
                            "signal_ref": spec.ref,
                            "unique_observations": 20,
                            "directional": {"wrong": 3, "unavailable": 0},
                            "reflection_attribution": {
                                "misleading": misleading
                            },
                        }
                    ),
                    encoding="utf-8",
                )

            install_profile("cash_reserves:v1", 2)
            install_profile("max_drawdown_1y:v1", 2)
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("rotation_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )

            fresh = engine._select_signal_update_targets(
                suggested_refs=("cash_reserves:v1",),
                recent_worked={"cash_reserves": 0},
            )
            self.assertEqual(fresh[0]["signal_ref"], "cash_reserves:v1")

            rotated = engine._select_signal_update_targets(
                suggested_refs=("cash_reserves:v1",),
                recent_worked={"cash_reserves": 2},
            )
            self.assertEqual(rotated[0]["signal_ref"], "max_drawdown_1y:v1")
            self.assertEqual(
                next(
                    item
                    for item in rotated
                    if item["signal_ref"] == "cash_reserves:v1"
                )["worked_recent_cycles"],
                2,
            )

    def test_controller_mining_dispatch_stages_materialized_candidate(self) -> None:
        class FakeControllerCaller:
            def __init__(self) -> None:
                self.stages: list[str] = []
                self.request_hash_trace: list[str] = []

            def complete_json(self, *, stage, **_kwargs):
                self.stages.append(stage)
                if stage == "mining_candidate_materialize":
                    payload = dict(_kwargs["payload"])
                    if not payload.get("last_issues"):
                        return ({"spec": {}}, AgentUsage(llm_calls=1))
                    stable = registry.latest_spec("revenue_growth_yoy")
                    spec = {
                        **stable.to_dict(),
                        "signal_id": "Fixture Controller Runway!!",
                        "version": 1,
                    }
                    spec["definition"]["description"] = (
                        "Measure the latest point-in-time year-over-year "
                        "revenue growth from cited spans with a stricter "
                        "positive threshold."
                    )
                    spec["parameters"]["positive_min"] = 0.15
                    growth = sec_company_facts_content(
                        ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                        ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                    )
                    return (
                        {
                            "spec": spec,
                            "skill": None,
                            "tests": [
                                {
                                    "name": "growth_positive",
                                    "expected": "positive",
                                    "as_of": "2025-02-01T00:00:00+00:00",
                                    "documents": [
                                        {
                                            "source_type": "financials",
                                            "content": growth,
                                        }
                                    ],
                                }
                            ],
                        },
                        AgentUsage(llm_calls=1),
                    )
                view = dict(_kwargs["payload"])
                if view.get("seed") == "discovery":
                    return (
                        {"action": "record_deferred", "rationale": ["Stop."]},
                        AgentUsage(llm_calls=1),
                    )
                if not view.get("known_fact_refs"):
                    families = view.get("available_source_families") or [
                        "financial"
                    ]
                    return (
                        {
                            "action": "fetch_evidence",
                            "rationale": ["Sweep the cohort."],
                            "case_refs": view["case_refs"][:2],
                            "source_families": families[:1],
                            "max_documents": 2,
                        },
                        AgentUsage(llm_calls=1),
                    )
                known = sorted(view.get("known_fact_refs", ()))
                cash = [ref for ref in known if ref] or known[:1]
                needs = view.get("backlog_needs") or []
                return (
                    {
                        "action": "propose_candidate",
                        "rationale": ["Grounded cash measurement."],
                        "candidate": {
                            "measurement": {
                                "observable": "controller_fixture_runway",
                                "value_kind": "numeric",
                                "normalization": (
                                    "CashAndCashEquivalentsAtCarryingValue "
                                    "divided by monthly burn"
                                ),
                            },
                            "falsifiers": [
                                {
                                    "condition": "Runway does not separate groups.",
                                    "expected_observation": "No contrast.",
                                }
                            ],
                            "evidence_refs": cash[:1],
                        },
                        "need_dispositions": [
                            {
                                "need_refs": [row["need_ref"]],
                                "disposition": "new_measurement",
                                "signal_refs": [],
                                "rationale": ["Covered by the new measurement."],
                            }
                            for row in needs
                        ],
                    },
                    AgentUsage(llm_calls=1),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = (
                *(make_case(f"ctl_pos_{index}", 4.0) for index in range(2)),
                *(make_case(f"ctl_ctl_{index}", 1.1) for index in range(2)),
            )
            documents = tuple(
                RawInfoDocument.create(
                    document_id=f"ctl_facts_{index}",
                    company_id=case.company_id,
                    source_type="financials",
                    published_at=NOW,
                    available_at=NOW,
                    content=sec_company_facts_content(
                        ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                        ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                    ),
                )
                for index, case in enumerate(cases)
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(documents=documents),
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            manifest = build_slow_sampling_manifest(
                cases,
                cycle_id=1,
                base_seed="controller-dispatch",
                dev_limit=4,
                check_limit=4,
            )
            engine._active_sampling_manifest = manifest

            caller_backed = EmptyMiningModel()
            caller_backed.caller = FakeControllerCaller()
            engine.mining_model = caller_backed

            output = engine._run_signal_mining(cycle_id=1)

            audit = output["audit"]
            self.assertEqual(audit["track"], "controller")
            self.assertEqual(audit["status"], "completed")
            terminals = {
                row["seed"]: row.get("terminal_kind")
                for row in audit["seeds"]
            }
            self.assertEqual(terminals["hypothesis"], "candidate")
            self.assertEqual(terminals["discovery"], "evidence_unavailable")
            self.assertTrue(output["candidate_refs"])
            staged_ref = output["candidate_refs"][0]
            self.assertTrue(
                staged_ref.startswith("fixture_controller_runway"),
                staged_ref,
            )
            self.assertTrue(
                output["induction_case_ids"][staged_ref]
            )
            self.assertTrue(
                output["validation_case_ids"][staged_ref]
            )
            spec, skill = registry.load_candidate(staged_ref)
            self.assertEqual(spec.signal_id, "fixture_controller_runway")
            self.assertIsNone(skill)

            no_caller_engine_output = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(documents=documents),
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace2"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            no_caller_engine_output._active_sampling_manifest = manifest
            role_output = no_caller_engine_output._run_signal_mining(cycle_id=1)
            self.assertNotEqual(role_output["audit"].get("track"), "controller")

    def test_controller_mining_audit_reports_true_modality_metrics(self) -> None:
        class FakeNarrativeCaller:
            def complete_json(self, *, stage, **_kwargs):
                if stage == "mining_candidate_materialize":
                    payload = dict(_kwargs["payload"])
                    if not payload.get("last_issues"):
                        return ({"spec": {}}, AgentUsage(llm_calls=1))
                    stable = registry.latest_spec("revenue_growth_yoy")
                    spec = {
                        **stable.to_dict(),
                        "signal_id": "fixture_narrative_order",
                        "version": 1,
                    }
                    spec["definition"]["description"] = (
                        "Measure the latest point-in-time year-over-year "
                        "revenue growth from cited spans with a stricter "
                        "positive threshold."
                    )
                    spec["parameters"]["positive_min"] = 0.15
                    # The retrieval declares the evidence family while the
                    # cited documents carry the concrete source type; the
                    # two vocabularies must stay interchangeable.
                    raw_retrieval = dict(spec.get("raw_retrieval") or {})
                    raw_retrieval["source_types"] = ["news"]
                    spec["raw_retrieval"] = raw_retrieval
                    growth = sec_company_facts_content(
                        ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                        ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                    )
                    return (
                        {
                            "spec": spec,
                            "skill": None,
                            "tests": [
                                {
                                    "name": "growth_positive",
                                    "expected": "positive",
                                    "as_of": "2025-02-01T00:00:00+00:00",
                                    "documents": [
                                        {
                                            "source_type": "company_news",
                                            "content": growth,
                                        }
                                    ],
                                }
                            ],
                        },
                        AgentUsage(llm_calls=1),
                    )
                view = dict(_kwargs["payload"])
                if view.get("seed") == "discovery":
                    return (
                        {"action": "record_deferred", "rationale": ["Stop."]},
                        AgentUsage(llm_calls=1),
                    )
                if not view.get("known_event_refs"):
                    return (
                        {
                            "action": "fetch_evidence",
                            "rationale": ["Fetch news."],
                            "case_refs": view["case_refs"][:2],
                            "source_families": ["news"],
                            "max_documents": 2,
                        },
                        AgentUsage(llm_calls=1),
                    )
                if dict(view.get("last_action_result", {})).get(
                    "action"
                ) != "read_span":
                    event_ref = sorted(view.get("known_event_refs", ()))[0]
                    return (
                        {
                            "action": "read_span",
                            "rationale": ["Read the event text."],
                            "event_ref": event_ref,
                        },
                        AgentUsage(llm_calls=1),
                    )
                needs = view.get("backlog_needs") or []
                return (
                    {
                        "action": "propose_candidate",
                        "rationale": ["Narrative headline contrast."],
                        "candidate": {
                            "measurement": {
                                "observable": (
                                    "controller_fixture_order_confirmed"
                                ),
                                "value_kind": "boolean",
                                "normalization": (
                                    "presence per case over the "
                                    "point-in-time narrative window"
                                ),
                                "predicate": {
                                    "modality": "narrative",
                                    "source_families": ["news"],
                                    "lookback_days": 180,
                                    "semantic_condition": (
                                        "news confirms a definitive purchase "
                                        "agreement"
                                    ),
                                },
                            },
                            "falsifiers": [
                                {
                                    "condition": (
                                        "Positives carry no confirming order "
                                        "news in the window."
                                    ),
                                    "expected_observation": (
                                        "Presence rate does not separate "
                                        "groups."
                                    ),
                                }
                            ],
                            "evidence_refs": [
                                sorted(view.get("known_event_refs", ()))[0]
                            ],
                        },
                        "need_dispositions": [
                            {
                                "need_refs": [row["need_ref"]],
                                "disposition": "new_measurement",
                                "signal_refs": [],
                                "rationale": ["Covered by the new measure."],
                            }
                            for row in needs
                        ],
                    },
                    AgentUsage(llm_calls=1),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = (
                *(make_case(f"narr_pos_{index}", 4.0) for index in range(2)),
                *(make_case(f"narr_ctl_{index}", 1.1) for index in range(2)),
            )
            documents = []
            for index, case in enumerate(cases):
                documents.append(
                    RawInfoDocument.create(
                        document_id=(
                            f"test_provider:cik_0000000123:company_news:"
                            f"narr_{index}"
                        ),
                        company_id=case.company_id,
                        source_type="company_news",
                        published_at=NOW,
                        available_at=NOW,
                        content=json.dumps(
                            {
                                "title": (
                                    f"Masked Corp secures purchase order "
                                    f"{index}"
                                ),
                                "summary": (
                                    "Masked Corp announced a definitive "
                                    "purchase agreement valued at "
                                    "approximately $120 million."
                                ),
                            }
                        ),
                    )
                )
                documents.append(
                    RawInfoDocument.create(
                        document_id=(
                            f"test_provider:cik_0000000123:financials:"
                            f"facts_{index}"
                        ),
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    )
                )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(documents=tuple(documents)),
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            manifest = build_slow_sampling_manifest(
                cases,
                cycle_id=1,
                base_seed="controller-narrative",
                dev_limit=4,
                check_limit=4,
            )
            engine._active_sampling_manifest = manifest

            caller_backed = EmptyMiningModel()
            caller_backed.caller = FakeNarrativeCaller()
            engine.mining_model = caller_backed

            output = engine._run_signal_mining(cycle_id=1)

            audit = output["audit"]
            self.assertEqual(audit["track"], "controller")
            self.assertEqual(audit["status"], "completed")
            metrics = audit["modality_metrics"]
            self.assertEqual(metrics["eligible_narrative_seed_count"], 2)
            self.assertEqual(metrics["narrative_exploration_completed"], 2)
            self.assertEqual(metrics["narrative_unavailable_count"], 0)
            self.assertEqual(metrics["narrative_read_count"], 1)
            self.assertEqual(metrics["narrative_candidate_count"], 1)
            self.assertEqual(metrics["narrative_materialization_count"], 1)
            self.assertEqual(metrics["narrative_validation_count"], 1)
            self.assertTrue(output["candidate_refs"])

    def test_fixture_with_no_visible_documents_is_unavailable_by_construction(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            from stock_opportunity_agent.research.signal_evolution import (
                SignalCandidateValidator,
            )

            validator = SignalCandidateValidator(registry, llm_runner=None)
            stable = registry.latest_spec("revenue_growth_yoy")
            spec = SignalSpec(
                **{
                    **stable.__dict__,
                    "signal_id": "fixture_visibility_measurement",
                    "version": 1,
                    "description": (
                        "Measure point-in-time revenue growth scaled to the "
                        "fixture visibility corpus."
                    ),
                    "parameters": {**stable.parameters, "positive_min": 0.15},
                }
            )
            future_doc = {
                "source_type": "financials",
                "published_at": "2025-06-01T00:00:00+00:00",
                "available_at": "2025-06-01T00:00:00+00:00",
                "content": '"val": 125.0',
            }
            abstain = validator.validate(
                spec,
                skill=None,
                tests=[
                    {
                        "name": "unavailable_before_evidence",
                        "expected": "unavailable",
                        "as_of": "2025-01-01T00:00:00+00:00",
                        "documents": [future_doc],
                    }
                ],
            )
            self.assertTrue(abstain.accepted, abstain.reasons)

            premature = validator.validate(
                spec,
                skill=None,
                tests=[
                    {
                        "name": "expects_value_without_evidence",
                        "expected": "positive",
                        "as_of": "2025-01-01T00:00:00+00:00",
                        "documents": [future_doc],
                    }
                ],
            )
            self.assertFalse(premature.accepted)
            self.assertTrue(
                any(
                    "no point-in-time visible documents" in str(reason)
                    for reason in premature.reasons
                ),
                premature.reasons,
            )

    def test_two_slow_only_cycles_feed_committed_first_cycle_to_reflection(self) -> None:
        class ReflectingMiningModel(EmptyMiningModel):
            def __init__(self) -> None:
                self.reflection_payloads = []

            def reflect_feedback(self, payload):
                self.reflection_payloads.append(payload)
                episodes = [
                    {
                        "episode_ref": payload["episode_slots"][index],
                        "source_refs": [unit["feedback_ref"]],
                        "reflection": "Preserve this exact completed-cycle outcome.",
                        "unresolved_questions": [],
                    }
                    for index, unit in enumerate(payload["feedback_units"])
                ]
                return AgentStep(
                    {
                        "episode_reflections": episodes,
                        "lesson_additions": [],
                    },
                    metadata={
                        "canonicalized_nested_refs": {
                            "slow-history:nested-locator": episodes[0][
                                "source_refs"
                            ][0]
                        }
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            snapshot = registry.freeze()
            workspace = EvolutionWorkspace(root / "workspace")
            model = ReflectingMiningModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=tuple(
                    make_case(f"slow_only_{index}", 2.5 if index % 2 else 1.2)
                    for index in range(1, 13)
                ),
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            empty_validation = SlowLoopValidation(
                mined_candidates=(),
                updated_candidates=(),
                validated_candidates={},
                provisional_candidates={},
                rejected={},
                refined_hypotheses={},
                input_registry_version=snapshot.version,
                input_registry_hash=snapshot.registry_hash,
                input_signal_refs=tuple(spec.ref for spec in snapshot.specs),
            )

            for cycle_id in (1, 2):
                workspace.start_or_resume_cycle(
                    run_contract_hash="slow-only-contract",
                    target_plan_rounds=0,
                    cycle_mode="slow_only",
                    initial_signal_registry_version=snapshot.version,
                    initial_signal_registry_hash=snapshot.registry_hash,
                    observed_signal_registry_version=registry.version,
                    observed_signal_registry_hash=registry.freeze().registry_hash,
                    max_slow_cycles=2,
                )
                with mock.patch.object(
                    engine, "_validate_cycle", return_value=empty_validation
                ):
                    result = engine.run_cycle(
                        cycle_id=cycle_id,
                        input_snapshot=registry.freeze(),
                    )
                workspace.stage_slow_result(
                    cycle_id=cycle_id,
                    result=result.to_dict(),
                )
                workspace.complete_cycle(
                    cycle_id=cycle_id,
                    observed_signal_registry_version=registry.version,
                    observed_signal_registry_hash=registry.freeze().registry_hash,
                )

            self.assertEqual(workspace.last_completed_round, 0)
            self.assertEqual(workspace.last_completed_cycle, 2)
            self.assertEqual(len(model.reflection_payloads), 1)
            self.assertTrue(model.reflection_payloads[0]["feedback_units"])
            second_input = workspace.load_slow_input(2)
            self.assertEqual(
                second_input["source_cutoff"],
                {"committed_fast_round": 0, "committed_slow_cycle": 1},
            )
            first_manifest = workspace.load_slow_input(1)[
                "sampling_manifest"
            ]
            second_manifest = second_input["sampling_manifest"]
            # Fresh per-cycle permutation: cohorts rotate, and evaluation
            # hygiene is per candidate (proposal-cycle dev cohort plus own
            # prior evaluation cases), not a global one-way pool.
            self.assertNotEqual(
                first_manifest["dev_case_ids"],
                second_manifest["dev_case_ids"],
            )
            self.assertNotEqual(
                first_manifest["check_case_ids"],
                second_manifest["check_case_ids"],
            )
            second_memory = workspace.load_slow_memory(2)
            prior_cycle_refs = {
                row["feedback_ref"]
                for row in second_input["feedback_rows"]
                if row["subject_ref"] == "cycle-0001"
            }
            self.assertTrue(prior_cycle_refs)
            self.assertTrue(
                prior_cycle_refs
                <= set(second_memory["processed_feedback_refs"])
            )
            self.assertEqual(
                set(second_memory["model_view_manifest"]["required_refs"]),
                prior_cycle_refs,
            )
            self.assertEqual(
                second_memory["model_view_manifest"]["max_items"], 12
            )
            self.assertEqual(
                second_memory["model_view_manifest"][
                    "canonicalized_nested_refs"
                ],
                {
                    "slow-history:nested-locator": second_memory[
                        "processed_feedback_refs"
                    ][0]
                },
            )

    def test_slow_memory_rejects_canonicalized_ref_to_unprocessed_owner(self) -> None:
        value = {
            "schema_version": "slow-memory-v1",
            "cycle_id": 1,
            "contract_hash": "contract",
            "input_hash": "input",
            "parent_memory_hash": "",
            "reflection_work_hash": "work",
            "status": "failed",
            "processed_feedback_refs": [],
            "pending_feedback_refs": ["feedback-1"],
            "episode_reflections": [],
            "lesson_additions": [],
            "model_view_manifest": {
                "canonicalized_nested_refs": {
                    "slow-history:nested-locator": "feedback-1"
                }
            },
            "usage_ref": None,
            "failure_ref": "failed",
        }

        with self.assertRaisesRegex(ValidationError, "canonicalized refs"):
            validate_slow_memory(
                value,
                available_feedback_refs=("feedback-1",),
                available_source_refs=("feedback-1",),
            )

    def test_validator_rejects_definition_implementation_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            stable = registry.load_spec("revenue_growth_yoy:v1")
            candidate = replace(
                stable,
                signal_id="segment_breadth",
                description="Measure breadth across reported business segments.",
            )
            validator = SignalCandidateValidator(registry, llm_runner=None)

            result = validator.validate(candidate, skill=None, tests=())

            self.assertFalse(result.accepted)
            self.assertTrue(
                any("definition-to-implementation mismatch" in item for item in result.reasons)
            )

    def test_handled_pipeline_failures_emit_typed_progress_before_continuing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            events = []
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("progress_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                on_progress=events.append,
            )
            empty_output = {
                "candidate_refs": (),
                "induction_case_ids": {},
                "validation_case_ids": {},
                "failures": {},
                "audit": {"status": "completed"},
            }

            with mock.patch.object(
                engine,
                "_run_signal_mining",
                side_effect=ValidationError("identity boundary failed"),
            ), mock.patch.object(
                engine, "_run_signal_update", return_value=empty_output
            ):
                validation = engine._validate_cycle(registry.freeze(), cycle_id=1)

            self.assertIn("slow_loop:mining_pipeline", validation.rejected)
            self.assertEqual(
                events,
                [
                    {
                        "event_type": "slow_pipeline_failed",
                        "cycle_id": 1,
                        "pipeline": "mining",
                        "error_type": "ValidationError",
                        "error": "identity boundary failed",
                        "usage": {"llm_calls": 0, "tokens": 0, "cost": 0.0},
                    }
                ],
            )

            events.clear()
            with mock.patch.object(
                engine,
                "_run_signal_mining",
                side_effect=RuntimeError("unanticipated local shape"),
            ), mock.patch.object(
                engine, "_run_signal_update", return_value=empty_output
            ) as update:
                validation = engine._validate_cycle(registry.freeze(), cycle_id=3)

            update.assert_called_once()
            self.assertIn("slow_loop:mining_pipeline", validation.rejected)
            self.assertIn(
                "unexpected_pipeline_failure",
                validation.rejected["slow_loop:mining_pipeline"][0],
            )
            self.assertEqual(events[0]["error_type"], "RuntimeError")

            with mock.patch.object(
                engine,
                "_run_signal_mining",
                side_effect=OpenAIClientError("provider contract failed"),
            ), mock.patch.object(engine, "_run_signal_update") as update:
                with self.assertRaisesRegex(OpenAIClientError, "provider contract"):
                    engine._validate_cycle(registry.freeze(), cycle_id=4)
            update.assert_not_called()

            events.clear()
            with mock.patch.object(
                engine, "_run_signal_mining", return_value={
                    **empty_output,
                    "refined_hypotheses": {},
                }
            ), mock.patch.object(
                engine,
                "_run_signal_update",
                side_effect=ValidationError("response could not be normalized"),
            ):
                validation = engine._validate_cycle(registry.freeze(), cycle_id=2)

            self.assertIn("slow_loop:update_pipeline", validation.rejected)
            self.assertEqual(
                events,
                [
                    {
                        "event_type": "slow_pipeline_failed",
                        "cycle_id": 2,
                        "pipeline": "update",
                        "error_type": "ValidationError",
                        "error": "response could not be normalized",
                        "usage": {"llm_calls": 0, "tokens": 0, "cost": 0.0},
                    }
                ],
            )

    def test_update_contract_preserves_complete_retrieval_and_rejects_empty_diff(
        self,
    ) -> None:
        from stock_opportunity_agent.research.signal_evolution import (
            validate_signal_update_candidate,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            stable = replace(
                registry.load_spec("revenue_growth_yoy:v1"),
                retrieval_policy=SignalRetrievalPolicy(
                    query_terms=("revenue sales", "annual comparison"),
                    lookback_days=730,
                    comparison_requirement="two comparable annual periods",
                    required_source_groups=(("financials",),),
                    minimum_distinct_periods=2,
                    minimum_period_span_days=300,
                    minimum_observations=3,
                ),
            )
            candidate_spec = {**stable.to_dict(), "version": 2}
            candidate_spec["raw_retrieval"] = {"minimum_observations": 4}
            candidate = {
                "signal_ref": stable.ref,
                "spec": candidate_spec,
                "tests": [candidate_growth_fixture()],
            }

            updated, skill, tests = validate_signal_update_candidate(
                stable.ref,
                candidate,
                stable,
                changed_paths=("spec.raw_retrieval.minimum_observations",),
            )

            self.assertEqual(updated.version, 2)
            self.assertEqual(skill, None)
            self.assertEqual(tests, [candidate_growth_fixture()])
            retrieval = updated.to_dict()["raw_retrieval"]
            self.assertEqual(retrieval["source_types"], ["financials"])
            self.assertEqual(
                retrieval["query_terms"], ["revenue sales", "annual comparison"]
            )
            self.assertEqual(retrieval["lookback_days"], 730)
            self.assertEqual(retrieval["minimum_observations"], 4)

            unchanged = {
                "signal_ref": stable.ref,
                "spec": {**stable.to_dict(), "version": 2},
                "tests": [candidate_growth_fixture()],
            }
            with self.assertRaisesRegex(ValidationError, "no effective change"):
                validate_signal_update_candidate(
                    stable.ref, unchanged, stable, changed_paths=()
                )
            with self.assertRaisesRegex(ValidationError, "unknown path"):
                validate_signal_update_candidate(
                    stable.ref,
                    candidate,
                    stable,
                    changed_paths=("spec.raw_retrieval.query",),
                )
            with self.assertRaisesRegex(ValidationError, "non-empty executable"):
                validate_signal_update_candidate(
                    stable.ref,
                    {**candidate, "tests": []},
                    stable,
                    changed_paths=("spec.raw_retrieval.minimum_observations",),
                )
            with self.assertRaisesRegex(ValidationError, "preserve stable executable"):
                validate_signal_update_candidate(
                    stable.ref,
                    candidate,
                    stable,
                    stable_tests=({"name": "different"},),
                    changed_paths=("spec.raw_retrieval.minimum_observations",),
                )

            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("schema_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            properties = engine._candidate_arguments_schema(clone=True)[
                "properties"
            ]["spec"]["properties"]["raw_retrieval"]["properties"]
            self.assertEqual(
                set(properties),
                {
                    "source_types",
                    "query_terms",
                    "lookback_days",
                    "comparison_requirement",
                    "required_source_groups",
                    "minimum_distinct_periods",
                    "minimum_period_span_days",
                    "minimum_observations",
                },
            )
            self.assertNotIn("query", properties)
            clone_schema = engine._candidate_arguments_schema(clone=True)
            document_required = clone_schema["properties"]["tests"]["items"][
                "properties"
            ]["documents"]["items"]["required"]
            self.assertEqual(
                document_required,
                ["source_type", "available_at", "content"],
            )
            self.assertIn(
                "tests must copy vnext_template.tests byte-for-byte",
                clone_schema["constraints"],
            )

    def test_update_sampling_separates_technical_and_domain_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(make_case(f"unavailable_{index}", 4.0) for index in range(11))
            documents = tuple(
                RawInfoDocument.create(
                    document_id=f"one-period-{index}",
                    company_id=case.company_id,
                    source_type="financials",
                    published_at=NOW,
                    available_at=NOW,
                    content=sec_company_facts_content(
                        ("2024-01-01", "2024-12-31", 100.0, "2025-01-10")
                    ),
                )
                for index, case in enumerate(cases)
            )
            store = RawInfoStore(documents=documents)
            target = {
                "signal_ref": "revenue_growth_yoy:v1",
                "problem_type": "repeated_explicit_misleading",
                "support": {"misleading_attributions": 11},
                "recurring_contexts": [],
            }

            domain_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "domain-workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            domain = domain_engine._run_one_signal_update(
                cycle_id=1,
                target=target,
                cases=cases,
                executor=SignalExecutor(
                    registry.freeze(),
                    store,
                    deterministic_functions=domain_engine.validator.deterministic_functions,
                ),
            )
            domain_selection = domain["audit"]["local_selection"]
            self.assertEqual(domain["audit"]["disposition"], "defer")
            self.assertEqual(
                domain["audit"]["defer_reason"],
                "insufficient_local_induction_or_holdout",
            )
            self.assertEqual(
                domain_selection["available_bucket_counts"]["unavailable"], 11
            )
            self.assertEqual(
                domain_selection["primary_sources"],
                ["domain_unavailable", "domain_unavailable"],
            )
            self.assertEqual(domain_selection["technical_failure_count"], 0)

            def fail_execution(*_args):
                raise ValidationError("fixture execution failed")

            technical_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"two-period-{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 120.0, "2025-01-10"),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            technical_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=technical_store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "technical-workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                deterministic_functions={
                    "financial.revenue_growth_yoy": fail_execution
                },
            )
            technical = technical_engine._run_one_signal_update(
                cycle_id=1,
                target=target,
                cases=cases,
                executor=SignalExecutor(
                    registry.freeze(),
                    technical_store,
                    deterministic_functions=(
                        technical_engine.validator.deterministic_functions
                    ),
                ),
            )
            technical_selection = technical["audit"]["local_selection"]
            self.assertEqual(
                technical_selection["available_bucket_counts"]["unavailable"], 0
            )
            self.assertEqual(technical_selection["technical_failure_count"], 11)
            self.assertEqual(len(technical["audit"]["technical_failures"]), 11)

    def test_company_facts_context_preserves_semantics_offsets_and_periods(self) -> None:
        from stock_opportunity_agent.research.evolution_core import (
            _agent_raw_document_view,
        )

        as_of = datetime(2025, 9, 30, tzinfo=timezone.utc)
        payload = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "label": "Revenue from customers",
                        "units": {
                            "USD": [
                                {"end": "2025-03-31", "val": 100, "filed": "2025-05-01"},
                                {"end": "2025-06-30", "val": 100, "filed": "2025-08-01"},
                                {"end": "2025-06-30", "val": 101, "filed": "2025-08-05"},
                                {"end": "2025-09-30", "val": 999, "filed": "2025-10-15"},
                            ]
                        },
                    },
                    "OperatingIncomeLoss": {
                        "label": "Operating income",
                        "units": {
                            "USD": [
                                {
                                    "start": "2024-01-01",
                                    "end": "2024-03-31",
                                    "fp": "Q1",
                                    "val": 80,
                                    "filed": "2024-05-01",
                                },
                                {
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "fp": "FY",
                                    "val": 350,
                                    "filed": "2025-02-15",
                                },
                                {
                                    "start": "2025-01-01",
                                    "end": "2025-03-31",
                                    "fp": "Q1",
                                    "val": 100,
                                    "filed": "2025-05-01",
                                },
                            ]
                        },
                    },
                }
            }
        }
        content = json.dumps(payload, separators=(",", ":"))
        document = RawInfoDocument.create(
            document_id="company-facts",
            company_id="issuer",
            source_type="sec_company_facts",
            published_at=as_of,
            available_at=as_of,
            content=content,
        )

        view = _agent_raw_document_view(
            document,
            max_content_chars=1_200,
            query="revenue operating income",
        )

        self.assertEqual(view["content_excerpt"], "")
        self.assertEqual(
            view["content_projection"], "sec_company_facts_context_v1"
        )
        concepts = {
            item["concept"]: item for item in view["structured_context"]["concepts"]
        }
        revenue = concepts[
            "RevenueFromContractWithCustomerExcludingAssessedTax"
        ]
        self.assertEqual(revenue["taxonomy"], "us-gaap")
        self.assertEqual(revenue["label"], "Revenue from customers")
        self.assertEqual(revenue["unit"], "USD")
        self.assertEqual(len(revenue["records"]), 2)
        self.assertIn('"val":101', revenue["records"][0]["exact_span"])
        self.assertNotIn('"filed":"2025-10-15"', json.dumps(view))
        operating_income = concepts["OperatingIncomeLoss"]
        self.assertEqual(len(operating_income["records"]), 2)
        self.assertIn('"end":"2025-03-31"', operating_income["records"][0]["exact_span"])
        self.assertIn('"end":"2024-03-31"', operating_income["records"][1]["exact_span"])
        self.assertNotIn('"end":"2024-12-31"', json.dumps(operating_income))
        for concept in concepts.values():
            for record in concept["records"]:
                self.assertEqual(
                    content[record["start"] : record["end"]],
                    record["exact_span"],
                )

    def test_company_facts_context_marks_bounded_omissions_partial(self) -> None:
        from stock_opportunity_agent.research.evolution_core import (
            _agent_raw_document_view,
        )

        as_of = datetime(2025, 9, 30, tzinfo=timezone.utc)
        payload = {
            "facts": {
                "us-gaap": {
                    f"VerboseConcept{index}": {
                        "label": "Very verbose financial concept label " + str(index),
                        "units": {
                            "USD": [
                                {
                                    "end": "2025-06-30",
                                    "val": index,
                                    "filed": "2025-08-01",
                                }
                            ]
                        },
                    }
                    for index in range(12)
                }
            }
        }
        document = RawInfoDocument.create(
            document_id="bounded-company-facts",
            company_id="issuer",
            source_type="sec_company_facts",
            published_at=as_of,
            available_at=as_of,
            content=json.dumps(payload, separators=(",", ":")),
        )

        view = _agent_raw_document_view(
            document, max_content_chars=350, query="financial concept"
        )

        context = view["structured_context"]
        self.assertTrue(context["partial"])
        self.assertGreater(context["omitted_concept_count"], 0)
        self.assertLessEqual(
            len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))),
            350,
        )

    def test_queryless_company_facts_prefers_comparable_operating_concepts(self) -> None:
        from stock_opportunity_agent.research.evolution_core import (
            _agent_raw_document_view,
        )

        as_of = datetime(2025, 9, 30, tzinfo=timezone.utc)
        concepts = {
            "ArbitraryLatestMetric": {
                "label": "Arbitrary latest metric",
                "units": {
                    "USD": [
                        {"end": "2025-09-30", "val": 999, "filed": "2025-09-30"}
                    ]
                },
            },
            "OperatingIncomeLoss": {
                "label": "Operating income",
                "units": {
                    "USD": [
                        {"end": "2025-06-30", "val": 20, "filed": "2025-08-01"},
                        {"end": "2024-06-30", "val": 10, "filed": "2024-08-01"},
                    ]
                },
            },
            "NetCashProvidedByUsedInOperatingActivities": {
                "label": "Operating cash flow",
                "units": {
                    "USD": [
                        {"end": "2025-06-30", "val": 30, "filed": "2025-08-01"},
                        {"end": "2024-06-30", "val": 15, "filed": "2024-08-01"},
                    ]
                },
            },
        }
        document = RawInfoDocument.create(
            document_id="queryless-company-facts",
            company_id="issuer",
            source_type="sec_company_facts",
            published_at=as_of,
            available_at=as_of,
            content=json.dumps({"facts": {"us-gaap": concepts}}, separators=(",", ":")),
        )

        view = _agent_raw_document_view(
            document, max_content_chars=900, query=None
        )
        selected = [
            item["concept"] for item in view["structured_context"]["concepts"]
        ]

        self.assertEqual(
            selected[:2],
            [
                "OperatingIncomeLoss",
                "NetCashProvidedByUsedInOperatingActivities",
            ],
        )
        self.assertNotIn("ArbitraryLatestMetric", selected)

    def test_company_facts_identity_masking_drops_nonliteral_records(self) -> None:
        from stock_opportunity_agent.research.evolution_core import (
            _model_evidence_view,
        )

        as_of = datetime(2025, 9, 30, tzinfo=timezone.utc)
        content = json.dumps(
            {
                "facts": {
                    "custom": {
                        "CustomerConcentration": {
                            "label": "Customer concentration",
                            "units": {
                                "count": [
                                    {
                                        "end": "2025-06-30",
                                        "val": 3,
                                        "filed": "2025-08-01",
                                        "customer": "Acme Corp",
                                    }
                                ]
                            },
                        }
                    }
                }
            },
            separators=(",", ":"),
        )
        document = RawInfoDocument.create(
            document_id="masked-company-facts",
            company_id="issuer",
            source_type="sec_company_facts",
            published_at=as_of,
            available_at=as_of,
            content=content,
        )

        view = _model_evidence_view(
            document,
            index=1,
            aliases=("Acme Corp",),
            query="customer concentration",
        )

        context = view["structured_context"]
        self.assertEqual(context["concepts"], [])
        self.assertEqual(context["redacted_record_count"], 1)
        self.assertTrue(context["partial"])
        self.assertNotIn("Acme Corp", json.dumps(view))

    def test_exploration_company_facts_citations_stay_inside_one_record(self) -> None:
        record_one = '{"end":"2025-06-30","val":101,"filed":"2025-08-05"}'
        record_two = '{"end":"2025-03-31","val":100,"filed":"2025-05-01"}'
        packet = {
            "case_ref": "case-001",
            "evidence": [
                {
                    "document_ref": "document-01",
                    "content_excerpt": "",
                    "structured_context": {
                        "concepts": [
                            {
                                "taxonomy": "us-gaap",
                                "concept": "Revenue",
                                "label": "Revenue from customers",
                                "unit": "USD",
                                "records": [
                                    {"exact_span": record_one, "start": 10, "end": 67},
                                    {"exact_span": record_two, "start": 68, "end": 125},
                                ],
                            }
                        ]
                    },
                }
            ],
        }
        valid = SignalMiningSignature(
            case_ref="case-001",
            observations=(
                SignalMiningObservation(
                    summary="The visible record reported 101.",
                    document_ref="document-01",
                    exact_span='"val":101',
                ),
            ),
        )
        self.assertEqual(
            validate_signal_mining_signatures((valid,), (packet,)), (valid,)
        )
        for invalid_span in (
            '"val":101 "val":100',
            "Revenue from customers",
        ):
            with self.subTest(invalid_span=invalid_span), self.assertRaisesRegex(
                ValidationError, "one supplied record literal"
            ):
                validate_signal_mining_signatures(
                    (
                        replace(
                            valid,
                            observations=(
                                replace(valid.observations[0], exact_span=invalid_span),
                            ),
                        ),
                    ),
                    (packet,),
                )

    def test_queryless_json_excerpt_reaches_recent_dated_records(self) -> None:
        from stock_opportunity_agent.research.evolution_core import _agent_raw_document_view

        as_of = datetime(2025, 9, 30, tzinfo=timezone.utc)
        rows = [{"end": "2009-01-01", "value": index} for index in range(80)]
        rows += [{"end": "2025-06-30", "filed": "2025-08-01", "value": 12345}]
        content = json.dumps({"observations": rows}, separators=(",", ":"))
        document = RawInfoDocument.create(
            document_id="dated", company_id="issuer", source_type="financials",
            published_at=as_of, available_at=as_of, content=content,
        )
        view = _agent_raw_document_view(document, max_content_chars=300)
        self.assertIn('"value":12345', view["content_excerpt"])
        self.assertIn(view["content_excerpt"], content)
        self.assertLessEqual(len(view["content_excerpt"]), 300)
        self.assertEqual(document.content, content)
        prose = RawInfoDocument.create(
            document_id="prose", company_id="issuer", source_type="financials",
            published_at=as_of, available_at=as_of,
            content="Introduction " + "ordinary prose " * 100,
        )
        preview = _agent_raw_document_view(prose, max_content_chars=300)
        self.assertTrue(preview["content_excerpt"].startswith("Introduction"))

    def test_queryless_json_excerpt_starts_at_complete_record_boundary(self) -> None:
        from stock_opportunity_agent.research.evolution_core import _agent_raw_document_view

        as_of = datetime(2025, 9, 30, tzinfo=timezone.utc)
        content = json.dumps(
            {
                "observations": [
                    {"end": "2009-01-01", "value": "x" * 400},
                    {"end": "2025-06-30", "value": 12345},
                ]
            },
            separators=(",", ":"),
        )
        document = RawInfoDocument.create(
            document_id="dated-boundary", company_id="issuer",
            source_type="market_data", published_at=as_of,
            available_at=as_of, content=content,
        )

        excerpt = _agent_raw_document_view(
            document, max_content_chars=200
        )["content_excerpt"]

        self.assertTrue(excerpt.startswith("{"), excerpt)
        self.assertIn('"value":12345', excerpt)

    def test_evidence_window_does_not_split_words_or_numeric_amounts(self) -> None:
        from stock_opportunity_agent.research.evolution_core import _complete_evidence_window

        for text, limit, expected in (
            ("We entered an ELOC agreement.", 17, "We entered an"),
            ("Proceeds were $6,200,000 in total.", 20, "Proceeds were"),
            ("Cash was 100 USD.", 12, "Cash was 100"),
            ("Complete sentence.", 100, "Complete sentence."),
        ):
            with self.subTest(text=text):
                excerpt = _complete_evidence_window(text, 0, limit)
                self.assertEqual(excerpt, expected)
                self.assertIn(excerpt, text)
                self.assertLessEqual(len(excerpt), limit)

    def test_queryless_filing_excerpt_skips_cover_boilerplate(self) -> None:
        from stock_opportunity_agent.research.evolution_core import _agent_raw_document_view

        as_of = datetime(2025, 9, 30, tzinfo=timezone.utc)
        cover = (
            "Commission file number 001. Exact name of registrant. "
            "State of incorporation. Securities registered and trading symbol. "
        ) * 20
        substance = (
            "Business operations revenue increased 18 percent. Gross profit and "
            "operating income improved while cash flow funded capital resources. "
        ) * 8
        document = RawInfoDocument.create(
            document_id="substantive-filing", company_id="issuer", source_type="10-k",
            published_at=as_of, available_at=as_of, content=cover + substance,
        )

        excerpt = _agent_raw_document_view(
            document, max_content_chars=400
        )["content_excerpt"]

        self.assertIn("Business operations revenue", excerpt)
        self.assertNotIn("Commission file number", excerpt)

    def test_queryless_filing_repetition_cannot_displace_operating_evidence(self) -> None:
        from stock_opportunity_agent.research.evolution_core import _query_relevant_excerpt

        risk = (
            "Our business operations and results face business risk. "
            "Business operations could suffer adverse results. "
        ) * 30
        facts = (
            "Revenue increased 18 percent to $240 million from $203 million. "
            "Gross profit reached $80 million and operating income was $25 million. "
            "Research and development expense was $12 million. "
        ) * 3
        for source_type in ("10-k", "20-f", "40-f", "6-k", "8-k", "sec_filing"):
            with self.subTest(source_type=source_type):
                document = RawInfoDocument.create(
                    document_id="window-repetition", company_id="issuer",
                    source_type=source_type, published_at=NOW, available_at=NOW,
                    content=risk + facts,
                )
                excerpt, _truncated = _query_relevant_excerpt(
                    document, query=None, max_chars=400,
                )
                self.assertIn("Revenue increased", excerpt)
                self.assertIn(excerpt, document.content)

    def test_exploration_literal_view_drops_model_authored_summary(self) -> None:
        from stock_opportunity_agent.research.signal_evolution import (
            _comparison_ready_exploration_signature,
            _literal_only_signature_view,
        )

        signature = SignalMiningSignature(
            case_ref="case-001",
            observations=(
                SignalMiningObservation(
                    summary="Invented growth from 10 to 20.",
                    document_ref="document-01",
                    exact_span="Revenue was 20 in the quarter.",
                ),
                SignalMiningObservation(
                    summary="Cover page.",
                    document_ref="document-02",
                    exact_span="Exact name of registrant as specified in its charter.",
                ),
            ),
        )

        filtered, reasons = _comparison_ready_exploration_signature(signature)
        view = _literal_only_signature_view(
            filtered,
            {
                "evidence": [
                    {
                        "document_ref": "document-01",
                        "source_type": "sec_company_facts",
                        "structured_context": {
                            "concepts": [
                                {
                                    "taxonomy": "us-gaap",
                                    "concept": "Revenue",
                                    "label": "Revenue from customers",
                                    "unit": "USD",
                                    "records": [
                                        {
                                            "exact_span": (
                                                '{"end":"2024-06-30",'
                                                '"val":"Revenue was 10 in the prior quarter."}'
                                            )
                                        },
                                        {
                                            "exact_span": (
                                                '{"end":"2025-06-30",'
                                                '"val":"Revenue was 20 in the quarter."}'
                                            )
                                        }
                                    ],
                                }
                            ]
                        },
                    }
                ]
            },
        )

        self.assertEqual(len(filtered.observations), 1)
        self.assertTrue(reasons)
        self.assertNotIn("Invented growth", json.dumps(view))
        self.assertIn("compare exact_span only", view["observations"][0]["summary"])
        self.assertIn("concept=Revenue", view["observations"][0]["summary"])
        self.assertIn("label=Revenue from customers", view["observations"][0]["summary"])
        self.assertEqual(len(view["observations"]), 2)
        self.assertIn(
            "Revenue was 10 in the prior quarter",
            view["observations"][1]["exact_span"],
        )

    def test_exploration_literal_view_preserves_long_comparable_records(self) -> None:
        from stock_opportunity_agent.research.signal_evolution import (
            _literal_only_signature_view,
        )

        current = json.dumps({"end": "2025-06-30", "val": 120})
        prior = json.dumps({
            "end": "2024-06-30", "val": 100,
            "source_note": "Original filing record with source-owned context. " * 8,
        })
        packet = {"evidence": [{
            "document_ref": "document-01", "source_type": "company_facts",
            "structured_context": {"concepts": [{
                "taxonomy": "us-gaap", "concept": "OperatingIncomeLoss",
                "label": "Operating income", "unit": "USD",
                "records": [{"exact_span": span} for span in (current, prior)],
            }]},
        }]}
        observations = tuple(SignalMiningObservation(
            summary="Source record.", document_ref="document-01", exact_span=span,
        ) for span in (current, prior))
        self.assertGreater(len(prior), 240)
        for selected in (observations[:1], observations):
            view = _literal_only_signature_view(
                SignalMiningSignature(case_ref="case-001", observations=selected), packet,
            )
            self.assertEqual(
                [item["exact_span"] for item in view["observations"]],
                [current, prior],
            )

    def test_exploration_comparison_filter_drops_generic_6k_admin_phrases(self) -> None:
        from stock_opportunity_agent.research.signal_evolution import (
            _comparison_ready_exploration_signature,
        )

        signature = SignalMiningSignature(
            case_ref="case-001",
            observations=tuple(
                SignalMiningObservation(
                    summary="Visible filing text.",
                    document_ref=f"document-{index:02d}",
                    exact_span=literal,
                )
                for index, literal in enumerate(
                    (
                        "For the month of July 2025",
                        "On July 7, 2025, the Registrant issued a press release.",
                        (
                            "On March 26, 2025, the Registrant issued a press "
                            "release, a copy of which is attached hereto as Exhibit 99.1"
                        ),
                        (
                            "On July 7, 2025, the Registrant issued a press release "
                            "announcing a merger agreement."
                        ),
                    ),
                    start=1,
                )
            ),
        )

        filtered, reasons = _comparison_ready_exploration_signature(signature)

        self.assertEqual(len(filtered.observations), 1)
        self.assertIn("merger agreement", filtered.observations[0].exact_span)
        self.assertEqual(len(reasons), 1)
        self.assertIn("3 observation(s)", reasons[0])

    def test_exploration_literal_view_omits_ambiguous_structured_semantics(self) -> None:
        from stock_opportunity_agent.research.signal_evolution import (
            _literal_only_signature_view,
        )

        signature = SignalMiningSignature(
            case_ref="case-001",
            observations=(
                SignalMiningObservation(
                    summary="Untrusted.",
                    document_ref="document-01",
                    exact_span='"val":100',
                ),
            ),
        )
        concepts = [
            {
                "taxonomy": "us-gaap",
                "concept": concept,
                "label": concept,
                "unit": "USD",
                "records": [{"exact_span": '{"end":"2025-06-30","val":100}'}],
            }
            for concept in ("Revenue", "OperatingIncomeLoss")
        ]

        view = _literal_only_signature_view(
            signature,
            {
                "evidence": [
                    {
                        "document_ref": "document-01",
                        "source_type": "sec_company_facts",
                        "structured_context": {"concepts": concepts},
                    }
                ]
            },
        )

        self.assertNotIn("source-owned structured context", view["observations"][0]["summary"])

    def test_exploration_packet_masks_case_local_natural_brand(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = replace(
                make_case("aflac_probe", 4.0),
                basic_info={
                    "company_name": "Aflac Inc / AFLAC INC",
                    "ticker": "AFL",
                },
            )
            document = RawInfoDocument.create(
                document_id="aflac-filing",
                company_id=case.company_id,
                source_type="10-k",
                published_at=NOW,
                available_at=NOW,
                content=(
                    "Aflac Incorporated reported revenue growth and operating income "
                    "improvement with stronger cash flow and liquidity. " * 20
                ),
            )
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(documents=(document,)),
                discovery_cases=(make_case("other_discovery_issuer", 1.1),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                identity_cases=(case,),
            )

            packet, _audit = engine._mining_evidence_packet(
                "case-001", case, source_types=("10-k",), query=None,
                lookback_days=365, reveal_label=False,
            )
            serialized = json.dumps(packet)

            self.assertNotIn("Aflac", serialized)
            self.assertIn("[MASKED_COMPANY]", serialized)

    def test_model_evidence_masks_named_target_affiliate_relation(self) -> None:
        from stock_opportunity_agent.research.evolution_core import (
            _model_evidence_view,
        )

        document = RawInfoDocument.create(
            document_id="affiliate-filing",
            company_id="issuer",
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content=(
                "Clean Earth, a division of Harsco Corporation, reported revenue "
                "growth and operating cash flow improvement. " * 20
            ),
        )

        view = _model_evidence_view(
            document,
            index=1,
            aliases=("Harsco Corporation",),
            query=None,
        )
        serialized = json.dumps(view)

        self.assertNotIn("Harsco", serialized)
        self.assertNotIn("Clean Earth", serialized)
        self.assertIn("[MASKED_COMPANY]", serialized)

    def test_fixture_unavailable_does_not_hide_technical_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            spec = SignalSpec(
                signal_id="fixture_failure_probe", version=1, category="financial",
                description="Measure year-over-year revenue growth.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy", source_types=("financials",),
            )
            def broken_function(*_args):
                raise ValueError("deliberate implementation failure")
            validator = SignalCandidateValidator(
                registry, llm_runner=None,
                deterministic_functions={"financial.revenue_growth_yoy": broken_function},
            )
            fixture = {**candidate_growth_fixture(), "expected": "unavailable"}
            result = validator.validate(spec, skill=None, tests=(fixture,))
            self.assertFalse(result.accepted)
            self.assertIn("technical execution failure", result.reasons[0])

    def test_fixture_failure_reports_pre_execution_coverage_gap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            spec = SignalSpec.from_dict({
                "signal_id": "fixture_coverage_probe", "version": 1,
                "category": "financial",
                "definition": {"description": "Measure year-over-year revenue growth."},
                "execution": {"type": "deterministic", "function": "financial.revenue_growth_yoy"},
                "raw_retrieval": {"source_types": ["financials"], "minimum_observations": 1},
                "evidence_policy": {"require_source": True, "require_timestamp": True, "require_exact_span": True},
            })
            validator = SignalCandidateValidator(registry, llm_runner=None)
            result = validator.validate(spec, skill=None, tests=(candidate_growth_fixture(),))
            self.assertFalse(result.accepted)
            self.assertIn("observations=0/1", result.reasons[0])
            self.assertIn("resolution=unresolved", result.reasons[0])

    def test_candidate_identity_guard_preserves_ticker_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            candidate = SignalSpec(
                signal_id="case_sensitive_probe", version=1, category="financial",
                description=(
                    "Measure year-over-year revenue growth while checking five "
                    "customers and cash for the next period."
                ),
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy", source_types=("financials",),
            )
            validator = SignalCandidateValidator(
                registry, llm_runner=None, forbidden_identity_terms=("FIVE", "CASH", "NEXT"),
            )
            self.assertTrue(validator.validate(candidate, skill=None, tests=(candidate_growth_fixture(),)).accepted)
            for ticker in ("FIVE", "CASH", "NEXT"):
                with self.subTest(ticker=ticker):
                    result = validator.validate(
                        replace(candidate, description=f"Measure {ticker} customer activity."),
                        skill=None, tests=(candidate_growth_fixture(),),
                    )
                    self.assertFalse(result.accepted)
                    self.assertTrue(any("identity leaked" in reason for reason in result.reasons))

    def test_mining_context_masks_persisted_reflections_without_mutating_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            case = make_case("fixture_issuer", 4.0)
            case = replace(
                case,
                basic_info={
                    **case.basic_info,
                    "company_name": "Kinross Gold Corporation",
                    "ticker": "KGC",
                },
            )
            memory = PlanMetaMemory(entries=(RoundMetaEntry(
                round_id=1,
                evidence_refs=("plan-1",),
                search_implications=(
                    "fixture_issuer has a clinical milestone and future business plans.",
                ),
            ),))
            original = memory.model_view()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("other_discovery_issuer", 1.1),),
                meta_memory=memory,
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                identity_cases=(case,),
            )
            engine.slow_role_identity_guards += ("Future Holdings", "Business Systems")
            (engine.workspace.root / "capability_backlog.json").write_text(
                json.dumps(
                    {
                        "schema_version": "capability-gap-report-v3",
                        "items": [],
                        "signal_need_items": [
                            {
                                "kind": "unmatched_signal_need",
                                "need_ref": "need-opaque",
                                "need": "What did Kinross disclose?",
                                "sources": [
                                    {
                                        "source_ref": f"plan-1:{case.case_id}",
                                        "source_round": 1,
                                        "source_fingerprint": "fingerprint",
                                        "original_need": "What did Kinross disclose?",
                                        "stop_reason": "no_signal_match",
                                    }
                                ],
                                "source_rounds": [1],
                                "source_fingerprints": ["fingerprint"],
                                "stop_reasons": ["no_signal_match"],
                                "occurrences": 1,
                                "source_count": 1,
                                "status": "open",
                            }
                        ],
                        "technical_failures": [],
                        "diagnostic_attempts": [
                            {"attempt_ref": "/private/path/attempt.json"}
                        ],
                        "open_count": 1,
                        "resolved_count": 0,
                    }
                ),
                encoding="utf-8",
            )

            context = engine._mining_context(cycle_id=1)

            self.assertNotIn("fixture_issuer", json.dumps(context["meta_info"]))
            self.assertIn("clinical milestone", json.dumps(context["meta_info"]))
            self.assertIn("future business plans", json.dumps(context["meta_info"]))
            rendered_backlog = json.dumps(context["capability_backlog"])
            self.assertNotIn("fixture_issuer", rendered_backlog)
            self.assertNotIn("Kinross", rendered_backlog)
            self.assertNotIn("/private/path", rendered_backlog)
            self.assertIn("source-", rendered_backlog)
            self.assertEqual(memory.model_view(), original)

            other = make_case("other_history_issuer", 1.1)
            engine._discovery_cases_by_id[other.case_id] = other
            source_rows = [
                {"need_ref": f"need-{index}", "sources": [{"source_ref": f"plan-1:{item.case_id}"}]}
                for index, item in enumerate((case, other, case))
            ]
            source_snapshot = json.dumps(source_rows)
            projected = engine._mining_capability_backlog_view(
                engine._mask_owned_backlog_identities({"signal_need_items": source_rows})
            )["signal_need_items"]
            sources = [row["sources"][0] for row in projected]
            self.assertEqual(sources[0]["source_ref"], sources[2]["source_ref"])
            self.assertNotEqual(sources[0]["source_ref"], sources[1]["source_ref"])
            self.assertNotEqual(sources[0]["source_case_ref"], sources[1]["source_case_ref"])
            self.assertEqual(json.dumps(source_rows), source_snapshot)

    def test_slow_start_recovers_backlog_after_post_commit_interruption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            base_record = make_record(
                "interrupted_backlog_plan", 1.0, (1.0, 0.0)
            )
            trajectory = replace(
                base_record.trajectories[0],
                final_state=ResearchState(
                    decision=ResearchDecision.FINALIZE,
                    next_information_needs=(
                        "Measure committed order conversion before the catalyst.",
                    ),
                ),
                stop_reason=RuntimeStopReason.NO_SIGNAL_MATCH,
            )
            record = replace(
                base_record,
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
                signal_registry_version=snapshot.version,
                signal_registry_hash=snapshot.registry_hash,
                run_contract_hash="contract-hash",
            )
            stale = {
                "schema_version": "capability-gap-report-v3",
                "items": [],
                "signal_need_items": [],
                "technical_failures": [],
                "diagnostic_attempts": [],
                "open_count": 0,
                "resolved_count": 0,
            }
            (workspace.root / "capability_backlog.json").write_text(
                json.dumps(stale), encoding="utf-8"
            )
            discovery_cases = tuple(
                [make_case(f"recovery_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"recovery_control_{index}", 1.1) for index in range(4)]
            )
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"recovery-financial-{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 120.0, "2025-01-10"),
                        ),
                    )
                    for index, case in enumerate(discovery_cases)
                )
            )
            mining_model = EmptyMiningModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=discovery_cases,
                meta_memory=workspace.restore_meta(),
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(discovery_cases) // 2),
            )

            engine.run_cycle(cycle_id=1, input_snapshot=snapshot)

            refreshed = json.loads(
                (workspace.root / "capability_backlog.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(refreshed["signal_need_items"]), 1)
            self.assertEqual(
                refreshed["signal_need_items"][0]["sources"][0]["source_round"],
                1,
            )
            sent_needs = mining_model.requests[0]["capability_backlog"][
                "signal_need_items"
            ]
            self.assertEqual(len(sent_needs), 1)
            self.assertEqual(
                sent_needs[0]["need"],
                "Measure committed order conversion before the catalyst.",
            )
            self.assertEqual(
                mining_model.requests[0]["h1_contract_version"],
                "signal-mining-hypothesis-v7",
            )

    def test_mining_sample_basis_rejects_malformed_persisted_values(self) -> None:
        payload = {
            "hypothesis_id": "h1-c0001-s01",
            "disposition": "inconclusive",
            "rationale": ["The supplied comparison is incomplete."],
            "candidate": None,
            "sample_basis": "positive-case",
        }

        with self.assertRaisesRegex(ValidationError, "must be an object"):
            SignalMiningDecision.from_dict(payload)

        payload["sample_basis"] = {
            "positive_refs": "positive-case",
            "control_refs": ["control-case"],
        }
        with self.assertRaisesRegex(ValidationError, "string arrays"):
            SignalMiningDecision.from_dict(payload)

    def test_slow_search_fingerprint_changes_only_for_relevant_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = (
                make_case("fingerprint_positive", 4.0),
                make_case("fingerprint_control", 1.1),
            )
            store = RawInfoStore()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(cases)),
            )
            snapshot = registry.freeze()
            initial = engine._search_input_fingerprint(snapshot)
            store.append(
                RawInfoDocument.create(
                    document_id="unrelated-document",
                    company_id="outside_discovery",
                    source_type="news",
                    published_at=NOW,
                    available_at=NOW,
                    content="This document cannot affect the frozen Discovery set.",
                )
            )

            self.assertEqual(engine._search_input_fingerprint(snapshot), initial)

            store.append(
                RawInfoDocument.create(
                    document_id="relevant-document",
                    company_id=cases[0].company_id,
                    source_type="news",
                    published_at=NOW,
                    available_at=NOW,
                    content="Management disclosed a new point-in-time observation.",
                )
            )

            self.assertNotEqual(engine._search_input_fingerprint(snapshot), initial)

    def test_item1_excerpt_skips_linked_navigation_and_filing_boilerplate(
        self,
    ) -> None:
        document = RawInfoDocument.create(
            document_id="filing-profile",
            company_id="company-profile",
            source_type="10-k",
            published_at=NOW,
            available_at=NOW,
            content=(
                "<html><body>"
                '<div><a href="#item1">ITEM 1. BUSINESS</a></div>'
                "<div>2</div>"
                '<div><a href="#item1a">ITEM 1A. RISK FACTORS</a></div>'
                '<div id="item1">ITEM 1. BUSINESS</div>'
                "<div>Cautionary Statement Regarding Forward-Looking Statements. "
                "These forward-looking statements involve risks.</div>"
                "<div>Reports are available on our website and filed with the "
                "Securities Exchange Commission. This Annual Report on Form 10-K "
                "is not incorporated by reference.</div>"
                "<div>We design and manufacture precision inspection products and "
                "provide monitoring services to semiconductor customers in global "
                "markets. Our business operates through two technology segments and "
                "offers recurring software solutions for advanced factories.</div>"
                '<div id="item1a">ITEM 1A. RISK FACTORS</div>'
                "<div>Demand volatility may harm future results.</div>"
                "</body></html>"
            ),
        )

        excerpt = _item1_business_excerpt((document,))

        self.assertIsNotNone(excerpt)
        assert excerpt is not None
        self.assertTrue(excerpt.startswith("We design and manufacture"))
        self.assertNotIn("forward-looking", excerpt.casefold())
        self.assertNotIn("Demand volatility", excerpt)

    def test_item1_excerpt_rejects_navigation_page_number(self) -> None:
        document = RawInfoDocument.create(
            document_id="filing-navigation-only",
            company_id="company-navigation",
            source_type="10-k",
            published_at=NOW,
            available_at=NOW,
            content=(
                "<html><body>"
                '<div><a href="#item1">ITEM 1. BUSINESS</a></div>'
                "<div>1</div>"
                '<div><a href="#item1a">ITEM 1A. RISK FACTORS</a></div>'
                "<div>5</div>"
                "</body></html>"
            ),
        )

        self.assertIsNone(_item1_business_excerpt((document,)))

    def test_h2_profile_preflight_pauses_before_h1_without_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                replace(
                    make_case(f"preflight_case_{index}", 4.0 if index < 8 else 1.1),
                    basic_info={
                        "company_name": f"Preflight Company {index}",
                        "ticker": f"PF{index:02d}",
                    },
                )
                for index in range(16)
            )
            model = EmptyMiningModel()
            resolver = EvidenceResolver(
                RawInfoStore(),
                adapters=(
                    UnavailableProviderAdapter(
                        "sec_edgar",
                        ("10-k", "filing", "sec_filing"),
                        ("filing_documents",),
                        "SOA_SEC_USER_AGENT is not configured.",
                        unavailability_reason="sec_user_agent_unconfigured",
                    ),
                ),
                policy=DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("sec_edgar",),
                    allowed_capabilities=("filing_documents",),
                    allowed_source_types=("filing",),
                    max_requests_per_cycle=1,
                    max_requests_per_run=1,
                ),
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                evidence_resolver=resolver,
            )

            with self.assertRaises(SlowLoopDataUnavailable) as context:
                engine._run_signal_mining(cycle_id=1)

            self.assertEqual(context.exception.case_ref, "profile-preflight")
            self.assertEqual(
                context.exception.reason, "sec_user_agent_unconfigured"
            )
            self.assertEqual(model.requests, [])

    def test_h2_profile_provider_failure_raises_retryable_slow_pause(self) -> None:
        class ProviderFailureResolver:
            available_source_types = ("filing",)

            def resolve(self, request, *, company_id, identity, as_of):
                del request, company_id, identity, as_of
                return type(
                    "Resolution",
                    (),
                    {
                        "gap": type(
                            "Gap",
                            (),
                            {
                                "reason": type(
                                    "Reason", (), {"value": "provider_error"}
                                )()
                            },
                        )()
                    },
                )()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            case = replace(
                make_case("profile_provider_failure", 4.0),
                basic_info={
                    "company_name": "Profile Provider Failure Corp",
                    "ticker": "PPFC",
                },
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(case,),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                evidence_resolver=ProviderFailureResolver(),
            )

            with self.assertRaises(SlowLoopDataUnavailable) as context:
                engine._mining_case_brief("case-001", case)

            self.assertEqual(context.exception.case_ref, "case-001")
            self.assertEqual(context.exception.reason, "provider_error")
            self.assertTrue(context.exception.retryable)

    def test_h2_profile_readiness_shortage_skips_h2_and_h3(self) -> None:
        class NoDataResolver:
            available_source_types = ("news", "filing")

            def can_acquire(self, request):
                del request
                return True

            def resolve(self, request, *, company_id, identity, as_of):
                del request, company_id, identity, as_of

                class Gap:
                    reason = type("Reason", (), {"value": "provider_no_data"})()

                    @staticmethod
                    def to_dict():
                        return {"reason": "provider_no_data"}

                return type(
                    "Resolution",
                    (),
                    {"gap": Gap(), "status": "unresolved"},
                )()

            def load_documents(self, resolution, *, as_of):
                del resolution, as_of
                return ()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                replace(
                    make_case(f"profile_case_{index}", 4.0 if index < 8 else 1.1),
                    basic_info={
                        "company_name": f"Profile Company {index}",
                        "ticker": f"P{index:02d}",
                    },
                )
                for index in range(16)
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="profile_gap",
                statement="Business profile separates outcomes.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases show a distinct profile.",
                source_types=("news",),
                query="guidance",
                falsifiers=("Controls show the same profile.",),
            )
            model = ScriptedMiningModel(hypotheses=(hypothesis,))
            raw_store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="profile-news",
                        company_id=cases[0].company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="Routine market update without a business profile.",
                    ),
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                evidence_resolver=NoDataResolver(),
            )

            result = engine._run_signal_mining(cycle_id=1)

            self.assertEqual(len(model.requests), 0)
            self.assertEqual(
                result["audit"]["status"], "insufficient_h2_profile_readiness"
            )
            self.assertEqual(result["audit"]["h2_profile_readiness"]["ready"], 0)
            self.assertEqual(result["candidate_refs"], ())

    def test_h2_profile_scan_stops_when_target_and_class_minima_are_met(self) -> None:
        class RankingModel(ScriptedMiningModel):
            def rank_cases(self, payload):
                self.requests.append(dict(payload))
                case_refs = tuple(
                    item["case_ref"] for item in payload["case_briefs"]
                )
                return AgentStep(
                    {"profile_signal": case_refs},
                    AgentUsage(llm_calls=1),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = (
                make_case("scan_control_a", 1.1),
                make_case("scan_positive_a", 2.5),
                make_case("scan_positive_b", 5.0),
                make_case("scan_positive_c", 12.0),
                make_case("scan_control_b", 1.2),
                make_case("scan_positive_d", 4.0),
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="profile_signal",
                statement="A public update separates outcomes.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases show the update.",
                source_types=("news",),
                query="public update",
                falsifiers=("Controls show the same update.",),
            )
            model = RankingModel(hypotheses=(hypothesis,))
            raw_store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="scan-news",
                        company_id=cases[0].company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="Scan Control A issued a public update.",
                    ),
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=4,
                    h2_profile_scan_limit=6,
                    h2_min_ready_issuers=4,
                    h2_min_ready_per_class=1,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )

            result = engine._run_signal_mining(cycle_id=1)

            self.assertEqual(
                result["audit"]["stages"]["H2"]["profile_readiness"]["scanned"],
                4,
            )
            self.assertEqual(
                len(result["audit"]["stages"]["H2"]["case_briefs"]),
                4,
            )
            self.assertEqual(
                result["audit"]["stages"]["H2"]["mode"],
                "deterministic_canonical_applicability",
            )
            self.assertEqual(
                model.requests[0]["h2_applicability_contract"]["observed_values"][
                    "industry_values"
                ],
                ["fixture"],
            )
            self.assertEqual(
                model.requests[0]["h2_applicability_contract"]["observed_values"][
                    "sector_values"
                ],
                [],
            )

    def test_h2_canonical_shortlist_is_local_and_field_exact(self) -> None:
        brief = {
            "business_description": "Develops seafloor mineral resources.",
            "exchange": "NASDAQ",
            "listing_age_bucket": "over_10y",
            "raw_info_coverage": {"source_types": ["10-k", "news"]},
        }

        self.assertTrue(
            SignalEvolutionEngine._h2_applicability_matches(
                "all_ready_issuers", brief
            )
        )
        self.assertTrue(
            SignalEvolutionEngine._h2_applicability_matches(
                "business_description_topics:mineral resource|extraction", brief
            )
        )
        self.assertTrue(
            SignalEvolutionEngine._h2_applicability_matches(
                "exchange_values:NYSE|NASDAQ", brief
            )
        )
        self.assertTrue(
            SignalEvolutionEngine._h2_applicability_matches(
                "raw_info_source_type_values:news", brief
            )
        )
        self.assertFalse(
            SignalEvolutionEngine._h2_applicability_matches(
                "exchange_values:NYSE", brief
            )
        )
        self.assertFalse(
            SignalEvolutionEngine._h2_applicability_matches(
                "business_description_topics:airline", brief
            )
        )

    def test_h3_news_requires_visible_issuer_and_query_relevance(self) -> None:
        case = replace(
            make_case("news_target", 4.0),
            basic_info={
                "company_name": "Target Systems Corp",
                "ticker": "TGTS",
                "industry": "Hardware",
            },
        )
        relevant = RawInfoDocument.create(
            document_id="relevant-news",
            company_id=case.company_id,
            source_type="news",
            published_at=NOW,
            available_at=NOW,
            content="Target Systems Corp raised full-year guidance.",
        )
        metadata_only = RawInfoDocument.create(
            document_id="metadata-only-news",
            company_id=case.company_id,
            source_type="news",
            published_at=NOW,
            available_at=NOW,
            content="Another issuer announced an unrelated product launch.",
            metadata={"associated_ticker": "TGTS", "title": "Market update"},
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (relevant, metadata_only), case=case, query="guidance", limit=2
        )

        self.assertEqual(tuple(item.document_id for item in kept), ("relevant-news",))
        self.assertEqual(
            audit["filtered_documents"],
            [
                {
                    "document_id": "metadata-only-news",
                    "reason": "missing_strong_issuer_match",
                }
            ],
        )
        self.assertTrue(audit["query_coverage"]["sufficient"])

    def test_h3_visible_brand_from_uppercase_formal_name_is_case_insensitive(
        self,
    ) -> None:
        case = replace(
            make_case("news_target", 4.0),
            basic_info={
                "company_name": "CIENA Corp / CIENA CORP",
                "ticker": "CIEN",
                "industry": "Networking",
            },
        )
        relevant = RawInfoDocument.create(
            document_id="relevant-news",
            company_id=case.company_id,
            source_type="news",
            published_at=NOW,
            available_at=NOW,
            content="Ciena raised full-year guidance for networking demand.",
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (relevant,), case=case, query="guidance", limit=1
        )

        self.assertEqual(tuple(item.document_id for item in kept), ("relevant-news",))
        self.assertEqual(audit["filtered_documents"], [])
        self.assertTrue(audit["query_coverage"]["sufficient"])

    def test_h3_filing_requires_query_relevance_and_projects_matching_window(
        self,
    ) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        relevant = RawInfoDocument.create(
            document_id="relevant-quarterly",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content=(
                "<html><body><div>XML namespace filing header</div>"
                + "<div>ordinary disclosure text</div>" * 100
                + "<div>Quarterly revenue and earnings exceeded analyst "
                "expectations by a material amount.</div>"
                + "<div>signature page tail</div>" * 100
                + "</body></html>"
            ),
        )
        irrelevant = RawInfoDocument.create(
            document_id="irrelevant-quarterly",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content="<html><body>Only a routine legal exhibit.</body></html>",
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (relevant, irrelevant),
            case=case,
            query="quarterly revenue earnings analyst expectations",
            limit=1,
        )
        view = _agent_raw_document_view(
            relevant,
            max_content_chars=240,
            query="quarterly revenue earnings analyst expectations",
        )

        self.assertEqual(tuple(item.document_id for item in kept), ("relevant-quarterly",))
        self.assertEqual(
            audit["filtered_documents"],
            [
                {
                    "document_id": "irrelevant-quarterly",
                    "reason": "document_limit_not_selected",
                }
            ],
        )
        self.assertIn("revenue and earnings exceeded analyst", view["content_excerpt"])
        self.assertNotIn("XML namespace filing header", view["content_excerpt"])
        self.assertEqual(view["content_projection"], "normalized_query_window_v1")
        self.assertTrue(audit["query_coverage"]["sufficient"])
        self.assertGreaterEqual(
            len(audit["query_coverage"]["matched_ordered_pairs"]), 1
        )

    def test_h3_marks_scattered_accounting_boilerplate_as_comparator_context(self) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        boilerplate = RawInfoDocument.create(
            document_id="accounting-boilerplate",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content=(
                "This quarterly report contains forward-looking statements. "
                "Management makes estimates and assumptions about liabilities. "
                "Reported amounts of revenues and expenses may differ from actual results."
            ),
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (boilerplate,), case=case,
            query="quarterly revenue analyst estimates comparison", limit=1,
        )

        self.assertEqual(kept, (boilerplate,))
        self.assertFalse(audit["query_coverage"]["sufficient"])
        self.assertEqual(audit["filtered_documents"], [])
        self.assertEqual(
            audit["query_match_status"], "unmatched_comparator_context"
        )

    def test_h3_excerpt_uses_complete_normalized_terms_not_header_substrings(self) -> None:
        document = RawInfoDocument.create(
            document_id="plural-query-window",
            company_id="fixture",
            source_type="10-k",
            published_at=NOW,
            available_at=NOW,
            content=(
                "Office registry reoffering approved guidelines " * 80
                + "Ordinary disclosure. " * 40
                + "The entity signed off-take agreements covering production. "
                + "Debt financing progressed under those agreements. "
                + "Ordinary disclosure. " * 80
            ),
        )
        view = _agent_raw_document_view(
            document, max_content_chars=240, query="off take agreement financing"
        )

        self.assertIn("off-take agreements", view["content_excerpt"])
        self.assertNotIn("Office registry", view["content_excerpt"])
        self.assertLessEqual(len(view["content_excerpt"]), 240)
        self.assertTrue(_h3_text_query_coverage(
            (view["content_excerpt"],), query="off take agreement financing"
        )["sufficient"])

    def test_h3_excerpt_prefers_visible_ordered_pair_over_scattered_terms(self) -> None:
        document = RawInfoDocument.create(
            document_id="ordered-query-window",
            company_id="fixture",
            source_type="filing",
            published_at=NOW,
            available_at=NOW,
            content=(
                "Revenue " + "ordinary legal terms " * 6 + "growth "
                + "ordinary legal terms " * 6 + "segment. "
                + "ordinary disclosure " * 80
                + "Revenue growth across the segment is discussed here. "
                + "ordinary disclosure " * 80
            ),
        )
        view = _agent_raw_document_view(
            document, max_content_chars=320, query="revenue growth segment"
        )

        self.assertIn("Revenue growth across the segment", view["content_excerpt"])
        self.assertTrue(_h3_text_query_coverage(
            (view["content_excerpt"],), query="revenue growth segment"
        )["sufficient"])

    def test_h3_selection_combines_complementary_documents_before_limit(self) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        routine = RawInfoDocument.create(
            document_id="routine",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content="Quarterly revenue was reported without comparative context.",
        )
        estimate = RawInfoDocument.create(
            document_id="estimate",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content="Analyst estimates were the relevant external baseline.",
        )

        selected, evidence, audit = _select_h3_model_evidence(
            (routine, estimate),
            case=case,
            query="quarterly revenue analyst estimates",
            limit=2,
        )

        self.assertEqual({item.document_id for item in selected}, {"routine", "estimate"})
        self.assertEqual(len(evidence), 2)
        self.assertTrue(audit["query_coverage"]["sufficient"])

        selected, evidence, audit = _select_h3_model_evidence(
            (routine, estimate),
            case=case,
            query="quarterly revenue analyst estimates",
            limit=1,
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(evidence), 1)
        self.assertFalse(audit["query_coverage"]["sufficient"])
        self.assertEqual(
            audit["query_match_status"], "unmatched_comparator_context"
        )

    def test_queryless_exploration_prefers_recent_distinct_source_families(
        self,
    ) -> None:
        case = replace(
            make_case("exploration_target", 4.0),
            basic_info={
                "company_name": "Exploration Target Corp",
                "ticker": "EXPT",
            },
        )
        rows = (
            ("old-financial", "financials", 10),
            ("news", "news", 4),
            ("transcript", "earnings_transcript", 3),
            ("filing", "8-k", 2),
            ("recent-financial", "sec_company_facts", 1),
        )
        documents = tuple(
            RawInfoDocument.create(
                document_id=document_id,
                company_id=case.company_id,
                source_type=source_type,
                published_at=NOW - timedelta(days=days_ago),
                available_at=NOW - timedelta(days=days_ago),
                content=(
                    "Exploration Target Corp disclosed one bounded source fact."
                ),
            )
            for document_id, source_type, days_ago in rows
        )

        selected, _evidence, _audit = _select_h3_model_evidence(
            documents,
            case=case,
            query=None,
            limit=4,
            prefer_source_diversity=True,
        )

        self.assertEqual(
            {item.document_id for item in selected},
            {"recent-financial", "filing", "transcript", "news"},
        )
        self.assertNotIn("old-financial", {item.document_id for item in selected})

    def test_queryless_exploration_requires_financial_and_filing_families(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            case = make_case("exploration_two_family", 4.0)
            store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="exploration-financials",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    ),
                    RawInfoDocument.create(
                        document_id="exploration-filing",
                        company_id=case.company_id,
                        source_type="10-k",
                        published_at=NOW,
                        available_at=NOW,
                        content="Revenue demand improved while inventory remained controlled.",
                    ),
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=(case,),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )

            packet, audit = engine._mining_evidence_packet(
                "case-001",
                case,
                source_types=("10-k", "financials"),
                query=None,
                lookback_days=365,
                reveal_label=False,
            )

            self.assertEqual(len(packet["evidence"]), 2)
            self.assertEqual(
                audit["required_source_groups"],
                [["financials"], ["10-k"]],
            )

    def test_exploration_comparison_inventory_contains_only_recurring_concepts(
        self,
    ) -> None:
        packets = [
            {
                "case_ref": f"case-{index:03d}",
                "evidence": [
                    {
                        "structured_context": {
                            "concepts": [
                                {
                                    "taxonomy": "us-gaap",
                                    "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                                    "label": "Revenue",
                                    "unit": "USD",
                                    "records": [{"exact_span": str(index)}],
                                },
                                {
                                    "taxonomy": "us-gaap",
                                    "concept": f"IssuerOnly{index}",
                                    "label": "Issuer only",
                                    "unit": "USD",
                                    "records": [{"exact_span": str(index)}],
                                },
                            ]
                        }
                    }
                ],
            }
            for index in range(3)
        ]

        inventory = _exploration_comparison_concepts(packets)

        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0]["case_count"], 3)
        self.assertEqual(
            inventory[0]["concept"],
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        )
        self.assertEqual(inventory[0]["source_display_name"], "Revenue")
        self.assertNotIn("source_label", inventory[0])
        self.assertFalse(any("value" in row for row in inventory))

    def test_comparison_inventory_counts_distinct_paired_cases_and_semantic_ties(
        self,
    ) -> None:
        def concept(name, spans):
            return {
                "taxonomy": "us-gaap", "concept": name, "label": name,
                "unit": "USD", "records": [{"exact_span": span} for span in spans],
            }

        packets = []
        for index in range(3):
            packets.append({
                "case_ref": f"case-{index}",
                "evidence": [
                    {"structured_context": {"concepts": [
                        concept("EntityCommonStockSharesOutstanding", ["a", "b"]),
                        concept("OperatingIncomeLoss", ["a"]),
                    ]}},
                    {"structured_context": {"concepts": [
                        concept("OperatingIncomeLoss", ["a", "b"]),
                    ]}},
                ],
            })
        baseline = _exploration_comparison_concepts(packets)
        self.assertEqual(baseline[0]["concept"], "OperatingIncomeLoss")
        self.assertEqual(baseline[0]["case_count"], 3)
        packets[0]["evidence"] *= 10
        self.assertEqual(_exploration_comparison_concepts(packets), baseline)
        for packet in packets:
            packet["evidence"][1]["structured_context"]["concepts"][0]["records"] = [
                {"exact_span": "a"}, {"exact_span": "a"},
            ]
        self.assertEqual(
            _exploration_comparison_concepts(packets)[0]["concept"],
            "EntityCommonStockSharesOutstanding",
        )

    def test_h3_model_view_coverage_rejects_terms_hidden_outside_excerpt(self) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        document = RawInfoDocument.create(
            document_id="scattered-full-filing",
            company_id=case.company_id,
            source_type="10-k",
            published_at=NOW,
            available_at=NOW,
            content=(
                "Revenue growth was discussed in this section. "
                + "ordinary disclosure text " * 120
                + "Composition volume price and segment terms occur elsewhere."
            ),
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (document,), case=case,
            query="revenue growth composition volume price segment", limit=1,
        )
        view = _agent_raw_document_view(
            document,
            max_content_chars=1_200,
            query="revenue growth composition volume price segment",
        )
        visible_coverage = _h3_text_query_coverage(
            (view["content_excerpt"],),
            query="revenue growth composition volume price segment",
        )

        self.assertEqual(kept, (document,))
        self.assertTrue(
            audit["query_coverage"]["full_document_coverage"]["sufficient"]
        )
        self.assertFalse(visible_coverage["sufficient"])
        self.assertNotIn("revenue", visible_coverage["matched_terms"])

    def test_h3_query_coverage_uses_strong_supermajority_not_all_terms(self) -> None:
        near_complete = _h3_text_query_coverage(
            ("Quarterly revenue and earnings analyst discussion.",),
            query="quarterly revenue earnings analyst outlook",
        )
        minority = _h3_text_query_coverage(
            ("Revenue growth segment discussion.",),
            query="revenue growth composition volume price segment",
        )

        self.assertEqual(near_complete["required_match_count"], 4)
        self.assertEqual(len(near_complete["matched_terms"]), 4)
        self.assertTrue(near_complete["sufficient"])
        self.assertEqual(minority["required_match_count"], 5)
        self.assertEqual(len(minority["matched_terms"]), 3)
        self.assertFalse(minority["sufficient"])

    def test_h3_packet_combines_complementary_ordered_query_pairs(self) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        actuals = RawInfoDocument.create(
            document_id="quarterly-actuals",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content="Quarterly revenue increased to $120 million.",
        )
        estimates = RawInfoDocument.create(
            document_id="analyst-estimates",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content="Analyst estimates called for $110 million.",
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (actuals, estimates), case=case,
            query="quarterly revenue analyst estimates", limit=2,
        )

        self.assertEqual(
            tuple(item.document_id for item in kept),
            ("quarterly-actuals", "analyst-estimates"),
        )
        self.assertEqual(audit["filtered_documents"], [])
        coverage = audit["query_coverage"]
        self.assertTrue(coverage["sufficient"])
        self.assertEqual(
            set(coverage["matched_ordered_pairs"]),
            {"analyst estimate", "quarterly revenue"},
        )

    def test_h3_hidden_xbrl_terms_do_not_create_a_query_match(self) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        hidden_only = RawInfoDocument.create(
            document_id="hidden-xbrl-terms",
            company_id=case.company_id,
            source_type="10-k",
            published_at=NOW,
            available_at=NOW,
            content=(
                "<html><body><ix:header><ix:hidden>production volume cost ounce "
                "guidance</ix:hidden></ix:header><div>Routine legal disclosure.</div>"
                "</body></html>"
            ),
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (hidden_only,), case=case,
            query="production volume cost ounce guidance", limit=1,
        )
        view = _agent_raw_document_view(
            hidden_only,
            max_content_chars=240,
            query="production volume cost ounce guidance",
        )

        self.assertEqual(kept, (hidden_only,))
        self.assertFalse(audit["query_coverage"]["sufficient"])
        self.assertEqual(
            audit["query_match_status"], "unmatched_comparator_context"
        )
        self.assertNotIn("production", view["content_excerpt"])
        self.assertIn("Routine legal disclosure", view["content_excerpt"])

    def test_mining_ranks_identity_and_label_hidden_briefs_then_overlays_labels(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            positive = replace(
                make_case("workflow_positive", 4.0),
                basic_info={
                    "ticker": "WINR",
                    "company_name": "Winner Corp",
                    "business_description": "Winner Corp builds optical systems.",
                    "industry": "Hardware",
                },
            )
            control = replace(
                make_case("workflow_control", 1.1),
                basic_info={
                    "ticker": "CTRL",
                    "company_name": "Control Corp",
                    "business_description": "Control Corp builds optical systems.",
                    "industry": "Hardware",
                },
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="order_confirmation",
                statement="Material order confirmation precedes repricing.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases disclose confirmed orders.",
                source_types=("news",),
                query="material order",
                falsifiers=("Controls disclose the same pattern.",),
            )
            second_hypothesis = replace(
                hypothesis,
                hypothesis_id="commercialization_confirmation",
            )
            deferred_hypothesis = replace(
                hypothesis,
                hypothesis_id="guidance_confirmation",
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(
                    hypothesis,
                    second_hypothesis,
                    deferred_hypothesis,
                ),
                rankings={
                    item.hypothesis_id: ("case-001", "case-002")
                    for item in (
                        hypothesis,
                        second_hypothesis,
                        deferred_hypothesis,
                    )
                },
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="order_confirmation",
                        disposition="refine",
                        rationale=("Two cases are not enough to draft a Signal.",),
                    ),
                    SignalMiningDecision(
                        hypothesis_id="commercialization_confirmation",
                        disposition="refine",
                        rationale=("The visible cases do not separate the groups.",),
                    ),
                ),
            )
            counterparty_by_company = {
                positive.company_id: control.basic_info["company_name"],
                control.company_id: positive.basic_info["company_name"],
            }
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"workflow_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported a material "
                            "order involving "
                            f"{counterparty_by_company[case.company_id]}."
                        ),
                    )
                    for index, case in enumerate((positive, control))
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(positive, control),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(2),
            )
            result = engine._run_signal_mining(cycle_id=1)

            ranking_payload = result["audit"]["stages"]["H2"]
            ranking_json = json.dumps(ranking_payload)
            self.assertNotIn("Winner Corp", ranking_json)
            self.assertNotIn("Control Corp", ranking_json)
            self.assertNotIn("WINR", ranking_json)
            self.assertNotIn("CTRL", ranking_json)
            self.assertNotIn("ground_truth", ranking_json)
            self.assertNotIn('"label"', ranking_json)
            for payload in mining_model.requests:
                self.assertEqual(payload["research_objective"], signal_research_objective())
                self.assertEqual(payload["fixed_prior"], engine.priors.mine_signal)
            comparisons = mining_model.requests[1]["comparisons"]
            contrast_cases = [
                packet
                for comparison in comparisons
                for packet in comparison["evidence_packets"]
            ]
            self.assertEqual(
                {item["label"] for item in contrast_cases},
                {"positive", "control"},
            )
            self.assertTrue(comparisons[0]["evidence_packets"])
            self.assertNotIn("evidence_packets", mining_model.requests[1])
            self.assertNotIn("Winner Corp", json.dumps(contrast_cases))
            self.assertNotIn("Control Corp", json.dumps(contrast_cases))
            self.assertEqual(result["candidate_refs"], ())
            self.assertIn("order_confirmation", result["refined_hypotheses"])
            self.assertEqual(
                result["refined_hypotheses"]["guidance_confirmation"],
                (
                    "deferred because the per-cycle evidence contrast budget was reached",
                ),
            )

    def test_mining_does_not_learn_refinement_from_unusable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            positive = make_case("evidence_positive", 4.0)
            control = make_case("evidence_control", 1.1)
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="production_cost_pattern",
                statement="Production and cost changes may precede repricing.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Production rises while cost declines.",
                source_types=("news",),
                query="production cost guidance",
                falsifiers=("Controls show the same pattern.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                rankings={
                    "production_cost_pattern": ("case-001", "case-002")
                },
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="production_cost_pattern",
                        disposition="inconclusive",
                        rationale=(
                            "The comparator packets contain no direct production-cost evidence.",
                        ),
                    ),
                ),
            )
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"unrelated_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} filed a routine legal "
                            "notice."
                        ),
                    )
                    for index, case in enumerate((positive, control))
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(positive, control),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(2),
            )
            result = engine._run_signal_mining(cycle_id=1)

            self.assertEqual(len(mining_model.requests), 2)
            self.assertNotIn(
                "production_cost_pattern", result["refined_hypotheses"]
            )
            self.assertIn(
                "production_cost_pattern", result["audit"]["evidence_unavailable"]
            )
            self.assertEqual(
                result["audit"]["stages"]["H3"]["status"],
                "completed_with_inconclusive",
            )
            packets = mining_model.requests[1]["comparisons"][0][
                "evidence_packets"
            ]
            self.assertEqual(
                {item["query_match_status"] for item in packets},
                {"unmatched_comparator_context"},
            )

    def test_mining_suppresses_only_identical_committed_terminal_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            cases = tuple(
                [make_case(f"repeat_positive_{index}", 4.0) for index in range(2)]
                + [make_case(f"repeat_control_{index}", 1.1) for index in range(2)]
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="repeatable_order_pattern",
                statement="Material order confirmations may separate outcomes.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases disclose material orders.",
                source_types=("news",),
                query="material order",
                falsifiers=("Controls disclose the same pattern.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id=hypothesis.hypothesis_id,
                        disposition="refine",
                        rationale=("The visible pattern needs a narrower rule.",),
                    ),
                ),
            )
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"repeat_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.company_id} disclosed a material order with "
                            "bounded commercial terms."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(cases)),
            )

            first = engine._run_signal_mining(cycle_id=1)
            self.assertEqual(len(mining_model.requests), 2)
            path = (
                workspace.experiments_root
                / "cycles"
                / "cycle-0001"
                / "slow_loop_validation.json"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "validation": {
                            "agent_audits": {
                                "mining_pipeline": first["audit"]
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            workspace.cycle_state_path.write_text(
                json.dumps({"last_completed_cycle": 1}), encoding="utf-8"
            )

            repeated = engine._run_signal_mining(cycle_id=2)

            self.assertEqual(len(mining_model.requests), 3)
            self.assertEqual(repeated["candidate_refs"], ())
            self.assertEqual(
                repeated["audit"]["hypothesis_work"][0]["status"],
                "unchanged_work_suppressed",
            )
            self.assertEqual(
                repeated["audit"]["stages"]["H3"]["status"],
                "not_called_unchanged_work",
            )

            changed_hypothesis = replace(
                hypothesis,
                hypothesis_id="named_counterparty_pattern",
                statement=(
                    "Material order confirmations with named counterparties "
                    "may separate outcomes."
                ),
            )
            mining_model.hypotheses = (hypothesis, changed_hypothesis)
            mining_model.decisions = (
                SignalMiningDecision(
                    hypothesis_id=changed_hypothesis.hypothesis_id,
                    disposition="refine",
                    rationale=("The narrower visible pattern remains tentative.",),
                ),
            )
            changed = engine._run_signal_mining(cycle_id=4)

            self.assertEqual(len(mining_model.requests), 5)
            self.assertEqual(
                {
                    item["hypothesis_id"]: item["status"]
                    for item in changed["audit"]["hypothesis_work"]
                },
                {
                    hypothesis.hypothesis_id: "unchanged_work_suppressed",
                    changed_hypothesis.hypothesis_id: "refine",
                },
            )
            self.assertEqual(
                [
                    item["hypothesis"]["hypothesis_id"]
                    for item in mining_model.requests[-1]["comparisons"]
                ],
                [changed_hypothesis.hypothesis_id],
            )

    def test_production_mining_falls_back_to_exploration_after_empty_h1(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"explore_{index}", 4.0 if index < 2 else 1.1)
                for index in range(4)
            )
            exploration = exploration_selection(
                cases, cycle_id=1, induction_per_class=1, validation_per_class=1
            )
            signatures = tuple(
                SignalMiningSignature(
                    case_ref=case_ref,
                    observations=(
                        SignalMiningObservation(
                            summary="A material operational event was disclosed.",
                            document_ref="document-01",
                            exact_span="disclosed an operational event.",
                        ),
                    ),
                )
                for case_ref in exploration["e1_refs"]
            )
            mining_model = ScriptedMiningModel(
                signatures=tuple(reversed(signatures)),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="exploration_event_pattern",
                        disposition="refine",
                        rationale=("The observable event category needs refinement.",),
                    ),
                ),
            )
            mining_model.supports_exploration_fallback = True
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"explore-news-{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} disclosed an operational event."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=4,
                    ranking_case_limit=4,
                    h2_profile_scan_limit=4,
                    h2_min_ready_issuers=4,
                    h2_min_ready_per_class=2,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )

            result = engine._run_signal_mining(cycle_id=1)

            self.assertEqual(
                result["audit"]["track"],
                "hypothesis_then_exploration_fallback",
            )
            self.assertEqual(result["audit"]["hypothesis"]["candidate_refs"], [])
            self.assertEqual(result["audit"]["exploration"]["track"], "exploration")
            self.assertIn(
                "exploration_event_pattern", result["refined_hypotheses"]
            )
            self.assertEqual(len(mining_model.requests), 3)

    def test_h1_payload_receives_value_free_measurable_evidence_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"h1m_{index}", 4.0 if index < 2 else 1.1)
                for index in range(4)
            )
            facts_content = json.dumps(
                {
                    "facts": {
                        "us-gaap": {
                            "CashAndCashEquivalentsAtCarryingValue": {
                                "label": (
                                    "Cash and Cash Equivalents at Carrying Value"
                                ),
                                "units": {
                                    "USD": [
                                        {
                                            "end": "2020-12-31",
                                            "val": 1000,
                                            "filed": "2021-02-01",
                                        },
                                        {
                                            "end": "2019-12-31",
                                            "val": 800,
                                            "filed": "2020-02-01",
                                        },
                                    ]
                                },
                            }
                        }
                    }
                }
            )
            documents = []
            for index, case in enumerate(cases):
                documents.extend(
                    (
                        RawInfoDocument.create(
                            document_id=f"h1m-facts-{index}",
                            company_id=case.company_id,
                            source_type="company_facts",
                            published_at=NOW,
                            available_at=NOW,
                            content=facts_content,
                        ),
                        RawInfoDocument.create(
                            document_id=f"h1m-price-{index}",
                            company_id=case.company_id,
                            source_type="price_daily",
                            published_at=NOW,
                            available_at=NOW,
                            content="adjusted close prices",
                        ),
                        RawInfoDocument.create(
                            document_id=f"h1m-8k-{index}",
                            company_id=case.company_id,
                            source_type="8-k",
                            published_at=NOW,
                            available_at=NOW,
                            content=(
                                f"{case.basic_info['company_name']} announced "
                                "a material agreement."
                            ),
                        ),
                    )
                )
            mining_model = ScriptedMiningModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(documents=tuple(documents)),
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(4),
            )

            engine._run_hypothesis_mining(cycle_id=1)

            manifest = mining_model.requests[0]["measurable_evidence_manifest"]
            self.assertEqual(
                manifest["schema_version"],
                "h1-measurable-evidence-manifest-v1",
            )
            self.assertEqual(manifest["cohort_case_count"], 4)
            cash_rows = [
                row
                for row in manifest["structured_financial_concepts"]
                if row["concept"] == "CashAndCashEquivalentsAtCarryingValue"
            ]
            self.assertEqual(len(cash_rows), 1)
            self.assertEqual(cash_rows[0]["case_count"], 4)
            self.assertEqual(cash_rows[0]["cases_with_comparable_records"], 4)
            self.assertEqual(cash_rows[0]["unit"], "USD")
            self.assertTrue(cash_rows[0]["source_display_name"])
            self.assertEqual(manifest["pre_cutoff_price_series_cases"], 4)
            self.assertIn(
                {"source_type": "8-k", "case_count": 4},
                manifest["narrative_source_families"],
            )
            serialized = json.dumps(manifest)
            self.assertNotIn("1000", serialized)
            self.assertNotIn("800", serialized)
            self.assertNotIn('"val"', serialized)

    def test_production_mining_falls_back_after_h1_correction_exhaustion(
        self,
    ) -> None:
        class FailedH1MiningModel(ScriptedMiningModel):
            supports_exploration_fallback = True

            def propose_hypotheses(self, payload):
                self.requests.append(dict(payload))
                raise CandidateExecutionRejected(
                    "signal_mining_hypotheses",
                    "signal_mining_hypotheses failed validation after 2 corrections",
                    AgentUsage(llm_calls=3, tokens=29, cost=0.03),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"recover_{index}", 4.0 if index < 2 else 1.1)
                for index in range(4)
            )
            signatures = tuple(
                SignalMiningSignature(
                    case_ref=f"case-{index:03d}",
                    observations=(
                        SignalMiningObservation(
                            summary="A material operational event was disclosed.",
                            document_ref="document-01",
                            exact_span="disclosed an operational event.",
                        ),
                    ),
                )
                for index in (1, 3)
            )
            mining_model = FailedH1MiningModel(
                signatures=signatures,
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="exploration_event_pattern",
                        disposition="refine",
                        rationale=("The repeated event needs refinement.",),
                    ),
                ),
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"recover-news-{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} disclosed an "
                            "operational event."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=4,
                    ranking_case_limit=4,
                    h2_profile_scan_limit=4,
                    h2_min_ready_issuers=4,
                    h2_min_ready_per_class=2,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )

            engine._active_sampling_manifest = {}
            events = []
            engine.on_progress = events.append
            result = engine._run_signal_mining(cycle_id=1)
            failure_events = [row for row in events if row["event_type"] == "signal_mining_track_failed"]
            self.assertEqual(len(failure_events), 1)
            self.assertEqual(failure_events[0]["track"], "hypothesis")

            self.assertEqual(
                result["audit"]["status"],
                "completed_with_hypothesis_failure",
            )
            self.assertEqual(
                result["audit"]["track"],
                "hypothesis_then_exploration_fallback",
            )
            hypothesis_audit = result["audit"]["hypothesis"]
            self.assertEqual(hypothesis_audit["status"], "failed")
            self.assertEqual(
                hypothesis_audit["failure_stage"],
                "signal_mining_hypotheses",
            )
            self.assertEqual(hypothesis_audit["usage"]["llm_calls"], 3)
            self.assertEqual(
                hypothesis_audit["failure_details"]["conclusion"]["conclusion"],
                "technical_failure",
            )
            self.assertTrue(
                hypothesis_audit["failure_details"]["input_fingerprint"]
            )
            self.assertEqual(result["audit"]["exploration"]["track"], "exploration")
            self.assertIn(
                "exploration_event_pattern", result["refined_hypotheses"]
            )
            self.assertEqual(len(mining_model.requests), 3)

            class FailedBothTracksModel(FailedH1MiningModel):
                def extract_exploration(self, payload):
                    self.requests.append(dict(payload))
                    raise CandidateExecutionRejected(
                        "signal_mining_exploration_extract",
                        "exploration extraction remained malformed",
                        AgentUsage(llm_calls=2, tokens=17, cost=0.02),
                    )

            failed_model = FailedBothTracksModel()
            failed_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "failed-workspace"),
                mining_model=failed_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=engine.mining_config,
            )

            failed = failed_engine._run_signal_mining(cycle_id=1)

            self.assertEqual(failed["candidate_refs"], ())
            self.assertEqual(
                failed["audit"]["status"], "completed_with_hypothesis_failure"
            )
            exploration = failed["audit"]["exploration"]
            self.assertEqual(
                exploration["stages"]["E2"]["status"],
                "not_called_evidence_unavailable",
            )
            self.assertEqual(
                exploration["stages"]["E1"]["usage"]["llm_calls"], 2
            )
            self.assertEqual(len(failed["failures"]), 2)
            self.assertTrue(
                all(
                    "exhausted structured recovery" in " ".join(reasons)
                    for reasons in failed["failures"].values()
                )
            )

    def test_identical_committed_no_hypothesis_suppresses_repeated_h1_work(
        self,
    ) -> None:
        class NoHypothesisModel(EmptyMiningModel):
            def propose_hypotheses(self, payload):
                self.requests.append(dict(payload))
                return AgentStep(
                    (),
                    AgentUsage(llm_calls=1),
                    metadata={
                        "conclusion": "no_testable_hypothesis",
                        "reason_code": "insufficient_retrieval_basis",
                        "rationale": ["No new measurable field is visible."],
                        "need_refs": [],
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"no_hypothesis_{index}", 4.0 if index < 2 else 1.1)
                for index in range(4)
            )
            store = RawInfoStore(
                documents=(
                    *tuple(
                        RawInfoDocument.create(
                            document_id=f"no-hypothesis-news-{index}",
                            company_id=case.company_id,
                            source_type="news",
                            published_at=NOW,
                            available_at=NOW,
                            content=f"{case.company_id} published a routine update.",
                        )
                        for index, case in enumerate(cases)
                    ),
                    RawInfoDocument.create(
                        document_id="baseline-unrelated-transcript",
                        company_id="outside-discovery",
                        source_type="transcript",
                        published_at=NOW,
                        available_at=NOW,
                        content="An outside issuer held a prior call.",
                    ),
                )
            )
            workspace = EvolutionWorkspace(root / "workspace")
            model = NoHypothesisModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=4,
                    ranking_case_limit=4,
                    h2_profile_scan_limit=4,
                    h2_min_ready_issuers=4,
                    h2_min_ready_per_class=2,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )

            first = engine._run_signal_mining(cycle_id=1)
            cycle_dir = workspace.experiments_root / "cycles" / "cycle-0001"
            cycle_dir.mkdir(parents=True)
            (cycle_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "refined_hypotheses": {},
                            "agent_audits": {"mining_pipeline": first["audit"]},
                        }
                    }
                ),
                encoding="utf-8",
            )
            workspace.cycle_state_path.write_text(
                json.dumps(
                    {
                        "last_completed_cycle": 1,
                        "last_completed_round": 0,
                        "run_contract_hash": "contract-hash",
                        "active_cycle": None,
                    }
                ),
                encoding="utf-8",
            )

            second = engine._run_signal_mining(cycle_id=2)

            self.assertEqual(len(model.requests), 1)
            self.assertEqual(
                second["audit"]["status"], "unchanged_h1_work_suppressed"
            )
            self.assertTrue(
                second["audit"]["stages"]["H1"]["reused_from_prior_cycle"]
            )

            store.append(
                RawInfoDocument.create(
                    document_id="unrelated-transcript",
                    company_id="outside-discovery",
                    source_type="transcript",
                    published_at=NOW,
                    available_at=NOW,
                    content="An unrelated issuer held a call.",
                )
            )
            still_suppressed = engine._run_signal_mining(cycle_id=2)
            self.assertEqual(len(model.requests), 1)
            self.assertEqual(
                still_suppressed["audit"]["status"],
                "unchanged_h1_work_suppressed",
            )

            store.append(
                RawInfoDocument.create(
                    document_id="relevant-transcript",
                    company_id=cases[0].company_id,
                    source_type="transcript",
                    published_at=NOW,
                    available_at=NOW,
                    content="Management added a point-in-time comparison on the call.",
                )
            )
            changed_by_data = engine._run_signal_mining(cycle_id=2)
            self.assertEqual(len(model.requests), 2)
            self.assertNotEqual(
                changed_by_data["audit"]["stages"]["H1"]["input_fingerprint"],
                first["audit"]["stages"]["H1"]["input_fingerprint"],
            )

            engine.meta_memory.append(RoundMetaEntry(
                round_id=1,
                missing_capabilities=("Separate committed orders from pipeline claims.",),
                evidence_refs=("plan_r0001_c01",),
            ))
            changed = engine._run_signal_mining(cycle_id=2)
            self.assertEqual(len(model.requests), 3)
            self.assertNotEqual(
                changed["audit"]["stages"]["H1"]["input_fingerprint"],
                first["audit"]["stages"]["H1"]["input_fingerprint"],
            )
            self.assertEqual(
                model.requests[-1]["meta_info"][0]["signal_observations"]["missing_capabilities"],
                ["Separate committed orders from pipeline claims."],
            )

    def test_technical_h1_failure_does_not_suppress_recovered_work(self) -> None:
        class RecoveringModel(EmptyMiningModel):
            def propose_hypotheses(self, payload):
                self.requests.append(dict(payload))
                if len(self.requests) == 1:
                    raise CandidateExecutionRejected(
                        "signal_mining_hypotheses",
                        "temporary structured failure",
                        AgentUsage(llm_calls=1),
                    )
                return AgentStep(
                    (),
                    AgentUsage(llm_calls=1),
                    metadata={
                        "conclusion": "no_testable_hypothesis",
                        "reason_code": "insufficient_retrieval_basis",
                        "rationale": ["No measurement is supported after recovery."],
                        "need_refs": [],
                        "need_dispositions": [],
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"technical_h1_{index}", 4.0 if index < 2 else 1.1)
                for index in range(4)
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"technical-h1-news-{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=f"{case.company_id} published a routine update.",
                    )
                    for index, case in enumerate(cases)
                )
            )
            workspace = EvolutionWorkspace(root / "workspace")
            model = RecoveringModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=4,
                    ranking_case_limit=4,
                    h2_profile_scan_limit=4,
                    h2_min_ready_issuers=4,
                    h2_min_ready_per_class=2,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )

            with self.assertRaises(CandidateExecutionRejected) as raised:
                engine._run_hypothesis_mining(cycle_id=1)
            details = raised.exception.details
            cycle_dir = workspace.experiments_root / "cycles" / "cycle-0001"
            cycle_dir.mkdir(parents=True)
            (cycle_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "refined_hypotheses": {},
                            "agent_audits": {
                                "mining_pipeline": {
                                    "track": "hypothesis",
                                    "stages": {
                                        "H1": {
                                            "input_fingerprint": details[
                                                "input_fingerprint"
                                            ],
                                            "conclusion": details["conclusion"],
                                        }
                                    },
                                }
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            recovered = engine._run_hypothesis_mining(cycle_id=2)

            self.assertEqual(len(model.requests), 2)
            self.assertEqual(recovered["audit"]["status"], "no_testable_hypothesis")

    def test_mining_falls_through_to_next_ranked_case_with_usable_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"fallback_positive_{index}", 4.0) for index in range(3)]
                + [make_case(f"fallback_control_{index}", 1.1) for index in range(3)]
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="production_cost_pattern",
                statement="Production and cost changes may precede repricing.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Production rises while cost declines.",
                source_types=("news",),
                query="production cost guidance",
                falsifiers=("Controls show the same pattern.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="production_cost_pattern",
                        disposition="refine",
                        rationale=("The visible pattern remains underspecified.",),
                    ),
                ),
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=6,
                    ranking_case_limit=6,
                    h2_profile_scan_limit=6,
                    h2_min_ready_issuers=6,
                    h2_min_ready_per_class=3,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )
            pairs = engine._mining_case_universe(limit=6)
            refs_by_class = {
                class_value: [
                    case_ref
                    for case_ref, case in pairs
                    if bool(case.ground_truth.is_surge) is class_value
                ]
                for class_value in (True, False)
            }
            ranking = tuple(
                value
                for index in range(3)
                for value in (
                    refs_by_class[True][index],
                    refs_by_class[False][index],
                )
            )
            mining_model.rankings = {"production_cost_pattern": ranking}
            usable_refs = {
                refs_by_class[True][1],
                refs_by_class[False][1],
            }
            engine.raw_info_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"usable_{case_ref}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported production "
                            "cost guidance."
                        ),
                    )
                    for case_ref, case in pairs
                    if case_ref in usable_refs
                )
            )
            engine.evidence_resolver = EvidenceResolver(engine.raw_info_store)

            result = engine._run_signal_mining(cycle_id=1)

            selected = result["audit"]["local_selection"][0]
            self.assertEqual(set(selected["induction_case_refs"]), usable_refs)
            self.assertEqual(len(mining_model.requests), 2)
            attempted = {
                item["case_ref"]
                for item in result["audit"]["stages"]["H3"]["resolutions"]
            }
            self.assertTrue(
                {
                    refs_by_class[True][0],
                    refs_by_class[False][0],
                }.issubset(attempted)
            )

    def test_mining_keeps_h3_inconclusive_out_of_semantic_refinement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            positive = make_case("inconclusive_positive", 4.0)
            control = make_case("inconclusive_control", 1.1)
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="production_cost_pattern",
                statement="Production and cost changes may precede repricing.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Production rises while cost declines.",
                source_types=("news",),
                query="production cost guidance",
                falsifiers=("Controls show the same pattern.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="production_cost_pattern",
                        disposition="inconclusive",
                        rationale=(
                            "The visible material remains insufficient to compare guidance.",
                        ),
                    ),
                ),
            )
            documents = tuple(
                RawInfoDocument.create(
                    document_id=f"inconclusive_{case.company_id}",
                    company_id=case.company_id,
                    source_type="news",
                    published_at=NOW,
                    available_at=NOW,
                    content=(
                        f"{case.basic_info['company_name']} reported production cost "
                        "guidance without a comparable historical range."
                    ),
                )
                for case in (positive, control)
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(documents=documents),
                discovery_cases=(positive, control),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(2),
            )
            mining_model.rankings = {
                "production_cost_pattern": tuple(
                    case_ref
                    for case_ref, _case in engine._mining_case_universe(limit=2)
                )
            }

            result = engine._run_signal_mining(cycle_id=1)

            self.assertNotIn(
                "production_cost_pattern", result["refined_hypotheses"]
            )
            self.assertIn(
                "production_cost_pattern", result["audit"]["evidence_unavailable"]
            )
            self.assertEqual(
                result["audit"]["stages"]["H3"]["status"],
                "completed_with_inconclusive",
            )

    def test_signal_update_makes_zero_calls_without_actionable_learning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            update_model = NoChangeUpdateModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("workflow_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=update_model,
                llm_signal_runner=None,
            )
            result = engine._run_signal_update(cycle_id=1)

            self.assertEqual(result["candidate_refs"], ())
            self.assertEqual(result["audit"]["disposition"], "no_actionable_target")
            self.assertFalse(result["audit"]["model_called"])
            self.assertEqual(update_model.requests, [])

    def test_signal_update_processes_top_three_actionable_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            fixture = candidate_growth_fixture()
            signal_refs: list[str] = []
            for suffix in ("a", "b", "c", "d"):
                spec = SignalSpec(
                    signal_id=f"update_signal_{suffix}",
                    version=1,
                    category="fundamental",
                    description=f"Revenue growth threshold variant {suffix}.",
                    execution_type=SignalExecutionType.DETERMINISTIC,
                    source_types=("financials",),
                    function="financial.revenue_growth_yoy",
                    parameters={"positive_min": 0.2, "negative_max": 0.0},
                )
                registry.register_stable(spec, tests=(fixture,))
                signal_refs.append(spec.ref)
                for index in range(2):
                    registry.record_learning_event(
                        SignalLearningEvent(
                            event_id=f"{suffix}-wrong-event-{index}",
                            observation_key=f"{suffix}-wrong-observation-{index}",
                            signal_ref=spec.ref,
                            round_id=1,
                            plan_id=f"plan-{suffix}-{index}",
                            case_id=f"fast-case-{suffix}-{index}",
                            company_id=f"fast-issuer-{suffix}-{index}",
                            prediction_time=NOW.isoformat(),
                            selection={
                                "signal_ref": spec.ref,
                                "reason_code": "answer_need",
                                "selection_reason": "Test reported revenue growth.",
                                "applicability_hypothesis": (
                                    "Annual periods are comparable."
                                ),
                                "expected_role": "primary",
                                "context_tags": ["comparable_financials"],
                            },
                            result_value=SignalValue.POSITIVE,
                            coverage=SignalCoverage.SUFFICIENT,
                            document_fingerprint=(f"hash-{suffix}-{index}",),
                            is_surge=False,
                            realized_max_multiple=1.2,
                            prediction_correct=False,
                        )
                    )

            cases = tuple(
                [make_case(f"portfolio_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"portfolio_control_{index}", 1.1) for index in range(4)]
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"portfolio_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            update_model = NoChangeUpdateModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=update_model,
                llm_signal_runner=None,
            )

            result = engine._run_signal_update(cycle_id=1)

            self.assertEqual(result["candidate_refs"], ())
            self.assertEqual(len(update_model.requests), 3, result["audit"])
            self.assertEqual(
                [request["target"]["signal_ref"] for request in update_model.requests],
                signal_refs[:3],
            )
            audit = result["audit"]
            self.assertEqual(audit["schema_version"], "signal-update-audit-v2")
            self.assertEqual(audit["target_limit"], 3)
            self.assertEqual(audit["target_count"], 3)
            self.assertEqual(audit["model_target_count"], 3)
            self.assertEqual(audit["model_usage"]["llm_calls"], 3)
            self.assertEqual(len(audit["targets"]), 3)
            self.assertTrue(all(item["model_called"] for item in audit["targets"]))

    def test_signal_update_isolates_one_target_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("workflow_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            targets = tuple(
                {
                    "signal_ref": f"test_signal_{index}:v1",
                    "problem_type": "repeated_directional_wrong",
                    "support": {"directional_wrong": 2},
                    "recurring_contexts": [],
                }
                for index in range(3)
            )
            attempted: list[str] = []
            engine._select_signal_update_targets = lambda: targets

            def run_one(*, cycle_id, target, cases, executor):
                attempted.append(target["signal_ref"])
                if len(attempted) == 1:
                    raise ValidationError("first target failed")
                return engine._signal_update_output(
                    audit={
                        "schema_version": "signal-update-target-audit-v1",
                        "cycle_id": cycle_id,
                        "status": "completed",
                        "model_called": False,
                        "target": dict(target),
                        "issue_fingerprint": "a" * 64,
                        "disposition": "defer",
                    }
                )

            engine._run_one_signal_update = run_one

            result = engine._run_signal_update(cycle_id=1)

            self.assertEqual(attempted, [item["signal_ref"] for item in targets])
            self.assertIn("update:test_signal_0:v1", result["failures"])
            self.assertEqual(
                [item["status"] for item in result["audit"]["targets"]],
                ["failed", "completed", "completed"],
            )

    def test_signal_update_finds_prior_work_audits_in_v1_and_v2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("workflow_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            cycles = workspace.experiments_root / "cycles"
            legacy_dir = cycles / "cycle-0001"
            legacy_dir.mkdir(parents=True)
            (legacy_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "agent_audits": {
                                "update_pipeline": {
                                    "schema_version": "signal-update-audit-v1",
                                    "issue_fingerprint": "same-problem",
                                    "work_fingerprint": "legacy-work",
                                    "disposition": "defer",
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            portfolio_dir = cycles / "cycle-0002"
            portfolio_dir.mkdir(parents=True)
            (portfolio_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "agent_audits": {
                                "update_pipeline": {
                                    "schema_version": "signal-update-audit-v2",
                                    "targets": [
                                        {
                                            "schema_version": (
                                                "signal-update-target-audit-v1"
                                            ),
                                            "issue_fingerprint": "same-problem",
                                            "work_fingerprint": "portfolio-work",
                                            "disposition": "defer",
                                        }
                                    ],
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertIsNone(engine._prior_signal_update("legacy-work"))
            self.assertIsNone(engine._prior_signal_update("portfolio-work"))
            self.assertIsNone(engine._prior_signal_update("same-problem"))

    def test_signal_update_suppresses_exact_work_but_retries_relevant_new_input(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"work_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"work_control_{index}", 1.1) for index in range(4)]
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"work_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                130.0 if case.ground_truth.is_surge else 125.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            workspace = EvolutionWorkspace(root / "workspace")

            class IdentifiedUpdateModel(NoChangeUpdateModel):
                def __init__(self) -> None:
                    super().__init__()
                    self.model_name = "update-model-a"

                @property
                def work_identity(self):
                    return {"model": self.model_name, "protocol": "update-v2"}

            update_model = IdentifiedUpdateModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=update_model,
                llm_signal_runner=None,
            )
            target = {
                "signal_ref": "revenue_growth_yoy:v1",
                "problem_type": "repeated_directional_wrong",
                "support": {
                    "unique_observations": 8,
                    "misleading_attributions": 0,
                    "directional_wrong": 4,
                    "unavailable": 0,
                    "unavailable_with_inputs": 0,
                },
                "recurring_contexts": [],
            }

            def execute_update():
                executor = SignalExecutor(registry.freeze(), store)
                return engine._run_one_signal_update(
                    cycle_id=2,
                    target=target,
                    cases=cases,
                    executor=executor,
                )

            first = execute_update()
            cycle_dir = workspace.experiments_root / "cycles" / "cycle-0001"
            cycle_dir.mkdir(parents=True)
            (cycle_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "agent_audits": {
                                "update_pipeline": {
                                    "schema_version": "signal-update-audit-v2",
                                    "targets": [first["audit"]],
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            repeated = execute_update()
            self.assertEqual(repeated["audit"]["disposition"], "unchanged_work_suppressed")
            self.assertEqual(len(update_model.requests), 1)
            self.assertEqual(
                update_model.requests[0]["research_objective"], signal_research_objective()
            )

            store.append(
                RawInfoDocument.create(
                    document_id="unrelated_work_document",
                    company_id="other_issuer",
                    source_type="financials",
                    published_at=NOW,
                    available_at=NOW,
                    content="Unrelated issuer revenue disclosure.",
                )
            )
            still_repeated = execute_update()
            self.assertEqual(
                still_repeated["audit"]["disposition"],
                "unchanged_work_suppressed",
            )
            self.assertEqual(len(update_model.requests), 1)
            self.assertEqual(
                update_model.requests[0]["research_objective"], signal_research_objective()
            )

            update_model.model_name = "update-model-b"
            changed_model = execute_update()
            self.assertEqual(changed_model["audit"]["disposition"], "no_change")
            self.assertNotEqual(
                changed_model["audit"]["work_fingerprint"],
                first["audit"]["work_fingerprint"],
            )
            self.assertEqual(len(update_model.requests), 2)

            store.append(
                RawInfoDocument.create(
                    document_id="relevant_work_document",
                    company_id=cases[0].company_id,
                    source_type="financials",
                    published_at=NOW,
                    available_at=NOW,
                    content=sec_company_facts_content(
                        ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                        ("2024-01-01", "2024-12-31", 140.0, "2025-01-10"),
                    ),
                )
            )
            changed = execute_update()
            self.assertEqual(changed["audit"]["disposition"], "no_change")
            self.assertNotEqual(
                changed["audit"]["work_fingerprint"],
                first["audit"]["work_fingerprint"],
            )
            self.assertEqual(len(update_model.requests), 3)

    def test_mining_context_preserves_refinement_reasons_and_data_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("workflow_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            refined = {
                "hypothesis_id": "refined_pattern",
                "statement": "An underspecified pattern.",
            }
            unavailable = {
                "hypothesis_id": "missing_evidence_pattern",
                "statement": "A pattern needing unavailable evidence.",
            }
            cycle_dir = workspace.experiments_root / "cycles" / "cycle-0001"
            cycle_dir.mkdir(parents=True)
            (cycle_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "refined_hypotheses": {
                                "refined_pattern": [
                                    "The visible controls show the same pattern."
                                ]
                            },
                            "agent_audits": {
                                "mining_pipeline": {
                                    "evidence_unavailable": {
                                        "missing_evidence_pattern": [
                                            "No query-relevant 10-Q was available."
                                        ]
                                    },
                                    "stages": {
                                        "H1": {
                                            "input_fingerprint": "h1-input-hash",
                                            "conclusion": {
                                                "conclusion": "no_testable_hypothesis",
                                                "reason_code": (
                                                    "insufficient_retrieval_basis"
                                                ),
                                            },
                                            "hypotheses": [refined, unavailable]
                                        }
                                    },
                                }
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            workspace.cycle_state_path.write_text(
                json.dumps(
                    {
                        "last_completed_cycle": 1,
                        "last_completed_round": 0,
                        "run_contract_hash": "contract-hash",
                        "active_cycle": None,
                    }
                ),
                encoding="utf-8",
            )

            prior = engine._mining_context(cycle_id=2)["prior_slow_work"][0]

            self.assertEqual(
                prior["refined_hypotheses"][0],
                {
                    "hypothesis": refined,
                    "reasons": ["The visible controls show the same pattern."],
                },
            )
            self.assertEqual(
                prior["evidence_unavailable"][0],
                {
                    "hypothesis": unavailable,
                    "reasons": ["No query-relevant 10-Q was available."],
                },
            )
            self.assertEqual(prior["h1_input_fingerprint"], "h1-input-hash")
            self.assertEqual(
                prior["h1_conclusion"]["conclusion"],
                "no_testable_hypothesis",
            )

    def test_signal_update_uses_one_induction_call_and_local_holdout_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            stable = registry.load_spec("revenue_growth_yoy:v1")
            for index in range(2):
                registry.record_learning_event(
                    SignalLearningEvent(
                        event_id=f"wrong-event-{index}",
                        observation_key=f"wrong-observation-{index}",
                        signal_ref=stable.ref,
                        round_id=1,
                        plan_id=f"plan-{index}",
                        case_id=f"fast-case-{index}",
                        company_id=f"fast-issuer-{index}",
                        prediction_time=NOW.isoformat(),
                        selection={
                            "signal_ref": stable.ref,
                            "reason_code": "answer_need",
                            "selection_reason": "Test reported revenue growth.",
                            "applicability_hypothesis": "Annual periods are comparable.",
                            "expected_role": "primary",
                            "context_tags": ["comparable_financials"],
                        },
                        result_value=SignalValue.POSITIVE,
                        coverage=SignalCoverage.SUFFICIENT,
                        document_fingerprint=(f"hash-{index}",),
                        is_surge=False,
                        realized_max_multiple=1.2,
                        prediction_correct=False,
                    )
                )

            cases = tuple(
                [make_case(f"update_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"update_control_{index}", 1.1) for index in range(4)]
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"{case.company_id}:financial:{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                130.0 if case.ground_truth.is_surge else 125.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            updated = replace(
                stable,
                version=2,
                parameters={"positive_min": 0.28, "negative_max": 0.0},
            )
            fixture = json.loads(json.dumps(registry.load_tests(stable.ref)[0]))
            update_model = ScriptedUpdateModel(
                SignalUpdateDecision(
                    signal_ref=stable.ref,
                    disposition="update",
                    problem_type="threshold_false_positives",
                    rationale=("The current threshold is repeatedly too permissive.",),
                    changed_paths=("spec.parameters",),
                    case_diagnostics=(
                        {
                            "case_ref": "update-case-001",
                            "evidence_verdict": "supported",
                            "outcome_relation": "misaligned",
                        },
                        {
                            "case_ref": "update-case-002",
                            "evidence_verdict": "supported",
                            "outcome_relation": "misaligned",
                        },
                        {
                            "case_ref": "update-case-003",
                            "evidence_verdict": "contradicted",
                            "outcome_relation": "aligned",
                        },
                        {
                            "case_ref": "update-case-004",
                            "evidence_verdict": "insufficient",
                            "outcome_relation": "not_assessable",
                        },
                    ),
                    candidate={
                        "signal_ref": stable.ref,
                        "spec": updated.to_dict(),
                        "skill": None,
                        "tests": [fixture],
                    },
                )
            )
            workspace = EvolutionWorkspace(root / "workspace")
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=update_model,
                llm_signal_runner=None,
            )
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            committed = make_record(
                "update_target_round",
                0.5,
                (1.0, 0.0),
                round_id=1,
            )
            workspace.commit_round(
                round_id=1,
                records=(committed,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=(committed.plan_id,),
                ),
                signal_registry_version=snapshot.version,
                signal_registry_hash=snapshot.registry_hash,
                run_contract_hash="contract-hash",
            )

            result = engine.run_cycle(cycle_id=1, input_snapshot=snapshot)

            self.assertEqual(result.promoted, (updated.ref,))
            self.assertEqual(len(update_model.requests), 1)
            self.assertEqual(
                update_model.requests[0]["research_objective"], signal_research_objective()
            )
            self.assertNotIn("example", update_model.requests[0]["candidate_contract"])
            template = update_model.requests[0]["candidate_contract"][
                "vnext_template"
            ]
            self.assertEqual(
                update_model.requests[0]["candidate_contract"][
                    "changed_paths_allowed"
                ],
                list(SIGNAL_UPDATE_MUTABLE_PATHS),
            )
            self.assertIn(
                "spec.version",
                update_model.requests[0]["candidate_contract"][
                    "changed_paths_excluded"
                ],
            )
            self.assertEqual(
                template["spec"], {**stable.to_dict(), "version": 2}
            )
            self.assertIsNone(template["skill"])
            self.assertEqual(template["tests"], list(registry.load_tests(stable.ref)))
            self.assertNotIn("example", engine._mining_candidate_contract())
            from stock_opportunity_agent.signal_library import (
                deterministic_signal_function_contracts,
            )
            expected_functions = deterministic_signal_function_contracts(
                engine.validator.deterministic_functions
            )
            self.assertEqual(
                engine._mining_candidate_contract()["deterministic_function_contracts"],
                expected_functions,
            )
            self.assertEqual(
                update_model.requests[0]["candidate_contract"]["deterministic_function_contracts"],
                expected_functions,
            )
            self.assertEqual(
                engine._mining_candidate_contract()["execution_semantics"],
                signal_candidate_execution_contract(),
            )
            self.assertEqual(
                update_model.requests[0]["candidate_contract"]["execution_semantics"],
                signal_candidate_execution_contract(),
            )
            request_json = json.dumps(update_model.requests[0])
            for case in cases:
                self.assertNotIn(case.company_id, request_json)
            update_audit = result.agent_audits["update_pipeline"]
            self.assertEqual(update_audit["target_count"], 1)
            target_audit = update_audit["targets"][0]
            self.assertEqual(
                target_audit["diagnostic_counts"],
                {
                    "evidence_verdict": {
                        "supported": 2,
                        "contradicted": 1,
                        "insufficient": 1,
                    },
                    "outcome_relation": {
                        "aligned": 1,
                        "misaligned": 2,
                        "not_assessable": 1,
                    },
                },
            )
            for packet in update_model.requests[0]["induction_cases"]:
                observation = packet["evidence_observation"]
                self.assertIn(
                    "excerpt cannot prove",
                    observation["evidence_scope"],
                )
                self.assertEqual(len(observation["evidence"]), 1)
                self.assertTrue(observation["executed_evidence"])
                cited_refs = {
                    item["document_ref"]
                    for item in observation["executed_evidence"]
                }
                self.assertEqual(
                    observation["evidence"][0]["document_ref"],
                    next(iter(cited_refs)),
                )
                result_evidence = observation["current_signal_result"]["evidence"]
                self.assertTrue(
                    result_evidence["supporting"] or result_evidence["counter"]
                )
                self.assertEqual(
                    {
                        item["document_id"]
                        for group in ("supporting", "counter")
                        for item in result_evidence[group]
                    },
                    cited_refs,
                )
            for resolution in target_audit["resolutions"]:
                self.assertTrue(resolution["reused_signal_execution_input"])
                self.assertEqual(resolution["document_count"], 1)
                self.assertEqual(len(resolution["document_ids"]), 1)
                self.assertEqual(len(resolution["document_hashes"]), 1)
                self.assertTrue(
                    resolution["input_request"]["request_id"].startswith("signal:")
                )
                self.assertEqual(
                    resolution["input_request"]["query"], "revenue sales"
                )
            induction_ids = set(
                target_audit["local_selection"]["induction_case_ids"]
            )
            holdout_ids = set(
                target_audit["local_selection"]["holdout_case_ids"]
            )
            self.assertFalse(induction_ids & holdout_ids)
            self.assertTrue(update_audit["model_called"])
            effectiveness = result.candidate_effectiveness[updated.ref]
            self.assertEqual(effectiveness["disposition"], "promoted")
            self.assertLess(
                effectiveness["candidate"]["directional_wrong"],
                effectiveness["current"]["directional_wrong"],
            )

    def test_mining_tool_rejects_existing_stable_signal_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )

            with self.assertRaisesRegex(
                ValidationError, "duplicates stable Signal identity"
            ):
                engine._stage_from_tool(
                    spec=registry.load_spec("price_momentum_126d:v1").to_dict(),
                    skill=None,
                    tests=(candidate_growth_fixture(),),
                    origin="mining",
                    collected=[],
                )

    def test_candidate_validation_rejects_leakage_duplicate_and_bad_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            validator = SignalCandidateValidator(registry, llm_runner=None)
            leaking = SignalSpec(
                signal_id="future_outcome_hint",
                version=1,
                category="risks",
                description="Use future price to infer the outcome label.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            finding = validator.validate(leaking, skill=None, tests=())
            self.assertFalse(finding.accepted)
            self.assertTrue(any("leakage" in reason for reason in finding.reasons))
            duplicate = SignalSpec(
                signal_id="duplicate_growth",
                version=1,
                category="financial",
                description=registry.latest_spec("revenue_growth_yoy").description,
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            self.assertFalse(
                validator.validate(duplicate, skill=None, tests=()).accepted
            )
            bad_update = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=3,
                category="financial",
                description="Updated growth measure.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            self.assertFalse(
                validator.validate(bad_update, skill=None, tests=()).accepted
            )

            common_word_validator = SignalCandidateValidator(
                registry,
                llm_runner=None,
                forbidden_identity_terms=("FOR",),
            )
            prose_candidate = SignalSpec(
                signal_id="catalyst_handling_quality",
                version=1,
                category="catalysts",
                description=(
                    "Measure year-over-year revenue growth while checking handling "
                    "for positive catalyst evidence."
                ),
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            self.assertTrue(
                common_word_validator.validate(
                    prose_candidate,
                    skill=None,
                    tests=(candidate_growth_fixture(),),
                ).accepted
            )

    def test_paired_effectiveness_tiers_a_directional_tie_into_provisional(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = (
                *(make_case(f"tier_positive_{index}", 4.0) for index in range(2)),
                *(make_case(f"tier_control_{index}", 1.1) for index in range(2)),
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"tier_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            current = registry.latest_spec("revenue_growth_yoy")
            candidate = SignalSpec(
                **{
                    **current.__dict__,
                    "signal_id": "novel_tier_measurement",
                    "version": 1,
                    "description": "Novel growth framing for tier testing.",
                }
            )

            result = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=cases,
                llm_runner=None,
            ).evaluate(candidate, skill=None)

            self.assertFalse(result.accepted)
            self.assertEqual(result.disposition, "provisional")
            self.assertIn(
                "lacks positive directional evidence",
                " ".join(result.reasons),
            )

    def test_paired_effectiveness_blocks_a_cowardly_new_signal(self) -> None:
        def coward_signal(spec, documents, as_of):
            document = documents[0]
            payload = json.loads(document.content)
            records = payload["facts"]["us-gaap"][
                "RevenueFromContractWithCustomerExcludingAssessedTax"
            ]["units"]["USD"]
            latest = max(records, key=lambda row: row["end"])
            declined = float(latest["val"]) < float(
                next(
                    row["val"]
                    for row in records
                    if row["end"] < latest["end"]
                )
            )
            span = document.content
            evidence = (
                SignalEvidence(
                    document_id=document.document_id,
                    exact_span=span,
                    timestamp=document.available_at,
                ),
            )
            if declined:
                return SignalResult(
                    signal_id=spec.signal_id,
                    version=spec.version,
                    value=SignalValue.NEGATIVE,
                    confidence=0.5,
                    interpretation="Revenue decline supports a negative call.",
                    supporting_evidence=evidence,
                )
            return SignalResult(
                signal_id=spec.signal_id,
                version=spec.version,
                value=SignalValue.NEUTRAL,
                confidence=0.5,
                interpretation="Growth profile does not justify a call.",
                supporting_evidence=evidence,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = (
                *(make_case(f"coward_positive_{index}", 4.0) for index in range(2)),
                *(make_case(f"coward_control_{index}", 1.1) for index in range(2)),
            )
            documents = []
            for index, case in enumerate(cases):
                surge = case.ground_truth.is_surge
                documents.append(
                    RawInfoDocument.create(
                        document_id=f"coward_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                50.0 if not surge else 125.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                )
            current = registry.latest_spec("revenue_growth_yoy")
            candidate = SignalSpec(
                **{
                    **current.__dict__,
                    "signal_id": "cowardly_measurement",
                    "version": 1,
                    "description": "Fires only where decline makes it safe.",
                }
            )

            result = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=RawInfoStore(documents=tuple(documents)),
                discovery_cases=cases,
                llm_runner=None,
                deterministic_functions={
                    current.function: coward_signal,
                },
            ).evaluate(candidate, skill=None)

            self.assertFalse(result.accepted)
            self.assertEqual(result.disposition, "provisional")
            self.assertIn(
                "positive-label check cases unflagged",
                " ".join(result.reasons),
            )
            self.assertEqual(result.candidate_confusion["tp"], 0)
            self.assertEqual(result.candidate_confusion["fn"], 2)

    def test_paired_effectiveness_rejects_an_identical_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"paired_positive_{index}", 4.0)
                for index in range(4)
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"paired_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            current = registry.latest_spec("revenue_growth_yoy")
            candidate = SignalSpec(
                **{
                    **current.__dict__,
                    "version": current.version + 1,
                    "description": "Equivalent revenue-growth wording.",
                }
            )

            result = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=cases,
                llm_runner=None,
            ).evaluate(candidate, skill=None)

            self.assertFalse(result.accepted)
            self.assertIn(
                "no strict paired effectiveness gain",
                " ".join(result.reasons),
            )

    def test_paired_effectiveness_materializes_both_arms_before_freeze(self) -> None:
        class FinancialAdapter:
            provider = "fixture_financials"
            source_types = ("financials",)
            capabilities = ("financials",)

            def __init__(self) -> None:
                self.calls = 0

            def acquire(self, request, *, company_id, as_of, **_kwargs):
                self.calls += 1
                return AcquisitionResult(
                    documents=(
                        RawInfoDocument.create(
                            document_id=f"acquired-{company_id}",
                            company_id=company_id,
                            source_type="financials",
                            published_at=as_of,
                            available_at=as_of,
                            content=sec_company_facts_content(
                                ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                                ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                            ),
                        ),
                    )
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"paired_acquired_{index}", 4.0)
                for index in range(4)
            )
            store = RawInfoStore()
            adapter = FinancialAdapter()
            resolver = EvidenceResolver(
                store,
                adapters=(adapter,),
                policy=DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=(adapter.provider,),
                    allowed_capabilities=adapter.capabilities,
                    allowed_source_types=adapter.source_types,
                    max_requests_per_cycle=8,
                    max_requests_per_run=8,
                ),
            )
            current = registry.latest_spec("revenue_growth_yoy")
            candidate = SignalSpec(
                **{
                    **current.__dict__,
                    "version": current.version + 1,
                    "description": "Equivalent revenue-growth wording.",
                }
            )

            result = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=cases,
                llm_runner=None,
                evidence_resolver=resolver,
            ).evaluate(candidate, skill=None)

            self.assertEqual(adapter.calls, 4)
            self.assertEqual(result.candidate_available, 4)
            self.assertEqual(result.current_available, 4)
            self.assertEqual(result.candidate_execution_failed, 0)
            self.assertEqual(result.current_execution_failed, 0)
            self.assertTrue(
                all(
                    row["candidate"]["resolution_status"] == "resolved"
                    and row["current"]["resolution_status"] == "resolved"
                    for row in result.case_diagnostics
                )
            )

    def test_paired_effectiveness_rejects_still_wrong_update_that_abstains(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"paired_case_{index}", 4.0) for index in range(4)
            )
            current = registry.latest_spec("revenue_growth_yoy")
            candidate = SignalSpec(
                **{
                    **current.__dict__,
                    "version": current.version + 1,
                    "description": "A candidate that merely abstains once.",
                }
            )

            with mock.patch(
                "stock_opportunity_agent.research.signal_evolution."
                "_signal_effectiveness_counts",
                side_effect=[(4, 3, 0, 3, 0), (4, 4, 0, 4, 0)],
            ):
                result = SignalCandidateEffectivenessEvaluator(
                    registry,
                    raw_info_store=RawInfoStore(),
                    discovery_cases=cases,
                    llm_runner=None,
                ).evaluate(candidate, skill=None)

            self.assertFalse(result.accepted)
            self.assertIn(
                "candidate lacks positive directional evidence over controls",
                result.reasons,
            )
            self.assertNotIn(
                "candidate shows no strict paired effectiveness gain",
                result.reasons,
            )

    def test_effectiveness_excludes_induction_and_marks_sparse_support_provisional(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            induction = (
                make_case("induction_positive", 4.0),
                make_case("induction_control", 1.1),
            )
            validation = (
                make_case("validation_positive", 4.0),
                make_case("validation_control", 1.1),
            )
            cases = (*induction, *validation)
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"independent_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                125.0 if case.ground_truth.is_surge else 90.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            candidate = SignalSpec(
                signal_id="independent_growth_direction",
                version=1,
                category="financial",
                description="Classify comparable revenue growth direction.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            evaluator = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=cases,
                llm_runner=None,
                case_limit=2,
                minimum_cases=2,
            )

            accepted = evaluator.evaluate(
                candidate,
                skill=None,
                preferred_case_ids=tuple(case.case_id for case in validation),
                excluded_case_ids=tuple(case.case_id for case in induction),
                induction_supported=True,
            )
            provisional = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=induction,
                llm_runner=None,
                case_limit=2,
                minimum_cases=2,
            ).evaluate(
                candidate,
                skill=None,
                excluded_case_ids=tuple(case.case_id for case in induction),
                induction_supported=True,
            )

            self.assertTrue(accepted.accepted)
            self.assertEqual(accepted.disposition, "promoted")
            self.assertEqual(set(accepted.case_ids), {case.case_id for case in validation})
            self.assertEqual(provisional.disposition, "provisional")
            self.assertFalse(provisional.accepted)

    def test_update_reuses_provisional_vnext_on_a_new_check_identity(self) -> None:
        class FailIfCalledUpdateModel(NoChangeUpdateModel):
            def update(self, payload):
                raise AssertionError("provisional vNext should be reused")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            dev_cases = tuple(
                [make_case(f"reuse_control_{index}", 1.1) for index in range(2)]
                + [make_case(f"reuse_positive_{index}", 4.0) for index in range(2)]
            )
            check_cases = tuple(
                make_case(f"reuse_check_{index}", 4.0) for index in range(4)
            )
            documents = tuple(
                RawInfoDocument.create(
                    document_id=f"reuse-financial-{index}",
                    company_id=case.company_id,
                    source_type="financials",
                    published_at=NOW,
                    available_at=NOW,
                    content=sec_company_facts_content(
                        ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                        ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                    ),
                )
                for index, case in enumerate((*dev_cases, *check_cases))
            )
            store = RawInfoStore(documents=documents)
            workspace = EvolutionWorkspace(root / "workspace")
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=(*dev_cases, *check_cases),
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=FailIfCalledUpdateModel(),
                llm_signal_runner=None,
            )
            current = registry.latest_spec("revenue_growth_yoy")
            candidate = SignalSpec(
                **{
                    **current.__dict__,
                    "version": current.version + 1,
                    "description": "Provisional revenue-growth wording.",
                }
            )
            registry.stage_candidate(
                candidate,
                skill=None,
                tests=registry.load_tests(current.ref),
                origin=f"update:{current.ref}",
            )
            candidate_hash = registry.candidate_hash(candidate.ref)
            evaluation_identity = engine.effectiveness_evaluator.evaluation_identity(
                candidate,
                candidate_hash=candidate_hash,
                preferred_case_ids=tuple(case.case_id for case in check_cases),
                excluded_case_ids=tuple(case.case_id for case in dev_cases),
                induction_supported=True,
                strict_preferred=True,
            )
            registry.record_candidate_validation(
                candidate.ref,
                candidate_hash=candidate_hash,
                evaluation_identity=evaluation_identity,
                accepted=False,
                reasons=("paired sample is temporarily sparse",),
                contract_validation={"accepted": True},
                effectiveness={
                    "schema_version": "signal-candidate-effectiveness-v4",
                    "signal_ref": candidate.ref,
                    "accepted": False,
                    "disposition": "provisional",
                    "reasons": ["paired sample is temporarily sparse"],
                },
            )
            executor = SignalExecutor(registry.freeze(), store)

            result = engine._run_one_signal_update(
                cycle_id=2,
                target={
                    "signal_ref": current.ref,
                    "problem_type": "repeated_explicit_misleading",
                },
                cases=dev_cases,
                check_cases=check_cases,
                executor=executor,
            )

            self.assertEqual(result["candidate_refs"], (candidate.ref,))
            self.assertEqual(
                result["audit"]["disposition"],
                "reused_provisional_new_evaluation",
            )

    def test_slow_loop_validates_and_auto_promotes_exact_batch_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            new_spec = SignalSpec(
                signal_id="discovery_growth_quality",
                version=1,
                category="financial",
                description=(
                    "Measure the latest point-in-time year-over-year revenue growth "
                    "with a stricter positive threshold."
                ),
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
                parameters={"positive_min": 0.10, "negative_max": 0.0},
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="broad_growth",
                statement="Point-in-time revenue acceleration separates winners.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases show stronger growth.",
                source_types=("financials",),
                query="revenue",
                falsifiers=("Controls show the same growth.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                rankings={
                    "broad_growth": tuple(
                        f"case-{index:03d}" for index in range(1, 9)
                    )
                },
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="broad_growth",
                        disposition="supported",
                        rationale=("Positive and control cases separate consistently.",),
                        candidate={
                            "spec": new_spec.to_dict(),
                            "skill": None,
                            "tests": [candidate_growth_fixture()],
                        },
                    ),
                ),
            )
            discovery_cases = tuple(
                [
                    make_case(f"discovery_positive_{index}", 4.0)
                    for index in range(8)
                ]
                + [
                    make_case(f"discovery_control_{index}", 1.1)
                    for index in range(8)
                ]
            )
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"effectiveness_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                115.0 if case.ground_truth.is_surge else 90.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(discovery_cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=discovery_cases,
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(discovery_cases) // 2),
            )
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            committed = make_record(
                "plan_before_signal_promotion",
                0.8,
                (1.0, 0.0),
                round_id=1,
            )
            workspace.commit_round(
                round_id=1,
                records=(committed,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=(committed.plan_id,),
                ),
                signal_registry_version=snapshot.version,
                signal_registry_hash=snapshot.registry_hash,
                run_contract_hash="contract-hash",
            )
            original_bump_version = registry.bump_version

            def interrupt_before_version_commit():
                registry.bump_version = original_bump_version
                raise RuntimeError("simulated interruption before Registry version commit")

            registry.bump_version = interrupt_before_version_commit
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                engine.run_cycle(cycle_id=1, input_snapshot=snapshot)
            self.assertEqual(registry.version, 1)
            mining_request_count = len(mining_model.requests)

            result = engine.run_cycle(cycle_id=1)
            self.assertEqual(
                set(result.validated_candidates),
                {"discovery_growth_quality:v1"},
            )
            self.assertEqual(set(result.promoted), set(result.validated_candidates))
            self.assertEqual(
                result.agent_audits["mining_pipeline"]["track"],
                "hypothesis",
            )
            sample_basis = result.agent_audits["mining_pipeline"]["stages"][
                "H3"
            ]["decisions"][0]["sample_basis"]
            self.assertEqual(len(sample_basis["positive_refs"]), 2)
            self.assertEqual(len(sample_basis["control_refs"]), 2)
            self.assertEqual(result.input_registry_version, 1)
            self.assertEqual(result.output_registry_version, 2)
            self.assertEqual(len(result.search_input_fingerprint), 64)
            self.assertEqual(registry.latest_spec("revenue_growth_yoy").version, 1)
            self.assertFalse(
                (
                    root
                    / "signals_candidates"
                    / "financial"
                    / "discovery_growth_quality"
                    / "v1"
                    / "approval.json"
                ).exists()
            )
            promoted = engine.run_cycle(cycle_id=1)
            self.assertEqual(
                set(promoted.promoted),
                {"discovery_growth_quality:v1"},
            )
            self.assertEqual(promoted.registry_version, 2)
            self.assertEqual(
                promoted.search_input_fingerprint,
                result.search_input_fingerprint,
            )
            self.assertEqual(len(mining_model.requests), mining_request_count)
            self.assertEqual(registry.latest_spec("revenue_growth_yoy").version, 1)
            self.assertEqual(registry.latest_spec("discovery_growth_quality").version, 1)

            class PromotedSignalSelector:
                def __init__(self) -> None:
                    self.selected_refs = []

                def select(
                    self,
                    information_needs,
                    signal_registry,
                    prior_signal_fingerprints=None,
                    prior_signal_results=None,
                    eligible_signal_refs=None,
                    research_state=None,
                    prior_context_tags=(),
                ):
                    self.selected_refs.append(new_spec.ref)
                    self.asserted_registry_refs = tuple(
                        item.ref for item in signal_registry.specs
                    )
                    return AgentStep(
                        (
                            SignalSelectionDecision(
                                signal_ref=new_spec.ref,
                                reason_code="answer_need",
                                selection_reason=(
                                    "Use the newly promoted growth measurement."
                                ),
                                applicability_hypothesis=(
                                    "Comparable annual financial periods exist."
                                ),
                                expected_role="primary",
                                context_tags=("comparable_financials",),
                            ),
                        ),
                        AgentUsage(llm_calls=1),
                    )

            selector = PromotedSignalSelector()
            next_fast_case = discovery_cases[0]
            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id=next_fast_case.company_id,
                case_id=next_fast_case.case_id,
                company_basic_source=next_fast_case.basic_info,
                prediction_time=next_fast_case.prediction_time,
                signal_registry=registry.freeze(),
                signal_executor=SignalExecutor(registry.freeze(), raw_store),
                controller=OneBatchController(),
                signal_agent=selector,
                predictor=FixedPredictor(),
                prediction_sink=lambda *_args: "next-fast-prediction.json",
                ground_truth_provider=lambda _company_id: next_fast_case.ground_truth,
            )
            self.assertIn(new_spec.ref, selector.asserted_registry_refs)
            self.assertEqual(selector.selected_refs, [new_spec.ref])
            self.assertEqual(
                trajectory.signal_rounds[0].selections[0].signal_ref,
                new_spec.ref,
            )
            self.assertEqual(
                trajectory.signal_rounds[0].batch.results[0].ref,
                new_spec.ref,
            )
            self.assertEqual(
                trajectory.signal_rounds[0].batch.results[0].execution_status,
                SignalExecutionStatus.SUCCESS,
            )

    def test_mining_controller_rejects_malformed_candidate_spec_locally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            invalid_spec = registry.load_spec("guidance_acceleration:v1").to_dict()
            invalid_spec["execution"].pop("type")
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="guidance_change",
                statement="Explicit guidance changes separate winners.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases raise guidance.",
                source_types=("news",),
                query="guidance",
                falsifiers=("Controls raise guidance equally often.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                rankings={"guidance_change": ("case-001", "case-002")},
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="guidance_change",
                        disposition="supported",
                        rationale=("The small sample separates.",),
                        candidate={
                            "spec": invalid_spec,
                            "skill": None,
                            "tests": [],
                        },
                    ),
                ),
            )
            positive = make_case("discovery_positive", 4.0)
            control = make_case("discovery_control", 1.1)
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"guidance_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} management changed "
                            "guidance."
                        ),
                    )
                    for index, case in enumerate((positive, control))
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(positive, control),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(2),
            )

            result = engine._validate_cycle(registry.freeze())

            self.assertEqual(result.validated_candidates, {})
            self.assertIn(
                "candidate SignalSpec JSON is invalid",
                str(result.rejected["slow_loop:mining_stage:guidance_change"]),
            )

    def test_exploration_freezes_label_hidden_signatures_before_reveal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"explore_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"explore_control_{index}", 1.1) for index in range(4)]
            )
            selection = exploration_selection(
                cases, cycle_id=3, induction_per_class=2, validation_per_class=2
            )
            induction_refs = selection["e1_refs"]
            mining_model = ScriptedMiningModel(
                signatures=tuple(
                    SignalMiningSignature(
                        case_ref=case_ref,
                        observations=(
                            SignalMiningObservation(
                                summary="A bounded observable event is present.",
                                document_ref="document-01",
                                exact_span="A bounded observable event was reported.",
                            ),
                        ),
                    )
                    for case_ref in induction_refs
                ),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="exploration_pattern",
                        disposition="refine",
                        rationale=("The extracted pattern needs more cases.",),
                    ),
                ),
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"exploration_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported: "
                            "A bounded observable event was reported."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(cases)),
            )

            result = engine._run_signal_mining(cycle_id=3)

            e1_payload, e2_payload = mining_model.requests
            for payload in (e1_payload, e2_payload):
                self.assertEqual(payload["research_objective"], signal_research_objective())
                self.assertEqual(payload["fixed_prior"], engine.priors.mine_signal)
            from stock_opportunity_agent.research.evolution_transport import _scan_payload
            _scan_payload(e1_payload, allow_outcomes=False, anonymous_aliases=())
            self.assertNotIn('"label"', json.dumps(e1_payload))
            self.assertEqual(
                {item["label"] for item in e2_payload["signatures"]},
                {"positive", "control"},
            )
            self.assertEqual(
                result["refined_hypotheses"]["exploration_pattern"],
                ("The extracted pattern needs more cases.",),
            )
            sample_basis = result["audit"]["stages"]["E2"]["decisions"][0][
                "sample_basis"
            ]
            self.assertEqual(len(sample_basis["positive_refs"]), 2)
            self.assertEqual(len(sample_basis["control_refs"]), 2)

    def test_exploration_uses_exact_available_source_type_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"catalog_positive_{index}", 4.0) for index in range(3)]
                + [make_case(f"catalog_control_{index}", 1.1) for index in range(3)]
            )
            selection = exploration_selection(
                cases, cycle_id=3, induction_per_class=1, validation_per_class=1
            )
            literal = "A bounded source fact was reported."
            mining_model = ScriptedMiningModel(
                signatures=tuple(
                    SignalMiningSignature(
                        case_ref=case_ref,
                        observations=(
                            SignalMiningObservation(
                                summary="One source fact was visible.",
                                document_ref="document-01",
                                exact_span=literal,
                            ),
                        ),
                    )
                    for case_ref in selection["e1_refs"]
                )
            )
            available_types = (
                "8-k", "financials", "market_data", "news", "transcript",
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"catalog-{index}",
                        company_id=cases[0].company_id,
                        source_type=source_type,
                        published_at=NOW,
                        available_at=NOW,
                        content=literal,
                    )
                    for index, source_type in enumerate(available_types)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=6,
                    ranking_case_limit=6,
                    h2_profile_scan_limit=6,
                    h2_min_ready_issuers=6,
                    h2_min_ready_per_class=3,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )
            captured_source_types = []

            def packet(case_ref, _case, *, source_types, **_kwargs):
                captured_source_types.append(tuple(source_types))
                return (
                    {
                        "case_ref": case_ref,
                        "evidence": [{
                            "document_ref": "document-01",
                            "content_excerpt": literal,
                        }],
                    },
                    {"case_ref": case_ref, "status": "resolved", "usable": True},
                )

            with mock.patch.object(
                engine, "_mining_evidence_packet", side_effect=packet
            ):
                engine._run_signal_mining(cycle_id=3)

            self.assertTrue(captured_source_types)
            self.assertTrue(
                all(
                    value == tuple(sorted(available_types))
                    for value in captured_source_types
                )
            )

    def test_exploration_does_not_call_e2_when_one_group_lacks_grounding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"explore_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"explore_control_{index}", 1.1) for index in range(4)]
            )
            selection = exploration_selection(
                cases, cycle_id=3, induction_per_class=2, validation_per_class=2
            )
            induction_refs = selection["e1_refs"]
            failed_ref = selection["e1_by_class"][True][0]
            signatures = []
            for case_ref in induction_refs:
                if case_ref == failed_ref:
                    signatures.append(
                        SignalMiningSignature(
                            case_ref=case_ref,
                            observations=(),
                            evidence_gaps=("No supportable observation was visible.",),
                        )
                    )
                else:
                    signatures.append(
                        SignalMiningSignature(
                            case_ref=case_ref,
                            observations=(
                                SignalMiningObservation(
                                    summary="A bounded event was reported.",
                                    document_ref="document-01",
                                    exact_span="A bounded observable event was reported.",
                                ),
                            ),
                        )
                    )
            mining_model = ScriptedMiningModel(signatures=tuple(signatures))
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"exploration_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported: "
                            "A bounded observable event was reported."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(cases)),
            )

            result = engine._run_signal_mining(cycle_id=3)

            self.assertEqual(len(mining_model.requests), 1)
            self.assertEqual(
                result["audit"]["stages"]["E2"]["status"],
                "not_called_evidence_unavailable",
            )
            self.assertIn("exploration_evidence", result["refined_hypotheses"])

    def test_exploration_budget_failure_propagates_to_cycle_control(self) -> None:
        class BudgetLimitedMiningModel(EmptyMiningModel):
            def extract_exploration(self, payload):
                raise RuntimeBudgetExceeded("E1 request exceeds frozen budget")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"budget_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"budget_control_{index}", 1.1) for index in range(4)]
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"budget_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported one "
                            "bounded observable operating event."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=BudgetLimitedMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(cases)),
            )

            with self.assertRaisesRegex(
                RuntimeBudgetExceeded, "E1 request exceeds frozen budget"
            ):
                engine._run_exploration_mining(cycle_id=3)

    def test_exploration_microbatch_failure_preserves_valid_siblings(self) -> None:
        class OneFailedMicrobatchModel(ScriptedMiningModel):
            def __init__(self, *, failed_ref, **kwargs):
                super().__init__(**kwargs)
                self.failed_ref = failed_ref

            def extract_exploration(self, payload):
                refs = [item["case_ref"] for item in payload["cases"]]
                if self.failed_ref in refs:
                    self.requests.append(dict(payload))
                    raise CandidateExecutionRejected(
                        "signal_mining_exploration_extract",
                        "one isolated response remained malformed",
                        AgentUsage(llm_calls=2),
                    )
                return super().extract_exploration(payload)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"micro_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"micro_control_{index}", 1.1) for index in range(4)]
            )
            selection = exploration_selection(
                cases, cycle_id=3, induction_per_class=1, validation_per_class=1
            )
            failed_ref = selection["e1_by_class"][True][0]
            signatures = tuple(
                SignalMiningSignature(
                    case_ref=case_ref,
                    observations=(
                        SignalMiningObservation(
                            summary="A bounded event was reported.",
                            document_ref="document-01",
                            exact_span="A bounded observable event was reported.",
                        ),
                    ),
                )
                for case_ref in selection["e1_refs"]
            )
            mining_model = OneFailedMicrobatchModel(
                failed_ref=failed_ref,
                signatures=signatures,
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="microbatch_pattern",
                        disposition="refine",
                        rationale=("More evidence is required.",),
                    ),
                ),
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"micro-news-{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported: "
                            "A bounded observable event was reported."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            config = SignalMiningConfig(
                case_pool_limit=8,
                ranking_case_limit=8,
                h2_profile_scan_limit=8,
                h2_min_ready_issuers=8,
                h2_min_ready_per_class=4,
                induction_cases_per_class=1,
                validation_cases_per_class=1,
                exploration_microbatch_size=1,
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=config,
            )

            result = engine._run_signal_mining(cycle_id=3)

            e1 = result["audit"]["stages"]["E1"]
            self.assertEqual(len(e1["microbatches"]), 4)
            self.assertEqual(e1["failures"].keys(), {failed_ref})
            self.assertEqual(len(e1["signatures"]), 3)
            self.assertIn("microbatch_pattern", result["refined_hypotheses"])
            self.assertEqual(
                result["audit"]["local_selection"]["validation_case_refs"],
                list(selection["validation_refs"]),
            )
            self.assertIn(
                f"slow_loop:exploration_e1:{failed_ref}", result["failures"]
            )

    def test_exploration_uses_bounded_same_group_evidence_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"explore_positive_{index}", 4.0) for index in range(6)]
                + [make_case(f"explore_control_{index}", 1.1) for index in range(6)]
            )
            selection = exploration_selection(
                cases, cycle_id=3, induction_per_class=2, validation_per_class=2
            )
            e1_refs = selection["e1_refs"]
            failed_ref = selection["e1_by_class"][True][0]
            signatures = tuple(
                SignalMiningSignature(
                    case_ref=case_ref,
                    observations=(
                        ()
                        if case_ref == failed_ref
                        else (
                            SignalMiningObservation(
                                summary="A bounded event was reported.",
                                document_ref="document-01",
                                exact_span=(
                                    "A bounded observable event was reported."
                                ),
                            ),
                        )
                    ),
                    evidence_gaps=(
                        ("No supportable observation was visible.",)
                        if case_ref == failed_ref
                        else ()
                    ),
                )
                for case_ref in e1_refs
            )
            mining_model = ScriptedMiningModel(
                signatures=tuple(reversed(signatures)),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="exploration_pattern",
                        disposition="refine",
                        rationale=("The extracted pattern needs more cases.",),
                    ),
                ),
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"exploration_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported: "
                            "A bounded observable event was reported."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(cases)),
            )

            result = engine._run_signal_mining(cycle_id=3)

            self.assertEqual(len(mining_model.requests), 2)
            grounded_by_class = {
                label: tuple(
                    ref
                    for ref in refs
                    if ref != failed_ref
                )[:2]
                for label, refs in selection["e1_by_class"].items()
            }
            expected_grounded = [
                ref
                for ref in selection["all_refs"]
                if ref in {*grounded_by_class[True], *grounded_by_class[False]}
            ]
            self.assertEqual(
                [item["case_ref"] for item in mining_model.requests[1]["signatures"]],
                expected_grounded,
            )
            self.assertEqual(
                result["audit"]["local_selection"]["validation_case_refs"],
                list(selection["validation_refs"]),
            )

    def test_exploration_reference_order_is_independent_of_outcomes(self) -> None:
        cases = tuple(
            [make_case(f"shuffle_positive_{index}", 4.0) for index in range(4)]
            + [make_case(f"shuffle_control_{index}", 1.1) for index in range(4)]
        )
        swapped = tuple(
            replace(
                case,
                ground_truth=GroundTruth(
                    1.1 if case.ground_truth.is_surge else 4.0
                ),
            )
            for case in cases
        )

        original_pairs = _exploration_case_pairs(cases, cycle_id=7)
        swapped_pairs = _exploration_case_pairs(swapped, cycle_id=7)

        self.assertEqual(
            [(ref, case.case_id) for ref, case in original_pairs],
            [(ref, case.case_id) for ref, case in swapped_pairs],
        )

    def test_exploration_rejects_a_fabricated_document_ref(self) -> None:
        signatures = (
            SignalMiningSignature(
                case_ref="case-001",
                observations=(
                    SignalMiningObservation(
                        summary="A bounded event was reported.",
                        document_ref="fabricated-document",
                        exact_span="A bounded observable event was reported.",
                    ),
                ),
            ),
        )

        with self.assertRaisesRegex(ValidationError, "unknown document_ref"):
            validate_signal_mining_signatures(
                signatures,
                (
                    {
                        "case_ref": "case-001",
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": (
                                    "A bounded observable event was reported."
                                ),
                            }
                        ],
                    },
                ),
            )

    def test_exploration_rejects_a_malformed_evidence_collection(self) -> None:
        signatures = (
            SignalMiningSignature(
                case_ref="case-001",
                observations=(),
                evidence_gaps=("No supportable observation was visible.",),
            ),
        )

        with self.assertRaisesRegex(ValidationError, "evidence must be an array"):
            validate_signal_mining_signatures(
                signatures,
                ({"case_ref": "case-001", "evidence": "not-an-array"},),
            )

    def test_exploration_rejects_a_malformed_evidence_item(self) -> None:
        signatures = (
            SignalMiningSignature(
                case_ref="case-001",
                observations=(),
                evidence_gaps=("No supportable observation was visible.",),
            ),
        )

        with self.assertRaisesRegex(ValidationError, "requires content_excerpt"):
            validate_signal_mining_signatures(
                signatures,
                (
                    {
                        "case_ref": "case-001",
                        "evidence": [{"document_ref": "document-01"}],
                    },
                ),
            )

    def test_signal_learning_keeps_plan_reasons_but_dedupes_effectiveness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            for index, reason in enumerate(("test growth", "confirm growth"), start=1):
                registry.record_learning_event(
                    SignalLearningEvent(
                        event_id=f"event-{index}",
                        observation_key="same-case-input",
                        signal_ref="revenue_growth_yoy:v1",
                        round_id=1,
                        plan_id=f"plan-{index}",
                        case_id="case-1",
                        company_id="issuer-1",
                        prediction_time=NOW.isoformat(),
                        selection={
                            "signal_ref": "revenue_growth_yoy:v1",
                            "reason_code": "answer_need",
                            "selection_reason": reason,
                            "applicability_hypothesis": "Comparable periods exist.",
                            "expected_role": "primary",
                            "context_tags": ["comparable_financials"],
                        },
                        result_value=SignalValue.POSITIVE,
                        coverage=SignalCoverage.SUFFICIENT,
                        document_fingerprint=("doc-hash",),
                        is_surge=True,
                        realized_max_multiple=3.0,
                        prediction_correct=True,
                    )
                )

            events = registry.load_learning_events("revenue_growth_yoy:v1")
            profile = registry.load_learning_profile("revenue_growth_yoy:v1")
            self.assertEqual(len(events), 2)
            self.assertEqual(
                {event.selection["selection_reason"] for event in events},
                {"test growth", "confirm growth"},
            )
            self.assertEqual(profile["selection_events"], 2)
            self.assertEqual(profile["unique_observations"], 1)
            self.assertNotIn("test growth", json.dumps(profile))
            self.assertNotIn("plan-1", json.dumps(profile))
            self.assertNotIn("case-1", json.dumps(profile))
            self.assertEqual(
                profile["state_outcome_matrix"]["positive"]["surge"], 1
            )
            cycle_start = registry.freeze(learning_round_cutoff=0)
            resumed_same_cycle = registry.freeze(learning_round_cutoff=0)
            next_cycle = registry.freeze(learning_round_cutoff=1)
            self.assertEqual(cycle_start.learning_hash, resumed_same_cycle.learning_hash)
            self.assertNotEqual(cycle_start.learning_hash, next_cycle.learning_hash)
            self.assertEqual(
                cycle_start.learned_profiles["revenue_growth_yoy:v1"][
                    "unique_observations"
                ],
                0,
            )

    def test_learning_disagreement_is_quarantined_and_replay_repairs_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            first = SignalLearningEvent(
                event_id="first", observation_key="same-input",
                signal_ref="revenue_growth_yoy:v1", round_id=1,
                plan_id="plan-1", case_id="case-1", company_id="issuer-1",
                prediction_time=NOW.isoformat(),
                selection={
                    "signal_ref": "revenue_growth_yoy:v1",
                    "reason_code": "answer_need", "selection_reason": "Test growth.",
                    "applicability_hypothesis": "Comparable periods exist.",
                    "expected_role": "primary", "context_tags": ["comparable_financials"],
                },
                result_value=SignalValue.POSITIVE, coverage=SignalCoverage.SUFFICIENT,
                document_fingerprint=("doc-hash",), is_surge=True,
                realized_max_multiple=3.0, prediction_correct=True,
            )
            disagreement = replace(
                first, event_id="second", plan_id="plan-2",
                result_value=SignalValue.UNAVAILABLE, coverage=SignalCoverage.UNAVAILABLE,
            )
            sibling = replace(
                first, event_id="third", observation_key="other-input",
                case_id="case-2", company_id="issuer-2",
            )
            self.assertEqual(registry.record_learning_events((first, disagreement, sibling)), 3)
            profile = registry.load_learning_profile(first.signal_ref)
            self.assertEqual(profile["selection_events"], 3)
            self.assertEqual(profile["unique_observations"], 1)
            self.assertEqual(profile["disputed_observations"], 1)
            self.assertEqual(profile["state_outcome_matrix"]["positive"]["surge"], 1)
            self.assertEqual(profile["directional"]["unavailable"], 0)
            profile_path = registry._learning_dir(first.signal_ref) / "profile.json"
            profile_path.unlink()
            self.assertEqual(registry.record_learning_events((first, disagreement, sibling)), 0)
            self.assertEqual(registry.load_learning_profile(first.signal_ref), profile)
            self.assertEqual(len(registry.load_learning_events(first.signal_ref)), 3)
            with self.assertRaisesRegex(ValidationError, "conflicting duplicate"):
                registry.record_learning_event(replace(first, event_id="bad", is_surge=False))
            self.assertEqual(len(registry.load_learning_events(first.signal_ref)), 3)

    def test_slow_loop_context_cannot_access_locked_test(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            mining_model = EmptyMiningModel()
            update_model = NoChangeUpdateModel()
            raw_store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="discovery_doc",
                        company_id="discovery_only",
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="start " + ("evidence " * 2_000) + "end",
                    ),
                    RawInfoDocument.create(
                        document_id="locked_doc",
                        company_id="locked_company",
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="Locked evidence.",
                    ),
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(make_case("discovery_only", 3.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=update_model,
                llm_signal_runner=None,
            )
            validation = engine._validate_cycle(registry.freeze())
            mining_workspace = engine._mining_context(cycle_id=1)
            serialized = json.dumps(mining_workspace)
            self.assertNotIn("locked_company", serialized)
            self.assertFalse(mining_workspace["locked_test_available"])
            self.assertIn("capability_backlog", mining_workspace)
            self.assertTrue(
                all(
                    "learned_profile" not in card
                    for card in mining_workspace["stable_signal_cards"]
                )
            )
            self.assertTrue(
                all(
                    "learned_profile" in card.to_dict()
                    for category in registry.list_categories()
                    for card in registry.list_signal_cards(category)
                )
            )
            self.assertEqual(update_model.requests, [])
            self.assertEqual(
                validation.agent_audits["update_pipeline"]["disposition"],
                "no_actionable_target",
            )

    def test_h1_card_projection_retains_nonempty_learned_profile(self) -> None:
        card = {
            "signal_ref": "revenue_growth_yoy:v1",
            "learned_profile": {
                "selection_events": 1,
                "unique_observations": 0,
                "directional": {"correct": 0, "wrong": 0},
            },
        }

        view = SignalEvolutionEngine._mining_signal_card_view(card)

        self.assertEqual(view, card)
        self.assertIn("learned_profile", view)

    def test_h1_context_projects_vertical_reflection_into_action_need(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            record = replace(
                make_record("reflection_action_plan", 0.8, (1.0, 0.0)),
                reflection=PlanReflection(
                    next_explorations=(
                        "Compare disclosed cash runway against operating cash burn.",
                    )
                ),
            )
            plan_reflection = PlanMetaReflection.from_record(record)
            memory = PlanMetaMemory(
                entries=(
                    RoundMetaEntry(
                        round_id=1,
                        plan_reflections=(plan_reflection,),
                        evidence_refs=(record.plan_id,),
                    ),
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("reflection_case", 4.0),),
                meta_memory=memory,
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )

            context = engine._mining_context(cycle_id=1)
            actions = [
                item
                for item in context["capability_backlog"]["signal_need_items"]
                if item.get("kind") == "meta_reflection_action"
            ]

            self.assertEqual(len(actions), 1)
            self.assertTrue(actions[0]["need_ref"].startswith("reflection-"))
            self.assertIn("cash runway", actions[0]["need"])
            self.assertEqual(
                context["reflection_action_audit"],
                {
                    "schema_version": "reflection-action-projection-v1",
                    "available_count": 1,
                    "projected_count": 1,
                    "omitted_count": 0,
                    "limit": 48,
                    "field_counts": {
                        "next_explorations": 1,
                        "missing_information_needs": 0,
                        "repeated_failure_modes": 0,
                        "misleading_signals": 0,
                    },
                },
            )


class DualLoopTests(TestCase):
    def test_slow_bootstrap_runs_no_fast_round_and_preserves_round_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=0,
                cycle_mode="slow_bootstrap",
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            meta = PlanMetaMemory()
            proposer = CountingProposer()
            evaluator = SyntheticPlanEvaluator(include_signal=False)
            plan_engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            mining_model = EmptyMiningModel()
            signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            dataset = EvolutionDataset(
                discovery=(make_case("discovery_case", 4.0),),
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )
            progress_events = []

            result = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=0,
                cycle_mode="slow_bootstrap",
                on_progress=progress_events.append,
            ).run_cycle(cycle_id=1)

            self.assertEqual(result.plan_rounds, ())
            self.assertEqual(proposer.calls, [])
            self.assertEqual(evaluator.seen_company_ids, [])
            self.assertEqual(workspace.last_completed_round, 0)
            self.assertEqual(len(mining_model.requests), 0)
            event_types = [item["event_type"] for item in progress_events]
            self.assertNotIn("fast_loop_started", event_types)
            self.assertIn("slow_loop_started", event_types)

    def test_offline_dual_loop_freezes_signals_then_runs_one_slow_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            meta = PlanMetaMemory()
            proposer = CountingProposer()
            evaluator = SyntheticPlanEvaluator(include_signal=False)
            plan_engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            mining_model = EmptyMiningModel()
            signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            dataset = EvolutionDataset(
                discovery=(make_case("discovery_case", 4.0),),
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )
            result = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=1,
            ).run_cycle(cycle_id=1)
            self.assertEqual(len(result.plan_rounds), 1)
            self.assertEqual(result.signal_evolution.promoted, ())
            self.assertEqual(workspace.last_completed_round, 1)
            self.assertEqual(len(evaluator.seen_company_ids), 24)
            self.assertEqual(len(set(evaluator.seen_company_ids)), 24)
            self.assertEqual(mining_model.requests, [])

    def test_next_cycle_uses_promoted_registry_without_reevaluating_old_plans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            initial = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=initial.version,
                initial_signal_registry_hash=initial.registry_hash,
                observed_signal_registry_version=initial.version,
                observed_signal_registry_hash=initial.registry_hash,
            )
            meta = PlanMetaMemory()
            proposer = CountingProposer()
            evaluator = SyntheticPlanEvaluator(include_signal=False)
            plan_engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
                run_contract_hash="contract-hash",
            )
            new_spec = SignalSpec(
                signal_id="cross_cycle_growth_quality",
                version=1,
                category="financial",
                description="Measure point-in-time year-over-year revenue growth.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            discovery_cases = tuple(
                [
                    make_case(f"discovery_positive_{index}", 4.0)
                    for index in range(8)
                ]
                + [
                    make_case(f"discovery_control_{index}", 1.1)
                    for index in range(8)
                ]
            )
            signal_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"cross_cycle_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                125.0 if case.ground_truth.is_surge else 90.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(discovery_cases)
                )
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="cross_cycle_growth",
                statement="Revenue growth direction separates winners.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases have stronger growth.",
                source_types=("financials",),
                query="revenue",
                falsifiers=("Controls have indistinguishable growth.",),
            )
            first_signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=signal_store,
                discovery_cases=discovery_cases,
                meta_memory=meta,
                workspace=workspace,
                mining_model=ScriptedMiningModel(
                    hypotheses=(hypothesis,),
                    rankings={
                        "cross_cycle_growth": tuple(
                            f"case-{index:03d}" for index in range(1, 9)
                        )
                    },
                    decisions=(
                        SignalMiningDecision(
                            hypothesis_id="cross_cycle_growth",
                            disposition="supported",
                            rationale=("Positive and control cases separate.",),
                            candidate={
                                "spec": new_spec.to_dict(),
                                "skill": None,
                                "tests": [candidate_growth_fixture()],
                            },
                        ),
                    ),
                ),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(discovery_cases) // 2),
            )
            dataset = EvolutionDataset(
                discovery=discovery_cases,
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )
            first = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=first_signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=1,
            ).run_cycle(cycle_id=1)
            self.assertEqual(first.signal_evolution.promoted, (new_spec.ref,))
            workspace.stage_slow_result(
                cycle_id=1,
                result=first.signal_evolution.to_dict(),
            )
            promoted_snapshot = registry.freeze()
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=promoted_snapshot.version,
                observed_signal_registry_hash=promoted_snapshot.registry_hash,
            )
            old_record = plan_engine.archive.records[0]
            old_f1 = old_record.metrics.binary_f1

            second_cycle = workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=initial.version,
                initial_signal_registry_hash=initial.registry_hash,
                observed_signal_registry_version=promoted_snapshot.version,
                observed_signal_registry_hash=promoted_snapshot.registry_hash,
            )
            second_signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            second = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=second_signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=1,
            ).run_cycle(cycle_id=int(second_cycle["cycle_id"]))

            self.assertNotIn(new_spec.ref, evaluator.seen_registry_refs[0])
            self.assertIn(new_spec.ref, evaluator.seen_registry_refs[1])
            self.assertEqual(len(evaluator.seen_registry_refs), 2)
            self.assertEqual(len(evaluator.seen_company_ids), 48)
            self.assertEqual(len(plan_engine.archive.records), 2)
            self.assertEqual(old_record.metrics.binary_f1, old_f1)
            self.assertIn(old_record.plan_id, proposer.calls[1]["parents"])
            round_one_checkpoint = json.loads(
                (
                    workspace.experiments_root
                    / "round-0001"
                    / "checkpoint.json"
                ).read_text(encoding="utf-8")
            )
            round_two_checkpoint = json.loads(
                (
                    workspace.experiments_root
                    / "round-0002"
                    / "checkpoint.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(round_one_checkpoint["signal_registry_version"], 1)
            self.assertEqual(round_two_checkpoint["signal_registry_version"], 2)
            self.assertEqual(second.signal_evolution.output_registry_version, 2)

    def test_dual_loop_resume_runs_only_remaining_fast_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=2,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            committed = make_record(
                "plan_committed",
                0.75,
                HashingPlanEmbedder().embed(default_information_plan()),
                round_id=1,
            )
            workspace.commit_round(
                round_id=1,
                records=(committed,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=(committed.plan_id,),
                ),
                signal_registry_version=registry.version,
                signal_registry_hash=snapshot.registry_hash,
                run_contract_hash="contract-hash",
            )
            meta = workspace.restore_meta()
            proposer = CountingProposer()
            evaluator = SyntheticPlanEvaluator(include_signal=False)
            plan_engine = PlanEvolutionEngine(
                archive=workspace.restore_archive(),
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            mining_model = EmptyMiningModel()
            signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            dataset = EvolutionDataset(
                discovery=(make_case("discovery_case", 4.0),),
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )

            result = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=2,
            ).run_cycle(cycle_id=1, completed_plan_rounds=1)

            self.assertEqual([item.round_id for item in result.plan_rounds], [2])
            self.assertEqual(workspace.last_completed_round, 2)
            self.assertEqual(len(proposer.calls), 1)
            self.assertEqual(len(result.plan_rounds[0].records), 1)
            self.assertFalse(
                (workspace.evaluation_root / "round_002" / "champion.json").exists()
            )
            self.assertEqual(len(evaluator.seen_company_ids), 24)
