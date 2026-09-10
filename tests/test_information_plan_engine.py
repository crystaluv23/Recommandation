"""Information Plan execution, metrics, and evaluation sampling tests."""

from tests.scheme_evolution_test_support import *  # noqa: F403
from stock_opportunity_agent.research.evolution_core import (
    _prediction_baseline_from_market_documents,
)


class InformationPlanRuntimeTests(TestCase):
    def test_reflection_budget_fallback_uses_reserve_once_without_forcing_success(self) -> None:
        for paid_tokens, outcome in ((0, "finalize"), (7000, "finalize"),
                                     (7000, "exhausted"), (0, "continue")):
            with self.subTest(paid_tokens=paid_tokens, outcome=outcome):
                class BudgetController(OneBatchController):
                    def __init__(self):
                        super().__init__()
                        self.contexts = []
                        self.reflections = []

                    def initialize(self, plan, basic_info):
                        step = super().initialize(plan, basic_info)
                        return AgentStep(step.value, AgentUsage(llm_calls=1, tokens=150_000))

                    def set_request_token_budget(self, value):
                        self.budget = value

                    def set_reflection_runtime_context(self, **context):
                        self.contexts.append(context)

                    def reflect(self, plan, state, batch):
                        self.reflections.append((state, batch, self.budget))
                        if len(self.reflections) == 1:
                            raise RuntimeBudgetExceeded(
                                "request does not fit adaptive envelope",
                                usage=AgentUsage(llm_calls=int(paid_tokens > 0),
                                                 tokens=paid_tokens, cost=0.003),
                            )
                        if outcome == "exhausted":
                            raise RuntimeBudgetExceeded("terminal envelope also cannot fit")
                        if outcome == "continue":
                            return AgentStep(state, AgentUsage(llm_calls=1, tokens=20))
                        return super().reflect(plan, state, batch)

                with tempfile.TemporaryDirectory() as directory:
                    registry, store = self._registry_and_store(directory)
                    controller = BudgetController()
                    trajectory = execute_information_plan(
                        plan=default_information_plan(), company_id="winner_1",
                        company_basic_source={}, prediction_time=NOW,
                        signal_registry=registry.freeze(),
                        signal_executor=SignalExecutor(registry.freeze(), store),
                        controller=controller, signal_agent=OneSignalSelector(),
                        predictor=FixedPredictor(), prediction_sink=lambda *args: "pred",
                        ground_truth_provider=lambda company_id: GroundTruth(2.5),
                        limits=RuntimeLimits(),
                    )
                self.assertEqual(len(controller.reflections), 2)
                first, terminal = controller.reflections
                self.assertIs(first[0], terminal[0])
                self.assertIs(first[1], terminal[1])
                self.assertEqual(terminal[2] - first[2], 64_000 - paid_tokens)
                self.assertEqual([c["must_finalize"] for c in controller.contexts], [False, True])
                self.assertEqual(trajectory.termination_trigger, RuntimeStopReason.BUDGET_EXHAUSTED)
                self.assertEqual(
                    trajectory.stop_reason,
                    RuntimeStopReason.FINALIZED if outcome == "finalize"
                    else RuntimeStopReason.BUDGET_EXHAUSTED,
                )
                self.assertEqual(trajectory.final_state.decision is ResearchDecision.FINALIZE,
                                 outcome == "finalize")
                self.assertGreaterEqual(trajectory.usage.model.tokens, 150_000 + paid_tokens)

    def test_predictor_preserves_complete_evidence_above_display_target(self) -> None:
        literal = "Complete source sentence with a qualifier. " * 700
        state = ResearchState(
            supporting_evidence=(ResearchEvidenceRef(
                kind="basic_info", claim="The full literal retains its qualifier.",
                projection_id="projection_fixture", exact_text=literal,
            ),), decision=ResearchDecision.FINALIZE,
        )
        context = _assemble_final_context(
            plan=default_information_plan(), company_id="issuer-fixture",
            additional_identity_aliases=(), basic_info={"requests": []},
            state=state, rounds=(), prediction_time=NOW,
        )
        self.assertTrue(context["context_contract"]["presentation_target_exceeded"])
        self.assertEqual(context["final_research_state"], state.to_dict())

    def test_baseline_source_integrity_and_insufficient_rows(self) -> None:
        cutoff = datetime(2025, 7, 31, tzinfo=timezone.utc)

        def document(closes, *, available_at=cutoff):
            return RawInfoDocument.create(
                document_id="market_fixture",
                company_id="issuer-fixture",
                source_type="market_data",
                published_at=available_at,
                available_at=available_at,
                content=json.dumps([
                    {"as_of_date": f"2025-07-{day:02d}", "adjusted_close": close}
                    for day, close in zip(range(21, 31), closes)
                ]),
            )

        for closes in ([], [100, 101, 102, 103], [100, 101, 102, True, -1]):
            with self.subTest(closes=closes):
                self.assertEqual(
                    _prediction_baseline_from_market_documents(
                        (document(closes),), cutoff
                    )["status"],
                    "unavailable",
                )
        complete = document(range(100, 110))
        result = _prediction_baseline_from_market_documents((complete,), cutoff)
        self.assertEqual(result["mean_adjusted_close"], 107)
        self.assertEqual(
            result,
            _prediction_baseline_from_market_documents((complete, complete), cutoff),
        )
        with self.assertRaisesRegex(ValidationError, "conflicting adjusted-close"):
            _prediction_baseline_from_market_documents(
                (complete, document(range(101, 111))), cutoff
            )
        with self.assertRaisesRegex(ValidationError, "not point-in-time"):
            _prediction_baseline_from_market_documents(
                (document(range(100, 110), available_at=cutoff + timedelta(days=1)),),
                cutoff,
            )

    def test_default_case_budget_keeps_soft_signal_correction_envelope(self) -> None:
        limits = RuntimeLimits()

        self.assertEqual(limits.max_tokens, 256_000)
        self.assertEqual(limits.finalization_token_reserve, 64_000)

    def test_slow_role_identity_guards_exclude_derived_protocol_words(self) -> None:
        cases = tuple(
            EvolutionCase(
                company_id=f"cik_000000000{index}",
                prediction_time=NOW,
                basic_info={
                    "company_name": company_name,
                    "ticker": ticker,
                    "identity_aliases": [ticker, company_name],
                },
                ground_truth=GroundTruth(1.2),
            )
            for index, (company_name, ticker) in enumerate(
                (
                    ("Match Group Inc - New / Match Group, Inc.", "MTCH"),
                    ("News Corp - Class A / NEWS CORP", "NWSA"),
                    (
                        "Alpha Metallurgical Resources Inc / "
                        "Alpha Metallurgical Resources, Inc.",
                        "AMR",
                    ),
                    ("Open Lending Corp", "LPRO"),
                ),
                start=1,
            )
        )

        guards = _slow_role_identity_guard_inventory(cases)

        self.assertIn("Match Group", guards)
        self.assertIn("NEWS CORP", guards)
        self.assertIn("Alpha Metallurgical Resources", guards)
        self.assertIn("Open Lending", guards)
        self.assertTrue({"MTCH", "NWSA", "AMR", "LPRO"} <= set(guards))
        self.assertTrue({"Match", "News", "Alpha", "Open"}.isdisjoint(guards))

    def test_identity_mask_reuses_compiled_aliases_across_payloads(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/v7_full_alias_scan_compile_thrash.json"
            ).read_text(encoding="utf-8")
        )
        aliases = tuple(
            f"Example Holdings {index} Corporation"
            for index in range(min(int(fixture["raw_alias_count"]), 80))
        )
        leaf_count = min(int(fixture["discovery_case_count"]), 180)
        real_compile = re.compile

        def compile_count(value: object) -> int:
            with mock.patch(
                "stock_opportunity_agent.research.scheme_evolution.re.compile",
                side_effect=real_compile,
            ) as compile_mock:
                _mask_identity_values(value, aliases)
            return compile_mock.call_count

        one_leaf = compile_count({"value": "ordinary reflection"})
        many_leaves = compile_count(
            {f"value_{index}": "ordinary reflection" for index in range(leaf_count)}
        )

        self.assertGreater(one_leaf, 0)
        self.assertEqual(many_leaves, 0)

    def test_composite_formal_name_masks_natural_name_but_keeps_third_party(self) -> None:
        masked = _mask_identity_values(
            "UBS Boosts Kinross Gold’s (KGC) Price Target; Kinross later responded.",
            ("KGC", "Kinross Gold Corp / KINROSS GOLD CORP"),
        )

        self.assertEqual(masked.count("[MASKED_COMPANY]"), 3)
        self.assertNotIn("Kinross Gold", masked)
        self.assertNotIn("Kinross", masked)
        self.assertNotIn("KGC", masked)
        self.assertIn("UBS Boosts", masked)
        self.assertEqual(
            _mask_identity_values("Company Inc reported.", ("Company Inc",)),
            "[MASKED_COMPANY] reported.",
        )

    def test_formal_name_mask_accepts_ampersand_and_possessive_variants(self) -> None:
        masked = _mask_identity_values(
            (
                "Air Products and Chemicals expanded while Alexander’s leased "
                "another property."
            ),
            ("AIR PRODUCTS & CHEMICALS INC", "ALEXANDERS INC"),
        )

        self.assertEqual(masked.count("[MASKED_COMPANY]"), 2)
        self.assertNotIn("Air Products", masked)
        self.assertNotIn("Alexander", masked)

    def test_short_ticker_masking_is_case_sensitive(self) -> None:
        masked = _mask_identity_values(
            (
                "low liquidity improved while LOW remained anonymous; "
                "https://www.low.com/LOW-news"
            ),
            ("LOW",),
        )
        self.assertEqual(
            masked,
            (
                "low liquidity improved while [MASKED_COMPANY] remained anonymous; "
                "https://www.[MASKED_COMPANY].com/[MASKED_COMPANY]-news"
            ),
        )

    def test_v30_common_leading_name_word_does_not_damage_plan_prose(self) -> None:
        masked = _mask_identity_values(
            (
                "High Tide announced an update while HITI traded higher; "
                "retain high decision relevance in the generic Plan instruction."
            ),
            ("HITI", "High Tide Inc / High Tide Inc."),
        )

        self.assertEqual(masked.count("[MASKED_COMPANY]"), 2)
        self.assertNotIn("High Tide", masked)
        self.assertNotIn("HITI", masked)
        self.assertIn("high decision relevance", masked)

    def test_formal_name_masks_short_uppercase_brand_and_url_alias(self) -> None:
        masked = _mask_identity_values(
            "AAR signed an agreement at https://www.aar.com/aar-update.",
            ("AIR", "AAR Corp / AAR CORP"),
        )

        self.assertEqual(masked.count("[MASKED_COMPANY]"), 3)
        self.assertNotIn("AAR", masked)
        self.assertNotIn("aar", masked)

    def test_formal_name_masks_four_letter_brand_inside_property_name(self) -> None:
        masked = _mask_identity_values(
            (
                "Wynn Mayfair supports the planned Wynn Al Marjan Island opening; "
                "WYNN remains the target ticker."
            ),
            ("WYNN", "Wynn Resorts, Limited"),
        )

        self.assertEqual(masked.count("[MASKED_COMPANY]"), 3)
        self.assertNotIn("Wynn", masked)
        self.assertNotIn("WYNN", masked)

    def test_legacy_basic_info_fields_read_but_new_artifacts_write_requests(self) -> None:
        policy = type(default_information_plan().basic_info_policy).from_dict(
            {"fields": ["industry", "business_description"]}
        )
        self.assertEqual(
            [item.request_id for item in policy.requests],
            ["legacy_industry", "legacy_business_description"],
        )
        self.assertEqual(set(policy.to_dict()), {"requests"})

    def test_basic_info_policy_cannot_request_outcome_fields(self) -> None:
        base = default_information_plan()
        with self.assertRaisesRegex(ValidationError, "outcome data"):
            InformationPlan(
                plan_id="leaking_plan",
                parent_ids=(),
                basic_info_policy=type(base.basic_info_policy)(
                    requests=(
                        RawInfoRequest(
                            request_id="hidden_ground_truth",
                            description="Retrieve a hidden outcome.",
                            source_types=("filing",),
                        ),
                    )
                ),
                initial_research_skill=base.initial_research_skill,
                reflection_skill=base.reflection_skill,
                analysis_prompt=base.analysis_prompt,
            )

    def _registry_and_store(self, directory: str):
        registry = SignalRegistry(Path(directory) / "signals")
        registry.install_catalog(SEED_CATALOG)
        document = RawInfoDocument.create(
            document_id="financial_1",
            company_id="winner_1",
            source_type="financials",
            published_at=NOW - timedelta(days=2),
            available_at=NOW - timedelta(days=1),
            content=sec_company_facts_content(
                ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                ("2024-01-01", "2024-12-31", 130.0, "2025-01-10"),
            ),
        )
        return registry, RawInfoStore(documents=(document,))

    def test_case_readiness_prepares_broad_stable_signal_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            snapshot = registry.freeze()
            case = make_case("issuer_ready", 4.0)

            def raw(source_type: str) -> RawInfoDocument:
                content = f"Point-in-time {source_type} evidence."
                if source_type == "financials":
                    content = json.dumps(
                        {
                            "facts": [
                                {"end": "2022-12-31", "value": 80},
                                {"end": "2023-12-31", "value": 100},
                                {"end": "2024-12-31", "value": 130},
                            ]
                        }
                    )
                if source_type == "news":
                    content = f"{case.company_id} disclosed point-in-time news evidence."
                return RawInfoDocument.create(
                    document_id=f"ready_{source_type}",
                    company_id=case.company_id,
                    source_type=source_type,
                    published_at=NOW,
                    available_at=NOW,
                    content=content,
                    metadata=(
                        {"prices": [float(value) for value in range(100, 227)]}
                        if source_type == "market_data"
                        else {}
                    ),
                )

            passing_store = RawInfoStore(
                documents=(raw("financials"), raw("market_data"), raw("filing"))
            )
            passing = RuntimePlanEvaluator(
                raw_info_store=passing_store,
                controller=OneBatchController(),
                signal_agent=OneSignalSelector(),
                predictor=FixedPredictor(),
                prediction_root=root / "passing_predictions",
                signal_readiness_snapshot=snapshot,
            ).check_case_readiness(case)

            failing_store = RawInfoStore(
                documents=(raw("financials"), raw("market_data"), raw("news"))
            )
            failing = RuntimePlanEvaluator(
                raw_info_store=failing_store,
                controller=OneBatchController(),
                signal_agent=OneSignalSelector(),
                predictor=FixedPredictor(),
                prediction_root=root / "failing_predictions",
                signal_readiness_snapshot=snapshot,
            ).check_case_readiness(case)

            self.assertTrue(passing.ready)
            self.assertFalse(failing.ready)
            self.assertEqual(
                failing.reason,
                "signal_data_readiness_below_threshold:10/14",
            )

    def test_runtime_reflects_over_batch_and_persists_before_label_reveal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry, store = self._registry_and_store(directory)
            controller = OneBatchController()
            selector = OneSignalSelector()
            predictor = FixedPredictor()
            persisted: list[str] = []

            def sink(company_id, prediction_time, final_context, prediction):
                serialized = json.dumps(final_context)
                self.assertNotIn("ground_truth", serialized)
                self.assertNotIn("Masked winner", serialized)
                self.assertNotIn("Legacy Winner", serialized)
                self.assertNotIn('"LOW"', serialized)
                self.assertNotIn("company_name", final_context["basic_info"])
                self.assertNotIn("ticker", final_context["basic_info"])
                self.assertNotIn("runtime_stop_reason", final_context)
                self.assertNotIn("runtime_termination_trigger", final_context)
                persisted.append(company_id)
                return "predictions/winner_1.json"

            def truth_provider(company_id):
                self.assertEqual(persisted, [company_id])
                return GroundTruth(4.0)

            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="winner_1",
                company_basic_source={
                    "company_name": "Masked winner",
                    "ticker": "LOW",
                    "market_cap": 6_000_000_000,
                    "industry": "industrial",
                    "business_description": "low liquidity equipment",
                    "revenue_segments": ["systems"],
                    "development_stage": "commercial",
                    "identity_aliases": ("Legacy Winner",),
                    "extra_raw_fact": "must not enter Basic Info",
                },
                prediction_time=NOW,
                signal_registry=registry.freeze(),
                signal_executor=SignalExecutor(registry.freeze(), store),
                controller=controller,
                signal_agent=selector,
                predictor=predictor,
                prediction_sink=sink,
                ground_truth_provider=truth_provider,
                limits=RuntimeLimits(max_llm_calls=10),
            )
            self.assertEqual(controller.reflected_batch_sizes, [1])
            self.assertNotIn("extra_raw_fact", trajectory.basic_info)
            self.assertEqual(trajectory.stop_reason, RuntimeStopReason.FINALIZED)
            self.assertEqual(trajectory.ground_truth.magnitude, MagnitudeClass.THREE_TO_TEN)
            self.assertEqual(trajectory.usage.signal_rounds, 1)
            self.assertEqual(trajectory.usage.signal_calls, 1)
            self.assertNotIn(
                "usage", trajectory.final_context["signal_rounds"][0]["batch"]
            )
            self.assertIn("usage", trajectory.signal_rounds[0].to_dict()["batch"])
            self.assertEqual(predictor.reflection_truths, [GroundTruth(4.0)])

    def test_runtime_skips_reflection_for_all_unavailable_signal_batch(self) -> None:
        class NoUnavailableReflectionController:
            def __init__(self) -> None:
                self.initial_state = ResearchState(
                    hypotheses=("A catalyst may still exist.",),
                    open_questions=("Which source can confirm the catalyst?",),
                    next_information_needs=("Find catalyst evidence.",),
                )
                self.reflect_calls = 0

            def initialize(self, plan, basic_info):
                return AgentStep(
                    self.initial_state,
                    AgentUsage(llm_calls=1, tokens=20, cost=0.01),
                )

            def reflect(self, plan, state, batch):
                self.reflect_calls += 1
                raise AssertionError("all-unavailable batch must not call H_reflect")

        class UnavailableThenEmptySelector:
            def __init__(self) -> None:
                self.eligible_calls: list[tuple[str, ...]] = []

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
                eligible = tuple(eligible_signal_refs or ())
                self.eligible_calls.append(eligible)
                if len(self.eligible_calls) == 1:
                    return AgentStep(
                        (
                            SignalSelectionDecision(
                                signal_ref="revenue_growth_yoy:v1",
                                reason_code="answer_need",
                                selection_reason="Try comparable financial evidence.",
                                applicability_hypothesis=(
                                    "The source may contain comparable periods."
                                ),
                                expected_role="coverage",
                            ),
                        ),
                        AgentUsage(llm_calls=1, tokens=10, cost=0.005),
                    )
                return AgentStep((), AgentUsage(llm_calls=1, tokens=5, cost=0.002))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            snapshot = registry.freeze()
            controller = NoUnavailableReflectionController()
            selector = UnavailableThenEmptySelector()
            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="issuer_without_documents",
                company_basic_source={},
                prediction_time=NOW,
                signal_registry=snapshot,
                signal_executor=SignalExecutor(
                    snapshot, RawInfoStore(documents=())
                ),
                controller=controller,
                signal_agent=selector,
                predictor=FixedPredictor(),
                prediction_sink=lambda *args: "pred",
                ground_truth_provider=lambda company_id: GroundTruth(2.5),
                limits=RuntimeLimits(max_llm_calls=10),
            )

        self.assertEqual(controller.reflect_calls, 0)
        expected_final_state = replace(
            controller.initial_state,
            decision=ResearchDecision.FINALIZE,
        )
        self.assertEqual(trajectory.final_state, expected_final_state)
        self.assertEqual(trajectory.stop_reason, RuntimeStopReason.FINALIZED)
        self.assertEqual(trajectory.termination_trigger, RuntimeStopReason.NO_SIGNAL_MATCH)
        self.assertEqual(len(trajectory.signal_rounds), 1)
        self.assertEqual(
            trajectory.signal_rounds[0].batch.results[0].value,
            SignalValue.UNAVAILABLE,
        )
        self.assertNotIn("revenue_growth_yoy:v1", selector.eligible_calls[1])
        self.assertEqual(trajectory.usage.model.llm_calls, 5)

    def test_runtime_preserves_deterministic_results_when_soft_preflight_stops(self) -> None:
        class BudgetBlockedRunner:
            def __init__(self) -> None:
                self.calls = 0
                self.request_token_budget = None

            def set_request_token_budget(self, value):
                self.request_token_budget = value

            def execute_many(self, inputs, as_of):
                self.calls += 1
                raise RuntimeBudgetExceeded(
                    "fixture soft correction cannot be reserved",
                    usage=AgentUsage(llm_calls=1, tokens=7, cost=0.003),
                )

        class MixedSelector:
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
                return AgentStep(
                    (
                        SignalSelectionDecision(
                            signal_ref="negative_word_count:v1",
                            reason_code="answer_need",
                            selection_reason="Check current negative news terms.",
                            applicability_hypothesis="Current news is available.",
                            expected_role="confirmation",
                        ),
                        SignalSelectionDecision(
                            signal_ref="customer_concentration:v1",
                            reason_code="answer_need",
                            selection_reason="Check customer dependence.",
                            applicability_hypothesis="A filing may disclose customers.",
                            expected_role="primary",
                        ),
                    ),
                    AgentUsage(llm_calls=1, tokens=10),
                )

        class PartialController:
            def __init__(self) -> None:
                self.reflected_refs: list[tuple[str, ...]] = []
                self.runtime_contexts: list[dict[str, Any]] = []

            def set_reflection_runtime_context(
                self,
                *,
                selections,
                must_finalize,
                termination_trigger,
            ):
                self.runtime_contexts.append(
                    {
                        "selections": tuple(item.signal_ref for item in selections),
                        "must_finalize": must_finalize,
                        "termination_trigger": termination_trigger,
                    }
                )

            def initialize(self, plan, basic_info):
                return AgentStep(
                    ResearchState(next_information_needs=("Check current risks.",)),
                    AgentUsage(llm_calls=1, tokens=10),
                )

            def reflect(self, plan, state, batch):
                self.reflected_refs.append(tuple(item.ref for item in batch.results))
                return AgentStep(
                    ResearchState(decision=ResearchDecision.FINALIZE),
                    AgentUsage(llm_calls=1, tokens=10),
                )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            runner = BudgetBlockedRunner()
            store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="current-news",
                        company_id="winner_1",
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="The company reported an ordinary operating update.",
                    ),
                    RawInfoDocument.create(
                        document_id="current-filing",
                        company_id="winner_1",
                        source_type="filing",
                        published_at=NOW,
                        available_at=NOW,
                        content="One customer represented 72 percent of revenue.",
                    ),
                )
            )
            controller = PartialController()
            snapshot = registry.freeze()
            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="winner_1",
                company_basic_source={},
                prediction_time=NOW,
                signal_registry=snapshot,
                signal_executor=SignalExecutor(
                    snapshot,
                    store,
                    llm_runner=runner,
                ),
                controller=controller,
                signal_agent=MixedSelector(),
                predictor=FixedPredictor(),
                prediction_sink=lambda *args: "pred",
                ground_truth_provider=lambda company_id: GroundTruth(2.5),
                limits=RuntimeLimits(max_llm_calls=10),
            )

        self.assertEqual(runner.calls, 1)
        self.assertEqual(
            controller.reflected_refs,
            [("negative_word_count:v1",)],
        )
        self.assertEqual(len(trajectory.signal_rounds), 1)
        self.assertEqual(
            trajectory.signal_rounds[0].selected_signals,
            ("negative_word_count:v1",),
        )
        self.assertEqual(trajectory.usage.signal_calls, 1)
        self.assertEqual(trajectory.usage.model.tokens, 82)
        self.assertEqual(trajectory.usage.model.llm_calls, 6)
        self.assertEqual(trajectory.final_state.decision, ResearchDecision.FINALIZE)
        self.assertEqual(trajectory.stop_reason, RuntimeStopReason.FINALIZED)
        self.assertEqual(
            trajectory.termination_trigger,
            RuntimeStopReason.BUDGET_EXHAUSTED,
        )
        self.assertEqual(
            controller.runtime_contexts,
            [
                {
                    "selections": ("negative_word_count:v1",),
                    "must_finalize": True,
                    "termination_trigger": RuntimeStopReason.BUDGET_EXHAUSTED,
                }
            ],
        )

    def test_runtime_terminally_reflects_unavailable_partial_batch(self) -> None:
        class BudgetBlockedRunner:
            def __init__(self) -> None:
                self.calls = 0

            def set_request_token_budget(self, value):
                pass

            def execute_many(self, inputs, as_of):
                self.calls += 1
                raise RuntimeBudgetExceeded(
                    "fixture soft request cannot be reserved",
                    usage=AgentUsage(),
                )

        class MixedSelector:
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
                return AgentStep(
                    (
                        SignalSelectionDecision(
                            signal_ref="revenue_growth_yoy:v1",
                            reason_code="answer_need",
                            selection_reason="Try comparable financial periods.",
                            applicability_hypothesis=(
                                "Comparable revenue periods may be available."
                            ),
                            expected_role="primary",
                        ),
                        SignalSelectionDecision(
                            signal_ref="order_quality:v1",
                            reason_code="confirm_hypothesis",
                            selection_reason="Check disclosed customer orders.",
                            applicability_hypothesis=(
                                "A filing may disclose binding customer orders."
                            ),
                            expected_role="confirmation",
                        ),
                    ),
                    AgentUsage(llm_calls=1, tokens=10),
                )

        class TerminalController:
            def __init__(self) -> None:
                self.initial_state = ResearchState(
                    hypotheses=("Customer orders may support growth.",),
                    open_questions=("Are customer orders binding?",),
                    next_information_needs=("Confirm purchase-order quality.",),
                )
                self.reflected_refs: list[tuple[str, ...]] = []
                self.runtime_contexts: list[dict[str, Any]] = []

            def set_reflection_runtime_context(
                self,
                *,
                selections,
                must_finalize,
                termination_trigger,
            ):
                self.runtime_contexts.append(
                    {
                        "selections": tuple(item.signal_ref for item in selections),
                        "must_finalize": must_finalize,
                        "termination_trigger": termination_trigger,
                    }
                )

            def initialize(self, plan, basic_info):
                return AgentStep(
                    self.initial_state,
                    AgentUsage(llm_calls=1, tokens=10),
                )

            def reflect(self, plan, state, batch):
                self.reflected_refs.append(tuple(item.ref for item in batch.results))
                return AgentStep(
                    replace(state, decision=ResearchDecision.FINALIZE),
                    AgentUsage(llm_calls=1, tokens=10),
                )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            runner = BudgetBlockedRunner()
            store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="current-filing",
                        company_id="winner_1",
                        source_type="filing",
                        published_at=NOW,
                        available_at=NOW,
                        content="The company discussed ordinary operations.",
                    ),
                )
            )
            controller = TerminalController()
            snapshot = registry.freeze()
            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="winner_1",
                company_basic_source={},
                prediction_time=NOW,
                signal_registry=snapshot,
                signal_executor=SignalExecutor(
                    snapshot,
                    store,
                    llm_runner=runner,
                ),
                controller=controller,
                signal_agent=MixedSelector(),
                predictor=FixedPredictor(),
                prediction_sink=lambda *args: "pred",
                ground_truth_provider=lambda company_id: GroundTruth(2.5),
                limits=RuntimeLimits(max_llm_calls=10),
            )

        self.assertEqual(runner.calls, 1)
        self.assertEqual(
            controller.reflected_refs,
            [("revenue_growth_yoy:v1",)],
        )
        self.assertEqual(
            trajectory.final_state,
            replace(controller.initial_state, decision=ResearchDecision.FINALIZE),
        )
        self.assertEqual(trajectory.stop_reason, RuntimeStopReason.FINALIZED)
        self.assertEqual(
            trajectory.termination_trigger,
            RuntimeStopReason.BUDGET_EXHAUSTED,
        )
        self.assertEqual(
            controller.runtime_contexts,
            [
                {
                    "selections": ("revenue_growth_yoy:v1",),
                    "must_finalize": True,
                    "termination_trigger": RuntimeStopReason.BUDGET_EXHAUSTED,
                }
            ],
        )

    def test_predictor_projection_omits_repeated_full_basic_and_signal_evidence(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests"
                / "fixtures"
                / "evolution_runtime"
                / "v6_predictor_terminal_reserve_overflow.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(fixture["failure"]["required_tokens"], 80_152)
        basic_info = {
            "max_normalized_characters": 32_000,
            "requests": [
                {
                    "request": {
                        "request_id": "annual_filing",
                        "source_types": ["10-k"],
                    },
                    "status": "resolved",
                    "data_gap": None,
                    "projections": [
                        {
                            "projection_id": "projection_large",
                            "exact_text": "full-basic-marker-" + "x" * 31_000,
                        }
                    ],
                }
            ],
        }
        timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rounds = []
        for round_index in range(5):
            results = []
            for result_index in range(4):
                signal_id = f"signal_{round_index}_{result_index}"
                results.append(
                    SignalResult(
                        signal_id=signal_id,
                        version=1,
                        value=SignalValue.POSITIVE,
                        confidence=0.8,
                        interpretation=(
                            f"{signal_id} compact interpretation " + "i" * 240
                        ),
                        supporting_evidence=(
                            SignalEvidence(
                                document_id=f"document_{signal_id}",
                                exact_span="signal-evidence-marker-" + "e" * 240,
                                timestamp=timestamp,
                            ),
                        ),
                    )
                )
            rounds.append(
                SignalRound(
                    information_needs=(f"need {round_index}",),
                    selections=tuple(
                        SignalSelectionDecision.legacy(result.ref)
                        for result in results
                    ),
                    batch=SignalBatchResult(
                        results=tuple(results), signal_calls=len(results)
                    ),
                )
            )
        state = ResearchState(
            supporting_evidence=(
                ResearchEvidenceRef(
                    kind="basic_info",
                    claim="The filing contains one relevant literal.",
                    projection_id="projection_large",
                    exact_text="full-basic-marker-",
                ),
                ResearchEvidenceRef(
                    kind="signal",
                    claim="The first Signal supports the hypothesis.",
                    signal_ref="signal_0_0:v1",
                    evidence_group="supporting",
                    evidence_index=0,
                ),
            ),
            decision=ResearchDecision.FINALIZE,
        )

        context = _assemble_final_context(
            plan=default_information_plan(),
            company_id="issuer-fixture",
            additional_identity_aliases=(),
            basic_info=basic_info,
            state=state,
            rounds=tuple(rounds),
            prediction_time=NOW,
        )

        serialized = json.dumps(
            context, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        self.assertLessEqual(
            len(serialized.encode("utf-8")), MAX_PREDICTOR_CONTEXT_UTF8_BYTES
        )
        self.assertNotIn("full-basic-marker-" + "x" * 100, serialized)
        self.assertEqual(
            context["basic_info"]["source_index"][0]["projection_ids"],
            ["projection_large"],
        )
        self.assertNotIn(
            "evidence", context["signal_rounds"][0]["batch"]["results"][0]
        )
        self.assertEqual(
            context["cited_signal_evidence"][0]["evidence"]["exact_span"],
            "signal-evidence-marker-" + "e" * 240,
        )

    def test_predictor_projection_treats_unavailable_as_coverage_only(self) -> None:
        unavailable = SignalResult(
            signal_id="customer_concentration",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.5,
            interpretation="No customer concentration was found.",
            coverage=SignalCoverage.UNAVAILABLE,
        )

        context = _assemble_final_context(
            plan=default_information_plan(),
            company_id="issuer-fixture",
            additional_identity_aliases=(),
            basic_info={"requests": []},
            state=ResearchState(decision=ResearchDecision.FINALIZE),
            rounds=(
                SignalRound(
                    information_needs=("Is concentration known?",),
                    selections=(
                        SignalSelectionDecision.legacy(unavailable.ref),
                    ),
                    batch=SignalBatchResult(
                        results=(unavailable,), signal_calls=1
                    ),
                ),
            ),
            prediction_time=NOW,
        )

        summary = context["signal_rounds"][0]["batch"]["results"][0][
            "interpretation"
        ]["summary"]
        self.assertNotIn("No customer concentration was found", summary)
        self.assertIn("not evidence", summary)

    def test_v78_predictor_projection_supplies_last_five_day_baseline(self) -> None:
        rows = [
            {"adjusted_close": close, "as_of_date": f"2025-07-{day:02d}"}
            for day, close in (
                (23, 100.0),
                (24, 101.0),
                (25, 102.0),
                (28, 103.0),
                (29, 104.0),
                (30, 105.0),
            )
        ]
        prediction_time = datetime(2025, 7, 31, tzinfo=timezone.utc)
        market_document = RawInfoDocument.create(
            document_id="complete_market",
            company_id="issuer-fixture",
            source_type="market_data",
            published_at=prediction_time,
            available_at=prediction_time,
            content=json.dumps(rows + [
                {"adjusted_close": 999, "as_of_date": "2025-07-31"},
                {"adjusted_close": 999, "as_of_date": "2025-08-01"},
            ]),
        )
        context = _assemble_final_context(
            plan=default_information_plan(),
            company_id="issuer-fixture",
            additional_identity_aliases=(),
            basic_info={
                "requests": [
                    {
                        "request": {
                            "request_id": "recent_market_backbone",
                            "source_types": ["market_data"],
                        },
                        "status": "resolved",
                        "data_gap": None,
                        "projections": [
                            {
                                "projection_id": "projection_market",
                                "exact_text": ",".join(
                                    json.dumps(row, separators=(",", ":"))
                                    for row in rows[:5]
                                ),
                            }
                        ],
                    }
                ]
            },
            state=ResearchState(decision=ResearchDecision.FINALIZE),
            rounds=(),
            prediction_time=prediction_time,
            market_documents=(market_document,),
        )

        self.assertEqual(
            context["prediction_baseline"],
            {
                "status": "available",
                "method": (
                    "mean_last_5_complete_adjusted_closes_strictly_before_"
                    "prediction_time"
                ),
                "mean_adjusted_close": 103.0,
                "trading_dates": [
                    "2025-07-24",
                    "2025-07-25",
                    "2025-07-28",
                    "2025-07-29",
                    "2025-07-30",
                ],
            },
        )

    def test_runtime_stops_at_fixed_round_guard(self) -> None:
        class LoopingController(OneBatchController):
            def reflect(self, plan, state, batch):
                return AgentStep(
                    ResearchState(next_information_needs=("repeat",)),
                    AgentUsage(llm_calls=1),
                )

        with tempfile.TemporaryDirectory() as directory:
            registry, store = self._registry_and_store(directory)
            persisted: list[str] = []
            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="winner_1",
                company_basic_source={},
                prediction_time=NOW,
                signal_registry=registry.freeze(),
                signal_executor=SignalExecutor(registry.freeze(), store),
                controller=LoopingController(),
                signal_agent=OneSignalSelector(),
                predictor=FixedPredictor(),
                prediction_sink=lambda *args: persisted.append("done") or "pred",
                ground_truth_provider=lambda company_id: GroundTruth(2.5),
                limits=RuntimeLimits(
                    max_signal_rounds=1,
                    max_signal_calls=5,
                    max_llm_calls=10,
                ),
            )
            self.assertEqual(
                trajectory.stop_reason,
                RuntimeStopReason.MAX_SIGNAL_ROUNDS,
            )
            self.assertEqual(
                trajectory.termination_trigger,
                RuntimeStopReason.MAX_SIGNAL_ROUNDS,
            )
            self.assertEqual(
                trajectory.final_state.decision,
                ResearchDecision.CONTINUE,
            )
            self.assertEqual(
                trajectory.final_state.next_information_needs,
                ("repeat",),
            )
            self.assertEqual(len(trajectory.signal_rounds), 1)
            self.assertEqual(persisted, ["done"])

    def test_runtime_preserves_continue_state_at_budget_guard(self) -> None:
        class LoopingController(OneBatchController):
            def reflect(self, plan, state, batch):
                return AgentStep(
                    ResearchState(
                        hypotheses=("growth remains unresolved",),
                        open_questions=("confirm the next catalyst",),
                        next_information_needs=("confirm the next catalyst",),
                    ),
                    AgentUsage(llm_calls=1),
                )

        with tempfile.TemporaryDirectory() as directory:
            registry, store = self._registry_and_store(directory)
            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="winner_1",
                company_basic_source={},
                prediction_time=NOW,
                signal_registry=registry.freeze(),
                signal_executor=SignalExecutor(registry.freeze(), store),
                controller=LoopingController(),
                signal_agent=OneSignalSelector(),
                predictor=FixedPredictor(),
                prediction_sink=lambda *args: "pred",
                ground_truth_provider=lambda company_id: GroundTruth(2.5),
                limits=RuntimeLimits(
                    max_signal_rounds=5,
                    max_signal_calls=5,
                    max_llm_calls=6,
                ),
            )

            self.assertEqual(
                trajectory.stop_reason,
                RuntimeStopReason.BUDGET_EXHAUSTED,
            )
            self.assertEqual(
                trajectory.termination_trigger,
                RuntimeStopReason.BUDGET_EXHAUSTED,
            )
            self.assertEqual(
                trajectory.final_state.decision,
                ResearchDecision.CONTINUE,
            )
            self.assertEqual(
                trajectory.final_state.next_information_needs,
                ("confirm the next catalyst",),
            )
            self.assertEqual(
                trajectory.final_state.open_questions,
                ("confirm the next catalyst",),
            )

    def test_completed_batch_at_token_reserve_gets_terminal_reflection(self) -> None:
        class TerminalController(OneBatchController):
            def __init__(self) -> None:
                super().__init__()
                self.must_finalize = False
                self.termination_trigger = None
                self.request_budgets: list[int] = []

            def initialize(self, plan, basic_info):
                return AgentStep(
                    ResearchState(
                        hypotheses=("growth remains unresolved",),
                        next_information_needs=("measure revenue growth",),
                    ),
                    AgentUsage(llm_calls=1, tokens=186_000),
                )

            def set_reflection_runtime_context(
                self, *, selections, must_finalize, termination_trigger
            ):
                self.must_finalize = must_finalize
                self.termination_trigger = termination_trigger

            def set_request_token_budget(self, value):
                self.request_budgets.append(value)

            def reflect(self, plan, state, batch):
                self.assert_terminal_context()
                return AgentStep(
                    ResearchState(
                        hypotheses=state.hypotheses,
                        next_information_needs=state.next_information_needs,
                        decision=ResearchDecision.FINALIZE,
                    ),
                    AgentUsage(llm_calls=1, tokens=20),
                )

            def assert_terminal_context(self):
                if not self.must_finalize:
                    raise AssertionError("completed reserve-bound batch must finalize")
                if self.termination_trigger is not RuntimeStopReason.BUDGET_EXHAUSTED:
                    raise AssertionError("terminal trigger must remain auditable")

        class HighUsageSelector(OneSignalSelector):
            def select(self, *args, **kwargs):
                step = super().select(*args, **kwargs)
                return AgentStep(step.value, AgentUsage(llm_calls=1, tokens=10_000))

        with tempfile.TemporaryDirectory() as directory:
            registry, store = self._registry_and_store(directory)
            controller = TerminalController()
            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="winner_1",
                company_basic_source={},
                prediction_time=NOW,
                signal_registry=registry.freeze(),
                signal_executor=SignalExecutor(registry.freeze(), store),
                controller=controller,
                signal_agent=HighUsageSelector(),
                predictor=FixedPredictor(),
                prediction_sink=lambda *args: "pred",
                ground_truth_provider=lambda company_id: GroundTruth(2.5),
                limits=RuntimeLimits(),
            )

        self.assertEqual(trajectory.stop_reason, RuntimeStopReason.FINALIZED)
        self.assertEqual(
            trajectory.termination_trigger,
            RuntimeStopReason.BUDGET_EXHAUSTED,
        )
        self.assertEqual(trajectory.final_state.decision, ResearchDecision.FINALIZE)
        self.assertEqual(controller.request_budgets[-1], 60_000)

    def test_runtime_omits_executed_refs_before_next_signal_selection(self) -> None:
        class LoopingController(OneBatchController):
            def reflect(self, plan, state, batch):
                return AgentStep(
                    ResearchState(next_information_needs=("find new evidence",)),
                    AgentUsage(llm_calls=1),
                )

        class EligibleSelector:
            def __init__(self) -> None:
                self.eligible_calls: list[tuple[str, ...]] = []
                self.prior_context_calls: list[tuple[str, ...]] = []

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
                eligible = tuple(eligible_signal_refs or ())
                self.eligible_calls.append(eligible)
                self.prior_context_calls.append(tuple(prior_context_tags))
                if "revenue_growth_yoy:v1" in eligible:
                    return AgentStep(
                        (
                            SignalSelectionDecision(
                                signal_ref="revenue_growth_yoy:v1",
                                reason_code="answer_need",
                                selection_reason="Answer the remaining evidence need.",
                                applicability_hypothesis="Comparable financial facts exist.",
                                expected_role="primary",
                                context_tags=("mature_operations",),
                            ),
                        ),
                        AgentUsage(),
                    )
                return AgentStep((), AgentUsage())

        with tempfile.TemporaryDirectory() as directory:
            registry, store = self._registry_and_store(directory)
            selector = EligibleSelector()
            trajectory = execute_information_plan(
                plan=default_information_plan(),
                company_id="winner_1",
                company_basic_source={},
                prediction_time=NOW,
                signal_registry=registry.freeze(),
                signal_executor=SignalExecutor(registry.freeze(), store),
                controller=LoopingController(),
                signal_agent=selector,
                predictor=FixedPredictor(),
                prediction_sink=lambda *args: "pred",
                ground_truth_provider=lambda company_id: GroundTruth(2.5),
                limits=RuntimeLimits(
                    max_signal_rounds=5,
                    max_signal_calls=5,
                    max_llm_calls=10,
                ),
            )

            self.assertEqual(len(trajectory.signal_rounds), 1)
            self.assertEqual(trajectory.stop_reason, RuntimeStopReason.FINALIZED)
            self.assertEqual(
                trajectory.final_state.decision,
                ResearchDecision.FINALIZE,
            )
            self.assertEqual(
                trajectory.final_state.next_information_needs,
                ("find new evidence",),
            )
            self.assertEqual(
                trajectory.termination_trigger,
                RuntimeStopReason.NO_SIGNAL_MATCH,
            )
            self.assertIn("revenue_growth_yoy:v1", selector.eligible_calls[0])
            self.assertNotIn("revenue_growth_yoy:v1", selector.eligible_calls[1])
            self.assertEqual(selector.prior_context_calls[0], ())
            self.assertEqual(
                selector.prior_context_calls[1],
                ("mature_operations",),
            )
            self.assertFalse(trajectory.signal_rounds[0].batch.skipped_unchanged_refs)

    def test_repeated_issuer_cases_keep_distinct_truths_and_prediction_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="shared_financials",
                        company_id="shared_issuer",
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    ),
                )
            )
            predictor = FixedPredictor()
            evaluator = RuntimePlanEvaluator(
                raw_info_store=store,
                controller=OneBatchController(),
                signal_agent=OneSignalSelector(),
                predictor=predictor,
                prediction_root=root / "predictions",
            )
            cases = (
                EvolutionCase(
                    company_id="shared_issuer",
                    prediction_time=NOW,
                    basic_info={"company_name": "Shared One"},
                    ground_truth=GroundTruth(1.2),
                ),
                EvolutionCase(
                    company_id="shared_issuer",
                    prediction_time=NOW + timedelta(days=1),
                    basic_info={"company_name": "Shared Two"},
                    ground_truth=GroundTruth(4.0),
                ),
            )
            attempt = evaluator.evaluate(
                default_information_plan(), cases, registry.freeze()
            )
            trajectories = attempt.trajectories
            self.assertEqual(
                [row.ground_truth.realized_max_multiple for row in trajectories],
                [1.2, 4.0],
            )
            self.assertEqual(len({row.case_id for row in trajectories}), 2)
            self.assertEqual(len({row.prediction_ref for row in trajectories}), 2)

            resumed_events = []
            resumed_predictor = FixedPredictor()
            resumed = RuntimePlanEvaluator(
                raw_info_store=store,
                controller=OneBatchController(),
                signal_agent=OneSignalSelector(),
                predictor=resumed_predictor,
                prediction_root=root / "predictions",
                on_progress=resumed_events.append,
            ).evaluate(default_information_plan(), cases, registry.freeze())
            self.assertEqual(resumed.trajectories, trajectories)
            self.assertEqual(resumed_predictor.reflection_truths, [])
            self.assertEqual(
                [event["event_type"] for event in resumed_events],
                ["case_trajectory_reused", "case_trajectory_reused"],
            )

            changed_case = EvolutionCase(
                company_id="shared_issuer",
                prediction_time=NOW,
                basic_info={"company_name": "Shared One"},
                ground_truth=GroundTruth(2.2),
            )
            with self.assertRaisesRegex(ValidationError, "conflicting staged"):
                RuntimePlanEvaluator(
                    raw_info_store=store,
                    controller=OneBatchController(),
                    signal_agent=OneSignalSelector(),
                    predictor=FixedPredictor(),
                    prediction_root=root / "predictions",
                ).evaluate(
                    default_information_plan(),
                    (changed_case,),
                    registry.freeze(),
                )

    def test_unfinalized_case_stops_candidate_and_restart_reuses_stop(self) -> None:
        class LoopingController(OneBatchController):
            def reflect(self, plan, state, batch):
                return AgentStep(
                    ResearchState(
                        hypotheses=state.hypotheses,
                        next_information_needs=("resolve remaining catalyst",),
                    ),
                    AgentUsage(llm_calls=1),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="shared_financials",
                        company_id="shared_issuer",
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content="Revenue grew 25 percent.",
                        metadata={"revenue_growth_yoy": 0.25},
                    ),
                )
            )
            cases = (
                EvolutionCase(
                    company_id="shared_issuer",
                    prediction_time=NOW,
                    basic_info={"company_name": "Shared One"},
                    ground_truth=GroundTruth(4.0),
                ),
                EvolutionCase(
                    company_id="shared_issuer",
                    prediction_time=NOW + timedelta(days=1),
                    basic_info={"company_name": "Shared Two"},
                    ground_truth=GroundTruth(4.0),
                ),
            )
            events = []
            predictor = FixedPredictor()
            attempt = RuntimePlanEvaluator(
                raw_info_store=store,
                controller=LoopingController(),
                signal_agent=OneSignalSelector(),
                predictor=predictor,
                prediction_root=root / "predictions",
                limits=RuntimeLimits(max_signal_rounds=1),
                on_progress=events.append,
            ).evaluate(default_information_plan(), cases, registry.freeze())

            self.assertEqual(len(attempt.trajectories), 1)
            self.assertEqual(attempt.failures, ())
            self.assertIsNone(attempt.metrics)
            self.assertEqual(
                attempt.fitness.reasons,
                ("incomplete_case_set", "unfinalized_case"),
            )
            self.assertEqual(
                attempt.trajectories[0].stop_reason,
                RuntimeStopReason.MAX_SIGNAL_ROUNDS,
            )
            self.assertEqual(
                attempt.trajectories[0].final_state.decision,
                ResearchDecision.CONTINUE,
            )
            self.assertEqual(len(predictor.reflection_truths), 1)
            self.assertEqual(
                [event["event_type"] for event in events],
                [
                    "case_started",
                    "case_completed",
                    "candidate_evaluation_stopped",
                ],
            )

            resumed_events = []
            resumed_predictor = FixedPredictor()
            resumed = RuntimePlanEvaluator(
                raw_info_store=store,
                controller=LoopingController(),
                signal_agent=OneSignalSelector(),
                predictor=resumed_predictor,
                prediction_root=root / "predictions",
                limits=RuntimeLimits(max_signal_rounds=1),
                on_progress=resumed_events.append,
            ).evaluate(default_information_plan(), cases, registry.freeze())

            self.assertEqual(resumed, attempt)
            self.assertEqual(resumed_predictor.reflection_truths, [])
            self.assertEqual(
                [event["event_type"] for event in resumed_events],
                ["case_trajectory_reused", "candidate_evaluation_stopped"],
            )


