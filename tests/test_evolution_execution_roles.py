"""Signal execution and initial ResearchState validation tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403


class SignalExecutionAndInitializeRoleTests(TestCase):
    def test_shared_projection_preserves_short_sources_and_independent_signals(self) -> None:
        from stock_opportunity_agent.research.evolution_signal_roles import (
            _shared_llm_signal_projection,
        )
        from stock_opportunity_agent.signal_library import SignalRetrievalPolicy

        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)

        def document(identifier, content):
            return RawInfoDocument.create(
                document_id=identifier, company_id="issuer", source_type="filing",
                published_at=as_of, available_at=as_of, content=content,
            )

        boilerplate = document(
            "long-filing",
            "Financing offering debt credit facility risk factors and governance. " * 2000,
        )
        action = "The company completed an offering of $400 million notes due in 2028."
        short = document("short-event", action)
        deployment = "The customer entered volume deployment under a binding contract."
        customer = document("customer-event", deployment)
        finance = SignalSpec(
            signal_id="financing", version=1, category="catalysts",
            description="Measure financing actions.", execution_type=SignalExecutionType.LLM,
            source_types=("filing",), skill_file="skill.md",
            retrieval_policy=SignalRetrievalPolicy(query_terms=("financing offering debt",)),
        )
        commercial = SignalSpec(
            signal_id="deployment", version=1, category="customers",
            description="Measure deployment.", execution_type=SignalExecutionType.LLM,
            source_types=("filing",), skill_file="skill.md",
            retrieval_policy=SignalRetrievalPolicy(query_terms=("customer volume deployment",)),
        )
        inputs = (
            LLMSignalBatchInput(finance, (boilerplate, short), "Risk factors governance. " * 100),
            LLMSignalBatchInput(commercial, (customer,), "Find literal deployment evidence."),
        )
        projected, lineage = _shared_llm_signal_projection(inputs)
        texts = [item["exact_text"] for item in projected]
        self.assertIn(action, texts)
        self.assertIn(deployment, texts)
        self.assertLessEqual(sum(map(len, texts)), 32_000)
        self.assertEqual(len(projected), len(lineage))
        self.assertEqual(projected, _shared_llm_signal_projection(tuple(reversed(inputs)))[0])
        changed_instructions = (
            LLMSignalBatchInput(finance, (short, boilerplate), "Different extraction instructions."),
            inputs[1],
        )
        self.assertEqual(projected, _shared_llm_signal_projection(changed_instructions)[0])
        for item in projected:
            self.assertIn(item["exact_text"], lineage[item["projection_id"]].document.content)

    def test_period_end_label_does_not_turn_as_of_guidance_into_realized_results(self) -> None:
        from stock_opportunity_agent.research.evolution_research_validation import (
            _raw_future_information_issues,
        )
        context = {"prediction_time": "2025-09-30T00:00:00+00:00"}
        for period in ("fiscal quarter ending on or about 2025-11-01", "year ending 2026-06-30"):
            with self.subTest(period=period):
                valid = f"What revenue and margin guidance had management disclosed by 2025-09-30 for the {period}, as stated in the Q3 2025 earnings release or call?"
                self.assertEqual(_raw_future_information_issues(
                    {"next_information_needs": [valid]}, context,
                ), [])
                for invalid in (
                    f"What actual revenue and margin results and guidance were reported for the {period}, as of 2025-09-30?",
                    f"What revenue guidance was disclosed on 2025-11-01 for the {period}?",
                    f"What were the results for the {period}?",
                ):
                    self.assertTrue(_raw_future_information_issues(
                        {"next_information_needs": [invalid]}, context,
                    ))

    def test_literal_residual_restores_prior_cutoff_without_waiving_future_checks(self) -> None:
        from stock_opportunity_agent.research.evolution_research_validation import (
            _restore_inherited_need_cutoffs, _raw_future_information_issues,
        )
        prior = "What outlook was disclosed by 2025-05-30 about any fiscal 2026 revenue-growth outlook?"
        previous = ResearchState(next_information_needs=(prior,))
        context = {"prediction_time": "2025-05-30T00:00:00+00:00"}
        value = {"next_information_needs": [
            "Fiscal 2026 revenue-growth outlook remains unresolved.",
            "What actual revenue was reported in 2026?",
            "What fiscal 2027 outlook was published?",
        ]}
        _restore_inherited_need_cutoffs(value, previous, context)
        self.assertEqual(value["next_information_needs"][0], prior)
        self.assertEqual(len(_raw_future_information_issues(value, context)), 2)
        self.assertEqual(previous.next_information_needs, (prior,))

    def test_posthoc_retains_complete_state_and_cited_signal_material(self) -> None:
        from stock_opportunity_agent.research.evolution_output_validation import (
            _compact_posthoc_context,
        )
        state = {"current_beliefs": ["A complete qualified belief. " * 1500]}
        citations = [{"evidence": {"exact_span": "Complete Signal literal."}}]
        result = _compact_posthoc_context({
            "final_research_state": state, "cited_signal_evidence": citations,
        })
        self.assertEqual(result["final_research_state"], state)
        self.assertEqual(result["cited_signal_evidence"], citations)
        self.assertTrue(result["context_contract"]["presentation_target_exceeded"])

    def test_plan_proposer_reports_invalid_shape_as_validation_error(self) -> None:
        proposer = LLMInformationPlanProposer(
            ScriptedRoleCaller([{"unexpected": True}, {"unexpected": True}])
        )

        with self.assertRaisesRegex(
            ValidationError, "information_plan_propose returned"
        ):
            proposer.propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(default_information_plan(),),
                meta_info=(),
                prior="fixed H_P",
            )

    def test_plan_proposer_rejects_deepseek_evidence_arrays_cleanly(self) -> None:
        proposer = LLMInformationPlanProposer(
            ScriptedRoleCaller(
                [
                    {
                        "B": {"purpose": "not a Basic Info policy"},
                        "H_init": [{"statement": "one"}],
                        "H_reflect": [{"statement": "two"}],
                        "H_analyse": [{"statement": "three"}],
                    },
                    {
                        "B": {"purpose": "still invalid"},
                        "H_init": [{"statement": "one"}],
                        "H_reflect": [{"statement": "two"}],
                        "H_analyse": [{"statement": "three"}],
                    },
                ]
            )
        )

        with self.assertRaisesRegex(
            ValidationError,
            "information_plan_propose returned incompatible semantic fields",
        ):
            proposer.propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(default_information_plan(),),
                meta_info=(),
                prior="fixed H_P",
            )

    def test_llm_signal_runner_conservatively_normalizes_unavailable_coverage(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "signal_id": "pilot_to_volume",
                    "version": 1,
                    "state": {"value": "unavailable", "confidence": 0.5},
                    "interpretation": {"summary": "No usable source evidence."},
                    "evidence": {"supporting": [], "counter": []},
                    "status": {"coverage": "partial"},
                }
            ]
        )
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="pilot_to_volume.md",
        )

        result, _usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (),
            "Extract only source-grounded transitions.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(result.coverage, SignalCoverage.UNAVAILABLE)

    def test_llm_signal_batch_repairs_versioned_inner_identity_with_exact_mapping(
        self,
    ) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v8_signal_batch_versioned_inner_identity.json"
            ).read_text(encoding="utf-8")
        )
        invalid = {
            "results": [
                {
                    "signal_ref": fixture["signal_ref"],
                    "result": fixture["invalid_result"],
                }
            ]
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["results"][0]["result"]["signal_id"] = fixture[
            "expected_signal_id"
        ]
        caller = ScriptedRoleCaller([invalid, corrected])
        spec = SignalSpec(
            signal_id=fixture["expected_signal_id"],
            version=fixture["expected_version"],
            category="management",
            description="Detect explicit management-guidance acceleration.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="guidance_acceleration.md",
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (),
            "Compare current with prior explicit guidance.",
            datetime(2025, 9, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(result.signal_id, fixture["expected_signal_id"])
        self.assertEqual(usage.llm_calls, 2)
        self.assertIn(
            "Output contract for SignalBatchResult",
            caller.calls[0]["system_prompt"],
        )
        self.assertNotIn(
            "Output contract for SignalResult:",
            caller.calls[0]["system_prompt"],
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertEqual(
            feedback["expected_result_identity"],
            {
                "signal_id": fixture["expected_signal_id"],
                "version": fixture["expected_version"],
            },
        )
        self.assertIn("without a version suffix", feedback["required_action"])
        self.assertIn("returned result.signal_id", feedback["validation_error"])

    def test_llm_signal_runner_repairs_invalid_exact_span_once(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-1",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="The customer entered volume deployment.",
        )
        base_result = {
            "signal_id": "pilot_to_volume",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "The pilot reached volume deployment."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": "filing-1",
                        "exact_span": "not a literal source span",
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        corrected = json.loads(json.dumps(base_result))
        corrected["evidence"]["supporting"][0]["exact_span"] = (
            "The customer entered volume deployment."
        )
        caller = ScriptedRoleCaller([base_result, corrected])
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="pilot_to_volume.md",
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Extract only source-grounded transitions.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertEqual(len(caller.calls), 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("supporting evidence[0] exact span", feedback["validation_error"])
        self.assertNotIn("failed_output", feedback)
        self.assertIn("smallest set of unique quotes", feedback["required_action"])
        self.assertIn("multiple current/prior", feedback["required_action"])
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        initial_payload = json.dumps(
            caller.calls[0]["payload"], sort_keys=True, separators=(",", ":")
        )
        correction_payload = json.dumps(
            caller.calls[1]["payload"], sort_keys=True, separators=(",", ":")
        )
        self.assertTrue(correction_payload.startswith(initial_payload[:-1] + ","))
        self.assertNotIn("validation_feedback", caller.calls[0]["payload"])
        self.assertEqual(usage.llm_calls, 2)
        self.assertAlmostEqual(usage.cost, 0.02)

    def test_v69_guidance_signal_rejects_unrelated_sale_leaseback_evidence(
        self,
    ) -> None:
        as_of = datetime(2025, 7, 31, tzinfo=timezone.utc)
        exact_span = (
            "In December 2022, the Company completed the sale-leaseback of "
            "Encore Boston Harbor for $1.70 billion and recorded a $182 million gain."
        )
        document = RawInfoDocument.create(
            document_id="filing-sale-leaseback",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content=exact_span,
        )
        invalid = {
            "signal_id": "guidance_acceleration",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {
                "summary": "The transaction materially strengthened guidance."
            },
            "evidence": {
                "supporting": [
                    {
                        "document_id": document.document_id,
                        "exact_span": exact_span,
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        corrected = {
            "signal_id": "guidance_acceleration",
            "version": 1,
            "state": {"value": "unavailable", "confidence": 0.0},
            "interpretation": {
                "summary": "Visible evidence did not name management guidance."
            },
            "evidence": {"supporting": [], "counter": []},
            "status": {"coverage": "unavailable"},
        }
        caller = ScriptedRoleCaller([invalid, corrected])
        spec = SignalSpec(
            signal_id="guidance_acceleration",
            version=1,
            category="management",
            description="Detect explicit management-guidance acceleration.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="guidance_acceleration.md",
            parameters={
                "result_required_evidence_phrases": [
                    "guidance",
                    "outlook",
                    "forecast",
                    "we expect",
                ]
            },
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Compare current with prior explicit guidance.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(usage.llm_calls, 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("guidance_acceleration:v1", feedback["validation_error"])
        self.assertIn(
            "result_required_evidence_phrases", feedback["validation_error"]
        )
        self.assertIn("Return unavailable", feedback["validation_error"])

    def test_v69_guidance_signal_accepts_explicit_guidance_evidence(self) -> None:
        as_of = datetime(2025, 7, 31, tzinfo=timezone.utc)
        exact_span = (
            "Management raised 2025 production guidance and now expects all-in "
            "sustaining cost of $1,500 per ounce."
        )
        document = RawInfoDocument.create(
            document_id="filing-guidance",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content=exact_span,
        )
        value = {
            "signal_id": "guidance_acceleration",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "Management raised 2025 guidance."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": document.document_id,
                        "exact_span": exact_span,
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        caller = ScriptedRoleCaller([value])
        spec = SignalSpec(
            signal_id="guidance_acceleration",
            version=1,
            category="management",
            description="Detect explicit management-guidance acceleration.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="guidance_acceleration.md",
            parameters={"result_required_evidence_phrases": ["guidance"]},
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Compare current with prior explicit guidance.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.POSITIVE)
        self.assertEqual(usage.llm_calls, 1)

    def test_v70_customer_signal_rejects_distribution_channels_as_customers(
        self,
    ) -> None:
        as_of = datetime(2025, 7, 31, tzinfo=timezone.utc)
        exact_span = (
            "For NNA, we have strength in all three channels. It is not just "
            "one channel."
        )
        document = RawInfoDocument.create(
            document_id="transcript-channels",
            company_id="issuer-1",
            source_type="earnings_call",
            published_at=as_of,
            available_at=as_of,
            content=exact_span,
        )
        invalid = {
            "signal_id": "customer_concentration",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {
                "summary": "Strength across three channels proves diversified customers."
            },
            "evidence": {
                "supporting": [
                    {
                        "document_id": document.document_id,
                        "exact_span": exact_span,
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        corrected = {
            "signal_id": "customer_concentration",
            "version": 1,
            "state": {"value": "unavailable", "confidence": 0.0},
            "interpretation": {
                "summary": "The cited excerpt names channels, not customers."
            },
            "evidence": {"supporting": [], "counter": []},
            "status": {"coverage": "unavailable"},
        }
        caller = ScriptedRoleCaller([invalid, corrected])
        spec = SignalSpec(
            signal_id="customer_concentration",
            version=1,
            category="risks",
            description="Judge dependence on one customer.",
            execution_type=SignalExecutionType.LLM,
            source_types=("earnings_call",),
            skill_file="customer_concentration.md",
            parameters={
                "result_required_evidence_phrases": [
                    "customer",
                    "client",
                    "buyer",
                    "offtake",
                    "backlog",
                    "order",
                    "account",
                    "program",
                ]
            },
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Measure customer concentration, not channel mix.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(usage.llm_calls, 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("customer_concentration:v1", feedback["validation_error"])
        self.assertIn(
            "result_required_evidence_phrases", feedback["validation_error"]
        )

    def test_llm_signal_runner_repairs_unavailable_with_placeholder_evidence(
        self,
    ) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-1",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="Routine filing cover-page text.",
        )
        invalid_result = {
            "signal_id": "pilot_to_volume",
            "version": 1,
            "state": {"value": "unavailable", "confidence": 0.5},
            "interpretation": {"summary": "No usable source evidence."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": "filing-1",
                        "exact_span": "Routine filing cover-page text.",
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "unavailable"},
        }
        corrected = json.loads(json.dumps(invalid_result))
        corrected["evidence"]["supporting"] = []
        caller = ScriptedRoleCaller([invalid_result, corrected])
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="pilot_to_volume.md",
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Extract only source-grounded transitions.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(result.supporting_evidence, ())
        self.assertEqual(len(caller.calls), 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("cannot carry evidence", feedback["validation_error"])
        self.assertIn("corrected result", feedback["required_action"])
        self.assertIn("only correction attempt", caller.calls[0]["system_prompt"])
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertEqual(usage.llm_calls, 2)

    def test_llm_signal_runner_canonicalizes_unique_case_only_span(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-1",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="The customer entered volume deployment.",
        )
        value = {
            "signal_id": "pilot_to_volume",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "The pilot reached volume deployment."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": "filing-1",
                        "exact_span": "the customer entered volume deployment.",
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        caller = ScriptedRoleCaller([value])
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="pilot_to_volume.md",
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Extract only source-grounded transitions.",
            as_of,
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(
            result.supporting_evidence[0].exact_span,
            "The customer entered volume deployment.",
        )
        self.assertEqual(usage.llm_calls, 1)

    def test_llm_signal_runner_projects_large_raw_info_to_exact_bounded_spans(
        self,
    ) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        target = "The customer entered repeatable scaled volume deployment."
        first = RawInfoDocument.create(
            document_id="filing-large",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content=("Routine governance disclosure. " * 8_000) + target,
        )
        second = RawInfoDocument.create(
            document_id="announcement-large",
            company_id="issuer-1",
            source_type="company_announcement",
            published_at=as_of,
            available_at=as_of,
            content="Certification roadmap update. " * 8_000,
        )
        value = {
            "signal_id": "pilot_to_volume",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "Commercial deployment is evidenced."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": "filing-large",
                        "exact_span": target,
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        caller = ScriptedRoleCaller([value])
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing", "company_announcement"),
            skill_file="pilot_to_volume.md",
        )

        result, _usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (first, second),
            "Find repeatable scaled sales and volume deployment evidence.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.POSITIVE)
        payload = caller.calls[0]["payload"]
        projected = payload["source_projection"]
        self.assertIn("filing-large", {item["document_id"] for item in projected})
        self.assertLess(len(json.dumps(payload)), 48_000)
        self.assertLessEqual(
            sum(len(item["exact_text"]) for item in projected),
            evolution_runtime_module.MAX_LLM_SIGNAL_CONTEXT_CHARS,
        )
        visible_text = ""
        for item in projected:
            self.assertNotIn("content", item)
            self.assertNotIn("metadata", item)
            self.assertIn("projection_id", item)
            visible_text += item["exact_text"]
        self.assertIn(target, visible_text)

    def test_llm_signal_runner_budget_trims_without_losing_each_signal_minimum(
        self,
    ) -> None:
        class BudgetAwareCaller:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def estimate_json_request_tokens(self, **kwargs) -> int:
                source_characters = sum(
                    len(item["exact_text"])
                    for item in kwargs["payload"]["source_projection"]
                )
                return int(kwargs["max_output_tokens"]) + 500 + source_characters

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                return (
                    {
                        "results": [
                            {
                                "signal_ref": item["signal_ref"],
                                "result": {
                                    "signal_id": item["signal_spec"]["signal_id"],
                                    "version": item["signal_spec"]["version"],
                                    "state": {
                                        "value": "unavailable",
                                        "confidence": 0.0,
                                    },
                                    "interpretation": {
                                        "summary": "Visible evidence was insufficient."
                                    },
                                    "evidence": {"supporting": [], "counter": []},
                                    "status": {"coverage": "unavailable"},
                                },
                            }
                            for item in kwargs["payload"]["signals"]
                        ]
                    },
                    AgentUsage(llm_calls=1, tokens=50, cost=0.01),
                )

        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        inputs = tuple(
            LLMSignalBatchInput(
                SignalSpec(
                    signal_id=signal_id,
                    version=1,
                    category="catalysts",
                    description=description,
                    execution_type=SignalExecutionType.LLM,
                    source_types=("filing",),
                    skill_file=f"{signal_id}.md",
                ),
                (
                    RawInfoDocument.create(
                        document_id=f"{signal_id}-document",
                        company_id="issuer-1",
                        source_type="filing",
                        published_at=as_of,
                        available_at=as_of,
                        content=target + (" Routine disclosure." * 1_500),
                    ),
                ),
                f"Extract {description}",
            )
            for signal_id, description, target in (
                (
                    "guidance_change",
                    "management guidance change",
                    "Management raised annual guidance.",
                ),
                (
                    "customer_order",
                    "customer order quality",
                    "A customer signed a repeat production order.",
                ),
            )
        )
        caller = BudgetAwareCaller()
        runner = StructuredLLMSignalRunner(caller)
        runner.set_request_token_budget(8_500)

        results, usage = runner.execute_many(inputs, as_of)

        self.assertEqual(set(results), {"guidance_change:v1", "customer_order:v1"})
        self.assertEqual(usage.llm_calls, 1)
        payload = caller.calls[0]["payload"]
        self.assertTrue(payload["context_contract"]["budget_trimmed"])
        self.assertLess(
            payload["context_contract"]["visible_source_characters"],
            evolution_runtime_module.MAX_LLM_SIGNAL_CONTEXT_CHARS,
        )
        self.assertTrue(
            all(item["eligible_projection_ids"] for item in payload["signals"])
        )
        visible = "\n".join(
            item["exact_text"] for item in payload["source_projection"]
        )
        self.assertIn("Management raised annual guidance.", visible)
        self.assertIn("A customer signed a repeat production order.", visible)
        self.assertLessEqual(
            caller.estimate_json_request_tokens(
                system_prompt=caller.calls[0]["system_prompt"],
                payload=payload,
                allow_outcomes=False,
                max_output_tokens=4_000,
            ),
            8_500,
        )

    def test_llm_signal_runner_falls_back_unavailable_after_failed_repair(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-1",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="The customer entered volume deployment.",
        )
        invalid_result = {
            "signal_id": "pilot_to_volume",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.8},
            "interpretation": {"summary": "Unsupported interpretation."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": "filing-1",
                        "exact_span": "not a literal source span",
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        caller = ScriptedRoleCaller([invalid_result, invalid_result])
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="pilot_to_volume.md",
        )

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Extract only source-grounded transitions.",
            as_of,
        )

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(result.coverage, SignalCoverage.UNAVAILABLE)
        self.assertEqual(
            result.execution_status,
            SignalExecutionStatus.VALIDATION_FAILED,
        )
        self.assertEqual(
            result.execution_error_code,
            "signal_output_validation_exhausted",
        )
        self.assertEqual(result.supporting_evidence, ())
        self.assertIn("failed strict validation", result.interpretation)
        self.assertEqual(usage.llm_calls, 2)

    def test_llm_signal_runner_rejects_duplicate_ref_then_repairs_it(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        spec = SignalSpec(
            signal_id="pilot_to_volume",
            version=1,
            category="customers",
            description="Detect conversion from pilot to volume deployment.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",),
            skill_file="pilot_to_volume.md",
        )
        result = {
            "signal_id": spec.signal_id,
            "version": spec.version,
            "state": {"value": "unavailable", "confidence": 0.0},
            "interpretation": {"summary": "No visible evidence."},
            "evidence": {"supporting": [], "counter": []},
            "status": {"coverage": "unavailable"},
        }
        row = {"signal_ref": spec.ref, "result": result}
        caller = ScriptedRoleCaller(
            [
                {"results": [row, row]},
                {"results": [row]},
            ]
        )

        results, usage = StructuredLLMSignalRunner(caller).execute_many(
            (LLMSignalBatchInput(spec, (), "Use only visible evidence."),),
            as_of,
        )

        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(
            results[spec.ref].execution_status,
            SignalExecutionStatus.DOMAIN_UNAVAILABLE,
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("duplicated requested signal_ref", feedback[0]["validation_error"])

    def test_llm_signal_correction_rebuilds_only_failed_signal_payload(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        first = SignalSpec(
            signal_id="guidance_change", version=1, category="catalysts",
            description="Measure guidance changes.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",), skill_file="guidance.md",
        )
        second = SignalSpec(
            signal_id="customer_order", version=1, category="customers",
            description="Measure customer orders.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",), skill_file="orders.md",
        )

        def unavailable(spec):
            return {
                "signal_id": spec.signal_id,
                "version": spec.version,
                "state": {"value": "unavailable", "confidence": 0.0},
                "interpretation": {"summary": "Visible evidence was insufficient."},
                "evidence": {"supporting": [], "counter": []},
                "status": {"coverage": "unavailable"},
            }

        caller = ScriptedRoleCaller(
            [
                {
                    "results": [
                        {"signal_ref": first.ref, "result": unavailable(first)},
                    ]
                },
                {
                    "results": [
                        {"signal_ref": second.ref, "result": unavailable(second)},
                    ]
                },
            ]
        )

        results, usage = StructuredLLMSignalRunner(caller).execute_many(
            (
                LLMSignalBatchInput(first, (), "Use visible evidence."),
                LLMSignalBatchInput(second, (), "Use visible evidence."),
            ),
            as_of,
        )

        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(
            [item["signal_ref"] for item in caller.calls[1]["payload"]["signals"]],
            [second.ref],
        )
        self.assertEqual(caller.calls[1]["payload"]["batch_signal_refs"], [second.ref])
        self.assertEqual(
            caller.calls[1]["payload"]["validation_feedback"][0]["signal_ref"],
            second.ref,
        )
        self.assertEqual(
            results[first.ref].execution_status,
            SignalExecutionStatus.DOMAIN_UNAVAILABLE,
        )
        self.assertEqual(
            results[second.ref].execution_status,
            SignalExecutionStatus.DOMAIN_UNAVAILABLE,
        )

    def test_llm_signal_unavailable_uses_one_changed_comparison_supplement(self) -> None:
        from stock_opportunity_agent.signal_library import SignalRetrievalPolicy

        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        comparison = SignalSpec(
            signal_id="guidance_comparison", version=1, category="catalysts",
            description="Compare current and prior guidance.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",), skill_file="guidance.md",
            retrieval_policy=SignalRetrievalPolicy(
                query_terms=("guidance comparison",),
                comparison_requirement="Compare current and prior guidance periods.",
            ),
        )
        sibling = SignalSpec(
            signal_id="customer_event", version=1, category="customers",
            description="Measure customer events.",
            execution_type=SignalExecutionType.LLM,
            source_types=("filing",), skill_file="customer.md",
        )
        documents = (
            RawInfoDocument.create(
                document_id="comparison-long", company_id="issuer",
                source_type="filing", published_at=as_of, available_at=as_of,
                content="Current and prior guidance comparison. " * 2_000,
            ),
        )
        sibling_documents = (
            RawInfoDocument.create(
                document_id="sibling-long", company_id="issuer",
                source_type="filing", published_at=as_of, available_at=as_of,
                content="Customer production event disclosure. " * 2_000,
            ),
        )

        class SupplementCaller:
            def __init__(self):
                self.calls = []

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                rows = []
                for item in kwargs["payload"]["signals"]:
                    spec = item["signal_spec"]
                    rows.append(
                        {
                            "signal_ref": item["signal_ref"],
                            "result": {
                                "signal_id": spec["signal_id"],
                                "version": spec["version"],
                                "state": {"value": "unavailable", "confidence": 0.0},
                                "interpretation": {"summary": "Comparison unavailable."},
                                "evidence": {"supporting": [], "counter": []},
                                "status": {"coverage": "unavailable"},
                            },
                        }
                    )
                return {"results": rows}, AgentUsage(llm_calls=1, tokens=10)

        caller = SupplementCaller()
        results, usage = StructuredLLMSignalRunner(caller).execute_many(
            (
                LLMSignalBatchInput(comparison, documents, "Compare periods."),
                LLMSignalBatchInput(sibling, sibling_documents, "Find customer events."),
            ),
            as_of,
        )

        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(
            caller.calls[1]["payload"]["batch_signal_refs"], [comparison.ref]
        )
        first_ids = {
            item["projection_id"]
            for item in caller.calls[0]["payload"]["source_projection"]
            if item["document_id"] == "comparison-long"
        }
        second_ids = {
            item["projection_id"]
            for item in caller.calls[1]["payload"]["source_projection"]
        }
        self.assertTrue(second_ids - first_ids)
        self.assertEqual(
            results[sibling.ref].execution_status,
            SignalExecutionStatus.DOMAIN_UNAVAILABLE,
        )
        self.assertEqual(
            results[comparison.ref].execution_status,
            SignalExecutionStatus.DOMAIN_UNAVAILABLE,
        )

    def test_llm_signal_correction_budget_keeps_successful_sibling(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        first = SignalSpec(
            signal_id="successful", version=1, category="catalysts",
            description="Successful signal.", execution_type=SignalExecutionType.LLM,
            source_types=("filing",), skill_file="successful.md",
        )
        second = SignalSpec(
            signal_id="failed", version=1, category="catalysts",
            description="Failed signal.", execution_type=SignalExecutionType.LLM,
            source_types=("filing",), skill_file="failed.md",
        )

        class BudgetCaller:
            def __init__(self):
                self.calls = []

            def estimate_json_request_tokens(self, **_kwargs):
                return 8_000

            def complete_json(self, **kwargs):
                if kwargs.get("max_request_tokens", 8_000) < 8_000:
                    raise RuntimeBudgetExceeded(
                        "exact reservation exceeds remaining request budget"
                    )
                self.calls.append(kwargs)
                valid = {
                    "signal_id": first.signal_id,
                    "version": first.version,
                    "state": {"value": "unavailable", "confidence": 0.0},
                    "interpretation": {"summary": "No visible evidence."},
                    "evidence": {"supporting": [], "counter": []},
                    "status": {"coverage": "unavailable"},
                }
                return {
                    "results": [{"signal_ref": first.ref, "result": valid}]
                }, AgentUsage(llm_calls=1, tokens=600)

        caller = BudgetCaller()
        runner = StructuredLLMSignalRunner(caller)
        runner.set_request_token_budget(8_500)
        results, usage = runner.execute_many(
            (
                LLMSignalBatchInput(first, (), "Use evidence."),
                LLMSignalBatchInput(second, (), "Use evidence."),
            ),
            as_of,
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(usage.llm_calls, 1)
        self.assertEqual(
            results[first.ref].execution_status,
            SignalExecutionStatus.DOMAIN_UNAVAILABLE,
        )
        self.assertEqual(
            results[second.ref].execution_status,
            SignalExecutionStatus.BUDGET_BLOCKED,
        )

    def test_v6_routing_normalizes_format_and_caps_four_with_two_llm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            snapshot = registry.freeze()
            raw = []
            for spec in snapshot.specs:
                raw.append(
                    {
                        "signal_ref": spec.ref,
                        "reason_code": "combine_evidence",
                        "selection_reason": "x" * 400,
                        "applicability_hypothesis": "y" * 400,
                        "expected_role": "primary",
                        "context_tags": [
                            "News Rich",
                            "news_rich",
                            "General",
                            "Scaling",
                            "Small Cap",
                        ],
                        "target_need_indices": [],
                        "answer_scope": None,
                        "residual_need": None,
                    }
                )
            caller = ScriptedRoleCaller([{"selections": raw}])

            selected = LLMSignalRetrievalAgent(caller).select(
                ("inspect everything",), snapshot, {}
            ).value

            self.assertLessEqual(len(selected), 4)
            by_ref = {spec.ref: spec for spec in snapshot.specs}
            self.assertLessEqual(
                sum(
                    by_ref[item.signal_ref].execution_type
                    is SignalExecutionType.LLM
                    for item in selected
                ),
                2,
            )
            self.assertTrue(all(len(item.selection_reason) == 240 for item in selected))
            self.assertTrue(all(len(item.context_tags) <= 4 for item in selected))
            self.assertTrue(all(len(set(item.context_tags)) == len(item.context_tags) for item in selected))

    def test_v17_routing_drops_visible_categories_used_as_context_tags(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/v17_signal_category_tags.json"
            ).read_text()
        )
        for item in fixture["selections"]:
            item["answer_scope"] = None
            item["residual_need"] = None
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller([fixture])

            selected = LLMSignalRetrievalAgent(caller).select(
                ("identify catalysts and risks",), registry.freeze(), {}
            ).value

            self.assertEqual(len(caller.calls), 1)
            self.assertEqual(
                tuple(item.signal_ref for item in selected),
                ("financing_listing_action:v1",),
            )
            self.assertEqual(
                selected[0].context_tags,
                ("capital_intensive", "mature_operations", "large_cap"),
            )

    def test_v6_initialize_canonicalizes_unique_basic_projection_reference(self) -> None:
        def state(projection_id: str) -> dict[str, Any]:
            return {
                "hypotheses": ["growth may accelerate"],
                "current_beliefs": [],
                "supporting_evidence": [
                    {
                        "kind": "basic_info",
                        "claim": "Revenue guidance increased.",
                        "projection_id": projection_id,
                        "exact_text": "guidance increased",
                    }
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["confirm customer demand"],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller([state("projection_unknown")])
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": "projection_ok",
                            "exact_text": "Management said guidance increased this year.",
                        }
                    ]
                }
            ]
        }

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(
            initialized.value.to_dict()["supporting_evidence"][0]["projection_id"],
            "projection_ok",
        )

    def test_v6_initialize_corrects_non_contiguous_basic_literal_once(self) -> None:
        def state(exact_text: str) -> dict[str, Any]:
            return {
                "hypotheses": ["growth may accelerate"],
                "current_beliefs": [],
                "supporting_evidence": [
                    {
                        "kind": "basic_info",
                        "claim": "Revenue increased.",
                        "projection_id": "projection_market",
                        "exact_text": exact_text,
                    }
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["confirm customer demand"],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller(
            [
                state('{"close":21.46}...{"close":24.37}'),
                state('{"close":21.46}'),
            ]
        )
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": "projection_market",
                            "exact_text": (
                                '[{"close":21.46},{"close":22.00},'
                                '{"close":24.37}]'
                            ),
                        }
                    ]
                }
            ]
        }

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(caller.calls), 2)
        correction_error = validation_error(caller.calls[1])
        self.assertIn("supporting_evidence[0]", correction_error)
        self.assertIn("contiguous literal substring", correction_error)
        self.assertIn("without ellipses", correction_error)
        self.assertEqual(
            initialized.value.to_dict()["supporting_evidence"][0]["exact_text"],
            '{"close":21.46}',
        )

    def test_v15_initialize_explains_market_rows_and_requires_real_correction(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v15_initialize_market_citation.json"
            ).read_text()
        )

        def state(exact_text: str) -> dict[str, Any]:
            return {
                "hypotheses": ["repricing depends on issuer-specific evidence"],
                "current_beliefs": [],
                "supporting_evidence": [
                    {
                        "kind": "basic_info",
                        "claim": fixture["claim"],
                        "projection_id": fixture["projection_id"],
                        "exact_text": exact_text,
                    }
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["confirm issuer-specific catalysts"],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller(
            [
                state(fixture["invalid_exact_text"]),
                state(fixture["valid_exact_text"]),
            ]
        )
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": fixture["projection_id"],
                            "exact_text": fixture["projection_text"],
                        }
                    ]
                }
            ]
        }

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(caller.calls), 2)
        initial_prompt = caller.calls[0]["system_prompt"]
        correction_prompt = caller.calls[1]["system_prompt"]
        self.assertEqual(initial_prompt, correction_prompt)
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        self.assertEqual(
            caller.calls[0]["payload"]["basic_info"],
            caller.calls[1]["payload"]["basic_info"],
        )
        self.assertEqual(
            caller.calls[0]["payload"]["initial_research_skill"],
            caller.calls[1]["payload"]["initial_research_skill"],
        )
        stable_prefix = json.dumps(
            {
                "basic_info": caller.calls[0]["payload"]["basic_info"],
                "initial_research_skill": caller.calls[0]["payload"][
                    "initial_research_skill"
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )[:-1] + ',"validation_feedback":'
        for call in caller.calls:
            rendered = json.dumps(
                call["payload"], sort_keys=True, separators=(",", ":")
            )
            self.assertTrue(rendered.startswith(stable_prefix))
        self.assertIn("evaluation definition, not an issuer statement", initial_prompt)
        self.assertIn("baseline date, or baseline price", initial_prompt)
        self.assertIn("future operating event outside the six-month horizon", initial_prompt)
        self.assertIn("within-horizon evidence or milestone", initial_prompt)
        self.assertIn("complete visible row", initial_prompt)
        self.assertIn("Returning the same rejected content", correction_prompt)
        self.assertIn(
            "contiguous literal substring",
            validation_error(caller.calls[1]),
        )
        self.assertEqual(
            initialized.value.supporting_evidence[0].exact_text,
            fixture["valid_exact_text"],
        )

    def test_v74_initialize_names_closest_visible_literal_window(self) -> None:
        projection_text = (
            "SFIX Q1 Loss Narrower Than Expected, Active Clients Decline Y/Y "
            "Stitch Fix, Inc. (SFIX) reported first-quarter fiscal 2025 results, "
            "with both top and bottom lines beating consensus estimates, despite "
            "a year-over-year decline in active clients and revenue. The company's "
            "adjusted loss narrowed significantly."
        )
        invalid_literal = (
            "SFIX reported first-quarter fiscal 2025 results, with both top and "
            "bottom lines beating consensus estimates, despite a year-over-year "
            "decline in active clients and revenue."
        )
        corrected_literal = (
            "Stitch Fix, Inc. (SFIX) reported first-quarter fiscal 2025 results, "
            "with both top and bottom lines beating consensus estimates, despite "
            "a year-over-year decline in active clients and revenue."
        )

        def state(literal: str) -> dict[str, Any]:
            return {
                "hypotheses": ["Revenue stabilization remains uncertain."],
                "current_beliefs": [literal],
                "supporting_evidence": [
                    {
                        "kind": "basic_info",
                        "claim": literal,
                        "projection_id": "projection_sfix",
                        "exact_text": literal,
                    }
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["Confirm active-client stabilization."],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller(
            [state(invalid_literal), state(corrected_literal)]
        )
        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_sfix",
                                "exact_text": projection_text,
                            }
                        ]
                    }
                ]
            },
        )

        error = validation_error(caller.calls[1])
        self.assertIn(f"invalid_exact_text={invalid_literal!r}", error)
        self.assertIn("occurrences_in_named_projection=0", error)
        self.assertIn("closest_visible_projection_window=", error)
        self.assertIn("Stitch Fix, Inc. (SFIX) reported", error)
        self.assertEqual(
            initialized.value.supporting_evidence[0].exact_text,
            corrected_literal,
        )

    def test_v107_initialize_stops_deep_checks_on_invalid_evidence_shape(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v20_initialize_layered_feedback.json"
            ).read_text(encoding="utf-8")
        )
        caller = ScriptedRoleCaller(
            [fixture["invalid_output"], fixture["corrected_output"]]
        )
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": fixture["projection_id"],
                            "exact_text": fixture["projection_text"],
                        }
                    ]
                }
            ]
        }

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(caller.calls), 2)
        error = validation_error(caller.calls[1])
        self.assertIn("unknown kind None", error)
        self.assertNotIn("numeric quantities", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligation_count"], 1)
        obligations = feedback["obligations"]
        self.assertEqual(
            obligations[0]["must_change_paths"],
            ["supporting_evidence[0].kind"],
        )
        self.assertIn(
            "Satisfy every validation_feedback.obligations row",
            caller.calls[1]["system_prompt"],
        )
        required_paths = feedback["required_change_paths"]
        self.assertEqual(
            feedback["required_change_path_count"],
            len(required_paths),
        )
        self.assertEqual(len(required_paths), len(set(required_paths)))
        self.assertIn("supporting_evidence[0].kind", required_paths)
        self.assertIn(
            "compare every required_change_paths",
            feedback["completion_check"],
        )
        self.assertNotIn("quantity_literal_checks", feedback)
        self.assertEqual(
            initialized.value.supporting_evidence[0].claim,
            fixture["corrected_claim"],
        )

    def test_v95_quantity_feedback_checks_each_linked_retained_path(self) -> None:
        error = ValidationError(
            "supporting_evidence[1] claim contains numeric quantities absent from "
            "all Basic exact_text refs with the same claim, "
            'missing_quantity_groups=["2031"], '
            'missing_quantity_literals=["2031"], '
            'same_claim_evidence_paths=["supporting_evidence[1].claim"]. '
            "Change or remove every listed evidence claim together. "
            'linked_assertions=["current_beliefs[1]"] must copy the corrected '
            "claim byte-for-byte"
        )

        feedback = evolution_runtime_module._validation_obligations(
            error,
            {
                "supporting_evidence": [
                    {"claim": "Unrelated claim."},
                    {"claim": "The milestone is expected in 2031."},
                ],
                "current_beliefs": [
                    "Unrelated belief.",
                    "The milestone is expected in 2031.",
                ],
            },
        )

        self.assertEqual(feedback["quantity_literal_check_count"], 1)
        check = feedback["quantity_literal_checks"][0]
        self.assertEqual(check["missing_quantity_literals"], ["2031"])
        self.assertEqual(
            check["affected_paths"],
            ["supporting_evidence[1].claim", "current_beliefs[1]"],
        )
        self.assertIn("every affected_path", check["completion_rule"])
        self.assertIn(
            "changing surrounding words",
            feedback["completion_check"],
        )

    def test_v105_quantity_feedback_names_complete_numeric_token_occurrence(
        self,
    ) -> None:
        claim = (
            "Bumble reported an 8.7% decrease in total paying users in Q2 2025, "
            "leading to a 15.94% stock price fall on August 7, 2025."
        )
        error = ValidationError(
            "supporting_evidence[0] claim contains numeric quantities absent from "
            "all Basic exact_text refs with the same claim, "
            'missing_quantity_groups=["7"], '
            'missing_quantity_literals=["7"], '
            'same_claim_evidence_paths=["supporting_evidence[0].claim"]. '
            "Change or remove every listed evidence claim together. "
            "linked_assertions=['current_beliefs[0]'] must copy the corrected "
            "claim byte-for-byte"
        )
        failed_output = {
            "supporting_evidence": [{"claim": claim}],
            "current_beliefs": [claim],
        }

        feedback = evolution_runtime_module._validation_obligations(
            error,
            failed_output,
        )

        check = feedback["quantity_literal_checks"][0]
        mentions = check["missing_quantity_mentions"]
        self.assertEqual(
            [item["affected_path"] for item in mentions],
            ["supporting_evidence[0].claim", "current_beliefs[0]"],
        )
        for mention in mentions:
            start, end = mention["authored_span"]
            self.assertEqual(claim[start:end], "7")
            self.assertEqual(mention["authored_literal"], "7")
            self.assertEqual(mention["normalized_group"], "7")
            self.assertIn("August 7, 2025", mention["verbatim_context"])
            self.assertIn("complete numeric token", mention["token_boundary_rule"])
        self.assertIn("inside another numeric token", check["completion_rule"])

    def test_v106_initialize_removes_invalid_claim_after_retries(
        self,
    ) -> None:
        invalid_claim = (
            "Bumble reported an 8.7% decrease in paying users in Q2 2025, "
            "followed by a 15.94% stock fall on August 7, 2025."
        )
        valid_claim = (
            "Bumble reported an 8.7% decrease in paying users in Q2 2025."
        )
        exact_text = (
            "Bumble reported an 8.7% decrease in paying users in Q2 2025, "
            "followed by a 15.94% stock fall."
        )
        invalid = {
            "hypotheses": [
                "Weak user trends may prevent a material expectation repricing."
            ],
            "current_beliefs": [invalid_claim, valid_claim],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": invalid_claim,
                    "projection_id": "projection_bumble",
                    "exact_text": exact_text,
                },
                {
                    "kind": "basic_info",
                    "claim": valid_claim,
                    "projection_id": "projection_bumble",
                    "exact_text": exact_text,
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [
                "What current product adoption evidence could reverse weak user trends?"
            ],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller(
            [json.loads(json.dumps(invalid)) for _index in range(3)]
        )
        caller.max_structured_corrections = 2
        events: list[dict[str, object]] = []
        caller.on_progress = events.append

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_bumble",
                                "exact_text": exact_text,
                            }
                        ]
                    }
                ]
            },
        )

        self.assertEqual(len(caller.calls), 3)
        self.assertEqual(initialized.usage.llm_calls, 3)
        self.assertEqual(
            initialized.value.current_beliefs,
            (valid_claim,),
        )
        self.assertEqual(len(initialized.value.supporting_evidence), 1)
        self.assertEqual(
            initialized.value.supporting_evidence[0].claim,
            valid_claim,
        )
        self.assertEqual(len(invalid["supporting_evidence"]), 2)
        fallback_events = [
            item
            for item in events
            if item["event_type"] == "structured_validation_fallback_applied"
        ]
        self.assertEqual(len(fallback_events), 1)
        self.assertEqual(
            fallback_events[0]["source_substitution_paths"],
            [],
        )
        self.assertEqual(
            fallback_events[0]["removed_paths"],
            ["supporting_evidence[0]", "current_beliefs[0]"],
        )

    def test_v105_evidence_grounding_refuses_mixed_validation_failures(
        self,
    ) -> None:
        claim = "The metric fell 7% in 2025."
        failure = ValidationError(
            "supporting_evidence[0] claim contains numeric quantities absent from "
            "all Basic exact_text refs with the same claim, "
            'missing_quantity_groups=["7"], '
            'missing_quantity_literals=["7"], '
            'same_claim_evidence_paths=["supporting_evidence[0].claim"]. '
            "Change or remove every listed evidence claim together; "
            "supporting_evidence[1] has unknown kind 'other', expected "
            "'basic_info' or 'signal'"
        )

        fallback = (
            evolution_runtime_module._research_state_evidence_grounding_fallback(
                {
                    "current_beliefs": [claim],
                    "supporting_evidence": [
                        {"claim": claim},
                        {"kind": "other", "claim": "Unrelated evidence."},
                    ],
                },
                failure,
            )
        )

        self.assertIsNone(fallback)

    def test_v105_initialize_removes_invalid_group_only_when_evidence_remains(
        self,
    ) -> None:
        invalid_claim = (
            "Users fell 8.7% in Q2 2025 and the stock fell 15.94% on day 7."
        )
        long_exact_text = (
            "Users fell 8.7% in Q2 2025 and the stock fell 15.94%."
            + " Additional source context." * 12
        )
        self.assertGreater(len(long_exact_text), 300)
        valid_claim = "Cash was 10 in 2025."
        invalid = {
            "hypotheses": ["Weak usage may limit expectation repricing."],
            "current_beliefs": [invalid_claim, valid_claim],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": invalid_claim,
                    "projection_id": "projection_usage",
                    "exact_text": long_exact_text,
                },
                {
                    "kind": "basic_info",
                    "claim": valid_claim,
                    "projection_id": "projection_cash",
                    "exact_text": valid_claim,
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["What could improve product adoption?"],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller(
            [json.loads(json.dumps(invalid)) for _index in range(3)]
        )
        caller.max_structured_corrections = 2
        events: list[dict[str, object]] = []
        caller.on_progress = events.append

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_usage",
                                "exact_text": long_exact_text,
                            },
                            {
                                "projection_id": "projection_cash",
                                "exact_text": valid_claim,
                            },
                        ]
                    }
                ]
            },
        )

        self.assertEqual(initialized.value.current_beliefs, (valid_claim,))
        self.assertEqual(
            tuple(item.claim for item in initialized.value.supporting_evidence),
            (valid_claim,),
        )
        fallback_event = next(
            item
            for item in events
            if item["event_type"] == "structured_validation_fallback_applied"
        )
        self.assertEqual(fallback_event["source_substitution_paths"], [])
        self.assertEqual(
            fallback_event["removed_paths"],
            ["supporting_evidence[0]", "current_beliefs[0]"],
        )

    def test_v106_initialize_removes_overlong_literal_and_keeps_valid_siblings(
        self,
    ) -> None:
        invalid_claim = "The adjusted close declined from $9.15 to $7.11."
        long_literal = "".join(
            f'{{"as_of_date":"2025-02-{day:02d}","adjusted_close":7.11}}'
            for day in range(1, 20)
        )
        self.assertGreater(len(long_literal), 800)
        valid_claims = (
            "Quarterly gold production was 89,073 ounces.",
            "The issuer raised approximately $478 million.",
        )
        invalid = {
            "hypotheses": ["Operations and financing may affect repricing."],
            "current_beliefs": [*valid_claims, invalid_claim],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": valid_claims[0],
                    "projection_id": "projection_production",
                    "exact_text": valid_claims[0],
                },
                {
                    "kind": "basic_info",
                    "claim": valid_claims[1],
                    "projection_id": "projection_financing",
                    "exact_text": valid_claims[1],
                },
                {
                    "kind": "basic_info",
                    "claim": invalid_claim,
                    "projection_id": "projection_market",
                    "exact_text": long_literal,
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["What guidance could change expectations?"],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller(
            [json.loads(json.dumps(invalid)) for _index in range(3)]
        )
        caller.max_structured_corrections = 2
        events: list[dict[str, object]] = []
        caller.on_progress = events.append

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_production",
                                "exact_text": valid_claims[0],
                            },
                            {
                                "projection_id": "projection_financing",
                                "exact_text": valid_claims[1],
                            },
                            {
                                "projection_id": "projection_market",
                                "exact_text": long_literal,
                            },
                        ]
                    }
                ]
            },
        )

        self.assertEqual(initialized.value.current_beliefs, valid_claims)
        self.assertEqual(
            tuple(item.claim for item in initialized.value.supporting_evidence),
            valid_claims,
        )
        fallback_event = next(
            item
            for item in events
            if item["event_type"] == "structured_validation_fallback_applied"
        )
        self.assertEqual(
            fallback_event["removed_paths"],
            ["supporting_evidence[2]", "current_beliefs[2]"],
        )
        self.assertEqual(len(fallback_event["fallback_steps"]), 1)

    def test_v106_initialize_revalidates_layered_live_failure_shape(self) -> None:
        ambiguous_claim = "Operating cash flow was $2,446,400,000."
        ambiguous_literal = (
            '"end":"2024-12-31","filed":"2025-03-27",'
            '"val":2446400000'
        )
        financing_claim = "Financing activities used $1,005,900,000."
        financing_literal = '"end":"2024-12-31","val":-1005900000'
        investing_claim = "Investing activities used $1,189,900,000."
        investing_literal = '"end":"2024-12-31","val":-1189900000'
        valid_claim = "Cost of sales guidance was $1,120 per ounce."
        invalid = {
            "hypotheses": ["Cash generation may support repricing."],
            "current_beliefs": [
                ambiguous_claim,
                financing_claim,
                investing_claim,
                valid_claim,
            ],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": ambiguous_claim,
                    "projection_id": "projection_wrong",
                    "exact_text": ambiguous_literal,
                },
                {
                    "kind": "basic_info",
                    "claim": financing_claim,
                    "projection_id": "projection_financing",
                    "exact_text": financing_literal,
                },
                {
                    "kind": "basic_info",
                    "claim": investing_claim,
                    "projection_id": "projection_investing",
                    "exact_text": investing_literal,
                },
                {
                    "kind": "basic_info",
                    "claim": valid_claim,
                    "projection_id": "projection_guidance",
                    "exact_text": valid_claim,
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["What operating result could change expectations?"],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller(
            [json.loads(json.dumps(invalid)) for _index in range(3)]
        )
        caller.max_structured_corrections = 2
        events: list[dict[str, object]] = []
        caller.on_progress = events.append

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_wrong",
                                "exact_text": "unrelated projection",
                            },
                            {
                                "projection_id": "projection_ambiguous_a",
                                "exact_text": ambiguous_literal,
                            },
                            {
                                "projection_id": "projection_ambiguous_b",
                                "exact_text": ambiguous_literal,
                            },
                            {
                                "projection_id": "projection_financing",
                                "exact_text": financing_literal,
                            },
                            {
                                "projection_id": "projection_investing",
                                "exact_text": investing_literal,
                            },
                            {
                                "projection_id": "projection_guidance",
                                "exact_text": valid_claim,
                            },
                        ]
                    }
                ]
            },
        )

        self.assertEqual(initialized.value.current_beliefs, (valid_claim,))
        self.assertEqual(
            tuple(item.claim for item in initialized.value.supporting_evidence),
            (valid_claim,),
        )
        fallback_event = next(
            item
            for item in events
            if item["event_type"] == "structured_validation_fallback_applied"
        )
        self.assertEqual(len(fallback_event["fallback_steps"]), 2)
        self.assertEqual(
            fallback_event["fallback_steps"][1]["removed_paths"],
            ["supporting_evidence[0]", "current_beliefs[0]"],
        )
        self.assertNotIn("projection_ambiguous_a", initialized.value.to_dict())
        self.assertNotIn("projection_ambiguous_b", initialized.value.to_dict())

    def test_v102_literal_repair_permits_only_linked_claim_changes(self) -> None:
        rows = [
            json.dumps(
                {
                    "adjusted_close": 6.1 + (index / 10),
                    "as_of_date": f"2025-09-{index + 2:02d}",
                    "close": 6.1 + (index / 10),
                    "high": 6.2 + (index / 10),
                    "low": 6.0 + (index / 10),
                    "open": 6.05 + (index / 10),
                    "volume": 4_000_000 + index,
                },
                separators=(",", ":"),
            )
            for index in range(10)
        ]
        projection_text = ",".join(rows)
        self.assertGreater(len(projection_text), 800)
        range_claim = (
            "Adjusted close ranged from 6.1 on 2025-09-02 to 7.0 on 2025-09-11."
        )
        invalid = {
            "contradictions": [],
            "current_beliefs": [range_claim],
            "decision": "continue",
            "hypotheses": ["Recent price action may show early market confirmation."],
            "next_information_needs": [
                "What issuer-specific event could materially change expectations?"
            ],
            "open_questions": [],
            "resolved_questions": [],
            "supporting_evidence": [
                {
                    "claim": range_claim,
                    "exact_text": rows[0] + " ... " + rows[-1],
                    "kind": "basic_info",
                    "projection_id": "projection_market",
                }
            ],
        }
        narrowed_claim = "Adjusted close was 6.1 on 2025-09-02."
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"] = [narrowed_claim]
        corrected["supporting_evidence"][0]["claim"] = narrowed_claim
        corrected["supporting_evidence"][0]["exact_text"] = rows[0]
        caller = ScriptedRoleCaller([invalid, invalid, corrected])
        caller.max_structured_corrections = 2

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_market",
                                "exact_text": projection_text,
                            }
                        ]
                    }
                ]
            },
        )

        self.assertEqual(len(caller.calls), 3)
        feedback = caller.calls[2]["payload"]["validation_feedback"]
        obligation = feedback["obligations"][0]
        self.assertEqual(
            obligation["must_change_paths"],
            ["supporting_evidence[0]"],
        )
        self.assertEqual(
            obligation["permitted_dependency_paths"],
            ["current_beliefs[0]"],
        )
        self.assertEqual(
            feedback["permitted_dependency_paths"],
            ["current_beliefs[0]"],
        )
        self.assertIn(
            "outside required_change_paths and permitted_dependency_paths",
            feedback["completion_check"],
        )
        self.assertIn(
            "When an obligation contains permitted_dependency_paths",
            caller.calls[0]["system_prompt"],
        )
        self.assertEqual(
            initialized.value.supporting_evidence[0].claim,
            narrowed_claim,
        )


    def test_v92_initialize_removes_exact_cross_frontier_duplicate(self) -> None:
        need = "What evidence would distinguish adoption from customer trials?"
        invalid = {
            "contradictions": [],
            "current_beliefs": [],
            "decision": "continue",
            "hypotheses": ["Adoption may accelerate within the forecast horizon."],
            "next_information_needs": [need],
            "open_questions": [need],
            "resolved_questions": [],
            "supporting_evidence": [],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["open_questions"] = []
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(initialized.value.open_questions, ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        duplicate = next(
            item
            for item in feedback["obligations"]
            if "duplicates one next information need" in item["instruction"]
        )
        self.assertEqual(duplicate["must_change_paths"], ["open_questions[0]"])
        self.assertIn(
            "Never repeat an exact next_information_needs string in open_questions",
            caller.calls[0]["system_prompt"],
        )

    def test_v29_initialize_binds_quantitative_belief_to_exact_evidence_claim(self) -> None:
        cash_text = (
            "The company delivered record free cash flow in the second quarter "
            "of almost $650 million."
        )
        market_text = '{"as_of_date":"2025-09-29","adjusted_close":24.37}'
        cash_claim = "The company delivered almost $650 million of free cash flow in Q2."
        unsupported_belief = (
            "The company delivered almost $650 million of free cash flow in Q2 2025 "
            "and expects net cash by Q3 2025."
        )
        invalid = {
            "hypotheses": ["Cash generation may support the repricing thesis."],
            "current_beliefs": [unsupported_belief],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": cash_claim,
                    "projection_id": "projection_cash",
                    "exact_text": cash_text,
                },
                {
                    "kind": "basic_info",
                    "claim": "The adjusted close was $24.37 on 2025-09-29.",
                    "projection_id": "projection_market",
                    "exact_text": market_text,
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": ["Will cash generation persist?"],
            "next_information_needs": ["Check the balance-sheet outlook."],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"] = [cash_claim]
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_cash",
                                "exact_text": cash_text,
                            },
                            {
                                "projection_id": "projection_market",
                                "exact_text": market_text,
                            },
                        ]
                    }
                ]
            },
        )

        error = validation_error(caller.calls[1])
        self.assertIn("quantitative ResearchState assertions", error)
        self.assertIn("Numbers from unrelated claims do not count", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertTrue(
            all(item["must_change_paths"] for item in feedback["obligations"])
        )
        self.assertEqual(initialized.value.current_beliefs, (cash_claim,))
        self.assertIn(
            "must copy one accepted supporting_evidence claim byte-for-byte",
            caller.calls[0]["system_prompt"],
        )

    def test_v62_initialize_correction_keeps_precise_semantic_paths(self) -> None:
        claim = (
            "Kinross Gold reported strong Q2 2025 results with record operating "
            "margins and free cash flow."
        )
        corrected_claim = (
            "Kinross Gold reported strong second-quarter results with record "
            "operating margins and free cash flow."
        )
        exact_text = (
            "Our production in the second quarter was on plan, delivering 513,000 "
            "ounces at a cost of sales of $1,074 per ounce. Our strong production "
            "and cost management, combined with the gold price, resulted in record "
            "operating margins. As a result, we also delivered record free cash "
            "flow in the second quarter of almost $650 million and a first half "
            "total of just over $1 billion."
        )
        invalid = {
            "hypotheses": ["Strong operations may support a further repricing."],
            "current_beliefs": [claim],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": claim,
                    "projection_id": "projection_21113038b3f46eedb508d711",
                    "exact_text": exact_text,
                }
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["Check the durability of operating margins."],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"] = [corrected_claim]
        corrected["supporting_evidence"][0]["claim"] = corrected_claim
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": (
                                    "projection_21113038b3f46eedb508d711"
                                ),
                                "exact_text": exact_text,
                            }
                        ]
                    }
                ]
            },
        )

        error = validation_error(caller.calls[1])
        self.assertIn("supporting_evidence[0]", error)
        self.assertIn('missing_quantity_groups=["2025"]', error)
        self.assertIn("linked_assertions=['current_beliefs[0]']", error)
        self.assertNotIn("returned invalid JSON fields", error)
        self.assertIn(
            "Preserve unrelated valid fields and items byte-for-byte",
            caller.calls[1]["system_prompt"],
        )
        self.assertEqual(initialized.value.current_beliefs, (corrected_claim,))
        self.assertEqual(
            initialized.value.supporting_evidence[0].claim,
            corrected_claim,
        )

    def test_reflect_retains_complete_grounded_long_claim(
        self,
    ) -> None:
        prior_claim = "The resort construction timeline remains the key uncertainty."
        prior_ref = ResearchEvidenceRef(
            kind="basic_info",
            claim=prior_claim,
            projection_id="projection-resort",
            exact_text="The resort remains under construction.",
        )
        previous = ResearchState(
            hypotheses=("The resort opening may support repricing.",),
            current_beliefs=(prior_claim,),
            supporting_evidence=(prior_ref,),
            open_questions=("Will construction remain on schedule?",),
            next_information_needs=("Check construction and funding updates.",),
        )
        overlong_claim = (
            "The 2022 sale-leaseback changed historical financing but does not "
            "by itself establish a current management-guidance revision. "
            + "This distinction must remain explicit in the active research state. "
            * 6
        )
        self.assertGreater(len(overlong_claim), 400)
        invalid = {
            "hypotheses": list(previous.hypotheses),
            "current_beliefs": [prior_claim, overlong_claim],
            "supporting_evidence": [
                prior_ref.to_dict(),
                {
                    "kind": "signal",
                    "claim": overlong_claim,
                    "signal_ref": "guidance_acceleration:v1",
                    "evidence_group": "supporting",
                    "evidence_index": 0,
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": list(previous.open_questions),
            "next_information_needs": list(previous.next_information_needs),
            "decision": "continue",
        }
        corrected_claim = (
            "The cited filing discusses a historical sale-leaseback, not a current "
            "management-guidance revision."
        )
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"][1] = corrected_claim
        corrected["supporting_evidence"][1]["claim"] = corrected_claim
        caller = ScriptedRoleCaller([invalid, corrected])
        result = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=0.6,
            interpretation="The filing contains historical financing context.",
            supporting_evidence=(
                SignalEvidence(
                    document_id="filing-1",
                    exact_span="The Company completed a sale-leaseback in 2022.",
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )

        controller = LLMResearchController(caller)
        controller.set_evaluation_context(
            datetime(2025, 7, 31, tzinfo=timezone.utc)
        )
        reflected = controller.reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        self.assertEqual(len(caller.calls), 1)
        capacity = caller.calls[0]["payload"]["research_state_capacity"]
        self.assertEqual(
            capacity["fields"]["supporting_evidence"],
            {
                "current_count": 1,
                "effective_maximum_count": 8,
                "new_item_capacity": 7,
            },
        )
        self.assertIn(
            "Use research_state_capacity as advisory compression guidance",
            caller.calls[0]["system_prompt"],
        )
        self.assertEqual(
            caller.calls[0]["payload"]["evaluation_context"]["prediction_time"],
            "2025-07-31T00:00:00+00:00",
        )
        self.assertIn(
            "every new or retained question must request only facts available",
            caller.calls[0]["system_prompt"],
        )
        self.assertEqual(reflected.value.current_beliefs[1], overlong_claim)
        self.assertEqual(
            reflected.value.supporting_evidence[1].claim,
            overlong_claim,
        )

    def test_initialize_keeps_complete_supported_content_above_summary_targets(self) -> None:
        claim = "Issuer guidance remains conditional on customer demand. " * 31
        literal = claim + " Additional disclosed context." * 30
        self.assertGreater(len(claim), 300)
        self.assertGreater(len(claim), 1600)
        self.assertGreater(len(literal), 800)
        evidence = [
            {"kind": "basic_info", "claim": claim,
             "projection_id": f"source_{letter}", "exact_text": literal}
            for letter in "ABCDEFGHI"
        ]
        output = ResearchState(
            current_beliefs=(claim,),
            next_information_needs=("What disclosed milestone would confirm demand?",),
        ).to_dict()
        output["supporting_evidence"] = evidence
        caller = ScriptedRoleCaller([output])
        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": [{"projections": [
                {"projection_id": row["projection_id"], "exact_text": literal}
                for row in evidence
            ]}]},
        )
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.to_dict(), output)

    def test_initialize_summary_targets_do_not_reject_valid_content(self) -> None:
        invalid = {
            "hypotheses": ["One material catalyst may support repricing."],
            "current_beliefs": [
                (
                    f"Source-summary item {chr(65 + index)} repeats one visible projection "
                    "instead of retaining only a decision-relevant belief."
                )
                for index in range(52)
            ],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [
                f"Resolved source-summary question {index}." for index in range(5)
            ],
            "open_questions": [
                f"Open source-summary question {index}." for index in range(10)
            ],
            "next_information_needs": [
                f"Check one distinct material uncertainty {index}." for index in range(10)
            ],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([invalid])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.to_dict(), invalid)
        self.assertGreater(len(json.dumps(invalid).encode()), 6000)


    def test_v79_initialize_aggregates_visible_answers_before_compaction(
        self,
    ) -> None:
        analyst_need = (
            "What are the latest analyst price targets and ratings for Kinross "
            "Gold, and have they been revised upward recently?"
        )
        construction_need = (
            "What is the current construction progress and expected opening timeline?"
        )
        invalid = {
            "hypotheses": ["A material catalyst may support repricing."],
            "current_beliefs": [
                f"Redundant source-summary belief {index}." for index in range(25)
            ],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": ["What is the current construction progress?"],
            "open_questions": [],
            "next_information_needs": [
                analyst_need,
                construction_need,
                "What issuer operating milestone could change expectations?",
            ],
            "decision": "continue",
        }
        corrected = {
            "hypotheses": ["A material catalyst may support repricing."],
            "current_beliefs": ["The catalyst remains unconfirmed."],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": ["What is the current construction progress?"],
            "open_questions": [],
            "next_information_needs": [
                construction_need,
                "What issuer operating milestone could change expectations?"
            ],
            "decision": "continue",
        }
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": "projection_analyst",
                            "exact_text": (
                                "UBS analyst recently increased Kinross Gold's price "
                                "target to $27 from $20 while reiterating a Buy rating."
                            ),
                        }
                    ]
                }
            ]
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            basic_info,
        )

        error = validation_error(caller.calls[1])
        self.assertIn("already answered by visible Basic Info", error)
        self.assertIn("matching_projection_id='projection_analyst'", error)
        self.assertIn("next_information_needs[0]", error)
        self.assertNotIn("contradicted its own resolved question", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        visible_obligation = next(
            item
            for item in feedback["obligations"]
            if "already answered by visible Basic Info" in item["instruction"]
        )
        self.assertIn(
            "next_information_needs[0]",
            visible_obligation["must_change_paths"],
        )
        self.assertEqual(
            initialized.value.next_information_needs,
            (
                construction_need,
                "What issuer operating milestone could change expectations?",
            ),
        )


    def test_v79_initialize_abstains_on_partial_basic_info_overlap(self) -> None:
        state = {
            "hypotheses": ["A material catalyst may support repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [
                "How could an analyst price target affect customer demand and "
                "operating margins?"
            ],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_analyst",
                                "exact_text": (
                                    "An analyst increased the price target and kept "
                                    "a Buy rating."
                                ),
                            }
                        ]
                    }
                ]
            },
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(
            initialized.value.next_information_needs,
            tuple(state["next_information_needs"]),
        )

    def test_v80_initialize_does_not_treat_issuer_name_as_resolved_topic(
        self,
    ) -> None:
        needs = [
            "What are Kinross Gold's recent quarterly earnings results and forward "
            "guidance for production and costs?",
            "Are there any regulatory approvals for Kinross Gold's major projects?",
            "How does Kinross Gold's valuation compare with mining peers?",
        ]
        state = {
            "hypotheses": ["An issuer catalyst may support repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [
                "What is Kinross Gold's recent stock price performance?"
            ],
            "open_questions": [],
            "next_information_needs": needs,
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, tuple(needs))

    def test_v83_initialize_does_not_treat_period_as_resolved_topic(self) -> None:
        need = (
            "What is the current gold price outlook and how does it compare to the "
            "average realized price in Q2 2025?"
        )
        state = {
            "hypotheses": ["Gold-price strength may support further repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [
                "What was the issuer's production and cost performance in Q2 2025?"
            ],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))

    def test_v84_initialize_does_not_treat_entity_metric_as_resolved_topic(
        self,
    ) -> None:
        need = (
            "What are the latest gold price forecasts and how do they impact "
            "Kinross's revenue and profitability?"
        )
        state = {
            "hypotheses": ["Gold-price strength may support further repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": ["What was Kinross's revenue in 2024?"],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))

    def test_v85_initialize_does_not_treat_generic_subject_as_topic(self) -> None:
        need = (
            "What are the company's revenue and EBITDA figures for Q1 compared to "
            "the prior year, and what trends did management identify?"
        )
        state = {
            "hypotheses": ["Revenue momentum may support further repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": ["What is the company's recent revenue?"],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))
        self.assertIn(
            "downstream Predictor receives this compact ResearchState",
            caller.calls[0]["system_prompt"],
        )

    def test_v88_initialize_preserves_named_project_unresolved_facets(self) -> None:
        need = (
            "What is the expected impact of the Southern Illinois Connector project "
            "on Enbridge's overall capacity and market share in the Gulf Coast "
            "region beyond the announced 200,000 barrels per day?"
        )
        state = {
            "hypotheses": ["A new pipeline may support volume growth."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [
                "Has Enbridge announced any new pipeline projects to the Gulf Coast? "
                "Yes, the Southern Illinois Connector with Energy Transfer LP."
            ],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))

    def test_v88_initialize_preserves_explicit_residual_scope_need(self) -> None:
        need = (
            "What are the latest analyst price targets and ratings beyond UBS's "
            "$27 target?"
        )
        state = {
            "hypotheses": ["Further estimate revisions may support repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_analyst",
                                "exact_text": (
                                    "UBS increased its price target to $27 and kept "
                                    "a Buy rating."
                                ),
                            }
                        ]
                    }
                ]
            },
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))

    def test_v88_initialize_preserves_partly_resolved_compound_need(self) -> None:
        need = (
            "What is the company's production guidance for the remainder of 2025 "
            "and 2026, and are there any updates on the Tasiast mill recovery and "
            "its impact on full-year production?"
        )
        state = {
            "hypotheses": ["Execution may determine further repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [
                "What is Kinross Gold's production guidance for 2025-2027?"
            ],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))

    def test_v88_initialize_reframes_outside_horizon_event_causality(self) -> None:
        invalid_hypothesis = (
            "Wynn's UAE resort opening in 2027 will drive significant revenue "
            "growth, supporting a doubling of adjusted share price within six months."
        )
        corrected_hypothesis = (
            "Within-horizon construction progress and pre-opening bookings could "
            "raise expectations for Wynn's 2027 UAE resort and support repricing."
        )

        def state(hypothesis: str) -> dict[str, Any]:
            return {
                "hypotheses": [hypothesis],
                "current_beliefs": [],
                "supporting_evidence": [],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": [
                    "What construction or booking milestone could change expectations?"
                ],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller(
            [state(invalid_hypothesis), state(corrected_hypothesis)]
        )
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(
            datetime(2025, 7, 31, tzinfo=timezone.utc)
        )

        initialized = controller.initialize(
            default_information_plan(),
            {"requests": []},
        )

        error = validation_error(caller.calls[1])
        self.assertIn("operating event outside the horizon", error)
        self.assertIn("hypotheses[0]", error)
        self.assertIn("2027", error)
        self.assertIn("2026-01-31", error)
        self.assertEqual(
            caller.calls[0]["payload"]["evaluation_context"],
            caller.calls[1]["payload"]["evaluation_context"],
        )
        self.assertEqual(
            initialized.value.hypotheses,
            (corrected_hypothesis,),
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligation_count"], 1)
        self.assertEqual(
            feedback["required_change_paths"],
            ["hypotheses[0]"],
        )

    def test_v103_initialize_rejects_future_source_contents(self) -> None:
        invalid_need = (
            "What metrics did the issuer provide in its Q3 earnings, reported in "
            "November 2025?"
        )
        corrected_need = (
            "What paying-user and revenue metrics had the issuer disclosed by "
            "September 30, 2025?"
        )

        def state(need: str) -> dict[str, Any]:
            return {
                "hypotheses": ["Recent user trends may change market expectations."],
                "current_beliefs": [],
                "supporting_evidence": [],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": [need],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller([state(invalid_need), state(corrected_need)])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(
            datetime(2025, 9, 30, tzinfo=timezone.utc)
        )

        initialized = controller.initialize(
            default_information_plan(),
            {"requests": []},
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("beyond prediction_time", feedback["validation_error"])
        self.assertIn("November 2025", feedback["validation_error"])
        self.assertEqual(
            feedback["required_change_paths"],
            ["next_information_needs[0]"],
        )
        self.assertIn(
            "must request evidence that could already exist by prediction_time",
            caller.calls[0]["system_prompt"],
        )
        self.assertEqual(
            initialized.value.next_information_needs,
            (corrected_need,),
        )

    def test_v111_initialize_rejects_all_live_future_need_forms(self) -> None:
        invalid_needs = [
            (
                "What specific milestones or updates regarding construction were "
                "disclosed between July 2025 and January 2026?"
            ),
            (
                "What were the quarterly earnings results and forward guidance for "
                "periods ending September 2025 and December 2025?"
            ),
            (
                "Did the issuer announce new partnerships, customer agreements, or "
                "regulatory approvals after July 2025?"
            ),
        ]
        corrected_needs = [
            "What construction milestones had the issuer disclosed by 2025-07-31?",
            "What earnings and guidance had the issuer reported by 2025-07-31?",
            "What partnerships or approvals had the issuer announced by 2025-07-31?",
        ]

        def state(needs: list[str]) -> dict[str, Any]:
            return {
                "hypotheses": ["Current disclosures may change expectations."],
                "current_beliefs": [],
                "supporting_evidence": [],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": needs,
                "decision": "continue",
            }

        caller = ScriptedRoleCaller(
            [state(invalid_needs), state(corrected_needs)]
        )
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(
            datetime(2025, 7, 31, tzinfo=timezone.utc)
        )

        initialized = controller.initialize(
            default_information_plan(),
            {"requests": []},
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            [item["issue_code"] for item in feedback["obligations"]],
            ["future_information_unavailable"] * 3,
        )
        self.assertEqual(
            feedback["required_change_paths"],
            [
                "next_information_needs[0]",
                "next_information_needs[1]",
                "next_information_needs[2]",
            ],
        )
        error = feedback["validation_error"]
        self.assertIn("January 2026", error)
        self.assertIn("September 2025", error)
        self.assertIn("December 2025", error)
        self.assertIn("after July 2025", error)
        self.assertEqual(
            initialized.value.next_information_needs,
            tuple(corrected_needs),
        )

    def test_v111_future_need_issue_generalizes_across_temporal_forms(self) -> None:
        invalid_needs = (
            "Which customer metrics were in Q4 2025 results?",
            "List production actuals for the next reporting period.",
            "What approvals were announced subsequent to July 2025?",
            "What 2026 revenue results did the issuer report?",
            "What actual results for Q1 2026 could we obtain as of 2025-07-31?",
        )
        corrected_need = (
            "What operating evidence had the issuer disclosed by 2025-07-31?"
        )

        for invalid_need in invalid_needs:
            with self.subTest(invalid_need=invalid_need):
                invalid = {
                    "hypotheses": ["Current evidence may change expectations."],
                    "current_beliefs": [],
                    "supporting_evidence": [],
                    "contradictions": [],
                    "resolved_questions": [],
                    "open_questions": [],
                    "next_information_needs": [invalid_need],
                    "decision": "continue",
                }
                corrected = json.loads(json.dumps(invalid))
                corrected["next_information_needs"] = [corrected_need]
                caller = ScriptedRoleCaller([invalid, corrected])
                controller = LLMResearchController(caller)
                controller.set_evaluation_context(
                    datetime(2025, 7, 31, tzinfo=timezone.utc)
                )

                initialized = controller.initialize(
                    default_information_plan(),
                    {"requests": []},
                )

                obligation = caller.calls[1]["payload"]["validation_feedback"][
                    "obligations"
                ][0]
                self.assertEqual(
                    obligation["issue_code"],
                    "future_information_unavailable",
                )
                self.assertEqual(
                    obligation["prediction_time"],
                    "2025-07-31",
                )
                self.assertEqual(
                    initialized.value.next_information_needs,
                    (corrected_need,),
                )

    def test_v111_future_boundary_preserves_as_of_expectations_and_hypothetical(
        self,
    ) -> None:
        state = {
            "hypotheses": ["Current evidence may change expectations."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [
                "How could a 2027 opening affect current market expectations?"
            ],
            "next_information_needs": [
                "What guidance had the issuer disclosed by 2025-07-31 for 2026?",
                "What did the issuer disclose by prediction_time about Q1 2026 guidance?",
                "What forecast was disclosed as_of the cutoff_time for 2026?",
                "What did the issuer disclose by 2025-07-31 about commitments that could convert to revenue by 2026-01-31?",
                "What did the issuer disclose by prediction_time that might affect demand in 2026?",
                (
                    "What had the issuer disclosed by July 31, 2025 about the "
                    "timing of its Q4 2025 earnings report?"
                ),
            ],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(
            datetime(2025, 7, 31, tzinfo=timezone.utc)
        )

        initialized = controller.initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(
            initialized.value.next_information_needs,
            tuple(state["next_information_needs"]),
        )
        self.assertEqual(
            initialized.value.open_questions,
            tuple(state["open_questions"]),
        )

    def test_v109_initialize_rejects_prediction_date_adjusted_close_lookup(
        self,
    ) -> None:
        invalid_need = (
            "What was the adjusted close price of the issuer on 2025-07-31?"
        )
        corrected_need = (
            "What financing or construction milestone had the issuer disclosed "
            "by 2025-07-31?"
        )

        def state(need: str) -> dict[str, Any]:
            return {
                "hypotheses": ["Current milestones may change market expectations."],
                "current_beliefs": [],
                "supporting_evidence": [],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": [need],
                "decision": "continue",
            }

        caller = ScriptedRoleCaller([state(invalid_need), state(corrected_need)])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(
            datetime(2025, 7, 31, tzinfo=timezone.utc)
        )

        initialized = controller.initialize(
            default_information_plan(),
            {"requests": []},
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("runtime-owned evaluation input", feedback["validation_error"])
        self.assertIn("next_information_needs[0]", feedback["validation_error"])
        self.assertEqual(
            feedback["required_change_paths"],
            ["next_information_needs[0]"],
        )
        self.assertEqual(
            initialized.value.next_information_needs,
            (corrected_need,),
        )

    def test_v109_initialize_allows_price_volume_trend_question(self) -> None:
        need = (
            "How did issuer price and volume trend through 2025-07-31 after the "
            "latest disclosed milestone?"
        )
        state = {
            "hypotheses": ["Market confirmation may distinguish the active thesis."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(
            datetime(2025, 7, 31, tzinfo=timezone.utc)
        )

        initialized = controller.initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))

    def test_v103_initialize_allows_as_of_future_schedule_question(self) -> None:
        need = (
            "What had the issuer disclosed by September 30, 2025 about the timing "
            "of its Q3 earnings report to be released in November 2025?"
        )
        state = {
            "hypotheses": ["A disclosed milestone may change market expectations."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(
            datetime(2025, 9, 30, tzinfo=timezone.utc)
        )

        initialized = controller.initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.next_information_needs, (need,))

    def test_v93_initialize_accepts_explicit_pricing_in_transmission(self) -> None:
        hypothesis = (
            "The market may be pricing in successful execution of a resort opening "
            "in 2027, which could support the stock price over the next six months."
        )
        state = {
            "hypotheses": [hypothesis],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [
                "What current milestone could change project expectations?"
            ],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([state])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(
            datetime(2025, 7, 31, tzinfo=timezone.utc)
        )

        initialized = controller.initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(initialized.value.hypotheses, (hypothesis,))
        self.assertEqual(caller.stages, ["research_controller_initialize"])

    def test_v85_initialize_keeps_unknown_kind_feedback_in_one_obligation(
        self,
    ) -> None:
        claim = "A direct issuer catalyst may change expectations."
        exact_text = "A direct issuer catalyst may change expectations."
        invalid = {
            "hypotheses": ["The catalyst may support further repricing."],
            "current_beliefs": [claim],
            "supporting_evidence": [
                {
                    "kind": "news",
                    "claim": claim,
                    "projection_id": "projection_news",
                    "exact_text": exact_text,
                }
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["Check whether the catalyst is durable."],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["supporting_evidence"][0]["kind"] = "basic_info"
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_news",
                                "exact_text": exact_text,
                            }
                        ]
                    }
                ]
            },
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligation_count"], 1)
        self.assertEqual(
            feedback["obligations"][0]["must_change_paths"],
            ["supporting_evidence[0].kind"],
        )
        self.assertIn(
            "expected 'basic_info' or 'signal'",
            feedback["obligations"][0]["instruction"],
        )
        self.assertEqual(initialized.value.supporting_evidence[0].kind, "basic_info")

    def test_initialize_rejects_runtime_baseline_need_above_summary_target(
        self,
    ) -> None:
        invalid = {
            "hypotheses": [
                f"Material issuer hypothesis {letter}." for letter in "ABC"
            ],
            "current_beliefs": [
                f"Decision-relevant issuer belief {letter}." for letter in "ABCDEFGH"
            ],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [
                f"Resolved issuer question {letter}." for letter in "ABCD"
            ],
            "open_questions": [
                "What is the exact baseline date and price for the six-month "
                "evaluation outcome?",
                "Could an operating disruption impair the active thesis?",
                "Could capital allocation strengthen the active thesis?",
                "Could a regulatory event impair the active thesis?",
            ],
            "next_information_needs": [
                f"Check unresolved issuer uncertainty {letter}." for letter in "ABCDEF"
            ],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["open_questions"] = corrected["open_questions"][1:]
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        error = validation_error(caller.calls[1])
        self.assertIn("runtime-owned evaluation input", error)
        self.assertIn("invalid_field='open_questions[0]'", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        baseline_obligation = next(
            item
            for item in feedback["obligations"]
            if "runtime-owned evaluation input" in item["instruction"]
        )
        self.assertEqual(
            baseline_obligation["must_change_paths"], ["open_questions[0]"]
        )
        self.assertEqual(
            initialized.value.open_questions,
            tuple(corrected["open_questions"]),
        )


    def test_initialize_duplicate_question_is_independent_of_summary_targets(
        self,
    ) -> None:
        repeated_question = "Is the customer renewal still pending?"
        invalid = {
            "hypotheses": [
                f"Material hypothesis {letter}." for letter in "ABC"
            ],
            "current_beliefs": [
                f"Distinct qualitative belief {letter}." for letter in "ABCDEFGH"
            ],
            "supporting_evidence": [],
            "contradictions": [
                f"Distinct qualitative contradiction {letter}." for letter in "ABCD"
            ],
            "resolved_questions": [],
            "open_questions": [
                repeated_question,
                "Could financing delay deployment?",
                "Could costs impair adoption?",
                "Could regulation delay adoption?",
            ],
            "next_information_needs": [
                repeated_question,
                "Check renewal disclosure.",
                "Check financing disclosure.",
                "Check deployment evidence.",
                "Check cost disclosure.",
                "Check regulatory disclosure.",
            ],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["open_questions"] = corrected["open_questions"][1:]
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(
            initialized.value.open_questions,
            tuple(corrected["open_questions"]),
        )




    def test_initialize_preserves_resolved_bookkeeping_above_summary_target(
        self,
    ) -> None:
        invalid = {
            "hypotheses": [f"Material hypothesis {item}." for item in "ABC"],
            "current_beliefs": [
                f"Active issuer belief {item}." for item in "ABCDEFGH"
            ],
            "supporting_evidence": [],
            "contradictions": [
                f"Material issuer contradiction {item}." for item in "ABC"
            ],
            "resolved_questions": [
                f"What issuer question {item} was resolved?" for item in "ABC"
            ],
            "open_questions": [
                f"What issuer uncertainty {item} remains?" for item in "ABC"
            ],
            "next_information_needs": [
                f"Check unresolved issuer evidence {item}." for item in "ABCDE"
            ],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["resolved_questions"] = corrected["resolved_questions"][:-1]
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(initialized.value.to_dict(), invalid)


    def test_v82_initialize_supplies_exact_claim_copy_candidates(self) -> None:
        exact_claim = (
            "Kinross's adjusted share price reached $24.37 on 2025-09-29."
        )
        invalid = {
            "hypotheses": ["Recent momentum may support further repricing."],
            "current_beliefs": [
                "Kinross Gold's adjusted share price reached $24.37 on 2025-09-29."
            ],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": exact_claim,
                    "projection_id": "projection_market",
                    "exact_text": (
                        '{"adjusted_close":24.37,"as_of_date":"2025-09-29"}'
                    ),
                }
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [
                "Check whether operating evidence confirms recent momentum."
            ],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"] = [exact_claim]
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_market",
                                "exact_text": (
                                    '{"adjusted_close":24.37,'
                                    '"as_of_date":"2025-09-29"}'
                                ),
                            }
                        ]
                    }
                ]
            },
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        obligation = next(
            item
            for item in feedback["obligations"]
            if "quantitative ResearchState assertions" in item["instruction"]
        )
        self.assertEqual(
            obligation["copy_candidates_by_path"],
            {
                "current_beliefs[0]": [
                    {
                        "source_path": "supporting_evidence[0].claim",
                        "exact_claim": exact_claim,
                    }
                ]
            },
        )
        self.assertIn(
            "do not restate, expand, or change issuer words",
            caller.calls[1]["system_prompt"],
        )
        self.assertEqual(initialized.value.current_beliefs, (exact_claim,))

    def test_v72_malformed_full_token_output_gets_truncation_feedback(self) -> None:
        corrected = {
            "hypotheses": ["One material catalyst may support repricing."],
            "current_beliefs": [],
            "supporting_evidence": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": ["Is the catalyst issuer-confirmed?"],
            "next_information_needs": ["Check issuer evidence for the catalyst."],
            "decision": "continue",
        }

        class TruncatedThenValidCaller(ScriptedRoleCaller):
            def complete_json(self, **kwargs):
                self.stages.append(str(kwargs["stage"]))
                self.calls.append(dict(kwargs))
                if len(self.calls) == 1:
                    raise StructuredOutputInvalid(
                        "provider returned invalid structured output",
                        '{"hypotheses":["unfinished output",',
                        AgentUsage(llm_calls=1, tokens=2_500, cost=0.01),
                        output_tokens=2_000,
                        output_token_limit=2_000,
                    )
                return self.outputs.pop(0), AgentUsage(
                    llm_calls=1,
                    tokens=500,
                    cost=0.01,
                )

        caller = TruncatedThenValidCaller([corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {"requests": []},
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        self.assertIn("reached max_output_tokens=2000", feedback["validation_error"])
        self.assertIn("output-ceiling truncation", feedback["validation_error"])
        self.assertEqual(
            caller.calls[0]["system_prompt"],
            caller.calls[1]["system_prompt"],
        )
        self.assertEqual(initialized.value, ResearchState.from_dict(corrected))
