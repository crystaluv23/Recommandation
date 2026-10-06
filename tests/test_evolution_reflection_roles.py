"""Research reflection, evidence mapping, and terminal role tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403
from stock_opportunity_agent.research.evolution_research_validation import (
    _normalize_research_state_output,
    _validate_research_state_refs,
    _reflection_need_transition_contract,
    _targeted_answer_need_transition_errors,
)


def claim_error(value, *, basic_info=None, previous_state=None, batch=None):
    """Inspect owning rejection before safe programmatic quarantine."""
    try:
        normalized = _normalize_research_state_output(value, initialize=batch is None,
            basic_info=basic_info, previous_state=previous_state)
        _validate_research_state_refs(ResearchState.from_dict(normalized),
            phase='initialize' if batch is None else 'reflect', basic_info=basic_info,
            previous_state=previous_state, batch=batch)
    except StructuredValidationError as error:
        return error
    raise AssertionError('Expected an independently invalid claim.')


V117_PRIOR_NEED = (
    "What forward guidance or production outlook had Kinross Gold disclosed "
    "by 2025-09-30 regarding gold equivalent production and cost per ounce "
    "for the remainder of 2025 and 2026?"
)
V117_RAW_RESIDUAL = (
    "Cost per ounce guidance for the remainder of 2025 and 2026 is not "
    "covered by this card."
)
V117_BOUNDED_RESIDUAL = (
    "Cost per ounce guidance for the remainder of 2025 and 2026 is not "
    "covered by this card, by 2025-09-30."
)


class PartialResidualTemporalScopeTests(TestCase):
    def _v117_reflect_inputs(self):
        previous = ResearchState(
            hypotheses=("Cost guidance may compress margins.",),
            next_information_needs=(V117_PRIOR_NEED,),
        )
        selection = SignalSelectionDecision(
            signal_ref="guidance_acceleration:v1",
            reason_code="answer_need",
            selection_reason="The card covers the disclosed production outlook.",
            applicability_hypothesis="Guidance disclosures apply to this need.",
            expected_role="primary",
            context_tags=("general",),
            target_need_indices=(0,),
            answer_scope="partial",
            residual_need=V117_RAW_RESIDUAL,
        )
        result = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.POSITIVE,
            confidence=0.7,
            interpretation="guidance_acceleration=positive",
            coverage=SignalCoverage.SUFFICIENT,
            supporting_evidence=(
                SignalEvidence(
                    document_id="kinross-guidance-document",
                    exact_span="Kinross guided 2025 production toward the upper end.",
                    timestamp=datetime(2025, 9, 1, tzinfo=timezone.utc),
                ),
            ),
        )
        return previous, selection, SignalBatchResult(
            results=(result,), signal_calls=1,
        )

    def _adopting_output(self, need):
        return {
            "hypotheses": ["Cost guidance may compress margins."],
            "current_beliefs": [],
            "supporting_evidence": [
                {
                    "kind": "signal",
                    "claim": "Kinross guided 2025 production toward the upper end.",
                    "signal_ref": "guidance_acceleration:v1",
                    "evidence_group": "supporting",
                    "evidence_index": 0,
                }
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [need],
            "decision": "continue",
        }

    def test_partial_residual_contract_is_satisfiable_and_survives_both_guards(self) -> None:
        previous, selection, batch = self._v117_reflect_inputs()
        caller = ScriptedRoleCaller(
            [self._adopting_output(V117_RAW_RESIDUAL),
             self._adopting_output(V117_BOUNDED_RESIDUAL)]
        )
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(datetime(2025, 9, 30, tzinfo=timezone.utc))
        controller.set_reflection_runtime_context(
            selections=(selection,), must_finalize=False, termination_trigger=None,
        )

        reflected = controller.reflect(default_information_plan(), previous, batch)

        self.assertEqual(
            reflected.value.next_information_needs, (V117_BOUNDED_RESIDUAL,)
        )
        self.assertEqual(len(caller.calls), 2)
        contract = caller.calls[0]["payload"]["need_transition_contract"]
        action = contract["need_rules"][0]["available_answer_actions"][0]
        self.assertEqual(action["residual_need"], V117_BOUNDED_RESIDUAL)
        self.assertEqual(
            contract["need_rules"][0]["required_transition"],
            "if evidence from this available partial answer is adopted, "
            "replace_with_exact_residual_need; otherwise preserve_exactly",
        )
        intents = caller.calls[0]["payload"]["executed_selection_intents"]
        self.assertEqual(intents[0]["residual_need"], V117_BOUNDED_RESIDUAL)
        feedback = validation_error(caller.calls[1])
        self.assertIn("beyond prediction_time", feedback)
        self.assertIn(V117_RAW_RESIDUAL, feedback)

    def test_exact_residual_from_contract_is_accepted_without_correction(self) -> None:
        previous, selection, batch = self._v117_reflect_inputs()
        caller = ScriptedRoleCaller([self._adopting_output(V117_BOUNDED_RESIDUAL)])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(datetime(2025, 9, 30, tzinfo=timezone.utc))
        controller.set_reflection_runtime_context(
            selections=(selection,), must_finalize=False, termination_trigger=None,
        )

        reflected = controller.reflect(default_information_plan(), previous, batch)

        self.assertEqual(
            reflected.value.next_information_needs, (V117_BOUNDED_RESIDUAL,)
        )
        self.assertEqual(len(caller.calls), 1)

    def _partial_selection(self, residual_need):
        return {
            "selections": [
                {
                    "signal_ref": "guidance_acceleration:v1",
                    "reason_code": "answer_need",
                    "selection_reason": "The card covers the disclosed outlook.",
                    "applicability_hypothesis": "Guidance disclosures apply.",
                    "expected_role": "primary",
                    "context_tags": ["general"],
                    "target_need_indices": [0],
                    "answer_scope": "partial",
                    "residual_need": residual_need,
                }
            ]
        }

    def test_unrepresentable_residual_cannot_remove_need_and_finalize(self) -> None:
        previous, selection, batch = self._v117_reflect_inputs()
        legacy = replace(
            selection,
            residual_need="What were the realized revenue results for Q1 2026?",
        )
        output = self._adopting_output("placeholder")
        output["next_information_needs"] = []
        output["decision"] = "finalize"
        caller = ScriptedRoleCaller([output, output])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(datetime(2025, 9, 30, tzinfo=timezone.utc))
        controller.set_reflection_runtime_context(
            selections=(legacy,), must_finalize=False, termination_trigger=None,
        )

        with self.assertRaises(ValidationError) as context:
            controller.reflect(default_information_plan(), previous, batch)

        failure = str(context.exception)
        self.assertIn("cannot be represented within the prediction-time", failure)
        self.assertIn("Q1 2026", failure)
        self.assertEqual(len(caller.calls), 0)

    def test_unrepresentable_residual_cannot_hide_removal_behind_continue(self) -> None:
        previous, selection, batch = self._v117_reflect_inputs()
        legacy = replace(
            selection,
            residual_need="What were the realized revenue results for Q1 2026?",
        )
        output = self._adopting_output(
            "What competitive threats were disclosed by 2025-09-30?"
        )
        caller = ScriptedRoleCaller([output, output])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(datetime(2025, 9, 30, tzinfo=timezone.utc))
        controller.set_reflection_runtime_context(
            selections=(legacy,), must_finalize=False, termination_trigger=None,
        )

        with self.assertRaises(ValidationError):
            controller.reflect(default_information_plan(), previous, batch)
        self.assertEqual(len(caller.calls), 0)

    def test_contract_builder_fails_closed_for_unrepresentable_residual(self) -> None:
        previous, selection, batch = self._v117_reflect_inputs()
        legacy = replace(
            selection,
            residual_need="What were the realized revenue results for Q1 2026?",
        )
        context = {"prediction_time": "2025-09-30T00:00:00+00:00"}

        with self.assertRaises(ValidationError) as raised:
            _reflection_need_transition_contract(
                previous, (legacy,), batch, evaluation_context=context,
            )

        self.assertIn(
            "will not delete the unresolved demand", str(raised.exception)
        )

    def test_unrepresentable_residual_requires_exact_restoration_not_deletion(self) -> None:
        previous, selection, _batch = self._v117_reflect_inputs()
        legacy = replace(
            selection,
            residual_need="What were the realized revenue results for Q1 2026?",
        )
        context = {"prediction_time": "2025-09-30T00:00:00+00:00"}
        adopted = {legacy.signal_ref}
        removed = ResearchState(
            hypotheses=previous.hypotheses,
            next_information_needs=(
                "What competitive threats were disclosed by 2025-09-30?",
            ),
        )

        self.assertEqual(
            _targeted_answer_need_transition_errors(
                previous, removed, (legacy,), adopted, adopted,
                evaluation_context=context,
            ),
            [
                {
                    "prior_state_path": "next_information_needs[0]",
                    "value": V117_PRIOR_NEED,
                    "signal_refs": [legacy.signal_ref],
                    "issue": (
                        "partial-answer residual is unrepresentable at the "
                        "prediction-time boundary and cannot authorize "
                        "removing the unresolved need"
                    ),
                    "required_action": "restore_exactly",
                    "required_need": V117_PRIOR_NEED,
                    "required_need_occurrences": 1,
                }
            ],
        )

        retained = ResearchState(
            hypotheses=previous.hypotheses,
            next_information_needs=(V117_PRIOR_NEED,),
        )
        self.assertEqual(
            _targeted_answer_need_transition_errors(
                previous, retained, (legacy,), adopted, adopted,
                evaluation_context=context,
            ),
            [],
        )

    def test_corrected_routing_selection_flows_into_next_routing_prompt(self) -> None:
        corrected_residual = (
            "What cost per ounce guidance had Kinross Gold disclosed by "
            "2025-09-30 for the remainder of 2025 and 2026?"
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            snapshot = registry.freeze()
            routing_caller = ScriptedRoleCaller(
                [self._partial_selection(V117_RAW_RESIDUAL),
                 self._partial_selection(corrected_residual)]
            )
            routed = LLMSignalRetrievalAgent(routing_caller).select(
                (V117_PRIOR_NEED,), snapshot, {},
            )
            self.assertEqual(routed.value[0].answer_scope, "partial")
            self.assertEqual(routed.value[0].residual_need, corrected_residual)

            previous, _selection, batch = self._v117_reflect_inputs()
            reflect_caller = ScriptedRoleCaller(
                [self._adopting_output(corrected_residual)]
            )
            controller = LLMResearchController(reflect_caller)
            controller.set_evaluation_context(
                datetime(2025, 9, 30, tzinfo=timezone.utc)
            )
            controller.set_reflection_runtime_context(
                selections=routed.value,
                must_finalize=False,
                termination_trigger=None,
            )
            reflected = controller.reflect(
                default_information_plan(), previous, batch,
            )
            self.assertEqual(
                reflected.value.next_information_needs, (corrected_residual,)
            )
            contract = reflect_caller.calls[0]["payload"][
                "need_transition_contract"
            ]
            action = contract["need_rules"][0]["available_answer_actions"][0]
            self.assertEqual(action["residual_need"], corrected_residual)
            self.assertIn(
                "replace_with_exact_residual_need",
                contract["need_rules"][0]["required_transition"],
            )

            next_caller = ScriptedRoleCaller([{"selections": []}])
            LLMSignalRetrievalAgent(next_caller).select(
                reflected.value.next_information_needs, snapshot, {},
            )
            self.assertEqual(len(next_caller.calls), 1)
            self.assertEqual(
                next_caller.calls[0]["payload"]["information_needs"],
                [corrected_residual],
            )


class ReflectionRoleAdapterTests(TestCase):
    def test_v72_reflect_preserves_legacy_over_limit_state_without_growth(self) -> None:
        legacy_beliefs = tuple(
            f"Legacy belief {chr(65 + index)}: " + "material issuer context " * 15
            for index in range(9)
        )
        self.assertTrue(all(len(item) > 300 for item in legacy_beliefs))
        previous = ResearchState(
            hypotheses=("One catalyst may support repricing.",),
            current_beliefs=legacy_beliefs,
            next_information_needs=("Check whether the catalyst remains feasible.",),
        )
        finalized = replace(previous, decision=ResearchDecision.FINALIZE)
        caller = ScriptedRoleCaller([finalized.to_dict()])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(),
            must_finalize=True,
            termination_trigger=RuntimeStopReason.MAX_SIGNAL_ROUNDS,
        )
        unavailable = SignalResult(
            signal_id="legacy_coverage",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.0,
            interpretation="No current evidence is available.",
            coverage=SignalCoverage.UNAVAILABLE,
        )

        reflected = controller.reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(unavailable,), signal_calls=1),
        )

        self.assertEqual(len(caller.calls), 0)
        self.assertEqual(reflected.value, finalized)
        self.assertEqual(reflected.usage, AgentUsage())

    def test_v64_initialize_aggregates_all_decidable_numeric_repairs(self) -> None:
        cash_claim = "Kinross Gold has $1.1 billion in cash and $2.8 billion in liquidity."
        market_claim = (
            "Kinross Gold's adjusted share price rose from $16.21 on 2025-08-01 "
            "to $24.37 on 2025-09-29."
        )
        free_cash_flow_claim = (
            "Kinross Gold delivered almost $650 million in Q2 2025 and over "
            "$1 billion in the first half of 2025."
        )
        net_cash_claim = (
            "Kinross Gold expects net cash in Q3 2025 and plans to repay its "
            "$500 million 2027 notes."
        )
        projections = {
            "projection_cash": (
                "Kinross Gold has $1.1 billion in cash and $2.8 billion in liquidity"
            ),
            "projection_market_start": (
                '{"adjusted_close":16.21,"as_of_date":"2025-08-01"}'
            ),
            "projection_market_end": (
                '{"adjusted_close":24.37,"as_of_date":"2025-09-29"}'
            ),
            "projection_free_cash_flow": (
                "delivered almost $650 million in the second quarter and over "
                "$1 billion in the first half"
            ),
            "projection_net_cash": (
                "expect net cash in Q3 and plan to repay our $500 million 2027 notes"
            ),
        }
        invalid = {
            "hypotheses": ["Cash generation may support further repricing."],
            "current_beliefs": [
                "Kinross Gold holds $1.1 billion cash and $2.8 billion liquidity.",
                "Adjusted price increased from $16.21 on 2025-08-01 to $24.37 on 2025-09-29.",
                free_cash_flow_claim,
                net_cash_claim,
            ],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": cash_claim,
                    "projection_id": "projection_cash",
                    "exact_text": projections["projection_cash"],
                },
                {
                    "kind": "basic_info",
                    "claim": market_claim,
                    "projection_id": "projection_market_start",
                    "exact_text": projections["projection_market_start"],
                },
                {
                    "kind": "basic_info",
                    "claim": market_claim,
                    "projection_id": "projection_market_end",
                    "exact_text": projections["projection_market_end"],
                },
                {
                    "kind": "basic_info",
                    "claim": free_cash_flow_claim,
                    "projection_id": "projection_free_cash_flow",
                    "exact_text": projections["projection_free_cash_flow"],
                },
                {
                    "kind": "basic_info",
                    "claim": net_cash_claim,
                    "projection_id": "projection_net_cash",
                    "exact_text": projections["projection_net_cash"],
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["Check the durability of cash generation."],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected_free_cash_flow_claim = (
            "Kinross Gold delivered almost $650 million in Q2 and over $1 billion "
            "in the first half."
        )
        corrected_net_cash_claim = (
            "Kinross Gold expects net cash in Q3 and plans to repay its "
            "$500 million 2027 notes."
        )
        corrected["current_beliefs"] = [
            cash_claim,
            market_claim,
            corrected_free_cash_flow_claim,
            corrected_net_cash_claim,
        ]
        corrected["supporting_evidence"][3]["claim"] = (
            corrected_free_cash_flow_claim
        )
        corrected["supporting_evidence"][4]["claim"] = corrected_net_cash_claim
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": projection_id,
                                "exact_text": exact_text,
                            }
                            for projection_id, exact_text in projections.items()
                        ]
                    }
                ]
            },
        )

        # Numeric-assertion aggregation now resolves deterministically
        # before any LLM correction: the promoted fallback copies the exact
        # claim candidates (or removes unsupported rows) on the first
        # answer, so no correction round is spent.
        self.assertEqual(len(caller.calls), 1)
        self.assertIn(
            "Every next_information_needs item must contain only facts absent",
            caller.calls[0]["system_prompt"],
        )
        # The fallback may remove every unsupported numeric belief row;
        # whatever remains must be an exact supported claim copy.
        beliefs = initialized.value.current_beliefs
        supported = {cash_claim, market_claim}
        self.assertTrue(
            all(belief in supported for belief in beliefs),
            beliefs,
        )

    def test_v83_initialize_names_every_invalid_same_claim_evidence_path(
        self,
    ) -> None:
        invalid_market_claim = (
            "The adjusted close rose from 19.38 on 2025-08-18 to 24.37 on "
            "2025-09-29, a 25.7% increase."
        )
        corrected_market_claim = (
            "The adjusted close rose from 19.38 on 2025-08-18 to 24.37 on "
            "2025-09-29."
        )
        valid_news_claim = "UBS raised its price target to $27 from $20."
        projections = {
            "projection_start": (
                '{"adjusted_close":19.38,"as_of_date":"2025-08-18"}'
            ),
            "projection_end": (
                '{"adjusted_close":24.37,"as_of_date":"2025-09-29"}'
            ),
            "projection_news": "UBS raised its price target to $27 from $20.",
        }
        invalid = {
            "hypotheses": ["Recent momentum may support further repricing."],
            "current_beliefs": [
                invalid_market_claim + " This indicates strong momentum."
            ],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": invalid_market_claim,
                    "projection_id": "projection_start",
                    "exact_text": projections["projection_start"],
                },
                {
                    "kind": "basic_info",
                    "claim": invalid_market_claim,
                    "projection_id": "projection_end",
                    "exact_text": projections["projection_end"],
                },
                {
                    "kind": "basic_info",
                    "claim": valid_news_claim,
                    "projection_id": "projection_news",
                    "exact_text": projections["projection_news"],
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [
                "Check whether operating evidence confirms the momentum."
            ],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["current_beliefs"] = [corrected_market_claim]
        corrected["supporting_evidence"][0]["claim"] = corrected_market_claim
        corrected["supporting_evidence"][1]["claim"] = corrected_market_claim
        caller = ScriptedRoleCaller([invalid, corrected])

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": projection_id,
                                "exact_text": exact_text,
                            }
                            for projection_id, exact_text in projections.items()
                        ]
                    }
                ]
            },
        )

        # Numeric-assertion obligations now resolve through the promoted
        # deterministic fallback on the first answer: the unsupported
        # market belief is replaced by the exact claim copy (or removed)
        # without an LLM correction round, and both evidence claims that
        # carried the unsupported literal are normalized consistently.
        self.assertEqual(len(caller.calls), 1)
        beliefs = initialized.value.current_beliefs
        claims = {
            item.claim for item in initialized.value.supporting_evidence
        }
        self.assertTrue(
            all(belief in claims for belief in beliefs), beliefs
        )

    def test_basic_info_projection_removes_html_and_repetitive_market_metadata(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        filing = RawInfoDocument.create(
            document_id="filing-html",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="<html><body><h1>Item 1</h1><p>Useful business text.</p></body></html>",
        )
        market = RawInfoDocument.create(
            document_id="market-json",
            company_id="issuer-1",
            source_type="market_data",
            published_at=as_of,
            available_at=as_of,
            content=json.dumps(
                [
                    {
                        "adjusted_close": 12.5 + offset,
                        "as_of_date": (as_of.date() - timedelta(days=offset)).isoformat(),
                        "close": 12.5 + offset,
                        "retrieved_at": "2026-08-16T08:41:17.052061+00:00",
                        "source": "fixture",
                        "symbol": "AAA",
                        "volume": 1_000 + offset,
                    }
                    for offset in range(45, -1, -1)
                ],
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        quarterly = RawInfoDocument.create(
            document_id="quarterly-long-tag",
            company_id="issuer-1",
            source_type="10-q",
            published_at=as_of,
            available_at=as_of,
            content=(
                '<html><body><table><td style="'
                + ("color:#000000;" * 180)
                + '">Cash flow debt liquidity improved to 2,165,476.</td>'
                "<td><xbrli:unit id=\"usd\">Readable filing evidence.</xbrli:unit>"
                "</td></table></body></html>"
            ),
        )
        resolver = EvidenceResolver(
            RawInfoStore(documents=(filing, market, quarterly))
        )
        bundle = resolver.resolve_basic_info(
            (
                RawInfoRequest("filing", "business", ("filing",), max_documents=1),
                RawInfoRequest(
                    "market",
                    "market",
                    ("market_data",),
                    lookback_days=45,
                    max_documents=1,
                ),
                RawInfoRequest(
                    "quarterly",
                    "cash flow debt liquidity",
                    ("10-q",),
                    query="cash flow debt liquidity",
                    max_documents=1,
                ),
            ),
            company_id="issuer-1",
            identity={},
            as_of=as_of,
        )

        model_view, audit = project_basic_info_bundle(bundle)
        rendered = json.dumps(model_view)
        self.assertNotIn("<html", rendered)
        self.assertNotIn("<body", rendered)
        self.assertNotIn("retrieved_at", rendered)
        self.assertNotIn('"symbol"', rendered)
        self.assertNotIn('"source"', rendered)
        self.assertNotIn("08:41:17.052061", rendered)
        self.assertNotIn("style=", rendered)
        self.assertNotIn("<xbrli", rendered)
        self.assertIn("Cash flow debt liquidity improved", rendered)
        self.assertTrue(audit["entries"])
        self.assertTrue(all(item["raw_offset_runs"] for item in audit["entries"]))
        self.assertLessEqual(
            sum(
                len(span["exact_text"])
                for request in model_view["requests"]
                for span in request["projections"]
            ),
            32_000,
        )

    def test_v79_basic_projection_preserves_each_resolved_request_boundary(
        self,
    ) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        documents = tuple(
            RawInfoDocument.create(
                document_id=f"document-{index}",
                company_id="issuer-1",
                source_type=f"source_{index}",
                published_at=as_of,
                available_at=as_of,
                content=f"request-{index} " + (f"evidence-{index} " * 2_000),
            )
            for index in range(4)
        )
        bundle = EvidenceResolver(
            RawInfoStore(documents=documents)
        ).resolve_basic_info(
            tuple(
                RawInfoRequest(
                    f"request_{index}",
                    f"Read source {index}.",
                    (f"source_{index}",),
                    max_documents=1,
                )
                for index in range(4)
            ),
            company_id="issuer-1",
            identity={},
            as_of=as_of,
        )

        model_view, _audit = project_basic_info_bundle(bundle)

        self.assertTrue(
            all(request["projections"] for request in model_view["requests"])
        )
        self.assertTrue(
            all(
                request["visible_projection_count"] >= 1
                and request["available_projection_count"]
                >= request["visible_projection_count"]
                and request["omitted_projection_count"]
                == request["available_projection_count"]
                - request["visible_projection_count"]
                for request in model_view["requests"]
            )
        )
        self.assertTrue(
            any(
                request["projection_status"] == "partial_context_budget"
                for request in model_view["requests"]
            )
        )
        self.assertLessEqual(
            sum(
                len(projection["exact_text"])
                for request in model_view["requests"]
                for projection in request["projections"]
            ),
            32_000,
        )

    def test_v11_markup_fragments_are_removed_from_model_projection(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v11_basic_markup_and_claim_support.json"
            ).read_text(encoding="utf-8")
        )

        for fragment in fixture["markup_fragments"]:
            normalized, _runs = _normalized_projection_text(fragment)
            self.assertNotIn("style=", normalized)
            self.assertNotIn("scale=", normalized)
            self.assertNotIn("<", normalized)
            self.assertNotIn(">", normalized)
        entity_text, _runs = _normalized_projection_text(fixture["entity_text"])
        self.assertEqual(entity_text, "Cash Company’s liquidity")

    def test_v11_basic_claim_requires_all_quantities_across_literal_refs(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v11_basic_markup_and_claim_support.json"
            ).read_text(encoding="utf-8")
        )
        cash = fixture["unsupported_cash_claim"]
        ending_text = "Balance, end of period 2,165,476 &#160;"
        invalid = {
            "hypotheses": ["liquidity may be tightening"],
            "current_beliefs": [],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": cash["claim"],
                    "projection_id": "projection_beginning",
                    "exact_text": cash["exact_text"],
                }
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["confirm ending liquidity"],
            "decision": "continue",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["supporting_evidence"].append(
            {
                "kind": "basic_info",
                "claim": cash["claim"],
                "projection_id": "projection_ending",
                "exact_text": ending_text,
            }
        )
        caller = ScriptedRoleCaller([invalid, corrected])
        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": "projection_beginning",
                            "exact_text": cash["exact_text"],
                        },
                        {
                            "projection_id": "projection_ending",
                            "exact_text": ending_text,
                        },
                    ]
                }
            ]
        }

        state = LLMResearchController(caller).initialize(
            default_information_plan(), basic_info
        )

        error = claim_error(invalid, basic_info=basic_info)
        self.assertIn("numeric quantities", str(error))
        self.assertIn("2165476", str(error))
        self.assertEqual(state.value.supporting_evidence, ())
        self.assertEqual(len(caller.calls), 1)
        valid_state = LLMResearchController(ScriptedRoleCaller([corrected])).initialize(
            default_information_plan(), basic_info)
        self.assertEqual(len(valid_state.value.supporting_evidence), 2)

        market = fixture["multi_span_market_claim"]
        market_output = json.loads(json.dumps(corrected))
        market_output["supporting_evidence"] = [
            {
                "kind": "basic_info",
                "claim": market["claim"],
                "projection_id": f"projection_market_{index}",
                "exact_text": exact_text,
            }
            for index, exact_text in enumerate(market["exact_texts"])
        ]
        market_caller = ScriptedRoleCaller([market_output])
        market_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": f"projection_market_{index}",
                            "exact_text": exact_text,
                        }
                        for index, exact_text in enumerate(market["exact_texts"])
                    ]
                }
            ]
        }
        market_state = LLMResearchController(market_caller).initialize(
            default_information_plan(), market_info
        )
        self.assertEqual(len(market_state.value.supporting_evidence), 2)

    def test_v14_basic_claim_accepts_exact_explicit_unit_scaling(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v14_scaled_financial_claim.json"
            ).read_text(encoding="utf-8")
        )

        def output(claim: str) -> dict[str, Any]:
            return {
                "hypotheses": ["Cash generation may be improving."],
                "current_beliefs": [claim],
                "supporting_evidence": [
                    {
                        "kind": "basic_info",
                        "claim": claim,
                        "projection_id": f"projection_financial_{index}",
                        "exact_text": exact_text,
                    }
                    for index, exact_text in enumerate(fixture["exact_texts"])
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["Confirm cash-flow durability."],
                "decision": "continue",
            }

        basic_info = {
            "requests": [
                {
                    "projections": [
                        {
                            "projection_id": f"projection_financial_{index}",
                            "exact_text": exact_text,
                        }
                        for index, exact_text in enumerate(fixture["exact_texts"])
                    ]
                }
            ]
        }
        valid_caller = ScriptedRoleCaller([output(fixture["claim"])])

        state = LLMResearchController(valid_caller).initialize(
            default_information_plan(), basic_info
        )

        self.assertEqual(len(state.value.supporting_evidence), 2)
        self.assertEqual(valid_caller.stages, ["research_controller_initialize"])

        invalid = output(fixture["unsupported_claim"])
        invalid_caller = ScriptedRoleCaller([invalid, invalid])
        self.assertIn("1605400000", str(claim_error(invalid, basic_info=basic_info)))
        quarantined = LLMResearchController(invalid_caller).initialize(default_information_plan(), basic_info)
        self.assertEqual(quarantined.value.supporting_evidence, ())
        self.assertEqual(quarantined.value.current_beliefs, ())
        self.assertEqual(len(invalid_caller.calls), 1)

    def test_v12_reflect_rejects_signal_claim_quantities_absent_from_evidence(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v12_reflect_signal_claim_support.json"
            ).read_text(encoding="utf-8")
        )
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        results = tuple(
            SignalResult(
                signal_id=item["signal_id"],
                version=item["version"],
                value=SignalValue(item["value"]),
                confidence=item["confidence"],
                interpretation=item["interpretation"],
                supporting_evidence=(
                    SignalEvidence(
                        document_id=f"{item['signal_id']}-document",
                        exact_span=item["supporting_exact_span"],
                        timestamp=timestamp,
                    ),
                ),
            )
            for item in fixture["signal_results"]
        )
        corrected_reflection = json.loads(
            json.dumps(fixture["corrected_reflection"])
        )
        invalid_reflection = json.loads(json.dumps(fixture["invalid_reflection"]))
        invalid_reflection["next_information_needs"] = [
            "Check the remaining mine-disruption risk."
        ]
        corrected_reflection["next_information_needs"] = invalid_reflection["next_information_needs"]
        caller = ScriptedRoleCaller(
            [invalid_reflection, corrected_reflection]
        )

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            ResearchState(next_information_needs=("Confirm the production outlook.",)),
            SignalBatchResult(results=results, signal_calls=2),
        )

        error = str(claim_error(invalid_reflection,
            previous_state=ResearchState(next_information_needs=("Confirm the production outlook.",)),
            batch=SignalBatchResult(results=results, signal_calls=2)))
        self.assertIn("referenced Signal evidence", error)
        self.assertIn("513000", error)
        self.assertIn("2200", error)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(reflected.value.supporting_evidence, ())
        valid = LLMResearchController(ScriptedRoleCaller([corrected_reflection])).reflect(
            default_information_plan(),
            ResearchState(next_information_needs=("Confirm the production outlook.",)),
            SignalBatchResult(results=results, signal_calls=2))
        self.assertEqual(len(valid.value.supporting_evidence), 2)
        self.assertIn(
            "Every numeric quantity in a new Signal claim",
            caller.calls[0]["system_prompt"],
        )

    def test_v20_reflect_compacts_signal_evidence_and_preserves_exact_need(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v20_reflect_adaptive_progress.json"
            ).read_text(encoding="utf-8")
        )
        canonical_span = fixture["canonical_evidence_prefix"] + (" detail" * 500)
        result = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=0.8,
            interpretation="Guidance was reaffirmed without an upward revision.",
            supporting_evidence=(
                SignalEvidence(
                    document_id="canonical-raw-document",
                    exact_span=canonical_span,
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        previous = ResearchState(
            hypotheses=("Guidance acceleration may support the thesis.",),
            open_questions=("Did management change guidance?",),
            next_information_needs=(fixture["previous_need"],),
        )
        caller = ScriptedRoleCaller([fixture["invalid_reflection"]])

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        self.assertEqual(
            reflected.value.next_information_needs,
            (fixture["previous_need"],),
        )
        self.assertEqual(caller.stages, ["research_controller_reflect"])
        model_evidence = caller.calls[0]["payload"]["signal_batch"][0][
            "evidence"
        ]["supporting"][0]
        self.assertEqual(model_evidence["evidence_index"], 0)
        self.assertLessEqual(
            len(model_evidence["model_evidence_text"]),
            evolution_runtime_module.MAX_REFLECT_SIGNAL_EVIDENCE_CHARS,
        )
        for omitted in (
            "document_id",
            "exact_span",
            "retrieved_at",
            '"source"',
            '"symbol"',
            "<p>",
        ):
            self.assertNotIn(omitted, json.dumps(model_evidence))
        self.assertEqual(result.supporting_evidence[0].exact_span, canonical_span)

        cosmetic = json.loads(json.dumps(fixture["invalid_reflection"]))
        cosmetic["next_information_needs"] = [
            fixture["previous_need"] + " given the available evidence"
        ]
        cosmetic_repair = json.loads(json.dumps(cosmetic))
        cosmetic_repair["next_information_needs"] = [fixture["narrowed_need"]]
        cosmetic_caller = ScriptedRoleCaller(
            [cosmetic, cosmetic_repair]
        )
        corrected = LLMResearchController(cosmetic_caller).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )
        self.assertEqual(
            corrected.value.next_information_needs,
            (fixture["narrowed_need"],),
        )
        error = validation_error(cosmetic_caller.calls[1])
        self.assertIn("cosmetically changed", error)
        self.assertIn("Keep an unanswered need byte-for-byte", error)

        deterministic = SignalResult(
            signal_id="max_drawdown_1y",
            version=1,
            value=SignalValue.POSITIVE,
            confidence=1.0,
            interpretation="max_drawdown_1y=-0.16",
            supporting_evidence=(
                SignalEvidence(
                    document_id="canonical-market-document",
                    exact_span=(
                        '[{"adjusted_close":9.36,"retrieved_at":"later",'
                        '"source":"massive","symbol":"KGC"}]'
                    ),
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        deterministic_view = evolution_runtime_module._signal_batch_model_view(
            SignalBatchResult(results=(deterministic,), signal_calls=1)
        )[0]
        self.assertEqual(
            deterministic_view["evidence"]["supporting"][0],
            {
                "evidence_index": 0,
                "available_at": "2025-07-31T00:00:00+00:00",
            },
        )
        self.assertEqual(
            deterministic_view["exact_claim_if_adopted"],
            "max_drawdown_1y=-0.16",
        )
        self.assertNotIn("interpretation", deterministic_view)

        no_adoption = fixture["invalid_reflection"] | {"supporting_evidence": []}
        unchanged = LLMResearchController(ScriptedRoleCaller([no_adoption])).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )
        self.assertEqual(
            unchanged.value.next_information_needs,
            previous.next_information_needs,
        )

    def test_v21_reflect_rejects_cosmetic_progress_and_hides_unavailable_claim(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v21_unavailable_cosmetic_reflect.json"
            ).read_text(encoding="utf-8")
        )
        unavailable = SignalResult(
            signal_id="customer_concentration",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.5,
            interpretation=fixture["unsafe_unavailable_interpretation"],
            coverage=SignalCoverage.UNAVAILABLE,
        )
        available = SignalResult(
            signal_id="negative_word_count",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=1.0,
            interpretation="negative_word_count=0",
            supporting_evidence=(
                SignalEvidence(
                    document_id="news-document",
                    exact_span="No configured negative terms occurred.",
                    timestamp=datetime(2025, 9, 24, tzinfo=timezone.utc),
                ),
            ),
        )
        caller = ScriptedRoleCaller(
            [fixture["unchanged_output"], fixture["cosmetic_correction"]]
        )

        with self.assertRaisesRegex(
            CandidateExecutionRejected,
            "outside typed authority",
        ):
            LLMResearchController(caller).reflect(
                default_information_plan(),
                ResearchState(
                    open_questions=("Is customer concentration known?",),
                    next_information_needs=(fixture["previous_need"],),
                ),
                SignalBatchResult(
                    results=(unavailable, available), signal_calls=2
                ),
            )

        unavailable_view = caller.calls[0]["payload"]["signal_batch"][0]
        summary = unavailable_view["interpretation"]["summary"]
        self.assertNotIn(fixture["unsafe_unavailable_interpretation"], summary)
        self.assertIn("not evidence", summary)
        self.assertEqual(
            unavailable_view["evidence"], {"supporting": [], "counter": []}
        )
        self.assertIn("not evidence of absence", caller.calls[0]["system_prompt"])
        self.assertIn(
            "treated an unavailable Signal as a finding",
            validation_error(caller.calls[1]),
        )

        compact_posthoc = evolution_runtime_module._compact_posthoc_context(
            {
                "basic_info": {},
                "final_research_state": {},
                "signal_rounds": [
                    {"batch": {"results": [unavailable.to_dict()]}}
                ],
            }
        )
        posthoc_summary = compact_posthoc["signal_results"][0]["interpretation"][
            "summary"
        ]
        self.assertIn("not evidence", posthoc_summary)

    def test_v22_reflect_aggregates_quantity_and_stale_resolved_need(self) -> None:
        result = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=0.8,
            interpretation="Guidance was reaffirmed without an upward revision.",
            supporting_evidence=(
                SignalEvidence(
                    document_id="guidance-document",
                    exact_span="Production and cost guidance was reaffirmed.",
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        prior_need = "What is the production and cost guidance outlook?"
        previous = ResearchState(next_information_needs=(prior_need,))
        invalid = {
            "contradictions": [],
            "current_beliefs": ["Management reaffirmed guidance."],
            "decision": "continue",
            "hypotheses": ["Execution now determines the thesis."],
            "next_information_needs": [prior_need],
            "open_questions": [],
            "resolved_questions": [
                "Management resolved the production and cost guidance outlook."
            ],
            "supporting_evidence": [
                {
                    "claim": "Management reaffirmed 2025 production and cost guidance.",
                    "evidence_group": "supporting",
                    "evidence_index": 0,
                    "kind": "signal",
                    "signal_ref": "guidance_acceleration:v1",
                }
            ],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["resolved_questions"] = []
        corrected["supporting_evidence"][0]["claim"] = (
            "Production and cost guidance was reaffirmed."
        )
        caller = ScriptedRoleCaller([invalid, corrected])

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(reflected.value.resolved_questions, ())
        self.assertEqual(reflected.value.supporting_evidence, ())
        self.assertEqual(
            reflected.value.next_information_needs,
            (prior_need,),
        )

    def test_v23_answer_need_evidence_requires_real_need_progress(self) -> None:
        result = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=0.8,
            interpretation="Guidance was reaffirmed without an upward revision.",
            supporting_evidence=(
                SignalEvidence(
                    document_id="guidance-document",
                    exact_span="Production and cost guidance was reaffirmed.",
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        prior_need = "What is the current production guidance and cost outlook?"
        other_need = "What operating disruption could prevent delivery?"
        previous = ResearchState(
            next_information_needs=(prior_need, other_need),
        )
        evidence_ref = {
            "claim": "Production and cost guidance was reaffirmed.",
            "evidence_group": "supporting",
            "evidence_index": 0,
            "kind": "signal",
            "signal_ref": "guidance_acceleration:v1",
        }
        unchanged = {
            "contradictions": [],
            "current_beliefs": ["Production and cost guidance was reaffirmed."],
            "decision": "continue",
            "hypotheses": ["Execution now determines the thesis."],
            "next_information_needs": [prior_need, other_need],
            "open_questions": [],
            "resolved_questions": [],
            "supporting_evidence": [evidence_ref],
        }
        corrected = json.loads(json.dumps(unchanged))
        corrected["next_information_needs"] = [other_need]
        caller = ScriptedRoleCaller([unchanged, corrected])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(
                SignalSelectionDecision(
                    signal_ref="guidance_acceleration:v1",
                    reason_code="answer_need",
                    selection_reason=(
                        "Directly answer the production-guidance and cost-outlook need."
                    ),
                    applicability_hypothesis="Current guidance is visible.",
                    expected_role="primary",
                    context_tags=("mature_operations",),
                ),
            ),
            must_finalize=False,
            termination_trigger=None,
        )

        reflected = controller.reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        error = validation_error(caller.calls[1])
        self.assertIn("reason_code='answer_need'", error)
        self.assertIn("exact same set", error)
        self.assertIn("invalid_field='next_information_needs'", error)
        self.assertIn("next_information_needs[0]", error)
        self.assertIn(prior_need, error)
        self.assertIn("next_information_needs[1]", error)
        self.assertEqual(reflected.value.next_information_needs, (other_need,))
        self.assertEqual(
            caller.calls[0]["payload"]["executed_selection_intents"][0][
                "selection_reason"
            ],
            "Directly answer the production-guidance and cost-outlook need.",
        )

    def test_v70_reflect_changes_targeted_need_not_an_unrelated_need(self) -> None:
        result = SignalResult(
            signal_id="cash_reserves",
            version=1,
            value=SignalValue.POSITIVE,
            confidence=1.0,
            interpretation="cash_reserves=2.07009e+09",
            supporting_evidence=(
                SignalEvidence(
                    document_id="cash-document",
                    exact_span="cash_reserves=2.07009e+09",
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        unrelated_need = (
            "What were Q2 revenue and earnings per share versus analyst expectations?"
        )
        targeted_need = (
            "What is the current debt level and liquidity position, and are there "
            "upcoming debt maturities or refinancing plans?"
        )
        narrowed_need = (
            "What is the current debt level, and are there upcoming debt maturities "
            "or refinancing plans?"
        )
        previous = ResearchState(
            next_information_needs=(unrelated_need, targeted_need),
        )
        evidence_ref = {
            "claim": "cash_reserves=2.07009e+09",
            "evidence_group": "supporting",
            "evidence_index": 0,
            "kind": "signal",
            "signal_ref": "cash_reserves:v1",
        }
        for decision, must_finalize in (("continue", False), ("finalize", True)):
            with self.subTest(decision=decision):
                invalid = {
                    "contradictions": [],
                    "current_beliefs": ["cash_reserves=2.07009e+09"],
                    "decision": decision,
                    "hypotheses": ["Liquidity may support execution."],
                    "next_information_needs": [targeted_need],
                    "open_questions": [],
                    "resolved_questions": [],
                    "supporting_evidence": [evidence_ref],
                }
                from tests.test_evolution_state_patch import PatchCaller, patch
                from stock_opportunity_agent.research.evolution_state_patch import recorded_response_patch

                def initial(request):
                    return recorded_response_patch(request["payload"]["research_state"], invalid)

                def correction(request):
                    return patch(request["payload"]["output_patch_contract"],
                        {"op": "replace", "path": "next_information_needs[0]", "value": narrowed_need},
                        {"op": "append", "path": "next_information_needs", "value": unrelated_need},
                    )

                caller = PatchCaller(initial, correction)
                controller = LLMResearchController(caller)
                controller.set_reflection_runtime_context(
                    selections=(
                        SignalSelectionDecision(
                            signal_ref="cash_reserves:v1",
                            reason_code="answer_need",
                            selection_reason="Answer the liquidity facet only.",
                            applicability_hypothesis=(
                                "A current cash balance is visible."
                            ),
                            expected_role="primary",
                            target_need_indices=(1,),
                        ),
                    ),
                    must_finalize=must_finalize,
                    termination_trigger=None,
                )

                reflected = controller.reflect(
                    default_information_plan(),
                    previous,
                    SignalBatchResult(results=(result,), signal_calls=1),
                )

                self.assertEqual(len(caller.calls), 1)
                self.assertEqual(reflected.value.next_information_needs, (unrelated_need,))
                selection_intent = caller.calls[0]["payload"][
                    "executed_selection_intents"
                ][0]
                self.assertEqual(selection_intent["target_need_indices"], [1])
                self.assertEqual(
                    set(selection_intent),
                    {
                        "signal_ref",
                        "reason_code",
                        "selection_reason",
                        "target_need_indices",
                    },
                )
                need_rules = caller.calls[0]["payload"][
                    "need_transition_contract"
                ]["need_rules"]
                self.assertEqual(need_rules[0]["required_transition"], "preserve_exactly")
                self.assertEqual(
                    need_rules[1]["available_answer_signal_refs"],
                    ["cash_reserves:v1"],
                )
                self.assertIn(
                    "remove_or_genuinely_narrow",
                    need_rules[1]["required_transition"],
                )
                self.assertIn(
                    "need_transition_contract as the sole need-ownership map",
                    caller.calls[0]["system_prompt"],
                )

    def test_v97_need_transition_restores_target_when_answer_not_adopted(
        self,
    ) -> None:
        original_need = (
            "What are the latest revenue trends and management guidance?"
        )
        residual_need = "What are the latest revenue trends?"
        errors = evolution_runtime_module._targeted_answer_need_transition_errors(
            ResearchState(next_information_needs=(original_need,)),
            ResearchState(next_information_needs=(residual_need,)),
            (
                SignalSelectionDecision(
                    signal_ref="guidance_acceleration:v1",
                    reason_code="answer_need",
                    selection_reason="Answer the guidance facet.",
                    applicability_hypothesis="Guidance may be visible.",
                    expected_role="primary",
                    target_need_indices=(0,),
                    answer_scope="partial",
                    residual_need=residual_need,
                ),
                SignalSelectionDecision(
                    signal_ref="revenue_growth_yoy:v1",
                    reason_code="combine_evidence",
                    selection_reason="Provide revenue context.",
                    applicability_hypothesis="Revenue facts are visible.",
                    expected_role="confirmation",
                    target_need_indices=(0,),
                ),
            ),
            {"revenue_growth_yoy:v1"},
            {"guidance_acceleration:v1", "revenue_growth_yoy:v1"},
        )

        self.assertEqual(
            errors,
            [
                {
                    "prior_state_path": "next_information_needs[0]",
                    "value": original_need,
                    "issue": "untargeted need changed or was removed",
                    "required_action": "restore_exactly",
                    "required_need": original_need,
                    "required_need_occurrences": 1,
                }
            ],
        )

    def test_v73_reflect_receives_result_aware_need_transition_contract(self) -> None:
        revenue = SignalResult(
            signal_id="revenue_growth_yoy",
            version=1,
            value=SignalValue.NEGATIVE,
            confidence=1.0,
            interpretation="revenue_growth_yoy=-0.0872356",
            supporting_evidence=(
                SignalEvidence(
                    document_id="revenue-document",
                    exact_span="revenue_growth_yoy=-0.0872356",
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        guidance = SignalResult(
            signal_id="guidance_acceleration",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.0,
            interpretation="No visible management guidance was found.",
            coverage=SignalCoverage.UNAVAILABLE,
        )
        cash = SignalResult(
            signal_id="cash_reserves",
            version=1,
            value=SignalValue.POSITIVE,
            confidence=1.0,
            interpretation="cash_reserves=2.07009e+09",
            supporting_evidence=(
                SignalEvidence(
                    document_id="cash-document",
                    exact_span='{"cash_and_equivalents":2070090000}',
                    timestamp=datetime(2025, 7, 31, tzinfo=timezone.utc),
                ),
            ),
        )
        financing = SignalResult(
            signal_id="financing_activity",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.0,
            interpretation="No visible financing event was found.",
            coverage=SignalCoverage.UNAVAILABLE,
        )
        revenue_need = "What is the current revenue growth trajectory and run-rate?"
        guidance_need = "What guidance or outlook has management provided?"
        liquidity_need = (
            "What is the current balance sheet, debt, liquidity, and financing position?"
        )
        narrowed_liquidity_need = (
            "What are the current debt obligations and upcoming maturities?"
        )
        previous = ResearchState(
            next_information_needs=(revenue_need, guidance_need, liquidity_need),
        )
        rounded_claim = "Wynn Resorts' cash reserves are approximately $2.07 billion."
        invalid = {
            "contradictions": [],
            "current_beliefs": [rounded_claim],
            "decision": "continue",
            "hypotheses": ["Liquidity may support continued execution."],
            "next_information_needs": [guidance_need, liquidity_need],
            "open_questions": [guidance_need],
            "resolved_questions": ["The current cash balance is now known."],
            "supporting_evidence": [
                {
                    "claim": rounded_claim,
                    "evidence_group": "supporting",
                    "evidence_index": 0,
                    "kind": "signal",
                    "signal_ref": "cash_reserves:v1",
                }
            ],
        }
        from tests.test_evolution_state_patch import PatchCaller, patch
        from stock_opportunity_agent.research.evolution_state_patch import recorded_response_patch

        def initial(request):
            return recorded_response_patch(request["payload"]["research_state"], invalid)

        def correct(request):
            return patch(request["payload"]["output_patch_contract"],
                {"op": "replace", "path": "current_beliefs[0]", "value": "cash_reserves=2.07009e+09"},
                {"op": "replace", "path": "supporting_evidence[0].claim", "value": "cash_reserves=2.07009e+09"},
            )

        caller = PatchCaller(initial, correct)
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(
                SignalSelectionDecision(
                    signal_ref="revenue_growth_yoy:v1",
                    reason_code="combine_evidence",
                    selection_reason="Provide context for the revenue trajectory.",
                    applicability_hypothesis="Revenue facts are visible.",
                    expected_role="confirmation",
                    target_need_indices=(0,),
                ),
                SignalSelectionDecision(
                    signal_ref="guidance_acceleration:v1",
                    reason_code="answer_need",
                    selection_reason="Answer the management-guidance need.",
                    applicability_hypothesis="Guidance may be visible.",
                    expected_role="primary",
                    target_need_indices=(1,),
                ),
                SignalSelectionDecision(
                    signal_ref="cash_reserves:v1",
                    reason_code="answer_need",
                    selection_reason="Answer the liquidity facet.",
                    applicability_hypothesis="A current cash balance is visible.",
                    expected_role="primary",
                    target_need_indices=(2,),
                ),
                SignalSelectionDecision(
                    signal_ref="financing_activity:v1",
                    reason_code="combine_evidence",
                    selection_reason="Provide financing context.",
                    applicability_hypothesis="Financing facts may be visible.",
                    expected_role="confirmation",
                    target_need_indices=(2,),
                ),
            ),
            must_finalize=False,
            termination_trigger=None,
        )

        reflected = controller.reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(
                results=(revenue, guidance, cash, financing),
                signal_calls=4,
            ),
        )

        payload = caller.calls[0]["payload"]
        cash_view = payload["signal_batch"][2]
        self.assertEqual(
            cash_view["exact_claim_if_adopted"],
            "cash_reserves=2.07009e+09",
        )
        self.assertNotIn("interpretation", cash_view)
        self.assertNotIn(
            "canonical_interpretation",
            cash_view["evidence"]["supporting"][0],
        )
        rules = payload["need_transition_contract"]["need_rules"]
        self.assertEqual(rules[0]["context_only_signal_refs"], ["revenue_growth_yoy:v1"])
        self.assertEqual(rules[0]["required_transition"], "preserve_exactly")
        self.assertEqual(
            rules[1]["unavailable_answer_signal_refs"],
            ["guidance_acceleration:v1"],
        )
        self.assertEqual(rules[1]["required_transition"], "preserve_exactly")
        self.assertEqual(rules[2]["available_answer_signal_refs"], ["cash_reserves:v1"])
        self.assertEqual(rules[2]["context_only_signal_refs"], ["financing_activity:v1"])
        self.assertEqual(
            payload["signal_evidence_ref_catalog"][1]["supporting_evidence_indices"],
            [],
        )
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(reflected.value.supporting_evidence, ())
        self.assertEqual(reflected.value.current_beliefs, ())
        self.assertEqual(reflected.value.open_questions, ())
        self.assertEqual(
            reflected.value.next_information_needs,
            (guidance_need, revenue_need, liquidity_need),
        )

    def test_v74_reflect_requires_exact_partial_answer_residual(self) -> None:
        result = SignalResult(
            signal_id="cash_reserves",
            version=1,
            value=SignalValue.POSITIVE,
            confidence=1.0,
            interpretation="cash_reserves=2.61739e+08",
            supporting_evidence=(
                SignalEvidence(
                    document_id="cash-document",
                    exact_span='{"cash_and_equivalents":261739000}',
                    timestamp=datetime(2025, 8, 7, tzinfo=timezone.utc),
                ),
            ),
        )
        target_need = (
            "What is the current cash position and what share-buyback or strategic "
            "funding plans remain?"
        )
        residual_need = "What share-buyback or strategic funding plans remain?"
        unrelated_need = "What competitive product launches are planned?"
        evidence_ref = {
            "claim": "cash_reserves=2.61739e+08",
            "evidence_group": "supporting",
            "evidence_index": 0,
            "kind": "signal",
            "signal_ref": "cash_reserves:v1",
        }
        invalid = {
            "contradictions": [],
            "current_beliefs": ["cash_reserves=2.61739e+08"],
            "decision": "continue",
            "hypotheses": ["Liquidity may support execution."],
            "next_information_needs": [unrelated_need],
            "open_questions": [],
            "resolved_questions": ["The current cash position is known."],
            "supporting_evidence": [evidence_ref],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["next_information_needs"] = [residual_need, unrelated_need]
        caller = ScriptedRoleCaller([invalid, corrected])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(
                SignalSelectionDecision(
                    signal_ref="cash_reserves:v1",
                    reason_code="answer_need",
                    selection_reason="Answer only the current cash-position facet.",
                    applicability_hypothesis="A current cash balance is visible.",
                    expected_role="primary",
                    target_need_indices=(0,),
                    answer_scope="partial",
                    residual_need=residual_need,
                ),
            ),
            must_finalize=False,
            termination_trigger=None,
        )

        reflected = controller.reflect(
            default_information_plan(),
            ResearchState(next_information_needs=(target_need, unrelated_need)),
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        action = caller.calls[0]["payload"]["need_transition_contract"][
            "need_rules"
        ][0]["available_answer_actions"][0]
        self.assertEqual(action["answer_scope"], "partial")
        self.assertEqual(action["residual_need"], residual_need)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(
            reflected.value.next_information_needs,
            (unrelated_need, residual_need),
        )

    def test_v23_terminal_reflection_requires_model_authored_finalize(self) -> None:
        result = SignalResult(
            signal_id="negative_word_count",
            version=1,
            value=SignalValue.NEUTRAL,
            confidence=1.0,
            interpretation="negative_word_count=0",
            supporting_evidence=(
                SignalEvidence(
                    document_id="news-document",
                    exact_span="No configured negative terms occurred.",
                    timestamp=datetime(2025, 9, 24, tzinfo=timezone.utc),
                ),
            ),
        )
        need = "What additional catalyst evidence is available?"
        continuing = {
            "contradictions": [],
            "current_beliefs": [],
            "decision": "continue",
            "hypotheses": ["A catalyst may still emerge."],
            "next_information_needs": [need],
            "open_questions": [],
            "resolved_questions": [],
            "supporting_evidence": [],
        }
        finalized = json.loads(json.dumps(continuing))
        finalized["decision"] = "finalize"
        caller = ScriptedRoleCaller([continuing, finalized])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(
                SignalSelectionDecision(
                    signal_ref="negative_word_count:v1",
                    reason_code="combine_evidence",
                    selection_reason="Add a bounded sentiment diagnostic.",
                    applicability_hypothesis="Current news is visible.",
                    expected_role="confirmation",
                    context_tags=("news_rich",),
                ),
            ),
            must_finalize=True,
            termination_trigger=RuntimeStopReason.BUDGET_EXHAUSTED,
        )

        reflected = controller.reflect(
            default_information_plan(),
            ResearchState(next_information_needs=(need,)),
            SignalBatchResult(results=(result,), signal_calls=1),
        )

        self.assertEqual(reflected.value.decision, ResearchDecision.FINALIZE)
        self.assertEqual(reflected.value.next_information_needs, (need,))
        self.assertIn("last executable evidence batch", validation_error(caller.calls[1]))
        self.assertEqual(
            caller.calls[0]["payload"]["reflection_runtime"],
            {
                "must_finalize": True,
                "termination_trigger": "budget_exhausted",
            },
        )

    def test_v63_unavailable_terminal_reflection_changes_only_decision(self) -> None:
        need = "What additional customer-order evidence is available?"
        previous = ResearchState(
            hypotheses=("Binding customer orders may support growth.",),
            open_questions=(need,),
            next_information_needs=(need,),
        )
        invalid = replace(
            previous,
            hypotheses=("Unavailable data weakens the order thesis.",),
            decision=ResearchDecision.FINALIZE,
        ).to_dict()
        corrected = replace(
            previous,
            decision=ResearchDecision.FINALIZE,
        ).to_dict()
        caller = ScriptedRoleCaller([invalid, corrected])
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(
                SignalSelectionDecision(
                    signal_ref="revenue_growth_yoy:v1",
                    reason_code="answer_need",
                    selection_reason="Try the available financial periods.",
                    applicability_hypothesis="Comparable periods may be available.",
                    expected_role="coverage",
                ),
            ),
            must_finalize=True,
            termination_trigger=RuntimeStopReason.BUDGET_EXHAUSTED,
        )
        unavailable = SignalResult(
            signal_id="revenue_growth_yoy",
            version=1,
            value=SignalValue.UNAVAILABLE,
            confidence=0.0,
            interpretation="Revenue periods are unavailable.",
            coverage=SignalCoverage.UNAVAILABLE,
        )

        reflected = controller.reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(unavailable,), signal_calls=1),
        )

        self.assertEqual(len(caller.calls), 0)
        self.assertEqual(reflected.usage, AgentUsage())
        self.assertEqual(
            reflected.value, replace(previous, decision=ResearchDecision.FINALIZE)
        )

    def test_v18_reflect_accepts_exact_deterministic_interpretation_not_rounding(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v18_deterministic_interpretation_claim.json"
            ).read_text()
        )
        timestamp = datetime(2025, 7, 31, tzinfo=timezone.utc)
        result = SignalResult(
            signal_id="revenue_growth_yoy",
            version=1,
            value=SignalValue.NEGATIVE,
            confidence=1.0,
            interpretation=fixture["interpretation"],
            supporting_evidence=(
                SignalEvidence(
                    document_id="wynn-facts",
                    exact_span=fixture["evidence_span"],
                    timestamp=timestamp,
                ),
            ),
        )

        def reflection(claim: str) -> dict[str, Any]:
            return {
                "hypotheses": ["Recent revenue may be weakening."],
                "current_beliefs": [claim],
                "supporting_evidence": [
                    {
                        "kind": "signal",
                        "claim": claim,
                        "signal_ref": "revenue_growth_yoy:v1",
                        "evidence_group": "supporting",
                        "evidence_index": 0,
                    }
                ],
                "contradictions": [],
                "resolved_questions": [],
                "open_questions": [],
                "next_information_needs": ["Check a current catalyst."],
                "decision": "continue",
            }

        exact_caller = ScriptedRoleCaller([reflection(fixture["exact_claim"])])
        reflected = LLMResearchController(exact_caller).reflect(
            default_information_plan(),
            ResearchState(next_information_needs=("Check revenue.",)),
            SignalBatchResult(results=(result,), signal_calls=1),
        )
        self.assertEqual(
            reflected.value.supporting_evidence[0].claim, fixture["exact_claim"]
        )
        self.assertIn("do not round it", exact_caller.calls[0]["system_prompt"])

        rounded_caller = ScriptedRoleCaller(
            [reflection(fixture["rounded_claim"]), reflection(fixture["rounded_claim"])]
        )
        self.assertIn("Do not round or convert", str(claim_error(reflection(fixture["rounded_claim"]),
            previous_state=ResearchState(next_information_needs=("Check revenue.",)),
            batch=SignalBatchResult(results=(result,), signal_calls=1))))
        quarantined = LLMResearchController(rounded_caller).reflect(
                default_information_plan(),
                ResearchState(next_information_needs=("Check revenue.",)),
                SignalBatchResult(results=(result,), signal_calls=1),
            )
        self.assertEqual(quarantined.value.supporting_evidence, ())
        self.assertEqual(quarantined.value.current_beliefs, ())
        self.assertEqual(len(rounded_caller.calls), 1)

    def test_v12_reflect_preserves_retained_signal_claim_without_old_batch(self) -> None:
        prior_claim = "Management reaffirmed rather than raised guidance."
        prior_ref = ResearchEvidenceRef(
            kind="signal",
            claim=prior_claim,
            signal_ref="guidance_acceleration:v1",
            evidence_group="supporting",
            evidence_index=0,
        )
        previous = ResearchState(
            hypotheses=("Guidance is not accelerating.",),
            supporting_evidence=(prior_ref,),
            next_information_needs=("Check a separate risk.",),
        )
        invalid = previous.to_dict()
        invalid["supporting_evidence"][0]["claim"] = (
            "Management raised guidance materially."
        )
        corrected = previous.to_dict()
        caller = ScriptedRoleCaller([invalid, corrected])

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            previous,
            SignalBatchResult(results=(), signal_calls=0),
        )

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(reflected.value.supporting_evidence[0].claim, prior_claim)

    def test_signal_internal_edges_ignore_surrounding_whitespace(self) -> None:
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        for whitespace in ("", " ", " \t\n"):
            for edge in ("start", "end"):
                with self.subTest(whitespace=whitespace, edge=edge):
                    fragment = "fragment at a truncated boundary"
                    text = (whitespace + fragment + ". Complete interior sentence. Tail."
                            if edge == "start" else
                            "Head. Complete interior sentence. " + fragment + whitespace)
                    document = RawInfoDocument.create(
                        document_id="edge-document", company_id="issuer-1", source_type="filing",
                        published_at=timestamp, available_at=timestamp,
                        content="prefix " + text + " suffix",
                    )
                    lineage = evolution_runtime_module._SignalProjectionLineage(
                        document=document, projection_text=text,
                        raw_offset_runs=((0, len(text), 7, 7 + len(text)),),
                        normalized_start=7, normalized_end=7 + len(text),
                        normalized_source_length=len(document.content),
                    )
                    result = {"evidence": {"supporting": [{
                        "projection_id": "edge", "exact_text": fragment,
                    }], "counter": []}}
                    with self.assertRaisesRegex(ValidationError, "edge=\\['" + edge + "'\\]"):
                        evolution_runtime_module._map_projected_signal_evidence(result, {"edge": lineage})

    def test_signal_document_boundaries_and_interior_literals_remain_valid(self) -> None:
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        for text, quote in (("  Management reaffirmed guidance.  ", "Management reaffirmed guidance."),
                            ("  First sentence. Interior evidence. Last sentence.  ", "Interior evidence.")):
            with self.subTest(quote=quote):
                document = RawInfoDocument.create(
                    document_id="whole-document", company_id="issuer-1", source_type="filing",
                    published_at=timestamp, available_at=timestamp, content=text,
                )
                lineage = evolution_runtime_module._SignalProjectionLineage(
                    document=document, projection_text=text,
                    raw_offset_runs=((0, len(text), 0, len(text)),),
                    normalized_start=0, normalized_end=len(text), normalized_source_length=len(text),
                )
                result = {"evidence": {"supporting": [{
                    "projection_id": "whole", "exact_text": quote,
                }], "counter": []}}
                mapped = evolution_runtime_module._map_projected_signal_evidence(result, {"whole": lineage})
                self.assertEqual(mapped["evidence"]["supporting"][0]["exact_span"], quote)

    def test_v12_signal_evidence_rejects_internal_projection_edge_fragment(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v12_reflect_signal_claim_support.json"
            ).read_text(encoding="utf-8")
        )
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        prefix = "Earlier transcript context. "
        projection_text = prefix + fixture["guidance_truncated_projection"]
        raw_prefix = "x" * 100
        document = RawInfoDocument.create(
            document_id="guidance-transcript",
            company_id="issuer-1",
            source_type="earnings_call",
            published_at=timestamp,
            available_at=timestamp,
            content=(
                raw_prefix
                + projection_text
                + "500 per ounce. Management reaffirmed the annual production "
                "range. Later context."
            ),
        )
        lineage = evolution_runtime_module._SignalProjectionLineage(
            document=document,
            projection_text=projection_text,
            raw_offset_runs=((0, len(projection_text), 100, 100 + len(projection_text)),),
            normalized_start=100,
            normalized_end=100 + len(projection_text),
            normalized_source_length=len(document.content),
        )
        overlap_start = lineage.normalized_end - 80
        overlap_text = document.content[overlap_start:]
        overlap_lineage = evolution_runtime_module._SignalProjectionLineage(
            document=document,
            projection_text=overlap_text,
            raw_offset_runs=(
                (
                    0,
                    len(overlap_text),
                    overlap_start,
                    len(document.content),
                ),
            ),
            normalized_start=overlap_start,
            normalized_end=len(document.content),
            normalized_source_length=len(document.content),
        )
        result = {
            "evidence": {
                "supporting": [
                    {
                        "projection_id": "projection_truncated",
                        "exact_text": fixture["guidance_truncated_projection"],
                    }
                ],
                "counter": [],
            }
        }

        with self.assertRaisesRegex(
            ValidationError, "touches internal projection edge"
        ) as context:
            evolution_runtime_module._map_projected_signal_evidence(
                result,
                {
                    "projection_truncated": lineage,
                    "projection_overlap": overlap_lineage,
                },
            )
        error = str(context.exception)
        self.assertIn("supporting evidence[0]", error)
        self.assertIn("projection_truncated", error)
        self.assertIn("edge=['end']", error)
        self.assertIn("projection_overlap", error)
        candidate_marker = "overlapping_projection_interior_candidates="
        candidate_payload = error.split(candidate_marker, 1)[1].split(". Copy", 1)[0]
        candidates = json.loads(candidate_payload)
        # The overlapping projection's anchored sentence is non-unique, but a
        # complete interior sentence of the cited projection itself is always
        # a compliant repair, so it is offered instead of an empty choice.
        self.assertEqual(
            candidates,
            {"projection_truncated": "Turning to our guidance."},
        )
        self.assertNotIn("Management reaffirmed", candidate_payload)

    def test_v103_signal_edge_candidate_is_anchored_to_rejected_boundary(self) -> None:
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        guidance = (
            "Turning to guidance, management remains on track to produce 2 million "
            "ounces at a cost of $1,500 per ounce."
        )
        prefix = "Earlier complete sentence. "
        suffix = " Unrelated operations continued with steady production."
        document = RawInfoDocument.create(
            document_id="guidance-transcript",
            company_id="issuer-1",
            source_type="earnings_call",
            published_at=timestamp,
            available_at=timestamp,
            content=prefix + guidance + suffix,
        )
        boundary = len(prefix) + guidance.index("$1,500") + len("$1,")
        truncated = document.content[:boundary]
        overlap_start = 0
        overlap = document.content[overlap_start:]
        result = {
            "evidence": {
                "supporting": [
                    {"projection_id": "truncated", "exact_text": truncated}
                ],
                "counter": [],
            }
        }
        lineage = {
            "truncated": evolution_runtime_module._SignalProjectionLineage(
                document=document,
                projection_text=truncated,
                raw_offset_runs=((0, len(truncated), 0, len(truncated)),),
                normalized_start=0,
                normalized_end=boundary,
                normalized_source_length=len(document.content),
            ),
            "overlap": evolution_runtime_module._SignalProjectionLineage(
                document=document,
                projection_text=overlap,
                raw_offset_runs=(
                    (0, len(overlap), overlap_start, len(document.content)),
                ),
                normalized_start=overlap_start,
                normalized_end=len(document.content),
                normalized_source_length=len(document.content),
            ),
        }

        with self.assertRaisesRegex(
            ValidationError, "touches internal projection edge"
        ) as context:
            evolution_runtime_module._map_projected_signal_evidence(result, lineage)

        marker = "overlapping_projection_interior_candidates="
        candidate_payload = str(context.exception).split(marker, 1)[1].split(
            ". Copy", 1
        )[0]
        candidates = json.loads(candidate_payload)
        self.assertEqual(candidates, {"overlap": guidance})
        self.assertNotIn("Unrelated operations", candidates["overlap"])

    def test_edge_repair_offers_same_projection_interior_when_no_overlap(self) -> None:
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        sentence = "The company received no qualifying customer orders."
        content = (
            "Earlier complete sentence. " + sentence + " Trailing text follows."
        )
        truncated = content[: len("Earlier complete sentence. ") + len(sentence)]
        document = RawInfoDocument.create(
            document_id="filing-chunk",
            company_id="issuer-1",
            source_type="sec_filing",
            published_at=timestamp,
            available_at=timestamp,
            content=content,
        )
        result = {
            "evidence": {
                "counter": [
                    {"projection_id": "truncated", "exact_text": truncated}
                ],
                "supporting": [],
            }
        }
        lineage = {
            "truncated": evolution_runtime_module._SignalProjectionLineage(
                document=document,
                projection_text=truncated,
                raw_offset_runs=((0, len(truncated), 0, len(truncated)),),
                normalized_start=0,
                normalized_end=len(truncated),
                normalized_source_length=len(content),
            )
        }

        with self.assertRaisesRegex(
            ValidationError, "touches internal projection edge"
        ) as context:
            evolution_runtime_module._map_projected_signal_evidence(result, lineage)

        error = str(context.exception)
        self.assertIn("edge=['end']", error)
        self.assertIn("overlapping_projection_ids=[]", error)
        marker = "overlapping_projection_interior_candidates="
        candidate_payload = error.split(marker, 1)[1].split(". Copy", 1)[0]
        candidates = json.loads(candidate_payload)
        # The informative sentence itself ends at the internal edge, so the
        # compliant repair is the last complete interior sentence.
        self.assertEqual(candidates, {"truncated": "Earlier complete sentence."})
        self.assertIn("shorten the citation", error)

    def test_v103_signal_raw_mapping_is_exact_quote_not_projection_window(self) -> None:
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        quote = "Operations continued with steady production."
        content = (
            "Management raised annual guidance. "
            + quote
            + " Later discussion covered exploration."
        )
        document = RawInfoDocument.create(
            document_id="transcript",
            company_id="issuer-1",
            source_type="earnings_call",
            published_at=timestamp,
            available_at=timestamp,
            content=content,
        )
        mapped = evolution_runtime_module._map_projected_signal_evidence(
            {
                "evidence": {
                    "supporting": [
                        {"projection_id": "whole", "exact_text": quote}
                    ],
                    "counter": [],
                }
            },
            {
                "whole": evolution_runtime_module._SignalProjectionLineage(
                    document=document,
                    projection_text=content,
                    raw_offset_runs=((0, len(content), 0, len(content)),),
                    normalized_start=0,
                    normalized_end=len(content),
                    normalized_source_length=len(content),
                )
            },
        )

        self.assertEqual(
            mapped["evidence"]["supporting"][0]["exact_span"], quote
        )
        self.assertNotIn(
            "guidance", mapped["evidence"]["supporting"][0]["exact_span"]
        )

    def test_v103_signal_required_phrase_cannot_come_from_uncited_window(self) -> None:
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        quote = "Operations continued with steady production."
        document = RawInfoDocument.create(
            document_id="transcript",
            company_id="issuer-1",
            source_type="earnings_call",
            published_at=timestamp,
            available_at=timestamp,
            content=(
                "Management raised annual guidance. "
                + quote
                + " Later discussion covered exploration."
            ),
        )
        invalid = {
            "results": [
                {
                    "signal_ref": "guidance_acceleration:v1",
                    "result": {
                        "signal_id": "guidance_acceleration",
                        "version": 1,
                        "state": {"value": "neutral", "confidence": 0.8},
                        "interpretation": {
                            "summary": "Management reaffirmed rather than raised guidance."
                        },
                        "evidence": {
                            "supporting": [
                                {
                                    "projection_id": "placeholder",
                                    "exact_text": quote,
                                }
                            ],
                            "counter": [],
                        },
                        "status": {"coverage": "sufficient"},
                    },
                }
            ]
        }

        class UnrelatedEvidenceCaller:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                response = json.loads(json.dumps(invalid))
                response["results"][0]["result"]["evidence"]["supporting"][0][
                    "projection_id"
                ] = kwargs["payload"]["source_projection"][0]["projection_id"]
                return response, AgentUsage(llm_calls=1, tokens=50, cost=0.01)

        spec = SignalSpec(
            signal_id="guidance_acceleration",
            version=1,
            category="management",
            description="Detect explicit management-guidance acceleration.",
            execution_type=SignalExecutionType.LLM,
            source_types=("earnings_call",),
            skill_file="guidance_acceleration.md",
            parameters={"result_required_evidence_phrases": ["guidance"]},
        )
        caller = UnrelatedEvidenceCaller()

        result, usage = StructuredLLMSignalRunner(caller).execute(
            spec,
            (document,),
            "Compare current with prior explicit guidance.",
            timestamp,
        )

        self.assertEqual(result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(usage.llm_calls, 2)
        self.assertIn(
            "result_required_evidence_phrases",
            caller.calls[1]["payload"]["validation_feedback"][0][
                "validation_error"
            ],
        )

    def test_v13_signal_evidence_relocates_unique_quote_from_wrong_overlap(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v13_signal_projection_relocation.json"
            ).read_text(encoding="utf-8")
        )
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        unique_text = (
            fixture["unique_projection_prefix"]
            + fixture["exact_text"]
            + fixture["unique_projection_suffix"]
        )
        document = RawInfoDocument.create(
            document_id="guidance-transcript",
            company_id="issuer-1",
            source_type="earnings_call",
            published_at=timestamp,
            available_at=timestamp,
            content=unique_text,
        )

        def lineage(text_value: str, *, start: int, source_length: int):
            return evolution_runtime_module._SignalProjectionLineage(
                document=document,
                projection_text=text_value,
                raw_offset_runs=((0, len(text_value), 0, len(text_value)),),
                normalized_start=start,
                normalized_end=start + len(text_value),
                normalized_source_length=source_length,
            )

        mapped = evolution_runtime_module._map_projected_signal_evidence(
            {
                "evidence": {
                    "supporting": [
                        {
                            "projection_id": fixture["wrong_projection_id"],
                            "exact_text": fixture["exact_text"],
                        }
                    ],
                    "counter": [],
                }
            },
            {
                fixture["wrong_projection_id"]: lineage(
                    fixture["wrong_projection_text"],
                    start=100,
                    source_length=100 + len(fixture["wrong_projection_text"]) + 50,
                ),
                fixture["unique_projection_id"]: lineage(
                    unique_text, start=0, source_length=len(unique_text)
                ),
            },
        )

        self.assertIn(
            fixture["exact_text"],
            mapped["evidence"]["supporting"][0]["exact_span"],
        )

    def test_v12_posthoc_preserves_predictor_basic_source_index(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v12_reflect_signal_claim_support.json"
            ).read_text(encoding="utf-8")
        )
        original_context = {
            "basic_info": fixture["predictor_basic_info"],
            "final_research_state": fixture["corrected_reflection"],
            "signal_rounds": [],
            "prediction_baseline": {
                "status": "available",
                "mean_adjusted_close": 23.982,
            },
        }

        compact = evolution_runtime_module._compact_posthoc_context(original_context)

        self.assertEqual(
            compact["basic_info_source_index"],
            fixture["predictor_basic_info"]["source_index"],
        )
        self.assertEqual(compact["data_gaps"], [])
        self.assertEqual(
            compact["prediction_baseline"]["mean_adjusted_close"], 23.982
        )
        serialized = json.dumps(compact, ensure_ascii=False)
        self.assertNotIn("source_projection", serialized)
        self.assertNotIn("guidance_source", serialized)

    def test_two_soft_signals_share_one_projection_call_and_map_to_raw(self) -> None:
        class ProjectionBatchCaller:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                projection = kwargs["payload"]["source_projection"][0]
                first_ref, second_ref = kwargs["payload"]["batch_signal_refs"]
                first_id, first_version = first_ref.split(":v")
                second_id, second_version = second_ref.split(":v")
                return (
                    {
                        "results": [
                            {
                                "signal_ref": first_ref,
                                "result": {
                                    "signal_id": first_id,
                                    "version": int(first_version),
                                    "state": {"value": "positive", "confidence": 0.8},
                                    "interpretation": {"summary": "Guidance improved."},
                                    "evidence": {
                                        "supporting": [
                                            {
                                                "projection_id": projection["projection_id"],
                                                "exact_text": "Management raised guidance.",
                                            }
                                        ],
                                        "counter": [],
                                    },
                                    "status": {"coverage": "sufficient"},
                                },
                            },
                            {
                                "signal_ref": second_ref,
                                "result": {
                                    "signal_id": second_id,
                                    "version": int(second_version),
                                    "state": {"value": "unavailable", "confidence": 0.0},
                                    "interpretation": {"summary": "No visible evidence."},
                                    "evidence": {"supporting": [], "counter": []},
                                    "status": {"coverage": "unavailable"},
                                },
                            },
                        ]
                    },
                    AgentUsage(llm_calls=1, tokens=50, cost=0.01),
                )

        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-html",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="<p>Management <b>raised</b> guidance.</p>",
        )
        inputs = tuple(
            LLMSignalBatchInput(
                SignalSpec(
                    signal_id=signal_id,
                    version=1,
                    category="catalysts",
                    description="Inspect management guidance.",
                    execution_type=SignalExecutionType.LLM,
                    source_types=("filing",),
                    skill_file=f"{signal_id}.md",
                ),
                (document,),
                "Extract source-grounded guidance evidence.",
            )
            for signal_id in ("guidance_a", "guidance_b")
        )
        caller = ProjectionBatchCaller()

        results, usage = StructuredLLMSignalRunner(caller).execute_many(inputs, as_of)

        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(usage.llm_calls, 1)
        self.assertEqual(set(results), {"guidance_a:v1", "guidance_b:v1"})
        self.assertEqual(
            results["guidance_a:v1"].supporting_evidence[0].exact_span,
            "Management <b>raised</b> guidance.",
        )
        rendered = json.dumps(caller.calls[0]["payload"])
        self.assertNotIn("<p>", rendered)
        self.assertNotIn("<b>", rendered)
        identities = [
            (item["document_id"], item["content_hash"])
            for item in caller.calls[0]["payload"]["source_projection"]
        ]
        self.assertEqual(len(identities), len(set(identities)))

    def test_v68_correction_budget_preserves_valid_soft_signal_sibling(self) -> None:
        class CorrectionBudgetCaller:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 2:
                    raise RuntimeBudgetExceeded(
                        "correction reservation exceeds remaining case budget"
                    )
                payload = kwargs["payload"]
                projections = {
                    item["projection_id"]: item
                    for item in payload["source_projection"]
                }
                rows = []
                for item in payload["signals"]:
                    signal_ref = item["signal_ref"]
                    projection = projections[item["eligible_projection_ids"][0]]
                    exact_text = projection["exact_text"]
                    if signal_ref == "customer_concentration:v1":
                        exact_text = exact_text.replace("One customer", "one customer")
                    signal_id, version = signal_ref.split(":v")
                    rows.append(
                        {
                            "signal_ref": signal_ref,
                            "result": {
                                "signal_id": signal_id,
                                "version": int(version),
                                "state": {
                                    "value": (
                                        "negative"
                                        if signal_id == "customer_concentration"
                                        else "positive"
                                    ),
                                    "confidence": 0.8,
                                },
                                "interpretation": {
                                    "summary": f"{signal_id} was source-backed."
                                },
                                "evidence": {
                                    "supporting": [
                                        {
                                            "projection_id": projection[
                                                "projection_id"
                                            ],
                                            "exact_text": exact_text,
                                        }
                                    ],
                                    "counter": [],
                                },
                                "status": {"coverage": "sufficient"},
                            },
                        }
                    )
                return (
                    {"results": rows},
                    AgentUsage(llm_calls=1, tokens=50, cost=0.01),
                )

        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        guidance = RawInfoDocument.create(
            document_id="guidance-document",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="Management raised annual guidance.",
        )
        concentration = RawInfoDocument.create(
            document_id="concentration-document",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="One customer represented 72 percent of revenue.",
        )
        inputs = tuple(
            LLMSignalBatchInput(
                SignalSpec(
                    signal_id=signal_id,
                    version=1,
                    category="catalysts",
                    description="Inspect the supplied disclosure.",
                    execution_type=SignalExecutionType.LLM,
                    source_types=("filing",),
                    skill_file=f"{signal_id}.md",
                ),
                (document,),
                "Extract one literal source-backed conclusion.",
            )
            for signal_id, document in (
                ("guidance_change", guidance),
                ("customer_concentration", concentration),
            )
        )
        caller = CorrectionBudgetCaller()
        runner = StructuredLLMSignalRunner(caller)
        runner.set_request_token_budget(100)

        results, usage = runner.execute_many(inputs, as_of)

        self.assertEqual(usage, AgentUsage(llm_calls=1, tokens=50, cost=0.01))
        self.assertEqual(results["guidance_change:v1"].value, SignalValue.POSITIVE)
        self.assertEqual(
            results["guidance_change:v1"].execution_status,
            SignalExecutionStatus.SUCCESS,
        )
        concentration_result = results["customer_concentration:v1"]
        self.assertEqual(concentration_result.value, SignalValue.UNAVAILABLE)
        self.assertEqual(
            concentration_result.execution_status,
            SignalExecutionStatus.BUDGET_BLOCKED,
        )
        self.assertIn("correction request was not sent", concentration_result.interpretation)
        self.assertEqual(len(caller.calls), 2)
        error = caller.calls[1]["payload"]["validation_feedback"][0][
            "validation_error"
        ]
        self.assertIn("Signal supporting evidence[0]", error)
        self.assertIn("supplied_occurrences=0", error)
        self.assertIn("visible_occurrences=0", error)
        self.assertIn("matching_projection_ids=[]", error)

    def test_v30_shared_soft_projection_preserves_per_signal_document_scope(self) -> None:
        class CrossScopeCaller:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def complete_json(self, **kwargs):
                self.calls.append(kwargs)
                payload = kwargs["payload"]
                if len(self.calls) == 1:
                    scopes = {
                        item["signal_ref"]: item["eligible_projection_ids"]
                        for item in payload["signals"]
                    }
                    return (
                        {
                            "results": [
                                {
                                    "signal_ref": "scope_a:v1",
                                    "result": {
                                        "signal_id": "scope_a",
                                        "version": 1,
                                        "state": {
                                            "value": "positive",
                                            "confidence": 0.8,
                                        },
                                        "interpretation": {
                                            "summary": "Peer evidence was cited."
                                        },
                                        "evidence": {
                                            "supporting": [
                                                {
                                                    "projection_id": scopes[
                                                        "scope_b:v1"
                                                    ][0],
                                                    "exact_text": (
                                                        "Customer B signed a contract."
                                                    ),
                                                }
                                            ],
                                            "counter": [],
                                        },
                                        "status": {"coverage": "sufficient"},
                                    },
                                },
                                {
                                    "signal_ref": "scope_b:v1",
                                    "result": {
                                        "signal_id": "scope_b",
                                        "version": 1,
                                        "state": {
                                            "value": "unavailable",
                                            "confidence": 0.0,
                                        },
                                        "interpretation": {
                                            "summary": "No conclusion."
                                        },
                                        "evidence": {
                                            "supporting": [],
                                            "counter": [],
                                        },
                                        "status": {"coverage": "unavailable"},
                                    },
                                },
                            ]
                        },
                        AgentUsage(llm_calls=1, tokens=50, cost=0.01),
                    )
                return (
                    {
                        "results": [
                            {
                                "signal_ref": "scope_a:v1",
                                "result": {
                                    "signal_id": "scope_a",
                                    "version": 1,
                                    "state": {
                                        "value": "unavailable",
                                        "confidence": 0.0,
                                    },
                                    "interpretation": {"summary": "No conclusion."},
                                    "evidence": {"supporting": [], "counter": []},
                                    "status": {"coverage": "unavailable"},
                                },
                            }
                        ]
                    },
                    AgentUsage(llm_calls=1, tokens=20, cost=0.005),
                )

        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document_a = RawInfoDocument.create(
            document_id="document-a",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="Issuer A raised guidance.",
        )
        document_b = RawInfoDocument.create(
            document_id="document-b",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="Customer B signed a contract.",
        )
        inputs = tuple(
            LLMSignalBatchInput(
                SignalSpec(
                    signal_id=signal_id,
                    version=1,
                    category="catalysts",
                    description="Inspect one bounded filing.",
                    execution_type=SignalExecutionType.LLM,
                    source_types=("filing",),
                    skill_file=f"{signal_id}.md",
                ),
                (document,),
                "Extract source-grounded evidence.",
            )
            for signal_id, document in (
                ("scope_a", document_a),
                ("scope_b", document_b),
            )
        )
        caller = CrossScopeCaller()

        results, usage = StructuredLLMSignalRunner(caller).execute_many(inputs, as_of)

        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(results["scope_a:v1"].value, SignalValue.UNAVAILABLE)
        first_scopes = {
            item["signal_ref"]: item["eligible_projection_ids"]
            for item in caller.calls[0]["payload"]["signals"]
        }
        self.assertTrue(first_scopes["scope_a:v1"])
        self.assertTrue(first_scopes["scope_b:v1"])
        self.assertTrue(
            set(first_scopes["scope_a:v1"]).isdisjoint(
                first_scopes["scope_b:v1"]
            )
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("outside this Signal's eligible_projection_ids", feedback["validation_error"])
        self.assertIn("this request's eligible_projection_ids", feedback["required_action"])
        self.assertIn(
            "Each Signal may cite only projection ids",
            caller.calls[0]["system_prompt"],
        )

    def test_proposer_corrects_unsupported_source_then_rejects_stale_probability(self) -> None:
        parent = default_information_plan()
        unsupported = {
            "used_experience_refs": [],
            "B": {
                "requests": [
                    {
                        "request_id": "market",
                        "description": "market",
                        "source_types": ["market_data"],
                        "lookback_days": 30,
                        "max_documents": 1,
                    },
                    {
                        "request_id": "unsupported",
                        "description": "unsupported",
                        "source_types": ["social_firehose"],
                        "max_documents": 1,
                    },
                ]
            },
            "H_init": "form needs",
            "H_reflect": "reflect on evidence",
            "H_analyse": "organize evidence",
        }
        stale = json.loads(json.dumps(unsupported))
        stale["B"]["requests"] = stale["B"]["requests"][:1]
        stale["H_analyse"] = "Compute P(surge) and apply a 0.55 probability threshold."
        caller = ScriptedRoleCaller([unsupported, stale])

        with self.assertRaises(CandidateProposalRejected):
            LLMInformationPlanProposer(
                caller,
                available_source_types=("market_data", "filing"),
            ).propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(parent,),
                meta_info=(),
                prior="fixed H_P",
            )

        self.assertEqual(len(caller.calls), 2)
        self.assertIn(
            "unsupported source types",
            caller.calls[1]["payload"]["validation_feedback"]["validation_error"],
        )
        self.assertEqual(
            caller.calls[0]["payload"]["proposal_context"][
                "available_source_types"
            ],
            ["filing", "market_data"],
        )

    def test_v30_proposer_rejects_controller_owned_prediction_ontology(self) -> None:
        parent = default_information_plan()
        invalid = {
            "used_experience_refs": [],
            "B": {
                "requests": [
                    {
                        "request_id": "market",
                        "description": "compact market evidence",
                        "source_types": ["market_data"],
                        "lookback_days": 30,
                        "max_documents": 1,
                    }
                ]
            },
            "H_init": (
                "Form a falsifiable hypothesis and list unresolved information "
                "needs and questions."
            ),
            "H_reflect": (
                "Reflect on supporting and contradictory evidence, then finalize "
                "the four-way judgment (strong up, up, down, strong down) or "
                "continue to the next information need."
            ),
            "H_analyse": (
                "Organize and weight supporting and counter-evidence while "
                "preserving uncertainty."
            ),
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["H_reflect"] = (
            "Reflect on supporting and contradictory evidence to update beliefs, "
            "then continue with the next information need or finalize evidence "
            "collection while keeping the four-way judgment intact and without "
            "altering the Predictor class ontology."
        )
        caller = ScriptedRoleCaller([invalid, corrected])

        plan = LLMInformationPlanProposer(
            caller,
            available_source_types=("market_data",),
        ).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(plan.reflection_skill, corrected["H_reflect"])
        self.assertIn(
            "cannot define or finalize a replacement Predictor class ontology",
            caller.calls[1]["payload"]["validation_feedback"]["validation_error"],
        )
        self.assertIn(
            "must not define, name, or finalize a replacement Predictor class ontology",
            caller.calls[0]["system_prompt"],
        )

    def test_posthoc_uses_compact_view_not_full_original_context(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "prediction_outcome": {"correct": True},
                    "decision_drivers": [
                        "The bounded evidence supported the negative judgment."
                    ],
                    "why_prediction_failed": [],
                    "misleading_signals": [],
                    "ignored_evidence": [],
                    "missing_information": [],
                    "plan_issues": [],
                }
            ]
        )
        predictor = LLMBlindPredictor(caller)
        prediction = BlindPrediction(
            is_surge=False,
            candidate_judgment=CandidateJudgment.UNLIKELY,
            magnitude=None,
            confidence=ConfidenceLevel.LOW,
            key_reasons=("bounded evidence",),
            uncertainties=(),
            session_id="fixture",
        )
        original = {
            "basic_info": {"requests": []},
            "signal_rounds": [],
            "final_research_state": ResearchState(
                decision=ResearchDecision.FINALIZE
            ).to_dict(),
            "full_original_marker": "do-not-send-" + "x" * 30_000,
        }

        predictor.reflect(original, prediction, GroundTruth(1.1))

        payload = caller.calls[0]["payload"]
        self.assertIn("compact_context", payload)
        self.assertNotIn("original_context", payload)
        self.assertNotIn("do-not-send", json.dumps(payload))
        self.assertLess(len(json.dumps(payload["compact_context"])), 24_000)

    def test_critic_masks_identity_in_accepted_output_before_meta(self) -> None:
        from tests.scheme_evolution_test_support import make_trajectory
        caller = ScriptedRoleCaller(
            [
                {
                    "successful_patterns": [],
                    "failed_patterns": [],
                    "repeated_failure_modes": [],
                    "misleading_signals": [],
                    "missing_information_needs": [
                        "Research Acme Systems Corp customer concentration."
                    ],
                    "next_explorations": [],
                }
            ]
        )
        critic = LLMPlanCritic(caller)
        critic.set_anonymous_aliases(("Acme Systems Corp", "Acme Systems"))
        metrics = PlanMetrics(
            binary_precision=1.0,
            binary_recall=1.0,
            binary_f1=1.0,
            magnitude_accuracy=1.0,
            magnitude_macro_f1=1.0,
            true_positive=1,
            false_positive=0,
            true_negative=1,
            false_negative=0,
            sample_count=2,
        )

        reflection = critic.critique(
            plan=default_information_plan(),
            trajectories=(make_trajectory("masked_fixture", 2.5, True, MagnitudeClass.TWO_TO_THREE),),
            metrics=metrics,
        )

        rendered = json.dumps(reflection.to_dict())
        self.assertNotIn("Acme", rendered)
        self.assertIn("MASKED_COMPANY", rendered)


class NeedCorrectionBeliefScopeTests(TestCase):
    def test_need_transition_correction_preserves_unrelated_beliefs(self) -> None:
        invalid = {
            "next_information_needs": ["What 2026 capacity will cost?"],
            "current_beliefs": ["Margins expanded sequentially."],
            "decision": "continue",
        }
        corrected = {
            "next_information_needs": ["Capacity cost remains unresolved."],
            "current_beliefs": ["Rewritten unauthorized belief."],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        def parse(value):
            if value["next_information_needs"][0] == "What 2026 capacity will cost?":
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="research_need_transition_invalid",
                            message=(
                                "research_controller_reflect violated the supplied "
                                "need transition contract"
                            ),
                            paths=("next_information_needs[0]",),
                            allowed_repairs=("replace", "remove", "add"),
                            repair_context={
                                "write_scope_complete": True,
                                "prior_need": "What 2026 capacity will cost?",
                                "required_action": "replace_with_exact_residual",
                                "required_need": "Capacity cost remains unresolved.",
                                "returned_need": "What 2026 capacity will cost?",
                            },
                        )
                    ]
                )
            if value["current_beliefs"] != ["Margins expanded sequentially."]:
                raise ValidationError(
                    "a need correction grants no authority over current_beliefs"
                )
            return value

        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={}, parser=parse,
            allow_outcomes=False, enforce_scoped_correction=True,
            exact_compaction_scope=True, stable_correction_prefix=True,
        )
        self.assertEqual(
            value,
            {
                "next_information_needs": ["Capacity cost remains unresolved."],
                "current_beliefs": ["Margins expanded sequentially."],
                "decision": "continue",
            },
        )
        self.assertEqual(usage.llm_calls, 2)

    def test_v144_model_view_discloses_omitted_ranked_spans(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        boilerplate = RawInfoDocument.create(
            document_id="boilerplate-10q",
            company_id="issuer-1",
            source_type="10-q",
            published_at=as_of,
            available_at=as_of,
            content=(
                "<p>Risk factors management discussion business risk factors "
                "management.</p>\n" * 120
            ),
        )
        catalyst = RawInfoDocument.create(
            document_id="catalyst-8k",
            company_id="issuer-1",
            source_type="8-k",
            published_at=as_of,
            available_at=as_of,
            content=(
                "<p>The subsidiary received export permits to resume shipping "
                "and expects several million dollars of new revenue not in "
                "guidance. Business improved.</p>\n" * 40
            ),
        )
        resolver = EvidenceResolver(
            RawInfoStore(documents=(boilerplate, catalyst))
        )
        bundle = resolver.resolve_basic_info(
            (
                RawInfoRequest(
                    "report",
                    "demo",
                    ("filing",),
                    max_documents=2,
                    query="business risk factors management discussion",
                ),
            ),
            company_id="issuer-1",
            identity={},
            as_of=as_of,
        )

        model_view, audit = project_basic_info_bundle(bundle)
        self.assertEqual(len(model_view["requests"]), 1)
        row = model_view["requests"][0]
        # Whatever the budgets funded, the model view must disclose previews
        # of the ranked-but-omitted content instead of letting it vanish
        # behind a green structural status.
        rendered_visible = " ".join(
            span["exact_text"] for span in row["projections"]
        )
        markers = row["omitted_context_markers"]
        self.assertTrue(isinstance(markers, list))
        self.assertLessEqual(len(markers), 8)
        for marker in markers:
            self.assertNotIn("<", marker)
            self.assertLessEqual(len(marker), 110)
        covered = rendered_visible + " " + " ".join(markers)
        self.assertIn("export permits", covered)
        self.assertTrue(audit["entries"])


class ReflectionSalvageTests(TestCase):
    def test_v144_invalid_mixed_axis_row_is_dropped_and_valid_siblings_persist(
        self,
    ) -> None:
        from stock_opportunity_agent.research.evolution_plan_roles import (
            _reflection_salvage_fallback,
            _structured_reflection_items,
        )
        from stock_opportunity_agent.research.evolution_reflection_memory import (
            ReflectionMemoryIndex,
        )

        # The audit's V143 mixed-outcome shape: binary direction correct,
        # magnitude class wrong. The model authored one why-it-failed item
        # whose binary claim is correct=true — a category/claim mismatch,
        # not a factual error.
        snapshot = {
            "source_identity": "case:mixed",
            "candidate_judgment_feedback": {"binary_correct": True},
            "magnitude_feedback": {
                "magnitude_applicable": True,
                "magnitude_correct": False,
            },
        }
        index = ReflectionMemoryIndex.from_case_rows(
            [snapshot], owner_ref="plan:mixed"
        )
        source = index.source_catalog()[0]
        good = {
            "category": "repeated_failure_modes",
            "kind": "action",
            "brief": (
                "Split mixed direction/magnitude outcomes into two items: the "
                "correct binary axis as a success item, the wrong magnitude "
                "axis as a failure item."
            ),
            "detail": (
                "When candidate_judgment_feedback.binary_correct is true but "
                "magnitude_feedback.magnitude_correct is false, author two "
                "scoped items instead of one straddling item so each claim "
                "matches its category axis."
            ),
            "scope": {
                "case_refs": list(source["case_refs"]),
                "plan_refs": list(source["plan_refs"]),
                "conditions": "When a mixed direction/magnitude outcome appears.",
            },
            "limitations": ["Untested attribution of the magnitude miss."],
            "source_refs": [source["source_ref"]],
            "counter_refs": [],
            "outcome_claims": [],
        }
        mixed = {
            "category": "failed_patterns",
            "kind": "fact",
            "brief": "Binary direction was right while magnitude class was wrong.",
            "detail": "The call was directionally correct but underestimated class.",
            "scope": {
                "case_refs": list(source["case_refs"]),
                "plan_refs": list(source["plan_refs"]),
                "conditions": "When both axes are observed together.",
            },
            "limitations": [],
            "source_refs": [source["source_ref"]],
            "counter_refs": [],
            "outcome_claims": [
                {
                    "source_ref": source["source_ref"],
                    "axis": "binary",
                    "correct": True,
                }
            ],
        }
        package = {
            "reflection_items": [good, mixed],
            "selected_reflection_refs": [],
            "no_findings_reason": None,
        }

        def parse(value):
            items, selected, projection = _structured_reflection_items(
                value, index=index, level="plan", owner_ref="plan:mixed",
            )
            return {"items": items, "selected": selected, **projection}

        # The model repeats the same straddling package on its one
        # correction attempt, exhausting the frontier without fixing it.
        caller = ScriptedRoleCaller([package, package])
        value, _usage = evolution_runtime_module._complete_parsed_role(
            caller,
            stage="plan_critic",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=parse,
            allow_outcomes=True,
            patch_corrections=True,
            final_validation_fallback=_reflection_salvage_fallback(
                index, "plan", "plan:mixed",
            ),
        )

        items = value["items"]
        self.assertEqual(len(items), 1)
        # Content-level assertions: the persisted lesson is the authored
        # sibling, verbatim and non-generic, not an empty salvage shell.
        self.assertIn("Split mixed direction/magnitude outcomes", items[0].brief)
        self.assertIn(
            "magnitude_feedback.magnitude_correct is false", items[0].detail
        )
        self.assertEqual(items[0].source_refs, (source["source_ref"],))
        self.assertEqual(items[0].category, "repeated_failure_modes")
        self.assertIsNone(value["no_findings_reason"])
        # The salvaged item must resolve as a real, selectable index entry.
        self.assertEqual(
            index.select_items([items[0].item_ref]), (items[0],)
        )

    def test_v144_salvage_reports_all_invalid_rows_as_explicit_reason(
        self,
    ) -> None:
        from stock_opportunity_agent.research.evolution_plan_roles import (
            _reflection_salvage_fallback,
        )
        from stock_opportunity_agent.research.evolution_reflection_memory import (
            ReflectionMemoryIndex,
        )

        snapshot = {
            "source_identity": "case:bad",
            "candidate_judgment_feedback": {"binary_correct": False},
            "magnitude_feedback": {
                "magnitude_applicable": True,
                "magnitude_correct": False,
            },
        }
        index = ReflectionMemoryIndex.from_case_rows(
            [snapshot], owner_ref="case:bad"
        )
        source = index.source_catalog()[0]
        broken = {
            "category": "why_prediction_failed",
            "kind": "fact",
            "brief": "Broken row.",
            "detail": "Broken row detail.",
            "scope": {
                "case_refs": list(source["case_refs"]),
                "plan_refs": [],
                "conditions": "Never.",
            },
            "limitations": [],
            "source_refs": [source["source_ref"]],
            "counter_refs": ["reflection_source:unknown"],
            "outcome_claims": [],
        }
        salvage = _reflection_salvage_fallback(index, "case", "case:bad")
        result = salvage(
            {
                "reflection_items": [broken],
                "selected_reflection_refs": [],
                "no_findings_reason": None,
            },
            ValidationError("reflection_items[0].counter_refs invalid"),
        )
        self.assertIsNotNone(result)
        next_output, actions = result
        self.assertEqual(next_output["reflection_items"], [])
        self.assertEqual(actions["removed_paths"], ("reflection_items[0]",))
        self.assertTrue(
            next_output["no_findings_reason"].startswith(
                "reflection_items_all_invalid_salvaged:"
            )
        )

class RetainedSignalClaimRestorationTests(TestCase):
    """Exercise immutable claim ownership, native terminal patches and ambiguity."""

    @staticmethod
    def _ref(claim, *, signal_ref="old_capability:v3", index=0):
        return ResearchEvidenceRef(kind="signal", claim=claim,
            signal_ref=signal_ref, evidence_group="supporting", evidence_index=index)

    @staticmethod
    def _visible_batch():
        return SignalBatchResult(results=(SignalResult(
            signal_id="new_capability", version=2, value=SignalValue.NEUTRAL,
            confidence=0.7, interpretation="Current outlook remains unchanged.",
            coverage=SignalCoverage.SUFFICIENT,
            supporting_evidence=(SignalEvidence(document_id="current-document",
                exact_span="Current outlook remains unchanged.",
                timestamp=datetime(2025, 8, 1, tzinfo=timezone.utc)),)),), signal_calls=1)

    def test_unique_claims_restore_with_linked_assertions_and_native_finalization(self):
        for claim in ("Management reaffirmed guidance.", "net_share_retirement_yoy=-0.0229939"):
            with self.subTest(claim=claim):
                previous = ResearchState(hypotheses=("Unrelated thesis.",),
                    current_beliefs=(claim, "A separate retained belief."),
                    contradictions=(claim,), supporting_evidence=(self._ref(claim),),
                    next_information_needs=("Check a separate risk.",))
                changed = "The issuer's prior claim was restated."
                new_claim = "Current outlook remains unchanged."

                def native(kwargs):
                    return {"base_hash": kwargs["payload"]["output_patch_contract"]["base_hash"],
                        "operations": [
                            {"op": "replace", "path": "supporting_evidence[0].claim", "value": changed},
                            {"op": "replace", "path": "current_beliefs[0]", "value": changed},
                            {"op": "replace", "path": "contradictions[0]", "value": changed},
                            {"op": "append", "path": "supporting_evidence", "value": self._ref(
                                new_claim, signal_ref="new_capability:v2").to_dict()},
                            {"op": "append", "path": "current_beliefs", "value": new_claim},
                            {"op": "replace", "path": "decision", "value": "finalize"},
                        ]}

                class NoCorrectionCaller(ScriptedRoleCaller):
                    def complete_json(self, **kwargs):
                        if self.calls:
                            raise RuntimeBudgetExceeded("No correction budget remains")
                        return super().complete_json(**kwargs)

                caller = NoCorrectionCaller([native])
                controller = LLMResearchController(caller)
                controller.reflection_must_finalize = True
                result = controller.reflect(default_information_plan(), previous, self._visible_batch())
                self.assertEqual(len(caller.calls), 1)
                self.assertEqual(result.usage.llm_calls, 1)
                self.assertEqual(result.value.decision, ResearchDecision.FINALIZE)
                self.assertEqual(result.value.current_beliefs, (*previous.current_beliefs, new_claim))
                self.assertEqual(result.value.contradictions, previous.contradictions)
                self.assertEqual(result.value.supporting_evidence[0], previous.supporting_evidence[0])
                self.assertEqual(result.value.supporting_evidence[1].claim, new_claim)
                self.assertEqual(result.value.next_information_needs, previous.next_information_needs)
                self.assertEqual(ResearchState.from_dict(result.value.to_dict()), result.value)

    def test_shared_tuple_retains_each_accepted_claim_and_never_selects_one_to_restore(self):
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )
        claims = ("Management reaffirmed guidance.", "Management discussed cost risks.")
        for ordered_claims in (claims, tuple(reversed(claims))):
            previous = ResearchState(hypotheses=("Guidance may matter.",),
                supporting_evidence=tuple(self._ref(x) for x in ordered_claims),
                next_information_needs=("Check a separate risk.",))
            self.assertEqual(_validate_research_state_refs(previous, phase="reflect",
                previous_state=previous, batch=self._visible_batch()), previous)
            invalid = previous.to_dict()
            invalid["supporting_evidence"][0]["claim"] = "Management raised guidance."
            failure = claim_error(invalid, previous_state=previous, batch=self._visible_batch())
            issue = next(x for x in failure.issues if x.code == "retained_signal_claim_changed")
            self.assertNotIn("prior_signal_claim", issue.repair_context)
            self.assertIsNone(_research_state_evidence_grounding_fallback(invalid, failure))
            caller = ScriptedRoleCaller([invalid, previous.to_dict()])
            result = LLMResearchController(caller).reflect(default_information_plan(), previous,
                self._visible_batch())
            self.assertEqual(len(caller.calls), 2)
            self.assertEqual(result.value.supporting_evidence, previous.supporting_evidence)

    def test_identical_prior_duplicates_supply_one_restoration_candidate(self):
        previous = ResearchState(hypotheses=("Guidance may matter.",),
            supporting_evidence=(self._ref("Guidance is unchanged."),) * 2,
            next_information_needs=("Check a separate risk.",))
        invalid = previous.to_dict()
        for row in invalid["supporting_evidence"]:
            row["claim"] = "Guidance is accelerating."
        caller = ScriptedRoleCaller([invalid])
        result = LLMResearchController(caller).reflect(default_information_plan(), previous,
            self._visible_batch())
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(result.value.supporting_evidence, previous.supporting_evidence)

    def test_restoration_refuses_stale_source_text_and_conflicting_dependencies(self):
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )
        previous = ResearchState(hypotheses=("Separate observations matter.",),
            supporting_evidence=(self._ref("First accepted claim."),
                self._ref("Second accepted claim.", index=1)),
            next_information_needs=("Check a separate risk.",))
        invalid = previous.to_dict()
        invalid["supporting_evidence"][0]["claim"] = "Changed claim."
        failure = claim_error(invalid, previous_state=previous, batch=self._visible_batch())
        for mutation in ("source", "claim"):
            stale = json.loads(json.dumps(invalid))
            row = stale["supporting_evidence"][0]
            row["signal_ref" if mutation == "source" else "claim"] = "Different value."
            self.assertIsNone(_research_state_evidence_grounding_fallback(stale, failure))
        invalid["supporting_evidence"][1]["claim"] = "Changed claim."
        invalid["current_beliefs"] = ["Changed claim."]
        failure = claim_error(invalid, previous_state=previous, batch=self._visible_batch())
        self.assertIsNone(_research_state_evidence_grounding_fallback(invalid, failure))

    def test_restoration_preserves_continue_and_cannot_author_terminal_decision(self):
        previous = ResearchState(hypotheses=("Guidance may matter.",),
            supporting_evidence=(self._ref("Guidance is unchanged."),),
            next_information_needs=("Check a separate risk.",))
        invalid = previous.to_dict()
        invalid["supporting_evidence"][0]["claim"] = "Guidance is accelerating."
        caller = ScriptedRoleCaller([invalid])
        result = LLMResearchController(caller).reflect(default_information_plan(), previous,
            self._visible_batch())
        self.assertEqual(result.value.decision, ResearchDecision.CONTINUE)

        class NoCorrectionCaller(ScriptedRoleCaller):
            def complete_json(self, **kwargs):
                if self.calls:
                    raise RuntimeBudgetExceeded("No correction budget remains")
                return super().complete_json(**kwargs)

        caller = NoCorrectionCaller([invalid])
        controller = LLMResearchController(caller)
        controller.reflection_must_finalize = True
        with self.assertRaises(RuntimeBudgetExceeded):
            controller.reflect(default_information_plan(), previous, self._visible_batch())
        self.assertEqual(len(caller.calls), 1)