class PredictionMetricTests(TestCase):
    def test_ground_truth_thresholds_and_two_stage_metrics(self) -> None:
        self.assertFalse(GroundTruth(1.999).is_surge)
        self.assertEqual(GroundTruth(2.0).magnitude, MagnitudeClass.TWO_TO_THREE)
        self.assertEqual(GroundTruth(3.0).magnitude, MagnitudeClass.THREE_TO_TEN)
        self.assertEqual(GroundTruth(10.0).magnitude, MagnitudeClass.TEN_PLUS)
        trajectories = (
            make_trajectory("case_1", 2.5, True, MagnitudeClass.TWO_TO_THREE),
            make_trajectory("case_2", 5.0, False, None),
            make_trajectory("case_3", 1.5, True, MagnitudeClass.TWO_TO_THREE),
            make_trajectory("case_4", 1.2, False, None),
            make_trajectory("case_5", 12.0, True, MagnitudeClass.TEN_PLUS),
        )
        metrics = score_predictions(trajectories)
        self.assertEqual(
            (
                metrics.true_positive,
                metrics.false_positive,
                metrics.true_negative,
                metrics.false_negative,
            ),
            (2, 1, 1, 1),
        )
        self.assertAlmostEqual(metrics.binary_precision, 2 / 3)
        self.assertAlmostEqual(metrics.binary_recall, 2 / 3)
        self.assertAlmostEqual(metrics.binary_f1, 2 / 3)
        self.assertAlmostEqual(metrics.magnitude_accuracy, 2 / 3)
        self.assertGreater(metrics.magnitude_macro_f1, 0)

    def test_prediction_schema_requires_stage_two_only_for_positive(self) -> None:
        with self.assertRaisesRegex(ValidationError, "requires magnitude"):
            BlindPrediction(
                is_surge=True,
                candidate_judgment=CandidateJudgment.POSSIBLE,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("reason",),
                uncertainties=(),
                session_id="s",
            )
        with self.assertRaisesRegex(ValidationError, "cannot include magnitude"):
            BlindPrediction(
                is_surge=False,
                candidate_judgment=CandidateJudgment.UNLIKELY,
                magnitude=MagnitudeClass.TWO_TO_THREE,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("reason",),
                uncertainties=(),
                session_id="s",
            )

    def test_prediction_schema_rejects_four_way_binary_mismatch(self) -> None:
        with self.assertRaisesRegex(ValidationError, "does not match is_surge"):
            BlindPrediction(
                is_surge=False,
                candidate_judgment=CandidateJudgment.POSSIBLE,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("reason",),
                uncertainties=(),
                session_id="s",
            )

    def test_candidate_judgment_feedback_covers_all_four_way_truth_pairs(self) -> None:
        expected = {
            (CandidateJudgment.LIKELY, True): "strong_correct_positive",
            (CandidateJudgment.POSSIBLE, True): "correct_positive_conservative",
            (CandidateJudgment.UNLIKELY, True): "severe_false_negative",
            (
                CandidateJudgment.INSUFFICIENT_INFORMATION,
                True,
            ): "false_negative_information_gap",
            (CandidateJudgment.UNLIKELY, False): "strong_correct_negative",
            (
                CandidateJudgment.INSUFFICIENT_INFORMATION,
                False,
            ): "correct_negative_information_gap",
            (CandidateJudgment.POSSIBLE, False): "false_positive",
            (
                CandidateJudgment.LIKELY,
                False,
            ): "severe_overconfident_false_positive",
        }
        for (judgment, true_is_surge), assessment in expected.items():
            with self.subTest(judgment=judgment.value, truth=true_is_surge):
                prediction = BlindPrediction(
                    is_surge=judgment.is_positive,
                    candidate_judgment=judgment,
                    magnitude=(
                        MagnitudeClass.TWO_TO_THREE
                        if judgment.is_positive
                        else None
                    ),
                    confidence=ConfidenceLevel.MEDIUM,
                    key_reasons=("source-backed reason",),
                    uncertainties=(),
                    session_id="s",
                )
                feedback = candidate_judgment_feedback(
                    prediction,
                    GroundTruth(2.2 if true_is_surge else 1.2),
                )
                self.assertEqual(feedback["assessment"], assessment)
                self.assertEqual(
                    feedback["binary_correct"],
                    judgment.is_positive == true_is_surge,
                )

    def test_trajectory_persists_and_validates_candidate_judgment_feedback(self) -> None:
        trajectory = make_trajectory(
            "feedback_case",
            2.2,
            True,
            MagnitudeClass.TWO_TO_THREE,
            candidate_judgment=CandidateJudgment.POSSIBLE,
        )
        serialized = trajectory.to_dict()

        self.assertEqual(
            serialized["prediction"]["candidate_judgment"],
            "possible",
        )
        self.assertEqual(
            serialized["candidate_judgment_feedback"]["assessment"],
            "correct_positive_conservative",
        )
        self.assertEqual(
            ExecutionTrajectory.from_dict(serialized).to_dict(),
            serialized,
        )

        tampered = json.loads(json.dumps(serialized))
        tampered["candidate_judgment_feedback"]["binary_correct"] = False
        with self.assertRaisesRegex(ValidationError, "does not match"):
            ExecutionTrajectory.from_dict(tampered)

    def test_four_way_categories_do_not_change_binary_f1_semantics(self) -> None:
        trajectories = (
            make_trajectory(
                "likely_true",
                2.2,
                True,
                MagnitudeClass.TWO_TO_THREE,
                candidate_judgment=CandidateJudgment.LIKELY,
            ),
            make_trajectory(
                "possible_true",
                2.2,
                True,
                MagnitudeClass.TWO_TO_THREE,
                candidate_judgment=CandidateJudgment.POSSIBLE,
            ),
            make_trajectory(
                "unlikely_false",
                1.2,
                False,
                None,
                candidate_judgment=CandidateJudgment.UNLIKELY,
            ),
            make_trajectory(
                "insufficient_false",
                1.2,
                False,
                None,
                candidate_judgment=CandidateJudgment.INSUFFICIENT_INFORMATION,
            ),
        )

        metrics = score_predictions(trajectories)

        self.assertEqual(metrics.binary_f1, 1.0)
        self.assertEqual(
            (metrics.true_positive, metrics.true_negative),
            (2, 2),
        )


