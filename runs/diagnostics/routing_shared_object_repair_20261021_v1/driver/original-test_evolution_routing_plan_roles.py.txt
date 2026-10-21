"""Signal routing, prediction, and Plan role-adapter tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403
from stock_opportunity_agent.research.basic_info_orientation import make_orientation_request
from stock_opportunity_agent.models import StructuredValidationError, ValidationIssue
from stock_opportunity_agent.research.evolution_output_validation import (
    _routing_context_only_fallback,
)
from stock_opportunity_agent.research.evolution_research_validation import (
    _reflection_need_transition_contract,
    _reflection_selection_intents,
    _shared_distinctive_phrase,
)


class RoutingResidualFacetContrastTests(TestCase):
    TARGET = (
        "What is net share retirement based on comparable FY 2024 versus FY 2023 "
        "weighted-average basic common shares, how did period-end common shares "
        "change, and what prospective net equity dilution is disclosed, using only "
        "disclosures available by 2025-02-01T00:00:00+00:00?"
    )
    RESIDUAL = (
        "Using only disclosures available by 2025-02-01T00:00:00+00:00, establish "
        "the FY 2024 versus FY 2023 period-end common share change and disclosed "
        "prospective net equity dilution."
    )
    # Exact reason strings from immutable role 54 and role 57, respectively.
    REASONS = (
        "Measures net share retirement from comparable FY 2024 versus FY 2023 "
        "weighted-average basic common share counts when these are the latest "
        "eligible durations.",
        "Measures net share retirement using comparable weighted-average basic "
        "common share counts when the requested annual pair is the latest "
        "eligible duration pair.",
    )

    def _select(self, outputs):
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            caller = ScriptedRoleCaller(outputs)
            selected = LLMSignalRetrievalAgent(caller).select(
                (self.TARGET,), registry.freeze(), {},
            )
        return selected, caller

    def _row(self, reason):
        raw = signal_selection("net_share_retirement_yoy:v1")
        raw["selections"][0].update(
            selection_reason=reason, answer_scope="partial",
            residual_need=self.RESIDUAL, context_tags=["comparable_financials"],
        )
        return raw

    def test_recorded_reason_variants_keep_partial_ownership(self):
        for reason in self.REASONS:
            with self.subTest(reason=reason):
                self.assertIsNotNone(_shared_distinctive_phrase(reason, self.RESIDUAL))
                selected, caller = self._select([self._row(reason)])
                self.assertEqual(len(caller.calls), 1)
                self.assertEqual(selected.value[0].reason_code, "answer_need")
                self.assertEqual(selected.value[0].answer_scope, "partial")
                self.assertEqual(selected.value[0].residual_need, self.RESIDUAL)

    def test_actual_retained_facets_receive_indexed_reason_correction(self):
        for claim in ("period-end common share change", "prospective net equity dilution"):
            with self.subTest(claim=claim):
                bad = self._row(self.REASONS[0] + " Also measures " + claim + ".")
                good = self._row(self.REASONS[0])
                selected, caller = self._select([bad, good])
                self.assertEqual(len(caller.calls), 2)
                feedback = caller.calls[1]["payload"]["validation_feedback"]
                self.assertIn("claims a facet retained", feedback["validation_error"])
                paths = {path for obligation in feedback["obligations"]
                         for path in obligation["must_change_paths"]}
                self.assertIn("selections[0].selection_reason", paths)
                self.assertEqual(selected.value[0].answer_scope, "partial")
                self.assertEqual(selected.value[0].selection_reason, self.REASONS[0])

    def test_unrepaired_real_claim_retains_context_only_fallback(self):
        bad = self._row(self.REASONS[0] + " Covers prospective net equity dilution.")
        selected, caller = self._select([bad, bad])
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(selected.value[0].reason_code, "assess_applicability")
        self.assertIsNone(selected.value[0].answer_scope)
        self.assertIsNone(selected.value[0].residual_need)
        self.assertEqual(selected.value[0].target_need_indices, (0,))

    def test_retained_facet_losing_one_modifier_still_rejects_claim(self):
        for replacement in ("future", ""):
            with self.subTest(replacement=replacement):
                bad = self._row(
                    self.REASONS[0] + " Also measures prospective net equity dilution."
                )
                bad["selections"][0]["residual_need"] = self.RESIDUAL.replace(
                    "prospective", replacement,
                )
                selected, caller = self._select([bad, bad])
                self.assertEqual(len(caller.calls), 2)
                self.assertEqual(selected.value[0].reason_code, "assess_applicability")
                self.assertIsNone(selected.value[0].answer_scope)
                self.assertIn("claims a facet retained", validation_error(caller.calls[1]))

    def test_common_objects_and_cutoffs_are_not_globally_ignored(self):
        target = (
            "What operating cash flow margin is disclosed for FY 2024 versus FY "
            "2023, and what prospective common share issuance is disclosed, "
            "using only disclosures available by 2025-02-01?"
        )
        residual = "What prospective common share issuance is disclosed by 2025-02-01?"
        self.assertIsNone(_shared_distinctive_phrase(
            "Measures operating cash flow margin for FY 2024 versus FY 2023.",
            residual, target_need=target,
        ))
        self.assertIsNotNone(_shared_distinctive_phrase(
            "Measures prospective common share issuance.", residual, target_need=target,
        ))

    def test_whole_word_and_clause_boundaries_remain_distinct(self):
        for reason in (
            "Measures weighted-average basic shares; prospectivefiction and equitylike remain unknown.",
            "Measures weighted-average basic shares with a period-ending observation.",
        ):
            with self.subTest(reason=reason):
                self.assertIsNone(_shared_distinctive_phrase(
                    reason, self.RESIDUAL, target_need=self.TARGET,
                ))
        self.assertIsNotNone(_shared_distinctive_phrase(
            "Measures period-end common shares.", self.RESIDUAL, target_need=self.TARGET,
        ))

    def test_unsplit_target_keeps_conservative_guard(self):
        reason = "Covers Tasiast mill restart impact."
        residual = "What Tasiast mill restart impact remains unknown?"
        self.assertEqual(
            _shared_distinctive_phrase(reason, residual, target_need=residual),
            _shared_distinctive_phrase(reason, residual),
        )


class RoutingPartialResidualTemporalScopeTests(TestCase):
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

    def test_partial_residual_dropping_target_cutoff_is_rejected_and_repaired(self) -> None:
        prior_need = (
            "What forward guidance or production outlook had Kinross Gold "
            "disclosed by 2025-09-30 regarding gold equivalent production "
            "and cost per ounce for the remainder of 2025 and 2026?"
        )
        raw_residual = (
            "Cost per ounce guidance for the remainder of 2025 and 2026 is "
            "not covered by this card."
        )
        corrected_residual = (
            "What cost per ounce guidance had Kinross Gold disclosed by "
            "2025-09-30 for the remainder of 2025 and 2026?"
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [self._partial_selection(raw_residual),
                 self._partial_selection(corrected_residual)]
            )
            selection = LLMSignalRetrievalAgent(caller).select(
                (prior_need,), registry.freeze(), {},
            )
            self.assertEqual(
                selection.value[0].residual_need, corrected_residual,
            )
            self.assertEqual(len(caller.calls), 2)
            feedback = validation_error(caller.calls[1])
            self.assertIn("temporal scope", feedback)
            self.assertIn("by 2025-09-30", feedback)

    def test_accepted_bounded_residual_is_consumable_as_next_routing_target(self) -> None:
        accepted_need = (
            "Cost per ounce guidance for the remainder of 2025 and 2026 is "
            "not covered by this card, by 2025-09-30."
        )
        retained_scope_residual = (
            "What cost per ounce guidance for 2026 had Kinross Gold "
            "disclosed by 2025-09-30?"
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [self._partial_selection(retained_scope_residual)]
            )
            selection = LLMSignalRetrievalAgent(caller).select(
                (accepted_need,), registry.freeze(), {},
            )
            self.assertEqual(
                selection.value[0].residual_need, retained_scope_residual,
            )
            self.assertEqual(len(caller.calls), 1)


class RoutingSymbolicCutoffTemporalScopeTests(TestCase):
    """The actual prediction date drives routing residual representability."""

    PARENT_NEED = (
        "What forward production, cost, and capital expenditure guidance did "
        "Kinross provide by the prediction time for the remainder of 2025 "
        "and 2026?"
    )
    RAW_RESIDUAL = (
        "Specific disclosed production, cost, and capital expenditure "
        "figures for the remainder of 2025 and 2026 are not fully covered."
    )
    PREDICTION_TIME = datetime(2025, 9, 30, tzinfo=timezone.utc)

    def _partial_selection(self, residual_need):
        return {
            "selections": [
                {
                    "signal_ref": "guidance_acceleration:v1",
                    "reason_code": "answer_need",
                    "selection_reason": (
                        "The card addresses the management signal for this facet."
                    ),
                    "applicability_hypothesis": "Guidance disclosures apply.",
                    "expected_role": "primary",
                    "context_tags": ["general"],
                    "target_need_indices": [0],
                    "answer_scope": "partial",
                    "residual_need": residual_need,
                }
            ]
        }

    def _select(self, caller, needs):
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            agent = LLMSignalRetrievalAgent(caller)
            agent.set_evaluation_context(self.PREDICTION_TIME)
            return agent.select(tuple(needs), registry.freeze(), {})

    def test_representable_residual_accepted_with_actual_date_context(self):
        caller = ScriptedRoleCaller(
            [self._partial_selection(self.RAW_RESIDUAL)]
        )
        selection = self._select(caller, (self.PARENT_NEED,))
        self.assertEqual(len(caller.calls), 1)
        context = caller.calls[0]["payload"]["evaluation_context"]
        self.assertEqual(
            context,
            {
                "prediction_time": "2025-09-30T00:00:00+00:00",
                "horizon": "six_calendar_months",
                "horizon_end": "2026-03-30",
            },
        )
        self.assertIn(
            "actual runtime cutoff", caller.calls[0]["system_prompt"]
        )
        self.assertEqual(selection.value[0].residual_need, self.RAW_RESIDUAL)
        intents = _reflection_selection_intents(
            selection.value,
            information_needs=(self.PARENT_NEED,),
            evaluation_context=context,
        )
        bounded = intents[0]["residual_need"]
        self.assertIn("by the prediction time", bounded)
        self.assertIn("guidance", bounded)
        batch = SignalBatchResult(
            results=(
                SignalResult(
                    signal_id="guidance_acceleration",
                    version=1,
                    value=SignalValue.POSITIVE,
                    confidence=0.9,
                    interpretation="guidance materially strengthened",
                    supporting_evidence=(
                        SignalEvidence(
                            document_id="synthetic-doc",
                            exact_span="guidance strengthened",
                            timestamp=self.PREDICTION_TIME,
                        ),
                    ),
                ),
            ),
            signal_calls=1,
        )
        contract = _reflection_need_transition_contract(
            ResearchState(next_information_needs=(self.PARENT_NEED,)),
            selection.value,
            batch,
            evaluation_context=context,
        )
        rule = contract["need_rules"][0]
        action = rule["available_answer_actions"][0]
        self.assertEqual(action["residual_need"], bounded)
        self.assertIn(
            "partial uses its actual bounded residual", rule["required_transition"]
        )
        # The corrected bounded representation is consumable as the next
        # routing target under the same actual date.
        next_caller = ScriptedRoleCaller([{"selections": []}])
        next_selection = self._select(next_caller, (bounded,))
        self.assertEqual(next_selection.value, ())
        self.assertEqual(len(next_caller.calls), 1)

    def test_realized_future_residual_corrected_before_signal_execution(self):
        realized = (
            "Actual 2026 production and cost results for the remainder of "
            "2025 and 2026 are not fully covered."
        )
        corrected = (
            "Specific disclosed production and cost guidance figures for "
            "the remainder of 2025 and 2026 are not fully covered, by the "
            "prediction time."
        )
        caller = ScriptedRoleCaller(
            [self._partial_selection(realized),
             self._partial_selection(corrected)]
        )
        selection = self._select(caller, (self.PARENT_NEED,))
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(selection.value[0].residual_need, corrected)
        feedback = validation_error(caller.calls[1])
        self.assertIn("temporal scope", feedback)
        self.assertIn("2025-09-30", feedback)
        self.assertIn("by the prediction time", feedback)
        self.assertIn("guidance", feedback)

    def test_round22_historical_actuals_residual_accepted_with_actual_date(
        self,
    ):
        parent = (
            "What 2024 actual production and cost results and guidance "
            "changes were disclosed by the prediction time?"
        )
        residual = "Actual 2024 cost results are not fully covered."
        caller = ScriptedRoleCaller([self._partial_selection(residual)])
        selection = self._select(caller, (parent,))
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(selection.value[0].residual_need, residual)

    def test_capitalized_guidance_marker_lends_framing(self):
        parent = self.PARENT_NEED.replace("guidance", "Guidance")
        caller = ScriptedRoleCaller(
            [self._partial_selection(self.RAW_RESIDUAL)]
        )
        selection = self._select(caller, (parent,))
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(selection.value[0].residual_need, self.RAW_RESIDUAL)

    def test_evaluation_context_resets_between_cases(self):
        realized = (
            "Actual 2026 production and cost results for the remainder of "
            "2025 and 2026 are not fully covered."
        )
        bounded = (
            "Specific disclosed production and cost guidance figures for "
            "the remainder of 2025 and 2026 are not fully covered, by the "
            "prediction time."
        )
        caller = ScriptedRoleCaller(
            [
                self._partial_selection(realized),
                self._partial_selection(bounded),
                self._partial_selection(realized),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            agent = LLMSignalRetrievalAgent(caller)
            agent.set_evaluation_context(self.PREDICTION_TIME)
            first = agent.select((self.PARENT_NEED,), snapshot, {})
            self.assertEqual(len(caller.calls), 2)
            self.assertEqual(first.value[0].residual_need, bounded)
            agent.set_evaluation_context(
                datetime(2026, 9, 30, tzinfo=timezone.utc)
            )
            second = agent.select((self.PARENT_NEED,), snapshot, {})
            self.assertEqual(len(caller.calls), 3)
            self.assertEqual(second.value[0].residual_need, realized)
            self.assertEqual(
                caller.calls[2]["payload"]["evaluation_context"][
                    "prediction_time"
                ],
                "2026-09-30T00:00:00+00:00",
            )

    def test_naive_prediction_time_is_rejected(self):
        agent = LLMSignalRetrievalAgent(ScriptedRoleCaller([]))
        with self.assertRaises(ValidationError):
            agent.set_evaluation_context(datetime(2025, 9, 30))

    def test_unrelated_residual_still_rejected_as_ungrounded(self) -> None:
        unrelated = (
            "Specific disclosed cryptocurrency mining figures for 2027 are "
            "not fully covered."
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            caller = ScriptedRoleCaller(
                [self._partial_selection(unrelated)] * 3
            )
            caller.max_structured_corrections = 2
            events: list[dict[str, object]] = []
            caller.on_progress = events.append
            selection = LLMSignalRetrievalAgent(caller).select(
                (self.PARENT_NEED,), registry.freeze(), {},
            )
        feedback = validation_error(caller.calls[1])
        self.assertIn("grounded", feedback)
        self.assertEqual(
            selection.value[0].reason_code, "assess_applicability"
        )
        self.assertIsNone(selection.value[0].answer_scope)
        self.assertIsNone(selection.value[0].residual_need)
        self.assertEqual(
            next(
                item
                for item in events
                if item["event_type"] == "structured_validation_fallback_applied"
            )["context_only_paths"],
            ["selections[0]"],
        )


class RoutingAndPlanRoleTests(TestCase):
    def test_direct_ownership_conflicts_preserve_selected_signals_and_unique_full_owner(self):
        need = "What cash reserves and liquidity runway were disclosed?"
        for scopes in (("partial", "full"), ("partial", "partial"), ("full", "full")):
            with self.subTest(scopes=scopes), tempfile.TemporaryDirectory() as directory:
                registry = SignalRegistry(Path(directory) / "signals")
                registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
                rows = []
                for ref, scope in zip(("cash_reserves:v1", "financing_listing_action:v1"), scopes):
                    row = signal_selection(ref)["selections"][0]
                    row.update(answer_scope=scope, residual_need=("What liquidity runway was disclosed?" if scope == "partial" else None),
                               selection_reason="Measures disclosed cash reserves.")
                    rows.append(row)
                caller = ScriptedRoleCaller([{"selections": rows}])
                result = LLMSignalRetrievalAgent(caller).select((need,), registry.freeze(), {})
                self.assertEqual(len(caller.calls), 1)
                self.assertEqual(tuple(item.signal_ref for item in result.value), tuple(row["signal_ref"] for row in rows))
                self.assertEqual(tuple(item.target_need_indices for item in result.value), ((0,), (0,)))
                if scopes == ("partial", "full"):
                    self.assertEqual(result.value[1].reason_code, "answer_need")
                    self.assertEqual(result.value[1].selection_reason, rows[1]["selection_reason"])
                    self.assertEqual(result.value[1].answer_scope, "full")
                else:
                    self.assertTrue(all(item.reason_code == "assess_applicability" for item in result.value))
                self.assertEqual(result.value[0].reason_code, "assess_applicability")

    def test_conflict_repair_requires_typed_row_and_identity_authority(self):
        from stock_opportunity_agent.research.repair import is_mechanical_issue

        row = signal_selection("cash_reserves:v1")["selections"][0]
        for context, item_id, expected in (({}, row["signal_ref"], False),
                ({"mechanical_action": "context_only_selection"}, "wrong:v1", False),
                ({"mechanical_action": "context_only_selection"}, row["signal_ref"], True)):
            issue = ValidationIssue(code="routing_answer_conflict", message="arbitrary prose",
                paths=("selections[0]",), item_id=item_id, item_id_field="signal_ref", repair_context=context)
            self.assertEqual(is_mechanical_issue(issue), bool(context))
            result = _routing_context_only_fallback({"selections": [row]}, StructuredValidationError([issue]))
            self.assertEqual(result is not None, expected)

    def test_mixed_routing_correction_uses_latest_mechanical_base(self):
        need = "What cash reserves and liquidity runway were disclosed?"
        invalid = signal_selection("guidance_acceleration:v1")["selections"][0]
        invalid.update(reason_code="assess_applicability", expected_role="coverage",
                       answer_scope=None, selection_reason="")
        partial = signal_selection("cash_reserves:v1")["selections"][0]
        partial.update(answer_scope="partial", residual_need="What liquidity runway was disclosed?",
                       selection_reason="Measures disclosed cash reserves.")
        full = signal_selection("financing_listing_action:v1")["selections"][0]

        def correct_one_row(kwargs):
            contract = kwargs["payload"]["output_patch_contract"]
            base = kwargs["payload"]
            for part in contract["base_location"].split("."):
                base = base[part]
            self.assertEqual(base["selections"][1]["reason_code"], "assess_applicability")
            self.assertIsNone(base["selections"][1]["residual_need"])
            self.assertEqual(base["selections"][2], full)
            corrected = json.loads(json.dumps(base))
            corrected["selections"][0]["selection_reason"] = "Inspect disclosed management guidance."
            return corrected

        caller = ScriptedRoleCaller([{"selections": [invalid, partial, full]}, correct_one_row])
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            result = LLMSignalRetrievalAgent(caller).select((need,), registry.freeze(), {})
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(len(result.value), 3)
        self.assertEqual(result.value[1].reason_code, "assess_applicability")
        self.assertEqual(result.value[2].answer_scope, "full")

    def test_routing_context_fallback_uses_typed_issues_not_diagnostic_words(self):
        row = signal_selection("guidance_acceleration:v1")["selections"][0]
        original = {"selections": [row]}
        recovered = []
        for message in ("bad residual", "unrelated diagnostic wording", "语义声明未验证"):
            failure = StructuredValidationError([ValidationIssue(
                code="routing_answer_ownership_invalid",
                message=message,
                paths=("selections[0].selection_reason", "selections[0]"),
                item_id=row["signal_ref"],
                item_id_field="signal_ref",
            )])
            result = _routing_context_only_fallback(original, failure)
            self.assertIsNotNone(result)
            recovered.append(result[0])
        self.assertEqual(recovered[0], recovered[1])
        self.assertEqual(recovered[1], recovered[2])
        self.assertEqual(original["selections"][0]["reason_code"], "answer_need")
        self.assertEqual(recovered[0]["selections"][0]["signal_ref"], row["signal_ref"])
        self.assertEqual(
            recovered[0]["selections"][0]["target_need_indices"],
            row["target_need_indices"],
        )
        for code, item_id in (("routing_selection_invalid", row["signal_ref"]),
                              ("routing_answer_ownership_invalid", "other:v1")):
            failure = StructuredValidationError([ValidationIssue(
                code=code, message="bad residual", paths=("selections[0]",),
                item_id=item_id, item_id_field="signal_ref",
            )])
            self.assertIsNone(_routing_context_only_fallback(original, failure))

    def test_controller_and_progressive_signal_selector_use_structured_roles(self) -> None:
        controller_caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": ["commercialization may accelerate"],
                    "current_beliefs": [],
                    "supporting_evidence": [],
                    "contradictions": [],
                    "resolved_questions": [],
                    "open_questions": [],
                    "next_information_needs": ["revenue growth"],
                    "decision": "continue",
                }
            ]
        )
        state = LLMResearchController(controller_caller).initialize(
            default_information_plan(), {"industry": "fixture"}
        )
        self.assertEqual(state.value.next_information_needs, ("revenue growth",))
        self.assertEqual(controller_caller.stages, ["research_controller_initialize"])
        self.assertIn(
            '"next_information_needs"',
            str(controller_caller.calls[0]["system_prompt"]),
        )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            selector_caller = ScriptedRoleCaller(
                [
                    signal_selection("revenue_growth_yoy:v1"),
                ]
            )
            routing_state = ResearchState(
                hypotheses=("A mature operator may benefit from stronger pricing.",),
                current_beliefs=("The issuer operates established mature mines.",),
                supporting_evidence=(
                    ResearchEvidenceRef(
                        kind="basic_info",
                        claim="The issuer operates established mature mines.",
                        projection_id="projection_mature",
                        exact_text="Literal mature-operation source text.",
                    ),
                ),
                contradictions=("No pre-commercial product is currently evidenced.",),
                resolved_questions=("The operating stage is established.",),
                open_questions=("Can production grow further?",),
                next_information_needs=("revenue growth",),
            )
            selection = LLMSignalRetrievalAgent(selector_caller).select(
                ("revenue growth",),
                registry.freeze(),
                {"cash_reserves:v1": ("opaque-document-hash",)},
                research_state=routing_state,
            )
            self.assertEqual(
                tuple(item.signal_ref for item in selection.value),
                ("revenue_growth_yoy:v1",),
            )
            self.assertEqual(
                selector_caller.stages,
                ["signal_retrieval_cards"],
            )
            payload = selector_caller.calls[0]["payload"]
            cards = payload["available_signal_cards"]
            self.assertEqual(len(cards), 12)
            self.assertNotIn(
                "order_quality:v1",
                {card["signal_ref"] for card in cards},
            )
            self.assertNotIn(
                "customer_concentration:v1",
                {card["signal_ref"] for card in cards},
            )
            self.assertIn("category", cards[0])
            self.assertNotIn("learned_profile", cards[0])
            self.assertEqual(
                payload["learned_profile_default"],
                "no committed observations",
            )
            self.assertNotIn(
                "previous_signal_document_fingerprints",
                payload,
            )
            self.assertEqual(
                payload["research_context"],
                {
                    "hypotheses": list(routing_state.hypotheses),
                    "current_beliefs": list(routing_state.current_beliefs),
                    "contradictions": list(routing_state.contradictions),
                    "resolved_questions": list(routing_state.resolved_questions),
                    "open_questions": list(routing_state.open_questions),
                    "evidence_claims": [
                        "The issuer operates established mature mines."
                    ],
                },
            )
            self.assertNotIn("projection_mature", json.dumps(payload["research_context"]))
            self.assertNotIn(
                "Literal mature-operation source text.",
                json.dumps(payload["research_context"]),
            )
            self.assertIn(
                "use it only to test Signal applicability",
                selector_caller.calls[0]["system_prompt"],
            )
            self.assertTrue(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).startswith(
                    '{"available_signal_cards":'
                )
            )

    def test_signal_selector_repairs_invalid_refs_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    signal_selection("unknown:v1"),
                    signal_selection("revenue_growth_yoy:v1"),
                ]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                ("revenue growth",), registry.freeze(), {}
            )

            self.assertEqual(
                tuple(item.signal_ref for item in selection.value),
                ("revenue_growth_yoy:v1",),
            )
            self.assertEqual(selection.usage.llm_calls, 2)
            self.assertIn("outside supplied cards", validation_error(caller.calls[1]))

    def test_signal_selector_fails_closed_after_invalid_correction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    signal_selection("unknown:v1"),
                    {"selections": "still-not-an-array"},
                ]
            )

            with self.assertRaisesRegex(
                CandidateExecutionRejected,
                "failed validation after one correction",
            ) as context:
                LLMSignalRetrievalAgent(caller).select(
                    ("revenue growth",), registry.freeze(), {}
                )

            self.assertEqual(context.exception.usage.llm_calls, 2)
            self.assertEqual(
                caller.stages,
                [
                    "signal_retrieval_cards",
                    "signal_retrieval_cards_correction",
                ],
            )

    def test_structured_role_revalidates_one_fresh_recovery_correction(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    signal_selection("unknown:v1"),
                    {"selections": "still-not-an-array"},
                    signal_selection("revenue_growth_yoy:v1"),
                ]
            )
            caller.max_structured_corrections = 2

            selection = LLMSignalRetrievalAgent(caller).select(
                ("revenue growth",), registry.freeze(), {}
            )

        self.assertEqual(
            tuple(item.signal_ref for item in selection.value),
            ("revenue_growth_yoy:v1",),
        )
        self.assertEqual(selection.usage.llm_calls, 3)
        self.assertEqual(
            caller.stages,
            [
                "signal_retrieval_cards",
                "signal_retrieval_cards_correction",
                "signal_retrieval_cards_correction",
            ],
        )
        first_feedback = caller.calls[1]["payload"]["validation_feedback"]
        second_feedback = caller.calls[2]["payload"]["validation_feedback"]
        self.assertIn("outside supplied cards", first_feedback["validation_error"])
        self.assertEqual(
            second_feedback["invalid_output"],
            signal_selection("unknown:v1"),
        )
        self.assertIn(
            "outside supplied cards", second_feedback["validation_error"]
        )
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[2]["system_prompt"]
        )

    def test_signal_selector_repairs_non_array_containers_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    {"selections": "revenue_growth_yoy:v1"},
                    signal_selection("revenue_growth_yoy:v1"),
                ]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                ("revenue growth",), registry.freeze(), {}
            )

            self.assertEqual(
                tuple(item.signal_ref for item in selection.value),
                ("revenue_growth_yoy:v1",),
            )
            self.assertEqual(selection.usage.llm_calls, 2)

    def test_signal_selector_accepts_empty_no_match_without_correction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller([{"selections": []}])

            selection = LLMSignalRetrievalAgent(caller).select(
                ("unmatched need",), registry.freeze(), {}
            )

            self.assertEqual(selection.value, ())
            self.assertEqual(selection.usage.llm_calls, 1)
            self.assertEqual(
                caller.stages,
                ["signal_retrieval_cards"],
            )

    def test_v16_signal_selector_corrects_explicit_term_matched_empty(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/v16_empty_signal_routing.json"
            ).read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    fixture["invalid_output"],
                    signal_selection(fixture["corrected_signal_ref"]),
                ]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                tuple(fixture["information_needs"]), registry.freeze(), {}
            )

            self.assertEqual(
                tuple(item.signal_ref for item in selection.value),
                (fixture["corrected_signal_ref"],),
            )
            self.assertEqual(selection.usage.llm_calls, 2)
            self.assertIn(
                fixture["corrected_signal_ref"],
                validation_error(caller.calls[1]),
            )
            self.assertIn(
                "Returning the same rejected content",
                caller.calls[1]["system_prompt"],
            )

    def test_v21_signal_selector_corrects_version_owned_guidance_empty(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/v21_empty_guidance_routing.json"
            ).read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            caller = ScriptedRoleCaller(
                [
                    fixture["invalid_output"],
                    {
                        "selections": [
                            {
                                **signal_selection(
                                    fixture["corrected_signal_ref"]
                                )["selections"][0],
                                "selection_reason": (
                                    "Answers only the production and cost guidance "
                                    "updates facet."
                                ),
                                "answer_scope": "partial",
                                "residual_need": (
                                    "What risks could prevent achieving the 2.0 "
                                    "million oz target?"
                                ),
                            }
                        ]
                    },
                ]
            )

            selection = LLMSignalRetrievalAgent(caller).select(
                tuple(fixture["information_needs"]), registry.freeze(), {}
            )

        self.assertEqual(
            tuple(item.signal_ref for item in selection.value),
            (fixture["corrected_signal_ref"],),
        )
        guidance_card = next(
            item
            for item in caller.calls[0]["payload"]["available_signal_cards"]
            if item["signal_ref"] == fixture["corrected_signal_ref"]
        )
        self.assertIn(
            "guidance updates", guidance_card["routing_need_phrases"]
        )
        self.assertIn(
            "version-owned information-need phrase",
            validation_error(caller.calls[1]),
        )
        required_target = caller.calls[1]["payload"]["validation_feedback"][
            "obligations"
        ][0]["instruction"]
        self.assertIn("'answer_scope': 'partial'", required_target)
        self.assertIn("'residual_facet_candidates'", required_target)
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        stable_context = {
            key: value
            for key, value in caller.calls[0]["payload"].items()
            if key not in {"validation_feedback", "output_patch_contract"}
        }
        self.assertEqual(
            stable_context,
            {
                key: value
                for key, value in caller.calls[1]["payload"].items()
                if key not in {"validation_feedback", "output_patch_contract"}
            },
        )
        self.assertNotIn("output_patch_contract", caller.calls[0]["payload"])
        self.assertEqual(
            caller.calls[1]["payload"]["output_patch_contract"]["base_location"],
            "validation_feedback.invalid_output",
        )

    def test_v99_guidance_benchmark_does_not_force_empty_correction(self) -> None:
        target_need = (
            "What are Kinross Gold's latest quarterly production and cost figures, "
            "and how do they compare to the 2.0 million oz annual guidance?"
        )
        caller = ScriptedRoleCaller([{"selections": []}])

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                (target_need,), registry.freeze(), {}
            )

        self.assertEqual(selection.value, ())
        self.assertEqual(selection.usage.llm_calls, 1)
        guidance_card = next(
            item
            for item in caller.calls[0]["payload"]["available_signal_cards"]
            if item["signal_ref"] == "guidance_acceleration:v1"
        )
        self.assertNotIn("guidance", guidance_card["routing_need_phrases"])
        self.assertIn("guidance updates", guidance_card["routing_need_phrases"])

    def test_v101_partial_signal_id_phrase_does_not_force_empty(self) -> None:
        target_need = (
            "What are the company's plans for using sale-leaseback proceeds and "
            "operating cash flow to fund expansion?"
        )
        caller = ScriptedRoleCaller([{"selections": []}])

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                (target_need,), registry.freeze(), {}
            )

        self.assertEqual(selection.value, ())
        self.assertEqual(selection.usage.llm_calls, 1)
        cash_flow_card = next(
            item
            for item in caller.calls[0]["payload"]["available_signal_cards"]
            if item["signal_ref"] == "operating_cash_flow_margin:v1"
        )
        self.assertEqual(
            cash_flow_card["routing_answer_need_phrases"],
            ["operating cash flow margin"],
        )

    def test_signal_selector_corrects_version_owned_excluded_context_tag(self) -> None:
        incompatible = signal_selection("commercialization_status:v1")
        item = incompatible["selections"][0]
        item["applicability_hypothesis"] = (
            "This mature gold producer reflects ordinary operations."
        )
        item["context_tags"] = ["mature_operations", "materials"]
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([incompatible, {"selections": []}])

            selection = LLMSignalRetrievalAgent(caller).select(
                ("Clarify a new product transition for the mature producer.",),
                snapshot,
                {},
            )
            applicable_caller = ScriptedRoleCaller(
                [signal_selection("commercialization_status:v1")]
            )
            applicable = LLMSignalRetrievalAgent(applicable_caller).select(
                ("Check a new product's commercial transition.",),
                snapshot,
                {},
            )
            prior_caller = ScriptedRoleCaller([{"selections": []}])
            prior_classified = LLMSignalRetrievalAgent(prior_caller).select(
                ("Check whether a distinct new product became commercial.",),
                snapshot,
                {},
                prior_context_tags=("mature_operations",),
            )

        self.assertEqual(selection.value, ())
        self.assertEqual(selection.usage.llm_calls, 2)
        card = next(
            card
            for card in caller.calls[0]["payload"]["available_signal_cards"]
            if card["signal_ref"] == "commercialization_status:v1"
        )
        self.assertEqual(
            card["routing_excluded_context_tags"], ["mature_operations"]
        )
        self.assertIn(
            "version-owned routing exclusion", validation_error(caller.calls[1])
        )
        self.assertIn("mature_operations", validation_error(caller.calls[1]))
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertEqual(
            tuple(item.signal_ref for item in applicable.value),
            ("commercialization_status:v1",),
        )
        self.assertEqual(applicable.usage.llm_calls, 1)
        self.assertEqual(prior_classified.value, ())
        self.assertEqual(
            prior_caller.calls[0]["payload"]["previous_context_tags"],
            ["mature_operations"],
        )
        self.assertEqual(prior_classified.usage.llm_calls, 1)
        self.assertNotIn(
            "commercialization_status:v1",
            {
                card["signal_ref"]
                for card in prior_caller.calls[0]["payload"][
                    "available_signal_cards"
                ]
            },
        )

    def test_v63_order_quality_cannot_relabel_a_share_sale_as_an_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([{"selections": []}])

            rejected_analogy = LLMSignalRetrievalAgent(caller).select(
                (
                    "What are the specific terms and potential impact of the Asante "
                    "Gold share sale on the company's financial position?",
                ),
                snapshot,
                {},
                research_state=ResearchState(
                    hypotheses=("Gold prices may support further repricing.",),
                    next_information_needs=(
                        "Clarify the financial impact of the share sale.",
                    ),
                ),
            )
            applicable_caller = ScriptedRoleCaller(
                [signal_selection("order_quality:v1")]
            )
            applicable = LLMSignalRetrievalAgent(applicable_caller).select(
                (
                    "Are the disclosed customer purchase orders binding and likely "
                    "to convert to revenue?",
                ),
                snapshot,
                {},
            )

        self.assertEqual(rejected_analogy.value, ())
        self.assertEqual(rejected_analogy.usage.llm_calls, 1)
        self.assertNotIn(
            "order_quality:v1",
            {
                card["signal_ref"]
                for card in caller.calls[0]["payload"][
                    "available_signal_cards"
                ]
            },
        )
        self.assertEqual(
            tuple(item.signal_ref for item in applicable.value),
            ("order_quality:v1",),
        )
        self.assertEqual(applicable.usage.llm_calls, 1)
        self.assertIn(
            "Use reason_code=answer_need only when the description and measurement_scope directly",
            caller.calls[0]["system_prompt"],
        )
        self.assertIn("object, period, unit and comparison facet", caller.calls[0]["system_prompt"])
        self.assertIn("declared scope does not prove issuer data is available", caller.calls[0]["system_prompt"])

    def test_v66_mining_project_is_not_a_product_commercialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([{"selections": []}])

            rejected_project = LLMSignalRetrievalAgent(caller).select(
                (
                    "What are the latest updates on major mining projects like "
                    "Tasiast and Lobo-Marte?",
                ),
                snapshot,
                {},
            )
            applicable_caller = ScriptedRoleCaller(
                [signal_selection("commercialization_status:v1")]
            )
            applicable = LLMSignalRetrievalAgent(applicable_caller).select(
                (
                    "Has the prototype technology become a sellable repeatable "
                    "product?",
                ),
                snapshot,
                {},
            )

        self.assertEqual(rejected_project.value, ())
        self.assertEqual(rejected_project.usage.llm_calls, 1)
        self.assertNotIn(
            "commercialization_status:v1",
            {
                card["signal_ref"]
                for card in caller.calls[0]["payload"][
                    "available_signal_cards"
                ]
            },
        )
        self.assertEqual(
            tuple(item.signal_ref for item in applicable.value),
            ("commercialization_status:v1",),
        )
        self.assertEqual(applicable.usage.llm_calls, 1)

    def test_v68_customer_concentration_requires_an_existing_customer_object(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([{"selections": []}])

            rejected_analogy = LLMSignalRetrievalAgent(caller).select(
                (
                    "What is the gold price outlook and its effect on revenue and "
                    "profitability?",
                ),
                snapshot,
                {},
            )
            applicable_caller = ScriptedRoleCaller(
                [signal_selection("customer_concentration:v1")]
            )
            applicable = LLMSignalRetrievalAgent(applicable_caller).select(
                (
                    "Does one customer program account for most backlog and revenue?",
                ),
                snapshot,
                {},
            )

        self.assertEqual(rejected_analogy.value, ())
        self.assertEqual(rejected_analogy.usage.llm_calls, 1)
        self.assertNotIn(
            "customer_concentration:v1",
            {
                card["signal_ref"]
                for card in caller.calls[0]["payload"][
                    "available_signal_cards"
                ]
            },
        )
        self.assertEqual(
            tuple(item.signal_ref for item in applicable.value),
            ("customer_concentration:v1",),
        )
        self.assertEqual(applicable.usage.llm_calls, 1)

    def test_v70_customer_contract_need_is_not_concentration_answer_need(
        self,
    ) -> None:
        invalid = signal_selection("customer_concentration:v1")
        invalid_item = invalid["selections"][0]
        invalid_item["selection_reason"] = (
            "Directly assesses announced customer contracts and revenue significance."
        )
        invalid_item["applicability_hypothesis"] = (
            "Recent announcements may reveal customer concentration."
        )
        corrected = json.loads(json.dumps(invalid))
        corrected_item = corrected["selections"][0]
        corrected_item["reason_code"] = "combine_evidence"
        corrected_item["target_need_indices"] = []
        corrected_item["answer_scope"] = None
        corrected_item["residual_need"] = None
        corrected_item["selection_reason"] = (
            "Adds customer-dependence context but does not enumerate contracts."
        )
        corrected_item["expected_role"] = "confirmation"
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([invalid, corrected])

            contextual = LLMSignalRetrievalAgent(caller).select(
                (
                    "What specific customer contracts or partnerships has the "
                    "company announced in the last six months that could "
                    "significantly increase revenue?",
                ),
                snapshot,
                {},
            )
            direct_caller = ScriptedRoleCaller(
                [signal_selection("customer_concentration:v1")]
            )
            direct = LLMSignalRetrievalAgent(direct_caller).select(
                ("Does one customer account for most revenue?",),
                snapshot,
                {},
            )

        self.assertEqual(contextual.usage.llm_calls, 2)
        self.assertEqual(contextual.value[0].reason_code, "combine_evidence")
        error = validation_error(caller.calls[1])
        self.assertIn("reason_code=answer_need", error)
        self.assertIn("version-owned direct-need phrase", error)
        self.assertIn("combine_evidence", error)
        card = next(
            item
            for item in caller.calls[0]["payload"]["available_signal_cards"]
            if item["signal_ref"] == "customer_concentration:v1"
        )
        self.assertIn("one customer", card["routing_answer_need_phrases"])
        self.assertEqual(direct.value[0].reason_code, "answer_need")
        self.assertEqual(direct.usage.llm_calls, 1)

    def test_v71_routing_aggregates_target_and_applicability_errors(self) -> None:
        customer = signal_selection("customer_concentration:v1")["selections"][0]
        customer["reason_code"] = "combine_evidence"
        customer["target_need_indices"] = [1]
        customer["answer_scope"] = None
        customer["residual_need"] = None
        customer["selection_reason"] = (
            "Use customer concentration as context for revenue shortfall risk."
        )
        customer["applicability_hypothesis"] = (
            "Concentration may explain revenue volatility."
        )
        financing = signal_selection("financing_listing_action:v1")["selections"][0]
        financing["reason_code"] = "combine_evidence"
        financing["target_need_indices"] = [2]
        financing["answer_scope"] = None
        financing["residual_need"] = None
        financing["selection_reason"] = (
            "Use financing actions to assess capital expenditure funding."
        )
        financing["applicability_hypothesis"] = (
            "Financing may reveal how capital expenditure is funded."
        )
        revenue = signal_selection("revenue_growth_yoy:v1")["selections"][0]
        revenue["target_need_indices"] = [9]
        corrected_financing = json.loads(json.dumps(financing))
        invalid = {"selections": [customer, financing, revenue]}
        corrected = {"selections": [corrected_financing]}
        information_needs = (
            "What is the current membership count and quarterly growth rate?",
            "What are revenue projections and possible shortfall factors?",
            "What is capital expenditure and how is it funded?",
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            snapshot = registry.freeze()
            caller = ScriptedRoleCaller([invalid, corrected])

            selection = LLMSignalRetrievalAgent(caller).select(
                information_needs,
                snapshot,
                {},
                research_state=ResearchState(
                    current_beliefs=("Revenue growth remains uncertain.",),
                    next_information_needs=information_needs,
                ),
            )

        error = validation_error(caller.calls[1])
        self.assertNotIn("non-answer reason_code requires an empty", error)
        self.assertIn("selections[2].target_need_indices", error)
        self.assertIn("outside the supplied information_needs", error)
        self.assertIn("outside supplied cards", error)
        self.assertIn("customer_concentration:v1", error)
        self.assertEqual(selection.usage.llm_calls, 2)
        self.assertEqual(
            tuple(item.signal_ref for item in selection.value),
            ("financing_listing_action:v1",),
        )
        self.assertEqual(selection.value[0].target_need_indices, (2,))
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )

    def test_v74_routing_persists_partial_answer_residual(self) -> None:
        target_need = (
            "What is the current cash position and what share-buyback or strategic "
            "funding plans remain?"
        )
        residual_need = "What share-buyback or strategic funding plans remain?"
        output = signal_selection("cash_reserves:v1")
        item = output["selections"][0]
        item["selection_reason"] = "Answer only the current cash-position facet."
        item["answer_scope"] = "partial"
        item["residual_need"] = residual_need
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            caller = ScriptedRoleCaller([output])

            selection = LLMSignalRetrievalAgent(caller).select(
                (target_need,),
                registry.freeze(),
                {},
            )

        self.assertEqual(selection.value[0].answer_scope, "partial")
        self.assertEqual(selection.value[0].residual_need, residual_need)
        self.assertIn("answer_scope=full only", caller.calls[0]["system_prompt"])
        self.assertIn(
            "at most one answer_need selection per target",
            caller.calls[0]["system_prompt"],
        )
        self.assertIn(
            "required context_tags array containing zero to four values",
            caller.calls[0]["system_prompt"],
        )
        self.assertNotIn(
            "up to four context_tags",
            caller.calls[0]["system_prompt"],
        )

    def test_v87_routing_names_residual_only_terms_in_correction(self) -> None:
        information_needs = (
            "What is current revenue and EBITDA from operations?",
            "What is management's guidance for 2025 and 2026 regarding revenue, "
            "EBITDA, and capital expenditures?",
            "What are current analyst price targets?",
            "What is the current construction status?",
        )
        financing = signal_selection("financing_listing_action:v1")[
            "selections"
        ][0]
        financing.pop("context_tags")
        financing["reason_code"] = "combine_evidence"
        financing["expected_role"] = "coverage"
        financing["target_need_indices"] = [3]
        financing["answer_scope"] = None
        financing["residual_need"] = None
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance.pop("context_tags")
        guidance["target_need_indices"] = [1]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = (
            "What are the numerical ranges for 2025 and 2026 revenue, EBITDA, "
            "and capital expenditures?"
        )
        guidance["selection_reason"] = (
            "Directly addresses management guidance regarding revenue, EBITDA, "
            "and capital expenditures."
        )
        corrected_financing = json.loads(json.dumps(financing))
        corrected_financing["context_tags"] = ["capital_intensive"]
        corrected_guidance = json.loads(json.dumps(guidance))
        corrected_guidance["context_tags"] = ["general"]
        corrected_guidance["selection_reason"] = (
            "Checks whether management issued fresh guidance that strengthened "
            "the growth path."
        )
        caller = ScriptedRoleCaller(
            [
                {"selections": [financing, guidance]},
                {"selections": [corrected_financing, corrected_guidance]},
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                information_needs,
                registry.freeze(),
                {},
                research_state=ResearchState(
                    next_information_needs=information_needs
                ),
            )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        overlap_obligation = next(
            item
            for item in feedback["obligations"]
            if "claims a facet retained" in item["instruction"]
        )
        self.assertEqual(
            overlap_obligation["must_change_paths"],
            ["selections[1].selection_reason", "selections[1]"],
        )
        self.assertEqual(
            overlap_obligation["remove_terms_from_selection_reason"],
            ["revenue", "ebitda", "capital", "expenditure"],
        )
        self.assertIn(
            "Remove every listed residual-only term",
            overlap_obligation["instruction"],
        )
        self.assertEqual(
            selection.value[1].selection_reason,
            corrected_guidance["selection_reason"],
        )

    def test_v87_routing_catches_reordered_residual_scope(self) -> None:
        target_need = (
            "What is production and cost guidance for 2025-2026, and what are "
            "the updates on growth projects?"
        )
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance["target_need_indices"] = [0]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = (
            "What are the specific updates on growth projects for 2025-2026?"
        )
        guidance["selection_reason"] = (
            "Directly covers production and cost guidance for 2025-2026 and "
            "growth project updates."
        )
        corrected = json.loads(json.dumps(guidance))
        corrected["selection_reason"] = (
            "Answers only the production and cost guidance facet."
        )
        caller = ScriptedRoleCaller(
            [{"selections": [guidance]}, {"selections": [corrected]}]
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                (target_need,),
                registry.freeze(),
                {},
                research_state=ResearchState(
                    next_information_needs=(target_need,)
                ),
            )

        overlap_obligation = next(
            item
            for item in caller.calls[1]["payload"]["validation_feedback"][
                "obligations"
            ]
            if "claims a facet retained" in item["instruction"]
        )
        self.assertEqual(
            overlap_obligation["remove_terms_from_selection_reason"],
            ["growth", "project", "update"],
        )
        self.assertEqual(
            selection.value[0].selection_reason,
            corrected["selection_reason"],
        )

    def test_v95_routing_catches_reordered_period_qualified_scope(self) -> None:
        target_need = (
            "What is the company's current production guidance for the remainder "
            "of 2025 and 2026, and any updates on regional operations?"
        )
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance["target_need_indices"] = [0]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = (
            "What are the specific updates on regional operations and any changes "
            "to 2025-2026 production guidance?"
        )
        guidance["selection_reason"] = (
            "Directly addresses current production guidance for 2025-2026."
        )
        corrected = json.loads(json.dumps(guidance))
        corrected["residual_need"] = (
            "What are the specific updates on regional operations?"
        )
        caller = ScriptedRoleCaller(
            [{"selections": [guidance]}, {"selections": [corrected]}]
        )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                (target_need,),
                registry.freeze(),
                {},
                research_state=ResearchState(
                    next_information_needs=(target_need,)
                ),
            )

        residual_obligation = next(
            item
            for item in caller.calls[1]["payload"]["validation_feedback"][
                "obligations"
            ]
            if "retain the target cosmetically" in item["instruction"]
        )
        self.assertEqual(
            residual_obligation["residual_facet_candidates"],
            ["any updates on regional operations"],
        )
        self.assertEqual(
            selection.value[0].residual_need,
            corrected["residual_need"],
        )

    def test_v98_cosmetic_residual_uses_unanswered_target_clause(self) -> None:
        target_need = (
            "What are Kinross Gold's specific production and cost guidance for "
            "2025-2026, and any updates on Tasiast mill restart timeline?"
        )
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance.pop("context_tags")
        guidance["target_need_indices"] = [0]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = target_need
        guidance["selection_reason"] = (
            "Directly covers Kinross's production and cost guidance for 2025-2026, "
            "including Tasiast mill restart timeline updates."
        )
        corrected = json.loads(json.dumps(guidance))
        corrected["context_tags"] = ["general"]
        corrected["residual_need"] = (
            "What updates are available on the Tasiast mill restart timeline?"
        )
        corrected["selection_reason"] = (
            "Directly covers production and cost guidance for 2025-2026."
        )
        caller = ScriptedRoleCaller(
            [{"selections": [guidance]}, {"selections": [corrected]}]
        )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                (target_need,),
                registry.freeze(),
                {},
                research_state=ResearchState(
                    next_information_needs=(target_need,)
                ),
            )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        shape_obligation = next(
            item
            for item in feedback["obligations"]
            if "requires exactly" in item["instruction"]
        )
        self.assertEqual(
            shape_obligation["must_change_paths"],
            ["selections[0].context_tags"],
        )
        residual_obligation = next(
            item
            for item in feedback["obligations"]
            if "retain the target cosmetically" in item["instruction"]
        )
        self.assertEqual(
            residual_obligation["residual_facet_candidates"],
            ["any updates on Tasiast mill restart timeline"],
        )
        scope_obligation = next(
            item
            for item in feedback["obligations"]
            if "claims a facet retained" in item["instruction"]
        )
        self.assertEqual(
            scope_obligation["remove_terms_from_selection_reason"],
            ["tasiast", "mill", "restart", "timeline"],
        )
        self.assertNotIn(
            "s", scope_obligation["remove_terms_from_selection_reason"]
        )
        self.assertEqual(
            feedback["required_change_paths"],
            [
                "selections[0].context_tags",
                "selections[0].residual_need",
                "selections[0]",
                "selections[0].selection_reason",
            ],
        )
        self.assertEqual(
            selection.value[0].residual_need,
            corrected["residual_need"],
        )

    def test_v100_one_word_scope_change_is_cosmetic(self) -> None:
        target_need = (
            "What are Kinross Gold's latest production and cost guidance updates "
            "for 2025-2027?"
        )
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance["target_need_indices"] = [0]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = (
            "What are Kinross Gold's latest production and cost guidance for "
            "2025-2027?"
        )
        guidance["selection_reason"] = (
            "Directly covers the production and cost guidance updates for "
            "2025-2027."
        )
        corrected = json.loads(json.dumps(guidance))
        corrected["answer_scope"] = "full"
        corrected["residual_need"] = None
        caller = ScriptedRoleCaller(
            [{"selections": [guidance]}, {"selections": [corrected]}]
        )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                (target_need,), registry.freeze(), {}
            )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        cosmetic_obligation = next(
            item
            for item in feedback["obligations"]
            if "retain the target cosmetically" in item["instruction"]
        )
        self.assertEqual(
            cosmetic_obligation["must_change_paths"],
            [
                "selections[0].residual_need",
                "selections[0].answer_scope",
                "selections[0]",
            ],
        )
        self.assertNotIn("residual_facet_candidates", cosmetic_obligation)
        self.assertEqual(selection.value[0].answer_scope, "full")
        self.assertIsNone(selection.value[0].residual_need)

    def test_v104_partial_residual_may_remove_one_complete_direct_facet(self) -> None:
        target_need = (
            "What specific fiscal 2025 guidance and Q1 fiscal 2025 revenue and "
            "active client figures were disclosed by SFIX as of 2025-05-30?"
        )
        residual = (
            "What specific Q1 fiscal 2025 revenue and active client figures were "
            "disclosed by SFIX as of 2025-05-30?"
        )
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance["target_need_indices"] = [0]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = residual
        guidance["selection_reason"] = (
            "Directly covers fiscal 2025 guidance disclosed by SFIX as of "
            "2025-05-30."
        )
        guidance["applicability_hypothesis"] = (
            "The accepted research context names a fiscal 2025 guidance update."
        )
        caller = ScriptedRoleCaller([{"selections": [guidance]}])

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                (target_need,), registry.freeze(), {}
            )

        self.assertEqual(selection.usage.llm_calls, 1)
        self.assertEqual(selection.value[0].answer_scope, "partial")
        self.assertEqual(selection.value[0].residual_need, residual)

    def test_v91_routing_allows_shared_topic_but_not_residual_year(self) -> None:
        target_need = (
            "What are the company's production and cost guidance for 2025 and "
            "2026?"
        )
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance.pop("context_tags")
        guidance["target_need_indices"] = [0]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = (
            "What are the company's production and cost guidance for 2026?"
        )
        guidance["selection_reason"] = (
            "Directly covers production and cost guidance for 2025 and 2026."
        )
        corrected = json.loads(json.dumps(guidance))
        corrected["context_tags"] = ["general"]
        corrected["selection_reason"] = (
            "Directly covers production and cost guidance for 2025."
        )
        caller = ScriptedRoleCaller(
            [{"selections": [guidance]}, {"selections": [corrected]}]
        )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                (target_need,),
                registry.freeze(),
                {},
                research_state=ResearchState(
                    next_information_needs=(target_need,)
                ),
            )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        scope_obligation = next(
            item
            for item in feedback["obligations"]
            if "explicit alternative facets" in item["instruction"]
        )
        self.assertEqual(
            scope_obligation["remove_terms_from_selection_reason"],
            ["2026"],
        )
        self.assertIn("selections[0]", scope_obligation["must_change_paths"])
        self.assertTrue(
            all(item["must_change_paths"] for item in feedback["obligations"])
        )
        self.assertEqual(
            selection.value[0].selection_reason,
            corrected["selection_reason"],
        )

    def test_routing_removes_answer_ownership_and_preserves_valid_siblings(
        self,
    ) -> None:
        information_needs = (
            "What specific management guidance or forward-looking statements were "
            "disclosed in the Q2 2025 earnings call or 10-Q regarding expected user "
            "growth, revenue, or cost savings?",
            "What restructuring actions were disclosed?",
            "What legal risks were disclosed?",
        )
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance["target_need_indices"] = [0]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = (
            "What specific management guidance or forward-looking statements were "
            "disclosed in the Q2 2025 earnings call or 10-Q regarding cost savings?"
        )
        guidance["selection_reason"] = (
            "Directly covers Q2 2025 earnings call disclosures on user growth, "
            "revenue, or cost savings."
        )
        financing = signal_selection("financing_listing_action:v1")["selections"][0]
        financing.update(
            {
                "reason_code": "combine_evidence",
                "selection_reason": "Provides restructuring context.",
                "expected_role": "coverage",
                "target_need_indices": [1],
                "answer_scope": None,
                "residual_need": None,
            }
        )
        negative = signal_selection("negative_word_count:v1")["selections"][0]
        negative.update(
            {
                "reason_code": "combine_evidence",
                "selection_reason": "Provides legal-risk context.",
                "expected_role": "coverage",
                "target_need_indices": [2],
                "answer_scope": None,
                "residual_need": None,
                "context_tags": ["news_rich"],
            }
        )
        invalid = {"selections": [guidance, financing, negative]}
        caller = ScriptedRoleCaller(
            [json.loads(json.dumps(invalid)) for _index in range(3)]
        )
        caller.max_structured_corrections = 2
        events: list[dict[str, object]] = []
        caller.on_progress = events.append

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                information_needs,
                registry.freeze(),
                {},
                research_state=ResearchState(
                    next_information_needs=information_needs
                ),
            )

        self.assertEqual(selection.usage.llm_calls, 3)
        self.assertEqual(
            tuple(item.signal_ref for item in selection.value),
            ("guidance_acceleration:v1", "financing_listing_action:v1", "negative_word_count:v1"),
        )
        self.assertEqual(selection.value[0].reason_code, "assess_applicability")
        self.assertIsNone(selection.value[0].answer_scope)
        self.assertIsNone(selection.value[0].residual_need)
        self.assertEqual(selection.value[1].selection_reason, financing["selection_reason"])
        self.assertEqual(selection.value[2].selection_reason, negative["selection_reason"])
        self.assertEqual(
            next(
                item
                for item in events
                if item["event_type"] == "structured_validation_fallback_applied"
            )["context_only_paths"],
            ["selections[0]"],
        )

    def test_routing_context_only_fallback_preserves_paid_usage_on_budget_stop(
        self,
    ) -> None:
        information_needs = (
            "What guidance was disclosed regarding revenue and cost savings?",
            "What legal risks were disclosed?",
        )
        invalid = signal_selection("guidance_acceleration:v1")["selections"][0]
        invalid.update(
            {
                "target_need_indices": [0],
                "answer_scope": "partial",
                "residual_need": (
                    "What guidance was disclosed regarding cost savings?"
                ),
                "selection_reason": (
                    "Covers guidance regarding revenue and cost savings."
                ),
            }
        )
        valid = signal_selection("negative_word_count:v1")["selections"][0]
        valid.update(
            {
                "reason_code": "combine_evidence",
                "selection_reason": "Provides legal-risk context.",
                "expected_role": "coverage",
                "target_need_indices": [1],
                "answer_scope": None,
                "residual_need": None,
                "context_tags": ["news_rich"],
            }
        )

        class BudgetCaller(ScriptedRoleCaller):
            max_structured_corrections = 2

            def complete_json(self, **kwargs):
                if self.calls:
                    self.stages.append(str(kwargs["stage"]))
                    self.calls.append(dict(kwargs))
                    raise RuntimeBudgetExceeded("correction envelope is unavailable")
                return super().complete_json(**kwargs)

        caller = BudgetCaller([{"selections": [invalid, valid]}])
        events: list[dict[str, object]] = []
        caller.on_progress = events.append
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                information_needs,
                registry.freeze(),
                {},
                research_state=ResearchState(
                    next_information_needs=information_needs
                ),
            )

        self.assertEqual(selection.usage, AgentUsage(llm_calls=1, tokens=5, cost=0.01))
        self.assertEqual(
            tuple(item.signal_ref for item in selection.value),
            ("guidance_acceleration:v1", "negative_word_count:v1"),
        )
        fallback = next(
            item
            for item in events
            if item["event_type"] == "structured_validation_fallback_applied"
        )
        self.assertEqual(fallback["correction_count"], 0)
        self.assertEqual(fallback["removed_paths"], [])
        self.assertEqual(fallback["context_only_paths"], ["selections[0]"])

    def test_routing_context_only_fallback_keeps_mandatory_signal_without_answer_claim(
        self,
    ) -> None:
        target_need = (
            "What guidance updates were disclosed in the Q2 earnings call regarding "
            "revenue or cost savings?"
        )
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance["target_need_indices"] = [0]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = (
            "What was disclosed in the Q2 earnings call regarding cost savings?"
        )
        guidance["selection_reason"] = (
            "Directly covers guidance updates in the Q2 earnings call regarding cost "
            "savings."
        )
        invalid = {"selections": [guidance]}
        caller = ScriptedRoleCaller(
            [json.loads(json.dumps(invalid)) for _index in range(3)]
        )
        caller.max_structured_corrections = 2

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selected = LLMSignalRetrievalAgent(caller).select(
                (target_need,),
                registry.freeze(),
                {},
            )

        self.assertEqual(len(caller.calls), 3)
        self.assertEqual(len(selected.value), 1)
        self.assertEqual(selected.value[0].signal_ref, "guidance_acceleration:v1")
        self.assertEqual(selected.value[0].reason_code, "assess_applicability")
        self.assertIsNone(selected.value[0].answer_scope)
        self.assertIsNone(selected.value[0].residual_need)
        transition = _reflection_need_transition_contract(
            ResearchState(next_information_needs=(target_need,)),
            selected.value,
            SignalBatchResult(results=(), signal_calls=0),
        )
        self.assertEqual(transition["need_rules"][0]["required_transition"], "preserve_exactly")
        self.assertEqual(transition["need_rules"][0]["available_answer_actions"], [])

    def test_v77_routing_aggregates_semantics_behind_missing_tags(self) -> None:
        information_needs = (
            "What are the latest analyst earnings estimates and revisions?",
            "What is the current gold price trend and forecast?",
            "Are there recent insider or institutional purchases?",
            "What is the current production guidance and any updates on project "
            "timelines?",
            "What are the key customer-related operational risks, such as "
            "geopolitical issues or cost inflation?",
        )
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance.pop("context_tags")
        guidance["target_need_indices"] = [3]
        guidance["answer_scope"] = "partial"
        guidance["residual_need"] = information_needs[0]
        guidance["selection_reason"] = (
            "Answer the production-guidance facet and retain project timelines."
        )
        customer = signal_selection("customer_concentration:v1")["selections"][0]
        customer.pop("context_tags")
        customer["target_need_indices"] = [4]
        customer["answer_scope"] = "partial"
        customer["residual_need"] = information_needs[4]
        customer["selection_reason"] = (
            "Treat customer concentration as a general operational risk."
        )
        corrected_guidance = json.loads(json.dumps(guidance))
        corrected_guidance["context_tags"] = ["general"]
        corrected_guidance["residual_need"] = (
            "What updates are there on project timelines?"
        )
        caller = ScriptedRoleCaller(
            [
                {"selections": [guidance, customer]},
                {"selections": [corrected_guidance]},
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selection = LLMSignalRetrievalAgent(caller).select(
                information_needs,
                registry.freeze(),
                {},
                research_state=ResearchState(
                    next_information_needs=information_needs
                ),
            )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        error = feedback["validation_error"]
        self.assertIn("selections[0] requires exactly", error)
        self.assertIn("selections[0].residual_need must be grounded", error)
        self.assertIn("selections[1] requires exactly", error)
        self.assertIn("selections[1].residual_need must remove", error)
        self.assertNotIn("version-owned required research context", error)
        self.assertIn("version-owned direct-need phrase", error)
        must_change_paths = {
            path
            for obligation in feedback["obligations"]
            for path in obligation["must_change_paths"]
        }
        self.assertIn("selections[0].residual_need", must_change_paths)
        self.assertIn("selections[1].residual_need", must_change_paths)
        self.assertEqual(selection.value[0].signal_ref, "guidance_acceleration:v1")
        self.assertEqual(
            selection.value[0].residual_need,
            "What updates are there on project timelines?",
        )

    def test_v78_empty_routing_feedback_names_target_before_bad_correction(
        self,
    ) -> None:
        information_needs = (
            "What regulatory milestones are required for the resort?",
            "What is current construction progress and cost?",
            "What is expected customer traffic and revenue contribution?",
            "Are there earnings guidance updates for first-year revenue?",
        )
        bad_guidance = signal_selection("guidance_acceleration:v1")[
            "selections"
        ][0]
        bad_guidance.pop("context_tags")
        bad_guidance["target_need_indices"] = [3]
        bad_guidance["answer_scope"] = "partial"
        bad_guidance["residual_need"] = information_needs[2]
        caller = ScriptedRoleCaller(
            [{"selections": []}, {"selections": [bad_guidance]}]
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            with self.assertRaises(CandidateExecutionRejected) as raised:
                LLMSignalRetrievalAgent(caller).select(
                    information_needs,
                    registry.freeze(),
                    {},
                )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligation_count"], 1)
        self.assertEqual(
            feedback["obligations"][0]["must_change_paths"], ["selections"]
        )
        self.assertIn("'target_need_index': 3", feedback["validation_error"])
        self.assertIn(
            "'matched_phrases': ['guidance updates']",
            feedback["validation_error"],
        )
        self.assertIn(
            "must not copy a different information_needs item",
            caller.calls[0]["system_prompt"],
        )
        self.assertIn("missing=['context_tags']", str(raised.exception))
        self.assertIn("residual_need must be grounded", str(raised.exception))

    def test_v78_partial_reason_cannot_claim_the_residual_facet(self) -> None:
        target_need = (
            "What are the latest production and cost guidance for 2025-2027, and "
            "any updates on Tasiast mill restart?"
        )
        invalid = signal_selection("guidance_acceleration:v1")
        invalid_item = invalid["selections"][0]
        invalid_item["answer_scope"] = "partial"
        invalid_item["residual_need"] = (
            "What are the latest Tasiast mill restart timeline updates and their "
            "impact on production?"
        )
        invalid_item["selection_reason"] = (
            "Covers production and cost guidance, including Tasiast mill restart "
            "impact."
        )
        corrected = json.loads(json.dumps(invalid))
        corrected["selections"][0]["selection_reason"] = (
            "Covers only the production and cost guidance facet."
        )
        caller = ScriptedRoleCaller([invalid, corrected])
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            selected = LLMSignalRetrievalAgent(caller).select(
                (target_need,), registry.freeze(), {}
            )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn(
            "selections[0].selection_reason claims a facet retained",
            feedback["validation_error"],
        )
        self.assertIn("'tasiast mill restart'", feedback["validation_error"])
        self.assertIn(
            "selections[0].selection_reason",
            {
                path
                for obligation in feedback["obligations"]
                for path in obligation["must_change_paths"]
            },
        )
        self.assertEqual(selected.value[0].selection_reason, corrected["selections"][0]["selection_reason"])

    def test_signal_selector_exposes_only_eligible_unexecuted_cards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller([{"selections": []}])
            prior_result = {
                "signal_id": "cash_reserves",
                "version": 1,
                "state": {"value": "positive", "confidence": 0.8},
                "interpretation": {"summary": "Cash remained ample."},
                "evidence": {
                    "supporting": [
                        {
                            "document_id": "private-document-id",
                            "exact_span": "A long literal must remain local.",
                            "timestamp": "2025-01-01T00:00:00+00:00",
                        }
                    ],
                    "counter": [],
                },
                "status": {"coverage": "sufficient"},
            }

            selection = LLMSignalRetrievalAgent(caller).select(
                ("revenue growth",),
                registry.freeze(),
                {"cash_reserves:v1": ("doc:hash",)},
                {"cash_reserves:v1": prior_result},
                ("revenue_growth_yoy:v1",),
            )

            self.assertEqual(selection.value, ())
            self.assertEqual(selection.usage.llm_calls, 1)
            payload = caller.calls[0]["payload"]
            self.assertEqual(
                [
                    card["signal_ref"]
                    for card in payload["available_signal_cards"]
                ],
                ["revenue_growth_yoy:v1"],
            )
            self.assertEqual(
                payload["previous_signal_results"]["cash_reserves:v1"],
                {
                    "signal_id": "cash_reserves",
                    "version": 1,
                    "state": {"value": "positive", "confidence": 0.8},
                    "interpretation": {"summary": "Cash remained ample."},
                    "status": {"coverage": "sufficient"},
                },
            )

    def test_signal_selector_skips_model_when_no_eligible_cards_remain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            caller = ScriptedRoleCaller([])

            selection = LLMSignalRetrievalAgent(caller).select(
                ("anything new",),
                registry.freeze(),
                {},
                {},
                (),
            )

            self.assertEqual(selection.value, ())
            self.assertEqual(selection.usage.llm_calls, 0)
            self.assertEqual(caller.stages, [])

    def test_soft_signal_apply_chain_retrieves_executes_and_reflects_once(self) -> None:
        as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(
            document_id="filing-guidance-1",
            company_id="issuer-1",
            source_type="filing",
            published_at=as_of,
            available_at=as_of,
            content="Management raised full-year revenue guidance to 40 percent growth.",
        )
        signal_output = {
            "signal_id": "guidance_acceleration",
            "version": 1,
            "state": {"value": "positive", "confidence": 0.9},
            "interpretation": {"summary": "Management materially raised guidance."},
            "evidence": {
                "supporting": [
                    {
                        "document_id": document.document_id,
                        "exact_span": document.content,
                        "timestamp": as_of.isoformat(),
                    }
                ],
                "counter": [],
            },
            "status": {"coverage": "sufficient"},
        }
        reflected_state = {
            "hypotheses": ["guidance is accelerating"],
            "current_beliefs": ["the source supports acceleration"],
            "supporting_evidence": [
                {
                    "kind": "signal",
                    "claim": "Management materially raised guidance.",
                    "signal_ref": "guidance_acceleration",
                    "evidence_group": "supporting",
                    "evidence_index": 0,
                    "projection_id": document.document_id,
                    "exact_text": document.content,
                }
            ],
            "contradictions": [],
            "resolved_questions": ["did management raise guidance"],
            "open_questions": [],
            "next_information_needs": [],
            "decision": "finalize",
            "need_dispositions": [{"need_index": 0, "answer_scope": "full", "residual_need": None,
                "evidence_refs": [{"signal_ref": "guidance_acceleration:v1", "evidence_group": "supporting", "evidence_index": 0}],
                "reason": "The disclosed guidance increase answers whether management raised guidance."}],
        }

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs" / "signals_v1.json")
            snapshot = registry.freeze()
            selector_caller = ScriptedRoleCaller(
                [signal_selection("guidance_acceleration:v1")]
            )
            signal_caller = ScriptedRoleCaller([signal_output])
            controller_caller = ScriptedRoleCaller([reflected_state])

            selected = LLMSignalRetrievalAgent(selector_caller).select(
                ("did management raise guidance",),
                snapshot,
                {},
                {},
                ("guidance_acceleration:v1",),
            )
            batch = SignalExecutor(
                snapshot,
                RawInfoStore(documents=(document,)),
                llm_runner=StructuredLLMSignalRunner(signal_caller),
            ).execute_batch(
                tuple(item.signal_ref for item in selected.value),
                company_id="issuer-1",
                as_of=as_of,
            )
            controller = LLMResearchController(controller_caller)
            controller.set_reflection_runtime_context(selections=selected.value, must_finalize=False, termination_trigger=None)
            reflected = controller.reflect(
                default_information_plan(),
                ResearchState(
                    hypotheses=("guidance may be accelerating",),
                    next_information_needs=("did management raise guidance",),
                ),
                batch,
            )

            self.assertEqual(selector_caller.stages, ["signal_retrieval_cards"])
            self.assertEqual(signal_caller.stages, ["llm_signal_batch_execute"])
            self.assertEqual(
                controller_caller.stages,
                ["research_controller_reflect"],
            )
            self.assertEqual(batch.signal_calls, 1)
            self.assertEqual(batch.results[0].value, SignalValue.POSITIVE)
            self.assertEqual(
                batch.results[0].supporting_evidence[0].exact_span,
                document.content,
            )
            self.assertEqual(reflected.value.decision, ResearchDecision.FINALIZE)
            self.assertEqual(
                set(reflected.value.to_dict()["supporting_evidence"][0]),
                {
                    "kind",
                    "claim",
                    "signal_ref",
                    "evidence_group",
                    "evidence_index",
                },
            )
            self.assertEqual(
                reflected.value.to_dict()["supporting_evidence"][0]["signal_ref"],
                "guidance_acceleration:v1",
            )
            self.assertEqual(
                controller_caller.calls[0]["payload"]["signal_batch"][0][
                    "signal_ref"
                ],
                "guidance_acceleration:v1",
            )

    def test_reflect_correction_names_exact_valid_signal_evidence_indices(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests"
                / "fixtures"
                / "evolution_runtime"
                / "v4_reflect_unknown_signal_evidence_index.json"
            ).read_text(encoding="utf-8")
        )
        invalid_output = {**fixture["invalid_output"], "need_dispositions": []}
        invalid_output["next_information_needs"] = ["confirm sustainability"]
        corrected_output = json.loads(json.dumps(invalid_output))
        corrected_output["supporting_evidence"][1]["evidence_index"] = 0
        timestamp = datetime(2025, 9, 30, tzinfo=timezone.utc)
        evidence = SignalEvidence(
            document_id="market-data-1",
            exact_span="price_momentum_126d=0.951161; max_drawdown_1y=-0.16",
            timestamp=timestamp,
        )
        batch = SignalBatchResult(
            results=(
                SignalResult(
                    signal_id="max_drawdown_1y",
                    version=1,
                    value=SignalValue.POSITIVE,
                    confidence=1.0,
                    interpretation="max_drawdown_1y=-0.16",
                    supporting_evidence=(evidence,),
                ),
                SignalResult(
                    signal_id="price_momentum_126d",
                    version=1,
                    value=SignalValue.POSITIVE,
                    confidence=1.0,
                    interpretation="price_momentum_126d=0.951161",
                    supporting_evidence=(evidence,),
                ),
            ),
            signal_calls=2,
        )
        caller = ScriptedRoleCaller([invalid_output, corrected_output])

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(),
            ResearchState(next_information_needs=("confirm sustainability",)),
            batch,
        )

        expected_catalog = [
            {
                "signal_ref": "max_drawdown_1y:v1",
                "supporting_evidence_indices": [0],
                "counter_evidence_indices": [],
            },
            {
                "signal_ref": "price_momentum_126d:v1",
                "supporting_evidence_indices": [0],
                "counter_evidence_indices": [],
            },
        ]
        self.assertEqual(
            caller.stages,
            ["research_controller_reflect", "research_controller_reflect_correction"],
        )
        self.assertEqual(
            caller.calls[0]["payload"]["signal_evidence_ref_catalog"],
            expected_catalog,
        )
        correction_payload = caller.calls[1]["payload"]
        self.assertEqual(
            correction_payload["signal_evidence_ref_catalog"], expected_catalog
        )
        error = validation_error(caller.calls[1])
        self.assertIn("supporting_evidence[1]", error)
        self.assertIn("max_drawdown_1y:v1", error)
        self.assertIn("evidence_index=1", error)
        self.assertIn("valid_evidence_indices=[0]", error)
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        self.assertNotIn("validation_error", correction_payload)
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertEqual(
            reflected.value.supporting_evidence[1].evidence_index,
            0,
        )

        failing_caller = ScriptedRoleCaller([invalid_output, invalid_output])
        with self.assertRaises(CandidateExecutionRejected):
            LLMResearchController(failing_caller).reflect(
                default_information_plan(),
                ResearchState(next_information_needs=("confirm sustainability",)),
                batch,
            )
        self.assertEqual(
            failing_caller.stages,
            ["research_controller_reflect", "research_controller_reflect_correction"],
        )

    def test_reflect_correction_names_malformed_retained_basic_ref_fields(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests"
                / "fixtures"
                / "evolution_runtime"
                / "v5_reflect_malformed_retained_basic_ref.json"
            ).read_text(encoding="utf-8")
        )
        invalid_output = {**fixture["invalid_output"], "need_dispositions": []}
        corrected_output = json.loads(json.dumps(invalid_output))
        corrected_output["supporting_evidence"] = [fixture["prior_evidence_ref"]]
        previous = ResearchState(
            supporting_evidence=(
                ResearchEvidenceRef.from_dict(fixture["prior_evidence_ref"]),
            ),
            next_information_needs=("clarify revenue",),
        )
        batch = SignalBatchResult(
            results=(
                SignalResult(
                    signal_id="revenue_growth_yoy",
                    version=1,
                    value=SignalValue.UNAVAILABLE,
                    confidence=0.0,
                    interpretation="Revenue inputs are unavailable.",
                    coverage=SignalCoverage.UNAVAILABLE,
                ),
                SignalResult(
                    signal_id="operating_cash_flow_margin",
                    version=1,
                    value=SignalValue.UNAVAILABLE,
                    confidence=0.0,
                    interpretation="Cash-flow inputs are unavailable.",
                    coverage=SignalCoverage.UNAVAILABLE,
                ),
            ),
            signal_calls=2,
        )
        caller = ScriptedRoleCaller([invalid_output, corrected_output])

        reflected = LLMResearchController(caller).reflect(
            default_information_plan(), previous, batch
        )

        correction_payload = caller.calls[1]["payload"]
        error = validation_error(caller.calls[1])
        self.assertIn("supporting_evidence[0]", error)
        self.assertIn("outside typed authority", error)
        self.assertIn("exact_text", error)
        self.assertEqual(
            correction_payload["research_state"]["supporting_evidence"][0],
            fixture["prior_evidence_ref"],
        )
        self.assertEqual(
            reflected.value.supporting_evidence[0].exact_text,
            fixture["prior_evidence_ref"]["exact_text"],
        )

        failing_caller = ScriptedRoleCaller([invalid_output, invalid_output])
        with self.assertRaises(CandidateExecutionRejected):
            LLMResearchController(failing_caller).reflect(
                default_information_plan(), previous, batch
            )
        self.assertEqual(
            failing_caller.stages,
            ["research_controller_reflect", "research_controller_reflect_correction"],
        )

    def test_blind_predictor_parses_two_stage_schema(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "candidate_judgment": "possible",
                    "magnitude": "2-3x",
                    "confidence": {"level": "medium"},
                    "key_reasons": ["source-backed evidence"],
                    "uncertainties": [],
                    "session_id": "fixture-session",
                }
            ]
        )
        prediction = LLMBlindPredictor(caller).predict(
            {"basic_info": {"industry": "fixture"}}
        )
        self.assertTrue(prediction.value.is_surge)
        self.assertEqual(prediction.value.magnitude.value, "2-3x")
        prompt = str(caller.calls[0]["system_prompt"])
        self.assertIn('"session_id"', prompt)
        self.assertIn("adjusted share price", prompt)
        self.assertIn("last five complete trading days", prompt)
        self.assertIn("not a requirement that revenue", prompt)
        self.assertIn("forecast under uncertainty, not a proof task", prompt)
        self.assertIn(
            'candidate_judgment must be "likely", "possible", "unlikely", or',
            prompt,
        )
        self.assertIn("Possible is a screening judgment", prompt)
        self.assertIn("does not require a quantified valuation bridge", prompt)
        self.assertIn("early market confirmation can support possible", prompt)
        self.assertIn(
            "at least one key_reasons item must affirmatively connect", prompt
        )
        self.assertIn(
            "do not return a positive judgment when every key reason explicitly",
            prompt,
        )
        self.assertIn("Do not require a guarantee", prompt)
        self.assertIn("outcome-stratified", prompt)
        self.assertIn("do not predict false merely because 2x moves are rare", prompt)
        self.assertIn("need not be more than 50% probable", prompt)
        self.assertNotIn("is_surge", prompt)

    def test_v110_blind_predictor_corrects_all_negative_positive_rationale(
        self,
    ) -> None:
        invalid = {
            "candidate_judgment": "possible",
            "magnitude": "2-3x",
            "confidence": {"level": "low"},
            "key_reasons": [
                "UBS raised price target to $27 from $20, implying ~13% upside "
                "from baseline of $23.98, but not 2x.",
                "Recent stock price momentum and strong production guidance "
                "(2.0M oz) support potential upside, but no evidence of doubling.",
                "Sale of Asante Gold shares for $53m provides liquidity, but is "
                "not a material catalyst for 2x repricing.",
            ],
            "uncertainties": [
                "No explicit forward projections or analyst targets suggest "
                "doubling within six months."
            ],
            "session_id": "anonymous-session-id",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["candidate_judgment"] = "unlikely"
        corrected["magnitude"] = None
        caller = ScriptedRoleCaller([invalid, corrected])

        prediction = LLMBlindPredictor(caller).predict(
            {
                "prediction_baseline": {
                    "status": "available",
                    "mean_adjusted_close": 23.982,
                    "trading_dates": ["2025-09-29"],
                },
                "final_research_state": {},
            }
        )

        self.assertFalse(prediction.value.is_surge)
        self.assertEqual(prediction.usage.llm_calls, 2)
        self.assertEqual(
            caller.stages,
            ["blind_predictor_predict", "blind_predictor_predict_correction"],
        )
        feedback = caller.calls[1]["payload"]
        self.assertIn(
            "every key_reasons item explicitly rejects",
            validation_error(caller.calls[1]),
        )
        self.assertEqual(
            feedback["alternative_change_groups"],
            [["candidate_judgment", "magnitude", "key_reasons"]],
        )
        self.assertEqual(
            feedback["obligations"][0]["must_change_any_of_paths"],
            ["candidate_judgment", "magnitude", "key_reasons"],
        )
        self.assertEqual(
            prediction.value.key_reasons,
            tuple(invalid["key_reasons"]),
        )
        self.assertEqual(
            prediction.value.uncertainties,
            tuple(invalid["uncertainties"]),
        )
        self.assertEqual(prediction.value.confidence, ConfidenceLevel.LOW)
        self.assertEqual(prediction.value.session_id, invalid["session_id"])

    def test_v110_blind_predictor_accepts_mixed_positive_and_counterevidence(
        self,
    ) -> None:
        output = {
            "candidate_judgment": "possible",
            "magnitude": "2-3x",
            "confidence": {"level": "low"},
            "key_reasons": [
                "A signed launch contract could drive a 2x repricing if adoption "
                "scales within the six-month horizon.",
                "The current analyst target is not 2x the supplied baseline.",
            ],
            "uncertainties": ["Adoption timing remains uncertain."],
            "session_id": "fixture-session",
        }
        caller = ScriptedRoleCaller([output])

        prediction = LLMBlindPredictor(caller).predict(
            {"basic_info": {"industry": "fixture"}}
        )

        self.assertTrue(prediction.value.is_surge)
        self.assertEqual(prediction.usage.llm_calls, 1)
        self.assertEqual(caller.stages, ["blind_predictor_predict"])

    def test_v110_blind_predictor_accepts_ambiguous_non_outcome_negation(
        self,
    ) -> None:
        reasons = (
            "The catalyst is not guaranteed to double the price; timing remains "
            "uncertain.",
            "Revenue may not double, while the supplied evidence leaves the "
            "share-price repricing direction uncertain.",
            "The setup is not only a 2x case but could reach 3x if adoption scales.",
        )
        for reason in reasons:
            with self.subTest(reason=reason):
                caller = ScriptedRoleCaller(
                    [
                        {
                            "candidate_judgment": "possible",
                            "magnitude": "2-3x",
                            "confidence": {"level": "low"},
                            "key_reasons": [reason],
                            "uncertainties": [],
                            "session_id": "fixture-session",
                        }
                    ]
                )

                prediction = LLMBlindPredictor(caller).predict(
                    {"basic_info": {"industry": "fixture"}}
                )

                self.assertTrue(prediction.value.is_surge)
                self.assertEqual(prediction.usage.llm_calls, 1)

    def test_v110_blind_predictor_can_repair_only_positive_rationale(
        self,
    ) -> None:
        invalid = {
            "candidate_judgment": "possible",
            "magnitude": "2-3x",
            "confidence": {"level": "medium"},
            "key_reasons": ["No evidence supports a 2x repricing."],
            "uncertainties": ["Adoption timing remains uncertain."],
            "session_id": "fixture-session",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["key_reasons"] = [
            "A signed launch contract could drive a 2x repricing if adoption "
            "scales within the six-month horizon."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        prediction = LLMBlindPredictor(caller).predict(
            {"basic_info": {"industry": "fixture"}}
        )

        self.assertTrue(prediction.value.is_surge)
        self.assertEqual(
            prediction.value.candidate_judgment,
            CandidateJudgment.POSSIBLE,
        )
        self.assertEqual(prediction.value.magnitude, MagnitudeClass.TWO_TO_THREE)
        self.assertEqual(prediction.value.confidence, ConfidenceLevel.MEDIUM)
        self.assertEqual(
            prediction.value.uncertainties,
            tuple(invalid["uncertainties"]),
        )
        self.assertEqual(prediction.value.session_id, invalid["session_id"])
        self.assertEqual(prediction.usage.llm_calls, 2)

    def test_v78_blind_predictor_corrects_stale_price_labeled_current(self) -> None:
        invalid = {
            "candidate_judgment": "unlikely",
            "magnitude": None,
            "confidence": {"level": "low"},
            "key_reasons": [
                "Current price $19.38 is far below the defined doubling threshold."
            ],
            "uncertainties": [],
            "session_id": "fixture-session",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["key_reasons"] = [
            "The prediction-time baseline price is $23.98, while visible catalyst "
            "evidence remains limited."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        prediction = LLMBlindPredictor(caller).predict(
            {
                "prediction_baseline": {
                    "status": "available",
                    "method": "mean_last_5_complete_adjusted_closes",
                    "mean_adjusted_close": 23.982,
                    "trading_dates": [],
                },
                "final_research_state": {},
            }
        )

        self.assertEqual(prediction.usage.llm_calls, 2)
        self.assertEqual(
            caller.stages,
            ["blind_predictor_predict", "blind_predictor_predict_correction"],
        )
        self.assertIn(
            "key_reasons[0] labels 19.38",
            caller.calls[1]["payload"]["validation_error"],
        )
        self.assertIn(
            "final_context.prediction_baseline", caller.calls[0]["system_prompt"]
        )
        self.assertIn("$23.98", prediction.value.key_reasons[0])

    def test_v89_blind_predictor_accepts_derived_two_x_baseline_threshold(
        self,
    ) -> None:
        output = {
            "candidate_judgment": "unlikely",
            "magnitude": None,
            "confidence": {"level": "low"},
            "key_reasons": [
                "The stock would need to reach the 2x baseline of $47.96 within "
                "six months, while visible catalysts remain limited."
            ],
            "uncertainties": ["Commodity prices may change the outlook."],
            "session_id": "fixture-session",
        }
        caller = ScriptedRoleCaller([output])

        prediction = LLMBlindPredictor(caller).predict(
            {
                "prediction_baseline": {
                    "status": "available",
                    "mean_adjusted_close": 23.982,
                    "trading_dates": ["2025-09-29"],
                },
                "final_research_state": {},
            }
        )

        self.assertFalse(prediction.value.is_surge)
        self.assertEqual(prediction.usage.llm_calls, 1)

    def test_v89_blind_predictor_rejects_unrelated_incremental_edits_before_repair(self) -> None:
        invalid = {
            "candidate_judgment": "unlikely",
            "magnitude": None,
            "confidence": {"level": "low"},
            "key_reasons": [
                "Current price $19.38 is far below the defined doubling threshold.",
                "Management reaffirmed guidance without an upward revision.",
            ],
            "uncertainties": ["Commodity prices may change the outlook."],
            "session_id": "fixture-session",
        }
        def drifted(request):
            return {
                "base_hash": request["payload"]["output_patch_contract"]["base_hash"],
                "operations": [
                    {"op": "replace", "path": "key_reasons[0]", "value": "Strong momentum may support a re-rating."},
                    {"op": "remove", "path": "key_reasons[1]"},
                    {"op": "replace", "path": "candidate_judgment", "value": "possible"},
                ],
            }

        corrected = json.loads(json.dumps(invalid))
        corrected["key_reasons"][0] = "Strong momentum may support a re-rating."
        caller = ScriptedRoleCaller([invalid, drifted, corrected])
        caller.max_structured_corrections = 2

        prediction = LLMBlindPredictor(caller).predict(
            {
                "prediction_baseline": {
                    "status": "available",
                    "mean_adjusted_close": 23.982,
                    "trading_dates": ["2025-09-29"],
                },
                "final_research_state": {},
            }
        )
        # The unauthorized patch is atomic and rejected. A subsequent delta
        # repairs only the authorized reason, retaining every valid sibling.
        self.assertEqual(prediction.usage.llm_calls, 3)
        self.assertEqual(prediction.value.candidate_judgment, "unlikely")
        self.assertIsNone(prediction.value.magnitude)
        self.assertIn("outside typed authority", str(caller.calls[2]["payload"]))
        self.assertEqual(
            prediction.value.key_reasons,
            (
                "Strong momentum may support a re-rating.",
                "Management reaffirmed guidance without an upward revision.",
            ),
        )
        self.assertEqual(
            prediction.value.uncertainties,
            ("Commodity prices may change the outlook.",),
        )

        self.assertEqual(
            caller.stages,
            ["blind_predictor_predict", "blind_predictor_predict_correction", "blind_predictor_predict_correction"],
        )

    def test_v88_blind_predictor_rejects_false_market_data_absence(self) -> None:
        invalid = {
            "candidate_judgment": "unlikely",
            "magnitude": None,
            "confidence": {"level": "low"},
            "key_reasons": ["A distant project is outside the six-month horizon."],
            "uncertainties": [
                "No financial projections or market data are provided."
            ],
            "session_id": "fixture-session",
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["uncertainties"] = [
            "Forward financial projections beyond the supplied price baseline are "
            "not provided."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        prediction = LLMBlindPredictor(caller).predict(
            {
                "prediction_baseline": {
                    "status": "available",
                    "mean_adjusted_close": 109.614,
                    "trading_dates": ["2025-07-30"],
                },
                "final_research_state": {},
            }
        )

        self.assertEqual(prediction.usage.llm_calls, 2)
        self.assertIn(
            "claimed market data was absent",
            validation_error(caller.calls[1]),
        )
        self.assertIn("uncertainties[0]", validation_error(caller.calls[1]))
        self.assertIn("supplied price baseline", prediction.value.uncertainties[0])

    def test_blind_predictor_repairs_legacy_binary_shape(self) -> None:
        valid = {
            "candidate_judgment": "unlikely",
            "magnitude": None,
            "confidence": {"level": "low"},
            "key_reasons": ["limited source-backed evidence"],
            "uncertainties": [],
            "session_id": "fixture-session",
        }
        legacy = dict(valid)
        legacy.pop("candidate_judgment")
        legacy["decision"] = "NO"
        caller = ScriptedRoleCaller([legacy, valid])

        prediction = LLMBlindPredictor(caller).predict(
            {"basic_info": {"industry": "fixture"}}
        )

        self.assertFalse(prediction.value.is_surge)
        self.assertEqual(
            caller.stages,
            ["blind_predictor_predict", "blind_predictor_predict_correction"],
        )
        self.assertIn("validation_error", caller.calls[1]["payload"])

    def test_blind_predictor_maps_four_way_candidate_judgment(self) -> None:
        class FourWayRoleCaller(ScriptedRoleCaller):
            def complete_binary_token_with_scores(self, **kwargs):
                raise AssertionError("four-way Predictor must not request token scores")

        expected = {
            "likely": True,
            "possible": True,
            "unlikely": False,
            "insufficient_information": False,
        }
        for judgment, is_surge in expected.items():
            with self.subTest(judgment=judgment):
                caller = FourWayRoleCaller(
                    [
                        {
                            "candidate_judgment": judgment,
                            "magnitude": "2-3x" if is_surge else None,
                            "confidence": {"level": "low"},
                            "key_reasons": ["source-backed assessment"],
                            "uncertainties": [],
                            "session_id": "fixture-session",
                        }
                    ]
                )
                prediction = LLMBlindPredictor(caller).predict(
                    {"basic_info": {"industry": "fixture"}}
                )
                self.assertEqual(prediction.value.is_surge, is_surge)
                self.assertEqual(
                    prediction.value.candidate_judgment.value,
                    judgment,
                )
                self.assertEqual(caller.stages, ["blind_predictor_predict"])

    def test_posthoc_reflection_does_not_rescan_low_confidence_as_ticker(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "prediction_outcome": {"correct": False},
                    "decision_drivers": [
                        "Limited supplied evidence supported the negative judgment."
                    ],
                    "why_prediction_failed": [],
                    "misleading_signals": [],
                    "ignored_evidence": [],
                    "missing_information": [],
                    "plan_issues": [],
                }
            ]
        )
        predictor = LLMBlindPredictor(caller, anonymous_aliases=("LOW",))

        reflection = predictor.reflect(
            {"summary": "anonymous evidence"},
            BlindPrediction(
                is_surge=False,
                candidate_judgment=CandidateJudgment.UNLIKELY,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("limited evidence",),
                uncertainties=(),
                session_id="anonymous-session",
            ),
            GroundTruth(1.2),
        )

        self.assertEqual(caller.calls[0]["anonymous_aliases"], ())
        self.assertNotIn(
            "decision_confidence_feedback", caller.calls[0]["payload"]
        )
        feedback = caller.calls[0]["payload"]["candidate_judgment_feedback"]
        self.assertEqual(feedback["assessment"], "strong_correct_negative")
        self.assertTrue(feedback["binary_correct"])
        self.assertTrue(reflection.value.correct)
        self.assertTrue(
            caller.calls[0]["payload"]["framework_prediction_correct"]
        )
        self.assertNotIn("token probability", caller.calls[0]["system_prompt"])
        self.assertIn(
            "candidate_judgment_feedback",
            caller.calls[0]["system_prompt"],
        )

    def test_v88_posthoc_rejects_false_market_data_absence(self) -> None:
        invalid = {
            "prediction_outcome": {"correct": True},
            "decision_drivers": [
                "The distant project did not supply a near-term catalyst."
            ],
            "why_prediction_failed": [],
            "misleading_signals": [],
            "ignored_evidence": [],
            "missing_information": [
                "No financial projections or market data were available."
            ],
            "plan_issues": [],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["missing_information"] = [
            "Forward financial projections beyond the supplied price baseline "
            "were unavailable."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])
        predictor = LLMBlindPredictor(caller)

        reflection = predictor.reflect(
            {
                "prediction_baseline": {
                    "status": "available",
                    "mean_adjusted_close": 109.614,
                    "trading_dates": ["2025-07-30"],
                }
            },
            BlindPrediction(
                is_surge=False,
                candidate_judgment=CandidateJudgment.UNLIKELY,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("The catalyst was outside the horizon.",),
                uncertainties=(),
                session_id="anonymous-session",
            ),
            GroundTruth(1.2),
        )

        self.assertEqual(reflection.usage.llm_calls, 2)
        self.assertIn(
            "Market data was supplied",
            validation_error(caller.calls[1]),
        )
        self.assertEqual(
            set(caller.calls[1]["payload"]["required_change_paths"]),
            {"reflection_items[1].brief", "reflection_items[1].detail"},
        )
        self.assertIn(
            "supplied price baseline",
            reflection.value.missing_information[0],
        )

    def test_posthoc_reflection_still_scans_original_context(self) -> None:
        predictor = LLMBlindPredictor(
            ScriptedRoleCaller([]), anonymous_aliases=("LEAKME",)
        )

        with self.assertRaisesRegex(ValidationError, "identity alias leaked"):
            predictor.reflect(
                {"summary": "LEAKME disclosed"},
                BlindPrediction(
                    is_surge=False,
                    candidate_judgment=CandidateJudgment.UNLIKELY,
                    magnitude=None,
                    confidence=ConfidenceLevel.LOW,
                    key_reasons=("limited evidence",),
                    uncertainties=(),
                    session_id="anonymous-session",
                ),
                GroundTruth(1.2),
            )

    def test_v12_correct_posthoc_requires_specific_decision_driver(self) -> None:
        empty = {
            "prediction_outcome": {"correct": True},
            "decision_drivers": [],
            "why_prediction_failed": [],
            "misleading_signals": [],
            "ignored_evidence": [],
            "missing_information": [],
            "plan_issues": [],
        }
        corrected = json.loads(json.dumps(empty))
        corrected["decision_drivers"] = [
            "No expectation-changing catalyst was present in the supplied evidence."
        ]
        caller = ScriptedRoleCaller([empty, corrected])
        predictor = LLMBlindPredictor(caller)

        reflection = predictor.reflect(
            {"summary": "No expectation-changing catalyst was present."},
            BlindPrediction(
                is_surge=False,
                candidate_judgment=CandidateJudgment.UNLIKELY,
                magnitude=None,
                confidence=ConfidenceLevel.LOW,
                key_reasons=("no catalyst",),
                uncertainties=(),
                session_id="anonymous-session",
            ),
            GroundTruth(1.2),
        )

        self.assertEqual(
            caller.stages,
            [
                "blind_predictor_posthoc_reflect",
                "blind_predictor_posthoc_reflect_correction",
            ],
        )
        self.assertIn(
            "no_findings_reason",
            caller.calls[1]["payload"]["validation_error"],
        )
        self.assertEqual(reflection.value.decision_drivers, tuple(corrected["decision_drivers"]))

    def test_v30_incorrect_posthoc_requires_specific_failure_attribution(self) -> None:
        empty = {
            "prediction_outcome": {"correct": False},
            "decision_drivers": [],
            "why_prediction_failed": [],
            "misleading_signals": [],
            "ignored_evidence": [],
            "missing_information": [],
            "plan_issues": [],
        }
        corrected = json.loads(json.dumps(empty))
        corrected["misleading_signals"] = [
            "The 52-week high and low drawdown were momentum evidence, not a "
            "source-backed catalyst for a six-month doubling."
        ]
        caller = ScriptedRoleCaller([empty, corrected])
        predictor = LLMBlindPredictor(caller)

        reflection = predictor.reflect(
            {"summary": "Momentum was positive but no doubling catalyst was supplied."},
            BlindPrediction(
                is_surge=True,
                candidate_judgment=CandidateJudgment.POSSIBLE,
                magnitude=MagnitudeClass.TWO_TO_THREE,
                confidence=ConfidenceLevel.MEDIUM,
                key_reasons=("strong momentum",),
                uncertainties=("no catalyst",),
                session_id="anonymous-session",
            ),
            GroundTruth(1.5),
        )

        self.assertEqual(
            caller.stages,
            [
                "blind_predictor_posthoc_reflect",
                "blind_predictor_posthoc_reflect_correction",
            ],
        )
        self.assertIn(
            "no_findings_reason",
            caller.calls[1]["payload"]["validation_error"],
        )
        self.assertEqual(
            reflection.value.misleading_signals,
            tuple(corrected["misleading_signals"]),
        )
        self.assertIn(
            "why_prediction_failed",
            caller.calls[0]["system_prompt"],
        )

    def test_plan_critic_receives_compact_anonymous_trajectories(self) -> None:
        from tests.scheme_evolution_test_support import make_trajectory
        from stock_opportunity_agent.research.scheme_evolution import score_predictions

        trajectory = make_trajectory(
            "identity_must_not_reach_critic", 2.2, True, MagnitudeClass.TWO_TO_THREE,
            signal_result=SignalResult(
                signal_id="revenue_growth_yoy", version=1,
                value=SignalValue.POSITIVE, confidence=0.8,
                interpretation="accelerating",
                supporting_evidence=(SignalEvidence(
                    document_id="fixture-source", exact_span="must be omitted",
                    timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
                ),),
            ),
        )
        trajectory = replace(
            trajectory,
            basic_info={"exact_text": "raw-info-must-not-reach-critic"},
            final_context={"exact_span": "source-span-must-not-reach-critic"},
        )

        caller = ScriptedRoleCaller(
            [
                {
                    "successful_patterns": ["well grounded judgment"],
                    "failed_patterns": [],
                    "repeated_failure_modes": [],
                    "misleading_signals": [],
                    "missing_information_needs": [],
                    "next_explorations": [],
                }
            ]
        )

        reflection = LLMPlanCritic(caller).critique(
            plan=default_information_plan(),
            trajectories=(trajectory,),
            metrics=score_predictions((trajectory,)),
            parent_comparisons=(
                {
                    "source_scope": "historical_seed",
                    "same_evaluation_snapshot": True,
                    "plan_diff": {
                        "basic_info_requests_removed": [
                            {"request_id": "recent_annual_filing"}
                        ]
                    },
                    "metric_delta": {
                        "binary_f1": -0.19,
                        "confusion": {
                            "true_positive": -3,
                            "false_negative": 3,
                        },
                    },
                },
            ),
        )

        self.assertEqual(
            reflection.successful_patterns, ("well grounded judgment",)
        )
        prompt = caller.calls[0]["system_prompt"]
        self.assertIn("canonical outcome feedback", prompt)
        self.assertNotIn("token probability", prompt)
        trajectories = caller.calls[0]["payload"]["trajectories"]
        self.assertNotIn("decision_confidence_feedback", trajectories[0])
        self.assertEqual(
            trajectories[0]["candidate_judgment_feedback"]["assessment"],
            "correct_positive_conservative",
        )
        self.assertIn("Combined Binary F1", prompt)
        self.assertIn("same_evaluation_snapshot", prompt)
        comparisons = caller.calls[0]["payload"]["parent_comparisons"]
        self.assertEqual(
            comparisons[0]["plan_diff"]["basic_info_requests_removed"][0][
                "request_id"
            ],
            "recent_annual_filing",
        )
        self.assertNotIn("company_id", json.dumps(comparisons))
        self.assertNotIn("ground_truth", json.dumps(comparisons))
        self.assertEqual(trajectories[0]["case_index"], 1)
        self.assertNotIn("case_id", trajectories[0])
        self.assertNotIn("company_id", trajectories[0])
        self.assertNotIn("basic_info_bundle", trajectories[0])
        self.assertNotIn("final_context", trajectories[0])
        self.assertNotIn("signal_rounds", trajectories[0])
        self.assertNotIn("self_reflection", trajectories[0])
        self.assertTrue(caller.calls[0]["payload"]["source_catalog"])
        self.assertIn("read_refs", caller.calls[0]["system_prompt"])
        rendered = json.dumps(trajectories)
        self.assertNotIn("raw-info-must-not-reach-critic", rendered)
        self.assertNotIn("source-span-must-not-reach-critic", rendered)
        self.assertNotIn("must be omitted", rendered)

    def test_round_reflector_receives_compact_records_and_parent_comparisons(
        self,
    ) -> None:
        from tests.scheme_evolution_test_support import make_record, make_trajectory
        from stock_opportunity_agent.research.scheme_evolution import score_predictions

        def record(plan_id):
            base = make_record(plan_id, 0.5, (1.0, 0.0))
            trajectory = make_trajectory(
                "identity_must_not_reach_round_reflector", 2.5, False, None,
            )
            trajectory = replace(
                trajectory,
                basic_info={"marker": "raw-info-must-not-reach-round-reflector"},
            )
            return replace(
                base,
                plan=replace(base.plan, parent_ids=("historical_seed_parent",)),
                reflection=PlanReflection(failed_patterns=("lost financial evidence",)),
                signal_usage={"revenue_growth_yoy:v1": {"retrieved": 24}},
                trajectories=(trajectory,),
                metrics=score_predictions((trajectory,)),
                evaluation=None,
                fitness=None,
            )

        caller = ScriptedRoleCaller(
            [
                {
                    "round_id": 1,
                    "plan_level": {
                        "successful_patterns": [],
                        "failed_patterns": ["financial evidence was removed"],
                    },
                    "prediction_errors": {
                        "false_positive": [],
                        "false_negative": ["positive recall regressed"],
                    },
                    "signal_observations": {
                        "useful": [],
                        "suspicious": [],
                        "missing_capabilities": [],
                    },
                    "search_implications": ["restore financial evidence"],
                    "evidence_refs": ["child_plan"],
                }
            ]
        )

        result = LLMRoundReflector(caller).reflect(
            round_id=1,
            records=(record("child_plan"), record("sibling_plan")),
            prior="reflect over the round",
            parent_comparisons_by_plan_id={
                "child_plan": (
                    {
                        "child_plan_id": "child_plan",
                        "same_evaluation_snapshot": True,
                        "plan_diff": {
                            "basic_info_requests_removed": [
                                {"request_id": "recent_annual_filing"}
                            ]
                        },
                        "metric_delta": {"binary_f1": -0.19},
                    },
                )
            },
        )

        self.assertEqual(result.evidence_refs, ("child_plan", "sibling_plan"))
        self.assertIn("horizontal insight", caller.calls[0]["system_prompt"])
        payload = caller.calls[0]["payload"]
        self.assertIn("parent_comparisons_by_plan_id", payload)
        self.assertNotIn("trajectories", payload["records"][0])
        self.assertNotIn("case_ids", json.dumps(payload["records"]))
        rendered = json.dumps(payload)
        self.assertNotIn("identity_must_not_reach_round_reflector", rendered)
        self.assertNotIn("raw-info-must-not-reach-round-reflector", rendered)

    def test_round_reflector_skips_single_record_horizontal_paraphrase(self) -> None:
        record = SimpleNamespace(plan_id="only_plan")
        caller = ScriptedRoleCaller([])

        result = LLMRoundReflector(caller).reflect(
            round_id=1,
            records=(record,),
            prior="reflect over the round",
            parent_comparisons_by_plan_id={"only_plan": ()},
        )

        self.assertEqual(result.round_id, 1)
        self.assertEqual(result.evidence_refs, ("only_plan",))
        self.assertEqual(result.plan_reflections, ())
        self.assertEqual(caller.calls, [])
        # The skip must be distinguishable from "the model found nothing"
        # in downstream learning audits.
        self.assertEqual(
            result.no_findings_reason,
            "round_reflection_skipped_single_complete_plan",
        )

    def test_fixed_menu_admits_existing_source_alias_routes_and_discloses_actions(self):
        from stock_opportunity_agent.research.evolution_core import BasicInfoPolicy
        from stock_opportunity_agent.research.evolution_output_validation import _validate_plan_for_proposer_context
        from stock_opportunity_agent.models import StructuredValidationError
        from dataclasses import replace
        parent = default_information_plan()
        plan = replace(parent, basic_info_policy=BasicInfoPolicy(tuple(
            make_orientation_request(action) for action in ("operating_report", "market_backbone"))))
        output = {"B": plan.basic_info_policy.to_dict(), "H_init": plan.initial_research_skill,
            "H_reflect": plan.reflection_skill, "H_analyse": plan.analysis_prompt,
            "used_experience_refs": []}
        caller = ScriptedRoleCaller([output])
        accepted = LLMInformationPlanProposer(caller, available_source_types=("sec_filing", "prices")).propose(
            round_id=1, candidate_index=1, candidate_count=1, proposal_attempt=1,
            forbidden_plan_ids=(), parents=(), meta_info=(), prior="Fixed prior")
        self.assertEqual(accepted.basic_info_policy.to_dict(), plan.basic_info_policy.to_dict())
        menu = caller.calls[0]["payload"]["proposal_context"]["basic_info_orientation_menu"]
        self.assertEqual(menu["available_action_ids"], ["orientation.v1.market_backbone", "orientation.v1.operating_report"])
        prompt = caller.calls[0]["system_prompt"]
        self.assertIn("positive-integer lookback_days", prompt)
        self.assertIn("at most once per action", prompt)
        self.assertNotIn("one to eight", prompt)
        self.assertNotIn("competitive requests must explicitly", prompt)
        self.assertNotIn("unless one exact SEC form", prompt)
        self.assertIn("Unsupported form coverage remains a gap", prompt)
        with self.assertRaises(StructuredValidationError) as caught:
            _validate_plan_for_proposer_context(plan, available_source_types=("social_media",))
        self.assertIn("plan_source_type_unsupported", [item.code for item in caught.exception.issues])

    def test_plan_proposer_accepts_canonical_fields_and_slots_children(self) -> None:
        policy = {
            "requests": [make_orientation_request("market_backbone").to_dict()]
        }
        caller = ScriptedRoleCaller([
            {
                "used_experience_refs": [],
                "B": policy,
                "H_init": "Form a falsifiable hypothesis and list unresolved information needs.",
                "H_reflect": "Track support and contradiction, then continue for the next need or finalize.",
                "H_analyse": "Weigh supporting and counter evidence while exposing uncertainty.",
            },
            {
                "used_experience_refs": [],
                "B": policy,
                "H_init": "Test a distinct hypothesis and list unresolved information needs.",
                "H_reflect": "Track disconfirming evidence first, then continue for the next need or finalize.",
                "H_analyse": "Weigh counter evidence while preserving uncertainty.",
            },
        ])
        proposer = LLMInformationPlanProposer(caller)
        parent = default_information_plan()

        first = proposer.propose(
            round_id=1,
            candidate_index=1,
            candidate_count=2,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )
        second = proposer.propose(
            round_id=1,
            candidate_index=2,
            candidate_count=2,
            proposal_attempt=1,
            forbidden_plan_ids=(first.plan_id,),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(first.plan_id, "plan_r0001_c01")
        self.assertEqual(
            first.basic_info_policy.requests[-1].request_id,
            "orientation.v1.market_backbone",
        )
        self.assertEqual(first.parent_ids, ("plan_manual_v1",))
        self.assertEqual(caller.calls[0]["temperature"], 1.0)
        self.assertIn(
            "strategy keys B, H_init, H_reflect, and H_analyse",
            str(caller.calls[0]["system_prompt"]),
        )
        self.assertIn("plus used_experience_refs", str(caller.calls[0]["system_prompt"]))
        self.assertIn("foreign issuers may use 20-F, 40-F, or 6-K", caller.calls[0]["system_prompt"])
        self.assertEqual(
            parent.basic_info_policy.requests[0].source_types,
            ("filing",),
        )
        self.assertEqual(
            caller.calls[0]["payload"]["proposal_context"]["proposal_slot"],
            {
                "round_id": 1,
                "candidate_index": 1,
                "candidate_count": 2,
                "proposal_attempt": 1,
            },
        )
        self.assertEqual(
            caller.calls[1]["payload"]["proposal_context"]["proposal_slot"],
            {
                "round_id": 1,
                "candidate_index": 2,
                "candidate_count": 2,
                "proposal_attempt": 1,
            },
        )
        self.assertIn(
            "strategy keys B, H_init, H_reflect, and H_analyse",
            str(caller.calls[1]["system_prompt"]),
        )
        self.assertNotIn("forbidden_plan_ids", str(caller.calls[1]["system_prompt"]))
        self.assertEqual(second.plan_id, "plan_r0001_c02")

    def test_plan_proposer_repairs_exact_parent_copy_with_change_focus(self) -> None:
        parent = default_information_plan()
        duplicate = {
            "used_experience_refs": [],
            "B": parent.basic_info_policy.to_dict(),
            "H_init": parent.initial_research_skill,
            "H_reflect": parent.reflection_skill,
            "H_analyse": parent.analysis_prompt,
        }
        repaired = json.loads(json.dumps(duplicate))
        repaired["H_reflect"] = (
            "Test the strongest disconfirming evidence, then continue for the next "
            "need or finalize."
        )
        caller = ScriptedRoleCaller([duplicate, repaired])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=2,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(plan.reflection_skill, repaired["H_reflect"])
        self.assertEqual(
            caller.stages,
            ["information_plan_propose", "information_plan_propose_correction"],
        )
        constraints = caller.calls[0]["payload"]["proposal_context"][
            "proposal_constraints"
        ]
        self.assertTrue(constraints["must_differ_from_every_parent"])
        self.assertIn("H_reflect", constraints["required_change_focus"])
        correction = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("exactly duplicates", correction["validation_error"])
        self.assertEqual(correction["invalid_output"], duplicate)

    def test_plan_proposer_accepts_rebased_imported_history_meta_prefix(self) -> None:
        """Imported and local lessons survive brief projection after id rebasing."""
        from stock_opportunity_agent.research.evolution_control import (
            _rebased_history_meta_entries,
        )

        parent = default_information_plan()
        valid = {
            "used_experience_refs": [],
            "B": {
                "requests": [
                    make_orientation_request("operating_report").to_dict(),
                    make_orientation_request("market_backbone").to_dict(),
                ]
            },
            "H_init": parent.initial_research_skill,
            "H_reflect": (
                "Test the strongest disconfirming evidence, then continue for "
                "the next need or finalize."
            ),
            "H_analyse": parent.analysis_prompt,
        }
        caller = ScriptedRoleCaller([valid])
        imported = RoundMetaEntry(
            round_id=1,
            evidence_refs=("imported-plan",),
            missing_capabilities=("Imported unresolved Fast need.",),
        )
        local = RoundMetaEntry(
            round_id=1,
            evidence_refs=("plan_r0001_c01",),
            successful_patterns=("correct binary separation",),
        )
        rebased = _rebased_history_meta_entries((imported,))

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=2,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(*rebased, local),
            prior="fixed H_P",
        )
        self.assertIsNotNone(plan)
        meta_payload = caller.calls[0]["payload"]["proposal_context"]["meta_info"]
        self.assertEqual([entry.round_id for entry in (*rebased, local)], [-1, 1])
        self.assertEqual(
            {item["brief"] for item in meta_payload["items"]},
            {"Imported unresolved Fast need.", "correct binary separation"},
        )
        self.assertTrue(all(item["source_refs"] for item in meta_payload["items"]))

    def test_v111_plan_proposer_does780_relabels_news_as_issuer_owned(self) -> None:
        parent = default_information_plan()
        invalid = {
            "used_experience_refs": [],
            "B": {
                "requests": [
                    dict(make_orientation_request("scoped_news").to_dict(), description="Target company's own disclosures about customers, financing, and product milestones."),
                    make_orientation_request("market_backbone").to_dict(),
                ]
            },
            "H_init": parent.initial_research_skill,
            "H_reflect": parent.reflection_skill,
            "H_analyse": parent.analysis_prompt,
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["B"]["requests"][0]["description"] = make_orientation_request("scoped_news").description
        caller = ScriptedRoleCaller([invalid, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("third-party reporting", feedback["validation_error"])
        self.assertEqual(
            feedback["required_change_paths"],
            ["B.requests[0].description"],
        )
        self.assertEqual(
            plan.basic_info_policy.requests[0].description,
            corrected["B"]["requests"][0]["description"],
        )
        self.assertIn(
            "company_news/news may contain third-party reporting",
            caller.calls[0]["system_prompt"],
        )

    def test_plan_proposer_repairs_unsupported_ownership_in_role_skill(self) -> None:
        parent = default_information_plan()
        invalid = {
            "used_experience_refs": [],
            "B": {
                "requests": [
                    make_orientation_request("scoped_news").to_dict(),
                    make_orientation_request("market_backbone").to_dict(),
                ]
            },
            "H_init": (
                "Form a hypothesis from the target company's own disclosures and "
                "identify unresolved information needs."
            ),
            "H_reflect": parent.reflection_skill,
            "H_analyse": parent.analysis_prompt,
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["H_init"] = (
            "Form a hypothesis from target-company-scoped evidence and identify "
            "unresolved information needs."
        )
        caller = ScriptedRoleCaller([invalid, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("no first-party-capable source", feedback["validation_error"])
        self.assertEqual(feedback["required_change_paths"], ["H_init"])
        self.assertEqual(plan.initial_research_skill, corrected["H_init"])

    def test_v10_proposer_allows_explicit_probability_prohibition(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v10_proposer_semantics_and_focus.json"
            ).read_text(encoding="utf-8")
        )
        parent = default_information_plan()
        for analysis_prompt in fixture["false_positive_analysis_prompts"]:
            output = {
                "used_experience_refs": [],
                "B": parent.basic_info_policy.to_dict(),
                "H_init": parent.initial_research_skill,
                "H_reflect": parent.reflection_skill,
                "H_analyse": analysis_prompt,
            }
            caller = ScriptedRoleCaller([output])

            plan = LLMInformationPlanProposer(caller).propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=3,
                forbidden_plan_ids=(),
                parents=(parent,),
                meta_info=(),
                prior="fixed H_P",
            )

            self.assertEqual(plan.analysis_prompt, analysis_prompt)
            self.assertEqual(caller.stages, ["information_plan_propose"])

    def test_v95_proposer_allows_operating_event_probability_in_h_init(self) -> None:
        parent = default_information_plan()
        output = {
            "used_experience_refs": [],
            "B": parent.basic_info_policy.to_dict(),
            "H_init": (
                "Form falsifiable hypotheses from source-backed evidence about "
                "whether the probability of commercial adoption changes, and list "
                "the smallest unresolved information needs and questions."
            ),
            "H_reflect": parent.reflection_skill,
            "H_analyse": parent.analysis_prompt,
        }
        caller = ScriptedRoleCaller([output])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(plan.initial_research_skill, output["H_init"])
        self.assertEqual(caller.stages, ["information_plan_propose"])

    def test_v95_proposer_scopes_direction_decision_repair_to_h_reflect(self) -> None:
        parent = default_information_plan()
        invalid = {
            "used_experience_refs": [],
            "B": parent.basic_info_policy.to_dict(),
            "H_init": parent.initial_research_skill,
            "H_reflect": (
                "Update beliefs from supporting and contradictory evidence, then "
                "decide whether the market trend is likely to continue or reverse; "
                "continue to the next need or finalize."
            ),
            "H_analyse": parent.analysis_prompt,
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["H_reflect"] = (
            "Update beliefs from supporting and contradictory evidence, then decide "
            "whether evidence collection should continue to the next need or "
            "finalize while preserving unresolved uncertainty."
        )
        caller = ScriptedRoleCaller([invalid, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=2,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("invalid_field='H_reflect'", feedback["validation_error"])
        self.assertEqual(feedback["required_change_paths"], ["H_reflect"])
        self.assertEqual(plan.reflection_skill, corrected["H_reflect"])
        self.assertEqual(corrected["B"], invalid["B"])
        self.assertEqual(corrected["H_init"], invalid["H_init"])
        self.assertEqual(corrected["H_analyse"], invalid["H_analyse"])

    def test_v14_fixed_threshold_reference_is_not_a_semantics_redefinition(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v14_fixed_threshold_reference.json"
            ).read_text(encoding="utf-8")
        )

        for text_value in fixture["allowed"]:
            with self.subTest(allowed=text_value):
                self.assertEqual(
                    evolution_runtime_module._reject_fixed_semantics_redefinition(
                        {"decision_drivers": [text_value]}
                    ),
                    {"decision_drivers": [text_value]},
                )
        for text_value in fixture["rejected"]:
            with self.subTest(rejected=text_value):
                with self.assertRaisesRegex(
                    ValidationError, "redefine fixed Predictor semantics"
                ):
                    evolution_runtime_module._reject_fixed_semantics_redefinition(
                        {"decision_drivers": [text_value]}
                    )

    def test_v10_proposer_corrects_change_outside_required_focus(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/evolution_runtime/"
                "v10_proposer_semantics_and_focus.json"
            ).read_text(encoding="utf-8")
        )
        unchanged = dict(fixture["unchanged_focus_fields"])
        unchanged["B"] = default_information_plan().basic_info_policy.to_dict()
        parent = InformationPlan.from_dict(
            {
                "plan_id": "historical_parent",
                "parent_ids": [],
                "basic_info_policy": unchanged["B"],
                "initial_research_skill": unchanged["H_init"],
                "reflection_skill": default_information_plan().reflection_skill,
                "analysis_prompt": fixture["parent_analysis_prompt"],
            }
        )
        wrong_focus = {
            "used_experience_refs": [],
            "B": unchanged["B"],
            "H_init": unchanged["H_init"],
            "H_reflect": parent.reflection_skill,
            "H_analyse": fixture["wrong_focus_analysis_prompt"],
        }
        corrected = json.loads(json.dumps(wrong_focus))
        corrected["H_init"] += " Identify the strongest unsupported assumption."
        caller = ScriptedRoleCaller([wrong_focus, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(plan.initial_research_skill, corrected["H_init"])
        self.assertIn(
            "B/H_init is unchanged",
            caller.calls[1]["payload"]["validation_feedback"]["validation_error"],
        )

    def test_plan_proposer_receives_briefs_with_exact_additive_sources_available(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "used_experience_refs": [],
                    "B": {
                        "requests": [
                            make_orientation_request("market_backbone").to_dict()
                        ]
                    },
                    "H_init": (
                        "Test the preserved hypothesis and list unresolved "
                        "information needs."
                    ),
                    "H_reflect": (
                        "Inspect contradiction before finalizing or continuing for "
                        "the next need."
                    ),
                    "H_analyse": (
                        "Weigh supporting and counter evidence while preserving "
                        "uncertainty."
                    ),
                }
            ]
        )
        parent = default_information_plan()
        metrics = PlanMetrics(
            binary_precision=1.0,
            binary_recall=1.0,
            binary_f1=1.0,
            magnitude_accuracy=1.0,
            magnitude_macro_f1=1 / 3,
            true_positive=1,
            false_positive=0,
            true_negative=0,
            false_negative=0,
            sample_count=1,
        )
        case_reflection = CaseReflectionEvidence(
            case_index=1,
            stop_reason=RuntimeStopReason.FINALIZED,
            termination_trigger=None,
            candidate_judgment_feedback=candidate_judgment_feedback(
                BlindPrediction(
                    is_surge=True,
                    candidate_judgment=CandidateJudgment.POSSIBLE,
                    magnitude=MagnitudeClass.TWO_TO_THREE,
                    confidence=ConfidenceLevel.MEDIUM,
                    key_reasons=("source-backed opportunity",),
                    uncertainties=("magnitude remains uncertain",),
                    session_id="anonymous-session",
                ),
                GroundTruth(2.2),
            ),
            self_reflection=PredictionSelfReflection(
                correct=True,
                ignored_evidence=("annual filing evidence was underweighted",),
            ),
        )
        plan_reflection = PlanMetaReflection(
            plan=parent,
            metrics=metrics,
            metrics_by_cohort={},
            evaluation_snapshot_ids=(),
            fitness=FitnessEligibility(
                eligible=True,
                reasons=(),
                expected_case_count=1,
                valid_case_count=1,
                evidence_covered_count=1,
                predicted_positive_count=1,
                true_positive_count=1,
            ),
            signal_usage={},
            original_case_reflections=(case_reflection,),
            vertical_plan_reflection=PlanReflection(
                next_explorations=("restore annual filing evidence",),
            ),
        )
        meta_entry = RoundMetaEntry(
            round_id=1,
            plan_reflections=(plan_reflection,),
            search_implications=("compare restored filing evidence",),
            evidence_refs=(parent.plan_id,),
        )

        proposed = LLMInformationPlanProposer(caller).propose(
            round_id=2,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(parent,),
            meta_info=(meta_entry,),
            prior="fixed H_P",
        )

        self.assertEqual(proposed.plan_id, "plan_r0002_c01")
        meta_payload = caller.calls[0]["payload"]["proposal_context"]["meta_info"]
        self.assertEqual(
            {item["brief"] for item in meta_payload["items"]},
            {
                "annual filing evidence was underweighted",
                "restore annual filing evidence",
                "compare restored filing evidence",
            },
        )
        self.assertTrue(all("detail" not in item for item in meta_payload["items"]))
        case_item = next(item for item in meta_payload["items"] if item["level"] == "case")
        from stock_opportunity_agent.research.evolution_core import PlanMetaMemory

        memory = PlanMetaMemory(entries=(meta_entry,))
        original = memory.read_refs(
            (case_item["source_refs"][-1],), role="proposer",
        )["sources"][0]["content"]
        self.assertEqual(
            original["candidate_judgment_feedback"]["assessment"],
            "correct_positive_conservative",
        )
        self.assertEqual(
            original["self_reflection"]["ignored_evidence"],
            ["annual filing evidence was underweighted"],
        )
        rendered = json.dumps(meta_payload)
        self.assertNotIn('"case_id"', rendered)
        self.assertNotIn('"company_id"', rendered)
        self.assertNotIn("original_case_reflections", rendered)
        self.assertIn("Complete originals remain stored", caller.calls[0]["system_prompt"])

    def test_plan_proposer_budget_preflight_pauses_before_model_call(self) -> None:
        class OversizedCaller(ScriptedRoleCaller):
            def estimate_json_request_tokens(self, **_kwargs):
                return 50_001

        caller = OversizedCaller([])
        proposer = LLMInformationPlanProposer(caller)
        proposer.set_request_token_budget(50_000)
        meta = RoundMetaEntry(
            round_id=1,
            successful_patterns=("Complete retained lesson.",),
            evidence_refs=("plan-1",),
        )

        with self.assertRaisesRegex(
            ExternalBudgetExhausted, "proposal working view"
        ):
            proposer.propose(
                round_id=2,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(default_information_plan(),),
                meta_info=(meta,),
                prior="fixed H_P",
            )

        self.assertEqual(caller.calls, [])

    def test_v145_proposer_pins_experience_snapshot_hash(self) -> None:
        policy = {
            "requests": [make_orientation_request("market_backbone").to_dict()]
        }
        plan_output = {
            "used_experience_refs": [],
            "B": policy,
            "H_init": "Form a falsifiable hypothesis and list unresolved information needs.",
            "H_reflect": "Track support and contradiction, then continue for the next need or finalize.",
            "H_analyse": "Weigh supporting and counter evidence while exposing uncertainty.",
        }
        caller = ScriptedRoleCaller([plan_output, plan_output])
        proposer = LLMInformationPlanProposer(caller)
        proposal = proposer.propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(),
            meta_info=(),
            prior="fixed prior",
        )
        self.assertTrue(proposal)
        payload = caller.calls[0]["payload"]["proposal_context"]
        snapshot_hash = payload.get("experience_snapshot_hash")
        self.assertIsInstance(snapshot_hash, str)
        self.assertEqual(len(snapshot_hash), 64)
        import hashlib
        expected = hashlib.sha256(
            json.dumps(
                payload["meta_info"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(snapshot_hash, expected)