class EvaluationDatasetSamplingTests(TestCase):
    def test_evaluation_contract_cannot_disable_finalized_fitness_gate(self) -> None:
        payload = PlanEvaluationConfig().to_dict()
        payload["fitness_gate"]["require_finalized"] = False

        with self.assertRaisesRegex(
            ValidationError, "requires finalized trajectories"
        ):
            PlanEvaluationConfig.from_dict(payload)

    def test_snapshots_freeze_anchor_and_rotate_exact_random_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evaluation"
            pool = make_evaluation_pool()
            anchors = make_anchor_pool()
            config = PlanEvaluationConfig()
            manager = EvaluationDatasetManager(root, pool, anchors, config)

            round_one = manager.get_or_create_round_dataset(1)
            round_two = manager.get_or_create_round_dataset(2)

            self.assertEqual(round_one.actual_counts, {
                "non_surge": 10,
                "2_3x": 7,
                "3_10x": 5,
                "10x_plus": 2,
            })
            self.assertEqual(round_two.actual_counts, round_one.actual_counts)
            self.assertEqual(round_one.anchor_case_ids, round_two.anchor_case_ids)
            self.assertFalse(
                set(round_one.random_case_ids) & set(round_two.random_case_ids)
            )
            all_round_cases = manager.resolve_cases(round_one.case_ids)
            self.assertEqual(
                len({case.company_id for case in all_round_cases}),
                len(all_round_cases),
            )
            self.assertEqual(round_one.random_seed, 43)
            self.assertTrue((root / "round_001" / "snapshot.json").is_file())
            self.assertTrue((root / "anchor.json").is_file())

            restarted = EvaluationDatasetManager(
                root, tuple(reversed(pool)), anchors, config
            )
            reused = restarted.get_or_create_round_dataset(1)
            self.assertEqual(reused.snapshot_id, round_one.snapshot_id)
            self.assertEqual(reused.case_ids, round_one.case_ids)

    def test_new_random_snapshot_skips_unready_case_without_changing_quotas(self) -> None:
        pool = make_evaluation_pool()
        anchors = make_anchor_pool()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = EvaluationDatasetManager(
                root / "baseline", pool, anchors
            ).get_or_create_round_dataset(1)
            blocked_case_id = baseline.random_case_ids[0]
            checked: list[str] = []

            def readiness(case: EvolutionCase) -> EvaluationCaseReadiness:
                checked.append(case.case_id)
                if case.case_id == blocked_case_id:
                    return EvaluationCaseReadiness(
                        case.case_id, False, "provider_no_data"
                    )
                return EvaluationCaseReadiness(case.case_id, True)

            snapshot = EvaluationDatasetManager(
                root / "ready",
                pool,
                anchors,
                case_readiness=readiness,
            ).get_or_create_round_dataset(1)

            self.assertNotIn(blocked_case_id, snapshot.random_case_ids)
            self.assertIn(blocked_case_id, checked)
            self.assertEqual(
                dict(snapshot.random_actual_counts),
                dict(PlanEvaluationConfig().random_label_counts),
            )
            self.assertEqual(len(snapshot.case_ids), 24)

    def test_hash_valid_snapshot_cannot_reuse_one_company(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evaluation"
            pool = make_evaluation_pool()
            anchors = make_anchor_pool()
            manager = EvaluationDatasetManager(root, pool, anchors)
            snapshot = manager.get_or_create_round_dataset(1)
            original = manager.resolve_cases((snapshot.random_case_ids[0],))[0]
            duplicate_company = EvolutionCase(
                company_id=original.company_id,
                prediction_time=NOW + timedelta(days=1),
                basic_info=original.basic_info,
                ground_truth=original.ground_truth,
            )
            path = root / "round_001" / "snapshot.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["random_case_ids"][1] = duplicate_company.case_id
            payload["case_ids"][len(snapshot.anchor_case_ids) + 1] = (
                duplicate_company.case_id
            )
            unhashed = {key: value for key, value in payload.items() if key != "snapshot_id"}
            payload["snapshot_id"] = hashlib.sha256(
                json.dumps(
                    unhashed,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            path.write_text(json.dumps(payload), encoding="utf-8")

            restarted = EvaluationDatasetManager(
                root, (*pool, duplicate_company), anchors
            )
            with self.assertRaisesRegex(ValidationError, "sampling contract"):
                restarted.get_or_create_round_dataset(1)

    def test_sampling_shortage_fails_closed(self) -> None:
        shared_one = EvolutionCase(
            company_id="shared",
            prediction_time=NOW,
            basic_info={"company_name": "shared"},
            ground_truth=GroundTruth(1.1),
            case_id="shared:first",
        )
        shared_two = EvolutionCase(
            company_id="shared",
            prediction_time=NOW + timedelta(days=1),
            basic_info={"company_name": "shared"},
            ground_truth=GroundTruth(1.2),
            case_id="shared:second",
        )
        positive = make_case("only_positive", 2.2)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(EvaluationDatasetInfeasible):
                EvaluationDatasetManager(
                    Path(directory),
                    (shared_one, shared_two, positive),
                    make_anchor_pool(),
                    PlanEvaluationConfig(),
                )
