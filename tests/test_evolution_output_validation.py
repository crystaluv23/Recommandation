"""Structured-correction projection tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403


class SymbolicCutoffResidualInheritanceTests(TestCase):
    """Round-21: bounded forward-guidance parents lend clause and framing."""

    PARENT = (
        "What forward production, cost, and capital expenditure guidance did "
        "Kinross provide by the prediction time for the remainder of 2025 "
        "and 2026?"
    )
    RESIDUAL = (
        "Specific disclosed production, cost, and capital expenditure "
        "figures for the remainder of 2025 and 2026 are not fully covered."
    )
    PREDICTION_DATE = date(2025, 9, 30)

    def test_symbolic_cutoff_residual_inherits_clause_and_guidance_framing(self):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _bounded_residual_need,
            _future_source_date_refs,
        )

        restored = _bounded_residual_need(
            self.RESIDUAL, self.PARENT, self.PREDICTION_DATE
        )
        self.assertIsNotNone(restored)
        self.assertIn("by the prediction time", restored)
        self.assertIn("guidance", restored)
        self.assertIn(
            "figures for the remainder of 2025 and 2026 are not fully covered",
            restored,
        )
        self.assertEqual(
            _future_source_date_refs(
                restored, self.PREDICTION_DATE, field_name="next_information_needs"
            ),
            [],
        )

    def test_explicit_cutoff_parent_restores_the_same_representation(self):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _bounded_residual_need,
            _future_source_date_refs,
        )

        parent = self.PARENT.replace(
            "by the prediction time", "by September 30, 2025"
        )
        restored = _bounded_residual_need(
            self.RESIDUAL, parent, self.PREDICTION_DATE
        )
        self.assertIsNotNone(restored)
        self.assertIn("by September 30, 2025", restored)
        self.assertIn("guidance", restored)
        self.assertEqual(
            _future_source_date_refs(
                restored, self.PREDICTION_DATE, field_name="next_information_needs"
            ),
            [],
        )

    def test_realized_parent_lends_no_inherited_permission(self):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _bounded_residual_need,
            _future_source_date_refs,
        )

        residual = (
            "Specific disclosed production figures for 2026 are not "
            "fully covered."
        )
        invalid_explicit_parent = (
            "What actual 2026 production results versus guidance were "
            "available by 2025-09-30?"
        )
        self.assertEqual(
            _future_source_date_refs(
                invalid_explicit_parent,
                self.PREDICTION_DATE,
                field_name="next_information_needs",
            ),
            ["2026"],
        )
        self.assertIsNone(
            _bounded_residual_need(
                residual, invalid_explicit_parent, self.PREDICTION_DATE
            )
        )
        invalid_symbolic_parent = (
            "What actual 2026 production results versus guidance were "
            "available by the prediction time?"
        )
        self.assertEqual(
            _future_source_date_refs(
                invalid_symbolic_parent,
                self.PREDICTION_DATE,
                field_name="next_information_needs",
            ),
            ["2026"],
        )
        self.assertIsNone(
            _bounded_residual_need(
                residual, invalid_symbolic_parent, self.PREDICTION_DATE
            )
        )

    def test_ordinary_historical_residual_passes_the_real_date_guard(self):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _bounded_residual_need,
            _future_source_date_refs,
        )

        historical = (
            "Specific disclosed production figures for 2024 are not "
            "fully covered."
        )
        self.assertEqual(
            _future_source_date_refs(
                historical,
                self.PREDICTION_DATE,
                field_name="next_information_needs",
            ),
            [],
        )
        self.assertEqual(
            _bounded_residual_need(
                historical, self.PARENT, self.PREDICTION_DATE
            ),
            historical,
        )

    def test_realized_future_residual_is_never_turned_into_a_forecast(self):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _bounded_residual_need,
        )

        realized = (
            "Actual production results and realized cost figures for 2026 "
            "are not fully covered."
        )
        self.assertIsNone(
            _bounded_residual_need(realized, self.PARENT, self.PREDICTION_DATE)
        )

    def test_unbounded_parent_lends_no_cutoff_or_framing(self):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _bounded_residual_need,
        )

        unbounded = (
            "What production, cost, and capital expenditure figures will "
            "Kinross report for 2026?"
        )
        self.assertIsNone(
            _bounded_residual_need(self.RESIDUAL, unbounded, self.PREDICTION_DATE)
        )
        clause_only_parent = (
            "What did Kinross disclose by the prediction time for 2026?"
        )
        self.assertIsNone(
            _bounded_residual_need(
                "Specific disclosed production figures for 2026 are not "
                "fully covered.",
                clause_only_parent,
                self.PREDICTION_DATE,
            )
        )

    def test_pre_reflection_admission_accepts_the_kinross_selection(self):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _reject_unrepresentable_partial_selections,
        )

        selection = SignalSelectionDecision(
            signal_ref="guidance_acceleration:v1",
            reason_code="answer_need",
            selection_reason=(
                "Directly addresses forward production, cost, and capex "
                "guidance for 2025-2026."
            ),
            applicability_hypothesis=(
                "Kinross management guidance may have strengthened."
            ),
            expected_role="primary",
            context_tags=("general",),
            target_need_indices=(1,),
            answer_scope="partial",
            residual_need=self.RESIDUAL,
        )
        needs = (
            "What specific operating or financial catalysts did Kinross "
            "management disclose by the prediction time?",
            self.PARENT,
        )
        _reject_unrepresentable_partial_selections(
            (selection,),
            needs,
            {"prediction_time": "2025-09-30T00:00:00+00:00"},
        )


class ReflectBasicLiteralIdentityTests(TestCase):
    PRIOR_STATE = {
        "contradictions": [],
        "current_beliefs": [
            "The filing identifies the registrant.",
            "cash_reserves=42",
        ],
        "decision": "continue",
        "hypotheses": ["One hypothesis."],
        "next_information_needs": ["Need one?"],
        "open_questions": [],
        "resolved_questions": ["Resolved one."],
        "supporting_evidence": [
            {
                "claim": "The filing identifies the registrant.",
                "exact_text": "8-K body with 17 CFR 230.425 and 17 CFR 240.14a-12 markers",
                "kind": "basic_info",
                "projection_id": "projection_lit_a",
            },
            {
                "claim": "cash_reserves=42",
                "evidence_group": "supporting",
                "evidence_index": 0,
                "kind": "signal",
                "signal_ref": "cash_reserves:v1",
            },
        ],
    }
    EVALUATION_CONTEXT = {
        "prediction_time": "2025-03-31T00:00:00+00:00",
        "horizon": "six_calendar_months",
        "horizon_end": "2025-09-30",
    }

    def _invalid_output(self) -> dict:
        from copy import deepcopy

        value = deepcopy(self.PRIOR_STATE)
        value["current_beliefs"][1] = "revenue_growth_yoy=0.182443"
        value["supporting_evidence"][0]["exact_text"] = (
            "8-K body with 230.425 and 17 CFR 240.14a-12 markers"
        )
        return value

    def _make_parser(self, prior: ResearchState):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _normalize_research_state_output,
            _validate_research_state_refs,
        )

        def parse(value):
            normalized = _normalize_research_state_output(
                dict(value),
                previous_state=prior,
                evaluation_context=self.EVALUATION_CONTEXT,
            )
            return _validate_research_state_refs(
                ResearchState.from_dict(normalized),
                phase="reflect",
                previous_state=prior,
            )

        return parse

    def _run_role(self, caller, prior: "ResearchState | None" = None):
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )

        if prior is None:
            prior = ResearchState.from_dict(self.PRIOR_STATE)
        return evolution_runtime_module._complete_parsed_role(
            caller,
            stage="research_controller_reflect",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=self._make_parser(prior),
            allow_outcomes=False,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            stable_correction_prefix=True,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )

    def test_initial_feedback_carries_assertion_and_literal_identity(self) -> None:
        from stock_opportunity_agent.research.evolution_research_validation import (
            _normalize_research_state_output,
        )

        prior = ResearchState.from_dict(self.PRIOR_STATE)
        with self.assertRaises(StructuredValidationError) as raised:
            _normalize_research_state_output(
                dict(self._invalid_output()),
                previous_state=prior,
                evaluation_context=self.EVALUATION_CONTEXT,
            )
        codes = {issue.code for issue in raised.exception.issues}
        self.assertEqual(
            codes,
            {"assertion_without_support", "basic_literal_identity_mismatch"},
        )
        identity = next(
            issue
            for issue in raised.exception.issues
            if issue.code == "basic_literal_identity_mismatch"
        )
        self.assertEqual(identity.paths, ("supporting_evidence[0].exact_text",))
        self.assertEqual(identity.allowed_repairs, ("replace",))
        self.assertEqual(
            identity.repair_context["prior_exact_text"],
            self.PRIOR_STATE["supporting_evidence"][0]["exact_text"],
        )

    def test_identity_correction_accepted_with_siblings_preserved(self) -> None:
        from copy import deepcopy

        invalid = self._invalid_output()
        corrected = deepcopy(invalid)
        corrected["supporting_evidence"][0]["exact_text"] = self.PRIOR_STATE[
            "supporting_evidence"
        ][0]["exact_text"]
        corrected["current_beliefs"].pop(1)
        caller = ScriptedRoleCaller([invalid, corrected])
        value, _ = self._run_role(caller)

        feedback = caller.calls[1]["payload"]["validation_feedback"]
        codes = sorted(
            obligation["issue_code"] for obligation in feedback["obligations"]
        )
        self.assertEqual(
            codes,
            ["basic_literal_identity_mismatch"],
        )
        self.assertEqual(
            [str(item) for item in value.current_beliefs],
            corrected["current_beliefs"],
        )
        self.assertEqual(
            value.supporting_evidence[0].exact_text,
            self.PRIOR_STATE["supporting_evidence"][0]["exact_text"],
        )
        self.assertEqual(value.supporting_evidence[1].claim, "cash_reserves=42")
        self.assertEqual(
            [str(item) for item in value.next_information_needs],
            ["Need one?"],
        )
        self.assertEqual([str(item) for item in value.hypotheses], ["One hypothesis."])
        self.assertEqual(
            [str(item) for item in value.resolved_questions],
            ["Resolved one."],
        )

    def test_claim_change_alongside_restored_literal_is_rejected(self) -> None:
        from copy import deepcopy

        invalid = self._invalid_output()
        corrected = deepcopy(invalid)
        corrected["supporting_evidence"][0]["exact_text"] = self.PRIOR_STATE[
            "supporting_evidence"
        ][0]["exact_text"]
        corrected["supporting_evidence"][0]["claim"] = "Rewritten claim."
        corrected["current_beliefs"].pop(1)
        caller = ScriptedRoleCaller([invalid, corrected])
        try:
            value, _ = self._run_role(caller)
        except CandidateExecutionRejected:
            return
        # When a safe projection accepts the authorized repairs, the unrelated
        # claim rewrite must be discarded, never laundered into the final state.
        first = value.supporting_evidence[0].to_dict()
        self.assertEqual(first["claim"], "The filing identifies the registrant.")
        self.assertEqual(
            first["exact_text"],
            self.PRIOR_STATE["supporting_evidence"][0]["exact_text"],
        )
        self.assertEqual(
            [str(item) for item in value.current_beliefs],
            ["The filing identifies the registrant."],
        )

    def test_truly_new_basic_ref_is_remove_only_and_never_accepted(self) -> None:
        from copy import deepcopy

        from stock_opportunity_agent.research.evolution_research_validation import (
            _raw_basic_literal_identity_issues,
        )

        prior = ResearchState.from_dict(self.PRIOR_STATE)
        invented = deepcopy(self._invalid_output())
        invented["supporting_evidence"][0] = {
            "claim": "Invented basic claim.",
            "exact_text": "invented literal",
            "kind": "basic_info",
            "projection_id": "projection_invented",
        }
        issues = _raw_basic_literal_identity_issues(invented, prior)
        self.assertEqual(
            [(issue.code, issue.paths, issue.allowed_repairs) for issue in issues],
            [
                (
                    "basic_ref_not_in_prior_state",
                    ("supporting_evidence[0]",),
                    ("remove",),
                )
            ],
        )
        caller = ScriptedRoleCaller([invented, deepcopy(invented)])
        try:
            value, _ = self._run_role(caller)
        except CandidateExecutionRejected:
            return
        # When the machinery accepts through projection plus deterministic
        # fallback, the invented ref must never survive into the final state
        # and no fabricated literal may remain.
        final_rows = [
            row.to_dict() if hasattr(row, "to_dict") else dict(row)
            for row in value.supporting_evidence
        ]
        prior_literal = self.PRIOR_STATE["supporting_evidence"][0]["exact_text"]
        self.assertTrue(
            all(row.get("projection_id") != "projection_invented" for row in final_rows)
        )
        for row in final_rows:
            if row.get("kind") == "basic_info":
                self.assertEqual(row.get("exact_text"), prior_literal)
        self.assertFalse(
            any(
                "revenue_growth_yoy" in str(item)
                for item in value.current_beliefs
            )
        )

    def test_ambiguous_prior_literal_permits_removal_not_substitution(self) -> None:
        from copy import deepcopy

        from stock_opportunity_agent.research.evolution_research_validation import (
            _normalize_research_state_output,
            _raw_basic_literal_identity_issues,
        )

        prior_dict = deepcopy(self.PRIOR_STATE)
        prior_dict["supporting_evidence"].append(
            {
                "claim": "The filing identifies the registrant.",
                "exact_text": "another distinct prior literal",
                "kind": "basic_info",
                "projection_id": "projection_lit_a",
            }
        )
        prior = ResearchState.from_dict(prior_dict)
        invalid = deepcopy(prior_dict)
        invalid["supporting_evidence"][0]["exact_text"] = "a third mutated literal"
        issues = _raw_basic_literal_identity_issues(invalid, prior)
        self.assertEqual(
            [(issue.code, issue.allowed_repairs) for issue in issues],
            [("basic_literal_identity_ambiguous", ("remove",))],
        )
        with self.assertRaises(StructuredValidationError) as raised:
            _normalize_research_state_output(
                dict(invalid),
                previous_state=prior,
                evaluation_context=self.EVALUATION_CONTEXT,
            )
        self.assertIn(
            "basic_literal_identity_ambiguous",
            {issue.code for issue in raised.exception.issues},
        )
        substituted = deepcopy(invalid)
        substituted["supporting_evidence"][0]["exact_text"] = (
            "another distinct prior literal"
        )
        prior_literals = {
            row["exact_text"]
            for row in prior_dict["supporting_evidence"]
            if row.get("kind") == "basic_info"
        }
        for variant in (substituted, None):
            if variant is None:
                variant = deepcopy(invalid)
                del variant["supporting_evidence"][0]
            caller = ScriptedRoleCaller([invalid, variant])
            try:
                value, _ = self._run_role(caller, prior)
            except CandidateExecutionRejected:
                continue
            # A substitution under remove-only authority is never laundered
            # into new content: every surviving Basic literal stays a byte
            # exact prior literal and the mutated one is gone.
            final_literals = [
                row.to_dict()["exact_text"]
                for row in value.supporting_evidence
                if row.to_dict().get("kind") == "basic_info"
            ]
            self.assertTrue(
                all(literal in prior_literals for literal in final_literals)
            )
            self.assertNotIn("a third mutated literal", final_literals)

    def test_signal_rows_are_outside_basic_identity_checks(self) -> None:
        from copy import deepcopy

        from stock_opportunity_agent.research.evolution_research_validation import (
            _raw_basic_literal_identity_issues,
        )

        prior = ResearchState.from_dict(self.PRIOR_STATE)
        output = self._invalid_output()
        output["supporting_evidence"][1]["claim"] = "Signal view text."
        issues = _raw_basic_literal_identity_issues(output, prior)
        self.assertEqual(
            [(issue.code, issue.paths) for issue in issues],
            [
                (
                    "basic_literal_identity_mismatch",
                    ("supporting_evidence[0].exact_text",),
                )
            ],
        )

    def test_fallback_restores_prior_literal_and_removes_assertion(self) -> None:
        from copy import deepcopy

        invalid = self._invalid_output()
        still_invalid = deepcopy(invalid)
        still_invalid["supporting_evidence"][0]["exact_text"] = (
            "8-K body with 230.425 and 240.14a-12 markers"
        )
        caller = ScriptedRoleCaller([invalid, still_invalid])
        caller.max_structured_corrections = 1
        events: list[dict] = []
        caller.on_progress = events.append
        value, _ = self._run_role(caller)
        self.assertEqual(
            value.supporting_evidence[0].exact_text,
            self.PRIOR_STATE["supporting_evidence"][0]["exact_text"],
        )
        self.assertEqual(
            [str(item) for item in value.current_beliefs],
            ["The filing identifies the registrant."],
        )
        fallback_events = [
            event
            for event in events
            if event["event_type"] == "structured_validation_fallback_applied"
        ]
        self.assertEqual(len(fallback_events), 1)
        progress_events = [event for event in events if event["event_type"] == "mechanical_repair_progress"]
        self.assertTrue(any("current_beliefs[1]" in event.get("actions", {}).get("removed_paths", []) for event in progress_events))
        self.assertIn(
            "supporting_evidence[0].exact_text",
            fallback_events[0]["normalized_paths"],
        )

    def test_literal_only_identity_fallback_restores_without_removals(self) -> None:
        from copy import deepcopy

        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )
        from stock_opportunity_agent.research.evolution_research_validation import (
            _normalize_research_state_output,
        )

        prior = ResearchState.from_dict(self.PRIOR_STATE)
        invalid = deepcopy(self.PRIOR_STATE)
        invalid["supporting_evidence"][0]["exact_text"] = (
            "8-K body with 230.425 and 17 CFR 240.14a-12 markers"
        )
        with self.assertRaises(StructuredValidationError) as raised:
            _normalize_research_state_output(
                dict(invalid),
                previous_state=prior,
                evaluation_context=self.EVALUATION_CONTEXT,
            )
        self.assertEqual(
            {issue.code for issue in raised.exception.issues},
            {"basic_literal_identity_mismatch"},
        )
        recovered = _research_state_evidence_grounding_fallback(
            invalid, raised.exception
        )
        self.assertIsNotNone(recovered)
        restored, actions = recovered
        self.assertEqual(actions["removed_paths"], ())
        self.assertEqual(
            actions["normalized_paths"], ("supporting_evidence[0].exact_text",)
        )
        self.assertEqual(
            restored["supporting_evidence"][0]["exact_text"],
            self.PRIOR_STATE["supporting_evidence"][0]["exact_text"],
        )
        self.assertEqual(
            restored["current_beliefs"], self.PRIOR_STATE["current_beliefs"]
        )

        # The production caller accepts the restoration only after full
        # parser revalidation, with every untouched sibling preserved.
        caller = ScriptedRoleCaller([invalid, deepcopy(invalid)])
        caller.max_structured_corrections = 1
        events: list[dict] = []
        caller.on_progress = events.append
        value, _ = self._run_role(caller)
        self.assertEqual(
            value.supporting_evidence[0].exact_text,
            self.PRIOR_STATE["supporting_evidence"][0]["exact_text"],
        )
        self.assertEqual(value.supporting_evidence[1].claim, "cash_reserves=42")
        self.assertEqual(
            [str(item) for item in value.current_beliefs],
            self.PRIOR_STATE["current_beliefs"],
        )
        self.assertEqual(
            [str(item) for item in value.next_information_needs], ["Need one?"]
        )
        self.assertEqual(
            [str(item) for item in value.hypotheses], ["One hypothesis."]
        )
        self.assertEqual(
            [str(item) for item in value.resolved_questions], ["Resolved one."]
        )
        fallback_events = [
            event
            for event in events
            if event["event_type"] == "structured_validation_fallback_applied"
        ]
        self.assertEqual(len(fallback_events), 1)
        self.assertEqual(fallback_events[0]["removed_paths"], [])
        self.assertEqual(
            fallback_events[0]["normalized_paths"],
            ["supporting_evidence[0].exact_text"],
        )

    def test_literal_restoration_validates_index_and_row_type(self) -> None:
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )

        def failure_for(path: str) -> StructuredValidationError:
            return StructuredValidationError(
                [
                    ValidationIssue(
                        code="basic_literal_identity_mismatch",
                        message="identity defect",
                        paths=(path,),
                        allowed_repairs=("replace",),
                        repair_context={
                            "projection_id": "projection_lit_a",
                            "prior_exact_text": self.PRIOR_STATE[
                                "supporting_evidence"
                            ][0]["exact_text"],
                        },
                    )
                ]
            )

        output = dict(self.PRIOR_STATE)
        for path in (
            "supporting_evidence[9].exact_text",
            "supporting_evidence[1].exact_text",
        ):
            with self.subTest(path=path):
                self.assertIsNone(
                    _research_state_evidence_grounding_fallback(
                        output, failure_for(path)
                    )
                )
        self.assertEqual(output, self.PRIOR_STATE)

    def test_remove_only_identity_codes_require_remove_authority(self) -> None:
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )

        output = dict(self.PRIOR_STATE)
        for code in (
            "basic_ref_not_in_prior_state",
            "basic_literal_identity_ambiguous",
        ):
            for repairs in (("replace",), ("add",)):
                with self.subTest(code=code, repairs=repairs):
                    self.assertIsNone(
                        _research_state_evidence_grounding_fallback(
                            output,
                            StructuredValidationError(
                                [
                                    ValidationIssue(
                                        code=code,
                                        message="identity defect",
                                        paths=("supporting_evidence[0]",),
                                        allowed_repairs=repairs,
                                        repair_context={
                                            "projection_id": "projection_lit_a"
                                        },
                                    )
                                ]
                            ),
                        )
                    )
            with self.subTest(code=code, repairs=("remove",)):
                recovered = _research_state_evidence_grounding_fallback(
                    output,
                    StructuredValidationError(
                        [
                            ValidationIssue(
                                code=code,
                                message="identity defect",
                                paths=("supporting_evidence[0]",),
                                allowed_repairs=("remove",),
                                repair_context={
                                    "projection_id": "projection_lit_a"
                                },
                            )
                        ]
                    ),
                )
            self.assertIsNotNone(recovered)
            restored, actions = recovered
            self.assertEqual(
                actions["removed_paths"],
                ("supporting_evidence[0]", "current_beliefs[0]"),
            )
            self.assertEqual(actions["normalized_paths"], ())
            self.assertEqual(restored["current_beliefs"], ["cash_reserves=42"])
            self.assertEqual(
                restored["supporting_evidence"][0]["signal_ref"],
                "cash_reserves:v1",
            )
        self.assertEqual(output, self.PRIOR_STATE)

    def test_novel_basic_ref_flagged_when_prior_has_only_signal_evidence(self) -> None:
        from copy import deepcopy

        from stock_opportunity_agent.research.evolution_research_validation import (
            _normalize_research_state_output,
            _raw_basic_literal_identity_issues,
            _validate_research_state_refs,
        )

        signal_only = deepcopy(self.PRIOR_STATE)
        signal_only["supporting_evidence"].pop(0)
        prior = ResearchState.from_dict(signal_only)
        output = deepcopy(self.PRIOR_STATE)
        issues = _raw_basic_literal_identity_issues(output, prior)
        self.assertEqual(
            [(issue.code, issue.paths, issue.allowed_repairs) for issue in issues],
            [
                (
                    "basic_ref_not_in_prior_state",
                    ("supporting_evidence[0]",),
                    ("remove",),
                )
            ],
        )
        # Initialize (no previous state) stays outside the identity check.
        self.assertEqual(_raw_basic_literal_identity_issues(output, None), [])

        # A combined numeric defect and the novel ref appear together in the
        # same initial feedback instead of the numeric issue masking the ref.
        combined = deepcopy(output)
        combined["current_beliefs"][1] = "revenue_growth_yoy=0.182443"
        with self.assertRaises(StructuredValidationError) as raised:
            _normalize_research_state_output(
                dict(combined),
                previous_state=prior,
                evaluation_context=self.EVALUATION_CONTEXT,
            )
        self.assertEqual(
            {issue.code for issue in raised.exception.issues},
            {"assertion_without_support", "basic_ref_not_in_prior_state"},
        )
        # The deep tagged-ref guard still rejects a surviving novel ref.
        with self.assertRaises(ValidationError) as guard:
            _validate_research_state_refs(
                ResearchState.from_dict(dict(combined)),
                phase="reflect",
                previous_state=prior,
            )
        self.assertIn(
            "reflect cannot introduce a new Basic Info ref", str(guard.exception)
        )

        caller = ScriptedRoleCaller([combined, deepcopy(combined)])
        try:
            value, _ = self._run_role(caller, prior)
        except CandidateExecutionRejected:
            return
        final_rows = [
            row.to_dict() if hasattr(row, "to_dict") else dict(row)
            for row in value.supporting_evidence
        ]
        self.assertTrue(
            all(row.get("projection_id") != "projection_lit_a" for row in final_rows)
        )


class ScopedCorrectionProjectionTests(TestCase):
    def test_runtime_need_fallback_preserves_evidence_and_uses_exact_instructions(self) -> None:
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_need_transition_fallback,
        )
        original = {"next_information_needs": ["Cash and funding?"],
                    "supporting_evidence": [{"claim": "cash_reserves=42"}]}
        issues = [ValidationIssue(
            code="research_need_transition_invalid", message="opaque wording",
            paths=("next_information_needs[0]",),
            repair_context={"prior_need": "Cash and funding?",
                            "returned_path": "next_information_needs[0]",
                            "returned_need": "Cash and funding?",
                            "required_action": "replace_with_exact_residual",
                            "required_need": "Funding remains unresolved."},
        ), ValidationIssue(
            code="research_need_transition_invalid", message="another wording",
            paths=("next_information_needs[1]",),
            repair_context={"prior_need": "Guidance?", "required_action": "restore_exactly",
                            "required_need": "Guidance?"},
        )]
        value, _ = _research_need_transition_fallback(original, StructuredValidationError(issues))
        self.assertEqual(value["next_information_needs"], ["Funding remains unresolved.", "Guidance?"])
        self.assertEqual(value["supporting_evidence"], original["supporting_evidence"])
        self.assertEqual(original["next_information_needs"], ["Cash and funding?"])
        self.assertIsNone(_research_need_transition_fallback(original, StructuredValidationError([
            ValidationIssue(code="unknown_issue", message="restore everything",
                            paths=("next_information_needs",)),
        ])))

    def test_controller_compaction_mode_preserves_ordinary_correction_siblings(self) -> None:
        invalid = {"next_information_needs": ["Preserve guidance question.", "Original liquidity question."]}
        corrected = {"next_information_needs": ["Unrelated rewrite.", "Financing remains unresolved."]}
        for structured in (True,):
            with self.subTest(structured=structured):
                caller = ScriptedRoleCaller([invalid, corrected])

                def parse(value):
                    if value["next_information_needs"][1] != "Financing remains unresolved.":
                        message = "next_information_needs[1] must retain the exact residual"
                        if structured:
                            raise StructuredValidationError([ValidationIssue(
                                code="need_transition_invalid", message=message,
                                paths=("next_information_needs[1]",),
                                repair_context={"write_scope_complete": True},
                            )])
                        raise ValidationError(message)
                    if value["next_information_needs"][0] != invalid["next_information_needs"][0]:
                        raise ValidationError("next_information_needs[0] was changed")
                    return value

                value, _ = evolution_runtime_module._complete_parsed_role(
                    caller, stage="research_controller_reflect",
                    system_prompt="Return the fixed contract.", payload={}, parser=parse,
                    allow_outcomes=False, enforce_scoped_correction=True,
                    exact_compaction_scope=True, stable_correction_prefix=True,
                )
                self.assertEqual(value["next_information_needs"], [
                    "Preserve guidance question.", "Financing remains unresolved.",
                ])
                self.assertEqual(len(caller.calls), 2)

    def test_signal_quantity_feedback_names_same_signal_evidence_locations(self) -> None:
        from stock_opportunity_agent.research import (
            evolution_research_validation,
        )

        claim = "Cash of $611.5 million against monthly outflow of $203.9 million."
        state = evolution_runtime_module.ResearchState(
            supporting_evidence=(
                evolution_runtime_module.ResearchEvidenceRef(
                    kind="signal",
                    claim=claim,
                    signal_ref="liquidity_runway_months:v1",
                    evidence_group="supporting",
                    evidence_index=0,
                ),
            ),
            next_information_needs=("Need liquidity runway.",),
        )
        available = {
            "liquidity_runway_months:v1": [
                ("supporting", 0, '{"val":611500000}'),
                ("supporting", 1, '{"val":2446400000}'),
            ]
        }
        issues = evolution_research_validation._validate_signal_claim_quantities(
            {claim: [(0, '{"val":611500000}')]}, state, available
        )
        self.assertEqual(len(issues), 1)
        context = issues[0].repair_context
        self.assertEqual(
            context["missing_quantity_groups"], ["203.9|203900000"]
        )
        hints = evolution_research_validation._signal_quantity_location_hints(
            ["203.9|203900000"], ("liquidity_runway_months:v1",), available
        )
        self.assertEqual(hints, {})
        available_with_outflow = {
            "liquidity_runway_months:v1": [
                ("supporting", 0, '{"val":611500000}'),
                ("supporting", 1, '{"val":203900000}'),
            ]
        }
        issues = evolution_research_validation._validate_signal_claim_quantities(
            {claim: [(0, '{"val":611500000}')]}, state, available_with_outflow
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("supporting[1]", issues[0].message)
        self.assertEqual(
            issues[0].repair_context["quantity_location_hints"],
            {"203.9|203900000": ["supporting[1]"]},
        )
        self.assertEqual(
            issues[0].repair_context["permitted_evidence_ref_paths"],
            [
                "supporting_evidence[0].evidence_group",
                "supporting_evidence[0].evidence_index",
            ],
        )
        self.assertEqual(
            issues[0].dependent_paths,
            (
                "supporting_evidence[0].evidence_group",
                "supporting_evidence[0].evidence_index",
            ),
        )

    def test_research_state_fallback_uses_issue_code_not_message_text(self) -> None:
        invalid = {
            "hypotheses": ["A catalyst may matter."],
            "current_beliefs": ["Revenue was $42 million.", "Margins improved."],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": "Revenue was $42 million.",
                    "projection_id": "bad",
                    "exact_text": "Revenue was $4 million.",
                },
                {
                    "kind": "basic_info",
                    "claim": "Margins improved.",
                    "projection_id": "good",
                    "exact_text": "Margins improved.",
                },
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": ["What guidance is visible?"],
            "decision": "continue",
        }
        issue_fields = {
            "code": "claim_quantity_not_supported",
            "paths": ("supporting_evidence[0].claim",),
            "allowed_repairs": ("replace", "remove", "add"),
            "dependent_paths": ("current_beliefs[0]",),
            "repair_context": {
                "missing_quantity_groups": ["42"],
                "missing_quantity_literals": ["42"],
                "same_claim_evidence_paths": [
                    "supporting_evidence[0].claim"
                ],
            },
        }

        results = []
        for message in (
            "Unsupported quantity.",
            "La cantidad no coincide; punctuation changed!",
        ):
            failure = StructuredValidationError(
                [ValidationIssue(message=message, **issue_fields)]
            )
            results.append(
                evolution_runtime_module._research_state_evidence_grounding_fallback(
                    invalid, failure
                )
            )

        self.assertEqual(results[0], results[1])
        self.assertEqual(
            results[0][0]["supporting_evidence"],
            [invalid["supporting_evidence"][1]],
        )
        self.assertEqual(results[0][0]["current_beliefs"], ["Margins improved."])

    def test_nested_projection_preserves_null_siblings_and_source_objects(self) -> None:
        invalid = {"rows": [{"value": "invalid", "keep": [1, 2]}], "keep": "old"}
        corrected = {"rows": [{"value": None, "keep": []}], "keep": "drift"}
        projected, paths = evolution_runtime_module._project_scoped_correction(
            invalid, corrected, ["rows[0].value"]
        )
        self.assertEqual(
            projected,
            {"rows": [{"value": None, "keep": [1, 2]}], "keep": "old"},
        )
        self.assertEqual(paths, ("rows[0].value",))
        projected["rows"][0]["keep"].append(3)
        self.assertEqual(invalid["rows"][0]["keep"], [1, 2])
        self.assertEqual(corrected["rows"][0]["keep"], [])

    def test_projection_revalidation_failure_retains_projected_object_for_next_correction(self) -> None:
        invalid = {
            "next_information_needs": [
                "Remove baseline bridge question.",
                "Keep sibling need.",
            ],
            "current_beliefs": ["Belief with 42 dollars."],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": "Copied claim.",
                    "projection_id": "p",
                    "exact_text": "text",
                }
            ],
            "open_questions": ["Unrelated open question."],
            "decision": "continue",
        }
        corrected = {
            # The model reordered the flagged need instead of removing it, so
            # the sibling shift is unrelated drift the projection must drop.
            "next_information_needs": [
                "Keep sibling need.",
                "Remove baseline bridge question.",
            ],
            "current_beliefs": ["Belief with 42 dollars."],
            "supporting_evidence": invalid["supporting_evidence"],
            "open_questions": ["Unrelated open question."],
            "decision": "continue",
        }

        def parse(value):
            needs = value["next_information_needs"]
            if any("baseline" in need for need in needs):
                raise ValidationError(
                    "invalid_field='next_information_needs[0]', "
                    f"next_information_needs[0]={needs[0]!r}. Remove this item"
                )
            if value["current_beliefs"][0] != value["supporting_evidence"][0]["claim"]:
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="assertion_without_support",
                            message=(
                                "quantitative ResearchState assertions must each "
                                "copy one supporting_evidence claim byte-for-byte"
                            ),
                            paths=("current_beliefs[0]",),
                            allowed_repairs=("replace", "remove"),
                        )
                    ]
                )
            return value

        final = {
            "next_information_needs": ["Keep sibling need.", "Keep sibling need."],
            "current_beliefs": ["Copied claim."],
            "supporting_evidence": invalid["supporting_evidence"],
            "open_questions": ["Unrelated open question."],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([invalid, corrected, final])
        caller.max_structured_corrections = 2
        value, _ = evolution_runtime_module._complete_parsed_role(
            caller,
            stage="research_controller_initialize",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=parse,
            allow_outcomes=False,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            stable_correction_prefix=True,
        )
        self.assertEqual(value["current_beliefs"], ["Copied claim."])
        self.assertEqual(len(caller.calls), 3)
        first = caller.calls[1]["payload"]["validation_feedback"]
        second = caller.calls[2]["payload"]["validation_feedback"]
        self.assertNotEqual(first, second)
        # The retained invalid output is the safe projection: the flagged need
        # was repaired, the drifted sibling rewrite was discarded, and every
        # otherwise-valid unrelated scalar/list value survives byte-for-byte.
        self.assertEqual(
            second["invalid_output"],
            {
                "next_information_needs": [
                    "Keep sibling need.",
                    "Keep sibling need.",
                ],
                "current_beliefs": ["Belief with 42 dollars."],
                "supporting_evidence": invalid["supporting_evidence"],
                "open_questions": ["Unrelated open question."],
                "decision": "continue",
            },
        )
        self.assertEqual(second["obligations"][0]["issue_code"], "assertion_without_support")
        self.assertEqual(
            second["obligations"][0]["must_change_paths"], ["current_beliefs[0]"]
        )

    def test_no_projection_scope_rejection_keeps_original_feedback_unchanged(self) -> None:
        invalid = {
            "next_information_needs": [
                "Remove baseline question.",
                "Keep sibling.",
                "Keep second sibling.",
            ]
        }
        corrected = {
            "next_information_needs": [
                "Fixed unrelated rewrite.",
                "Changed sibling.",
            ]
        }

        def parse(value):
            if "baseline" in value["next_information_needs"][0]:
                raise ValidationError(
                    "invalid_field='next_information_needs[0]' must change"
                )
            return value

        caller = ScriptedRoleCaller([invalid, corrected, corrected])
        caller.max_structured_corrections = 2
        with self.assertRaises(CandidateExecutionRejected):
            evolution_runtime_module._complete_parsed_role(
                caller,
                stage="research_controller_initialize",
                system_prompt="Return the fixed contract.",
                payload={},
                parser=parse,
                allow_outcomes=False,
                enforce_scoped_correction=True,
                exact_compaction_scope=True,
                stable_correction_prefix=True,
            )
        self.assertEqual(len(caller.calls), 3)
        first = caller.calls[1]["payload"]["validation_feedback"]
        second = caller.calls[2]["payload"]["validation_feedback"]
        # The original invalid object and obligations stay unchanged, but the
        # retry's validation_error carries the drift diagnostic so the request
        # is never a byte-identical replay that a deterministic response cache
        # would answer with the just-rejected drifted output.
        self.assertEqual(second["invalid_output"], first["invalid_output"])
        self.assertEqual(
            second["required_change_paths"], first["required_change_paths"]
        )
        self.assertEqual(second["obligations"], first["obligations"])
        self.assertNotIn("unrelated valid content", first["validation_error"])
        self.assertIn("unrelated valid content", second["validation_error"])
        self.assertEqual(
            caller.calls[2]["payload"]["validation_feedback"]["invalid_output"],
            invalid,
        )

    def test_projection_refuses_missing_paths_and_ambiguous_index_shifts(self) -> None:
        invalid = {"rows": [{"value": 0}, {"value": 1}]}
        for corrected, path in (
            ({"rows": [{"value": 1}]}, "rows[0].value"),
            ({"rows": [{}, {"value": 1}]}, "rows[0].value"),
            (invalid, "rows[*].value"),
            (invalid, "rows[-1].value"),
            (invalid, "rows[0:1]"),
        ):
            with self.subTest(path=path, corrected=corrected):
                self.assertIsNone(
                    evolution_runtime_module._project_scoped_correction(
                        invalid, corrected, [path]
                    )
                )

    def test_structured_issue_projects_by_stable_id_after_reordering(self) -> None:
        invalid = {
            "rows": [
                {"row_id": "bad", "value": 0, "keep": "bad sibling"},
                {"row_id": "good", "value": 2, "keep": "good sibling"},
            ],
            "keep": "root sibling",
        }
        corrected = {
            "rows": [
                {"row_id": "good", "value": 99, "keep": "drift"},
                {"row_id": "bad", "value": 1, "keep": "drift"},
            ],
            "keep": "drift",
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        def parse(value):
            if value["rows"][0]["value"] <= 0:
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="row_value_invalid",
                            message=(
                                "diagnostic prose mentions rows[1].value but does not "
                                "authorize it"
                            ),
                            paths=("rows[0].value",),
                            item_id="bad",
                            item_id_field="row_id",
                        )
                    ]
                )
            return value

        value, usage = evolution_runtime_module._complete_parsed_role(
            caller,
            stage="fixture",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=parse,
            allow_outcomes=False,
            enforce_scoped_correction=True,
            stable_correction_prefix=True,
        )

        self.assertEqual(
            value,
            {
                "rows": [
                    {"row_id": "bad", "value": 1, "keep": "bad sibling"},
                    {"row_id": "good", "value": 2, "keep": "good sibling"},
                ],
                "keep": "root sibling",
            },
        )
        self.assertEqual(usage.llm_calls, 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["validation_contract"], "structured-validation-v1")
        self.assertEqual(feedback["required_change_paths"], ["rows[0].value"])
        self.assertEqual(feedback["obligations"][0]["item_id"], "bad")

    def test_structured_issue_adds_only_missing_stable_item(self) -> None:
        invalid = {"rows": [{"row_id": "present", "value": 1}]}
        corrected = {
            "rows": [
                {"row_id": "present", "value": 99},
                {"row_id": "missing", "value": 2},
            ]
        }
        projected = evolution_runtime_module._project_scoped_correction(
            invalid,
            corrected,
            ["rows[1]"],
            stable_item_paths={
                "rows[1]": {
                    "item_id": "missing",
                    "item_id_field": "row_id",
                    "allowed_repairs": ("add",),
                }
            },
        )

        self.assertEqual(
            projected,
            (
                {
                    "rows": [
                        {"row_id": "present", "value": 1},
                        {"row_id": "missing", "value": 2},
                    ]
                },
                ("rows[1]",),
            ),
        )

    def test_remaining_correction_cannot_launder_unrelated_drift(self) -> None:
        for repairable_shape in (True, False):
            with self.subTest(repairable_shape=repairable_shape):
                invalid = {"rows": [{"value": 0}, {"value": 2}], "keep": "original"}
                drifted = {"rows": [{"value": -1}, {"value": 2}], "keep": "drift"}
                if not repairable_shape:
                    drifted["rows"].pop()
                corrected = {"rows": [{"value": 1}, {"value": 2}], "keep": "original"}
                caller = ScriptedRoleCaller([invalid, drifted, corrected])
                caller.max_structured_corrections = 2

                def parse(value):
                    if value["rows"][0]["value"] <= 0:
                        raise ValidationError("rows[0].value must be positive")
                    return value

                value, usage = evolution_runtime_module._complete_parsed_role(
                    caller,
                    stage="fixture",
                    system_prompt="Return the fixed contract.",
                    payload={},
                    parser=parse,
                    allow_outcomes=False,
                    enforce_scoped_correction=True,
                    stable_correction_prefix=True,
                )
                self.assertEqual(value, corrected)
                self.assertEqual(usage.llm_calls, 3)
                feedback = caller.calls[2]["payload"]["validation_feedback"]
                self.assertEqual(feedback["invalid_output"]["keep"], "original")
                self.assertEqual(len(feedback["invalid_output"]["rows"]), 2)
                self.assertEqual(feedback["required_change_paths"], ["rows[0].value"])

    def test_unprojectable_drift_retry_is_not_a_byte_identical_replay(self) -> None:
        invalid = {"rows": [{"value": 0}, {"value": 2}], "keep": "original"}
        drifted = {"rows": [{"value": 1}], "keep": "drifted"}
        corrected = {"rows": [{"value": 1}, {"value": 2}], "keep": "original"}
        caller = ScriptedRoleCaller([invalid, drifted, corrected])
        caller.max_structured_corrections = 2

        def parse(value):
            if value["rows"][0]["value"] <= 0:
                raise ValidationError("rows[0].value must be positive")
            return value

        value, usage = evolution_runtime_module._complete_parsed_role(
            caller,
            stage="fixture",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=parse,
            allow_outcomes=False,
            enforce_scoped_correction=True,
            stable_correction_prefix=True,
        )
        self.assertEqual(value, corrected)
        self.assertEqual(usage.llm_calls, 3)
        first = caller.calls[1]["payload"]["validation_feedback"]
        retry = caller.calls[2]["payload"]["validation_feedback"]
        # The retry keeps the original invalid object and obligations, but its
        # validation_error must carry the drift diagnostic: a byte-identical
        # retry would deterministically replay the just-rejected drifted
        # answer from the response cache and waste the correction budget.
        self.assertNotIn("unrelated valid content", first["validation_error"])
        self.assertIn("unrelated valid content", retry["validation_error"])
        self.assertIn("unrelated_changed_paths", retry["validation_error"])
        # Anti-laundering still holds: the drift note never widens the
        # authorized repair scope.
        self.assertEqual(retry["required_change_paths"], ["rows[0].value"])
        self.assertEqual(retry["invalid_output"]["keep"], "original")
        self.assertEqual(len(retry["invalid_output"]["rows"]), 2)

    def test_exact_compaction_scope_correction_cannot_undo_prior_need_repair(self) -> None:
        initial = {
            "next_information_needs": [
                "What will the 2027 capex plan imply for capacity?",
                "Liquidity runway remains unresolved.",
            ],
            "current_beliefs": ["Revenue will double by 2027."],
            "decision": "continue",
        }
        repaired_need = "What does the current capex plan imply for capacity?"
        first_correction = {
            "next_information_needs": [
                repaired_need,
                "Liquidity runway remains unresolved.",
            ],
            "current_beliefs": ["Margins expand 300bps in 2027."],
            "decision": "continue",
        }
        second_correction = {
            "next_information_needs": [
                "What will the 2027 capex plan imply for capacity?",
                "Liquidity runway remains unresolved.",
            ],
            "current_beliefs": ["Margins expand sequentially."],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([initial, first_correction, second_correction])
        caller.max_structured_corrections = 2
        events = []
        caller.on_progress = events.append

        def parse(value):
            issues = [
                ValidationIssue(
                    code="need_temporal_scope_invalid",
                    message=(
                        f"next_information_needs[{index}] requests future-dated "
                        "information"
                    ),
                    paths=(f"next_information_needs[{index}]",),
                )
                for index, need in enumerate(value["next_information_needs"])
                if "2027" in need
            ]
            issues.extend(
                ValidationIssue(
                    code="belief_quantity_unsupported",
                    message=f"current_beliefs[{index}] cites an unsupported quantity",
                    paths=(f"current_beliefs[{index}]",),
                )
                for index, belief in enumerate(value["current_beliefs"])
                if any(character.isdigit() for character in belief)
            )
            if issues:
                raise StructuredValidationError(issues)
            return value

        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={}, parser=parse,
            allow_outcomes=False, enforce_scoped_correction=True,
            exact_compaction_scope=True, stable_correction_prefix=True,
        )

        self.assertEqual(value, {
            "next_information_needs": [
                repaired_need,
                "Liquidity runway remains unresolved.",
            ],
            "current_beliefs": ["Margins expand sequentially."],
            "decision": "continue",
        })
        self.assertEqual(usage.llm_calls, 3)
        feedback = caller.calls[2]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], first_correction)
        self.assertEqual(feedback["required_change_paths"], ["current_beliefs[0]"])
        projections = [
            event for event in events
            if event["event_type"] == "structured_correction_projection_applied"
        ]
        self.assertEqual(len(projections), 1)
        self.assertEqual(projections[0]["stage"], "research_controller_reflect")
        self.assertEqual(
            projections[0]["request_stage"], "research_controller_reflect_correction"
        )
        self.assertEqual(projections[0]["correction_count"], 2)
        self.assertEqual(projections[0]["copied_paths"], ["current_beliefs[0]"])
        self.assertEqual(projections[0]["discarded_paths"], ["next_information_needs"])

    def test_exact_compaction_scope_keeps_permitted_dependency_edits(self) -> None:
        initial = {
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": "Revenue was $42 million.",
                    "projection_id": "p1",
                    "exact_text": "Revenue was $4 million.",
                }
            ],
            "current_beliefs": ["Cash position stayed flat."],
            "decision": "continue",
        }
        for corrected, expected_beliefs in (
            (
                {
                    "supporting_evidence": [
                        {
                            "kind": "basic_info",
                            "claim": "Margins improved.",
                            "projection_id": "p1",
                            "exact_text": "Revenue was $4 million.",
                        }
                    ],
                    "current_beliefs": ["Margins improved."],
                    "decision": "continue",
                },
                ["Margins improved."],
            ),
            (
                {
                    "supporting_evidence": [
                        {
                            "kind": "basic_info",
                            "claim": "Margins improved.",
                            "projection_id": "p1",
                            "exact_text": "Revenue was $4 million.",
                        }
                    ],
                    "current_beliefs": ["Cash position stayed flat."],
                    "decision": "continue",
                },
                ["Cash position stayed flat."],
            ),
        ):
            with self.subTest(expected_beliefs=expected_beliefs):
                caller = ScriptedRoleCaller([initial, corrected])
                events = []
                caller.on_progress = events.append

                def parse(value):
                    if "42" in value["supporting_evidence"][0]["claim"]:
                        raise StructuredValidationError(
                            [
                                ValidationIssue(
                                    code="claim_quantity_not_supported",
                                    message=(
                                        "supporting_evidence[0].claim cites an "
                                        "unsupported quantity"
                                    ),
                                    paths=("supporting_evidence[0].claim",),
                                    dependent_paths=("current_beliefs[0]",),
                                )
                            ]
                        )
                    if "42" in value["current_beliefs"][0]:
                        raise ValidationError(
                            "current_beliefs[0] cites an unsupported quantity"
                        )
                    return value

                value, usage = evolution_runtime_module._complete_parsed_role(
                    caller, stage="research_controller_reflect",
                    system_prompt="Return the fixed contract.", payload={},
                    parser=parse, allow_outcomes=False,
                    enforce_scoped_correction=True, exact_compaction_scope=True,
                    stable_correction_prefix=True,
                )
                self.assertEqual(value, corrected)
                self.assertEqual(value["current_beliefs"], expected_beliefs)
                self.assertEqual(usage.llm_calls, 2)
                self.assertEqual(events, [])
                feedback = caller.calls[1]["payload"]["validation_feedback"]
                self.assertEqual(
                    feedback["permitted_dependency_paths"], ["current_beliefs[0]"]
                )

    def test_exact_compaction_scope_keeps_indexed_compaction_removal(self) -> None:
        initial = {
            "open_questions": [
                "Margin bridge?",
                "Churn drivers?",
                "Unit economics?",
                "Capital cycle?",
            ],
            "next_information_needs": ["Resolve churn drivers from the latest batch."],
            "decision": "continue",
        }
        corrected = {
            "open_questions": ["Margin bridge?", "Churn drivers?", "Unit economics?"],
            "next_information_needs": ["Resolve churn drivers from the latest batch."],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([initial, corrected])
        events = []
        caller.on_progress = events.append

        def parse(value):
            if len(value["open_questions"]) > 3:
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="research_state_item_over_limit",
                            message=(
                                "combined ResearchState array count exceeds the "
                                'effective limit; minimum_removed_items=1 '
                                'must_reduce_any_of_paths=["open_questions"]'
                            ),
                            paths=("open_questions",),
                            repair_context={
                                "minimum_removed_items": 1,
                                "must_reduce_any_of_paths": ["open_questions"],
                                "required_compaction_remove_paths": [
                                    "open_questions[3]"
                                ],
                            },
                        )
                    ]
                )
            return value

        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={}, parser=parse,
            allow_outcomes=False, enforce_scoped_correction=True,
            exact_compaction_scope=True, stable_correction_prefix=True,
        )
        self.assertEqual(value, corrected)
        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(events, [])
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligations"][0]["minimum_removed_items"], 1)
        self.assertEqual(
            feedback["obligations"][0]["required_compaction_remove_paths"],
            ["open_questions[3]"],
        )

    def test_exact_compaction_scope_projects_removal_discarding_beside_drift(self) -> None:
        initial = {
            "open_questions": [
                "Margin bridge?",
                "Churn drivers?",
                "Unit economics?",
                "Capital cycle?",
            ],
            "next_information_needs": ["Resolve churn drivers from the latest batch."],
            "decision": "continue",
        }
        drifted = {
            "open_questions": ["Margin bridge?", "Churn drivers?", "Unit economics?"],
            "next_information_needs": ["Different rewritten need."],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([initial, drifted])

        def parse(value):
            if len(value["open_questions"]) > 3:
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="research_state_item_over_limit",
                            message="combined array count exceeds the effective limit",
                            paths=("open_questions",),
                            repair_context={
                                "minimum_removed_items": 1,
                                "must_reduce_any_of_paths": ["open_questions"],
                                "required_compaction_remove_paths": [
                                    "open_questions[3]"
                                ],
                            },
                        )
                    ]
                )
            return value

        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={},
            parser=parse, allow_outcomes=False,
            enforce_scoped_correction=True, exact_compaction_scope=True,
            stable_correction_prefix=True,
        )
        self.assertEqual(value["open_questions"], drifted["open_questions"])
        self.assertEqual(
            value["next_information_needs"], initial["next_information_needs"]
        )
        self.assertEqual(usage.llm_calls, 2)

    def test_lenient_projection_extends_only_through_structured_revalidation(self) -> None:
        invalid = {"fix": 0, "hidden": 0, "keep": "original"}
        drifted = {"fix": 1, "hidden": 1, "keep": "unrelated drift"}
        caller = ScriptedRoleCaller([invalid, drifted])

        def parse(value):
            issues = []
            if value["fix"] == 0:
                issues.append(ValidationIssue(
                    code="invalid_value", message="fix is invalid",
                    paths=("fix",),
                ))
            elif value["hidden"] == 0:
                issues.append(ValidationIssue(
                    code="invalid_value", message="hidden is invalid",
                    paths=("hidden",),
                ))
            if issues:
                raise StructuredValidationError(issues)
            return value

        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={},
            parser=parse, allow_outcomes=False,
            enforce_scoped_correction=True, exact_compaction_scope=True,
            stable_correction_prefix=True,
        )
        self.assertEqual(value, {"fix": 1, "hidden": 1, "keep": "original"})
        self.assertEqual(usage.llm_calls, 2)

    def test_lenient_projection_fails_closed_on_prose_only_revalidation(self) -> None:
        invalid = {"fix": 0, "keep": "original"}
        drifted = {"fix": 1, "keep": "unrelated drift"}
        caller = ScriptedRoleCaller([invalid, drifted])

        def parse(value):
            if value["fix"] == 0:
                raise StructuredValidationError([ValidationIssue(
                    code="invalid_value", message="fix is invalid",
                    paths=("fix",),
                )])
            if value["keep"] == "original":
                raise ValidationError("prose-only semantic rejection grants no scope")
            return value

        with self.assertRaises(CandidateExecutionRejected):
            evolution_runtime_module._complete_parsed_role(
                caller, stage="research_controller_reflect",
                system_prompt="Return the fixed contract.", payload={},
                parser=parse, allow_outcomes=False,
                enforce_scoped_correction=True, exact_compaction_scope=True,
                stable_correction_prefix=True,
            )

    def test_lenient_projection_fails_closed_on_list_membership_drift(self) -> None:
        invalid = {"fix": 0, "keep": ["original"]}
        drifted = {"fix": 1, "keep": ["drift", "extra"]}
        caller = ScriptedRoleCaller([invalid, drifted])

        def parse(value):
            if value["fix"] == 0:
                raise StructuredValidationError([ValidationIssue(
                    code="invalid_value", message="fix is invalid",
                    paths=("fix",),
                )])
            if value["keep"] == ["original"]:
                raise ValidationError("prose-only semantic rejection grants no scope")
            return value

        with self.assertRaises(CandidateExecutionRejected):
            evolution_runtime_module._complete_parsed_role(
                caller, stage="research_controller_reflect",
                system_prompt="Return the fixed contract.", payload={},
                parser=parse, allow_outcomes=False,
                enforce_scoped_correction=True, exact_compaction_scope=True,
                stable_correction_prefix=True,
            )

    def test_lenient_projection_fails_closed_on_same_length_list_drift(self) -> None:
        invalid = {"fix": 0, "keep": ["original"]}
        drifted = {"fix": 1, "keep": ["rewritten"]}
        caller = ScriptedRoleCaller([invalid, drifted])

        def parse(value):
            if value["fix"] == 0:
                raise StructuredValidationError([ValidationIssue(
                    code="invalid_value", message="fix is invalid",
                    paths=("fix",),
                )])
            if value["keep"] == ["original"]:
                raise ValidationError("prose-only semantic rejection grants no scope")
            return value

        with self.assertRaises(CandidateExecutionRejected):
            evolution_runtime_module._complete_parsed_role(
                caller, stage="research_controller_reflect",
                system_prompt="Return the fixed contract.", payload={},
                parser=parse, allow_outcomes=False,
                enforce_scoped_correction=True, exact_compaction_scope=True,
                stable_correction_prefix=True,
            )

    def test_leaf_correction_cannot_rewrite_members_or_change_membership(self) -> None:
        invalid = {
            "rows": [
                {"fix": 0, "keep": "original"},
                {"fix": 2, "keep": "protected"},
            ]
        }
        rejected_corrections = (
            (
                "pure removal",
                {"rows": [{"fix": 2, "keep": "protected"}]},
            ),
            (
                "replacement and addition",
                {
                    "rows": [
                        {"fix": 1, "keep": "drift"},
                        {"fix": 2, "keep": "protected"},
                        {"fix": 3, "keep": "extra"},
                    ],
                },
            ),
            (
                "insertion",
                {
                    "rows": [
                        {"fix": 1, "keep": "drift"},
                        {"fix": 3, "keep": "extra"},
                        {"fix": 2, "keep": "protected"},
                    ],
                },
            ),
        )

        def parse(value):
            # The parser rejects only the diagnosed invalid leaf; every
            # corrected object below is otherwise valid, so rejection or
            # drift-discard can come only from the scoped-correction guard.
            if any(row["fix"] == 0 for row in value["rows"]):
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="invalid_value",
                            message="rows[0].fix is invalid",
                            paths=("rows[0].fix",),
                            allowed_repairs=("replace",),
                        )
                    ]
                )
            return value

        for label, corrected in rejected_corrections:
            with self.subTest(membership_change=label):
                caller = ScriptedRoleCaller([invalid, corrected])
                with self.assertRaises(CandidateExecutionRejected):
                    evolution_runtime_module._complete_parsed_role(
                        caller,
                        stage="research_controller_reflect",
                        system_prompt="Return the fixed contract.",
                        payload={},
                        parser=parse,
                        allow_outcomes=False,
                        enforce_scoped_correction=True,
                        exact_compaction_scope=True,
                        stable_correction_prefix=True,
                    )
                self.assertEqual(len(caller.calls), 2)
                feedback = caller.calls[1]["payload"]["validation_feedback"]
                self.assertEqual(
                    feedback["required_change_paths"], ["rows[0].fix"]
                )
                self.assertEqual(
                    feedback["obligations"][0]["allowed_repairs"], ["replace"]
                )
                self.assertNotIn(
                    "authorized_member_removals", feedback["obligations"][0]
                )

        with self.subTest(membership_change="same-length sibling mutation"):
            drifted = {
                "rows": [
                    {"fix": 1, "keep": "drift"},
                    {"fix": 2, "keep": "protected"},
                ]
            }
            caller = ScriptedRoleCaller([invalid, drifted])
            value, usage = evolution_runtime_module._complete_parsed_role(
                caller,
                stage="research_controller_reflect",
                system_prompt="Return the fixed contract.",
                payload={},
                parser=parse,
                allow_outcomes=False,
                enforce_scoped_correction=True,
                exact_compaction_scope=True,
                stable_correction_prefix=True,
            )
            self.assertEqual(
                value,
                {
                    "rows": [
                        {"fix": 1, "keep": "original"},
                        {"fix": 2, "keep": "protected"},
                    ]
                },
            )
            self.assertEqual(usage.llm_calls, 2)

    def test_member_removal_requires_explicit_validator_authorization(self) -> None:
        invalid = {
            "rows": [
                {"fix": 0, "keep": "original"},
                {"fix": 2, "keep": "protected"},
            ]
        }
        corrected = {"rows": [{"fix": 2, "keep": "protected"}]}

        def whole_member_parse(value):
            if value["rows"][0]["fix"] == 0:
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="invalid_value",
                            message="rows[0] is invalid",
                            paths=("rows[0]",),
                            allowed_repairs=("replace", "remove"),
                        )
                    ]
                )
            return value

        caller = ScriptedRoleCaller([invalid, corrected])
        value, usage = evolution_runtime_module._complete_parsed_role(
            caller,
            stage="research_controller_reflect",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=whole_member_parse,
            allow_outcomes=False,
            enforce_scoped_correction=True,
            stable_correction_prefix=True,
        )
        self.assertEqual(value, corrected)
        self.assertEqual(usage.llm_calls, 2)

        def member_removal_metadata_parse(value):
            if any(row["fix"] == 0 for row in value["rows"]):
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="invalid_value",
                            message="rows[0].fix is invalid",
                            paths=("rows[0].fix",),
                            allowed_repairs=("replace", "remove"),
                            repair_context={
                                "authorized_member_removals": ["rows[0]"]
                            },
                        )
                    ]
                )
            return value

        caller = ScriptedRoleCaller([invalid, corrected])
        value, usage = evolution_runtime_module._complete_parsed_role(
            caller,
            stage="research_controller_reflect",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=member_removal_metadata_parse,
            allow_outcomes=False,
            enforce_scoped_correction=True,
            stable_correction_prefix=True,
        )
        self.assertEqual(value, corrected)
        self.assertEqual(usage.llm_calls, 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["obligations"][0]["authorized_member_removals"], ["rows[0]"]
        )

    def test_authorized_leaf_list_replacement_survives_neighbor_removal(self) -> None:
        invalid = {
            "rows": [
                {"fix": 1, "tags": ["stale"], "keep": "original"},
                {"fix": 2, "obsolete": True},
            ]
        }
        corrected = {
            "rows": [
                {"fix": 1, "tags": ["fresh"], "keep": "original"},
            ]
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        def parse(value):
            issues = []
            rows = value["rows"]
            if rows[0]["tags"] == ["stale"]:
                issues.append(
                    ValidationIssue(
                        code="invalid_value",
                        message="rows[0].tags is invalid",
                        paths=("rows[0].tags",),
                        allowed_repairs=("replace",),
                    )
                )
            issues.extend(
                ValidationIssue(
                    code="invalid_value",
                    message=f"rows[{index}] is obsolete",
                    paths=(f"rows[{index}]",),
                    allowed_repairs=("replace", "remove"),
                )
                for index, row in enumerate(rows)
                if row.get("obsolete")
            )
            if issues:
                raise StructuredValidationError(issues)
            return value

        value, usage = evolution_runtime_module._complete_parsed_role(
            caller,
            stage="research_controller_reflect",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=parse,
            allow_outcomes=False,
            enforce_scoped_correction=True,
            stable_correction_prefix=True,
        )
        self.assertEqual(
            value,
            {"rows": [{"fix": 1, "tags": ["fresh"], "keep": "original"}]},
        )
        self.assertEqual(usage.llm_calls, 2)

    def test_compaction_revalidation_extension_applies_exact_removal_scope(self) -> None:
        invalid = {"fix": 0, "rows": ["original", "second"]}
        corrected = {"fix": 1, "rows": ["drift"]}
        caller = ScriptedRoleCaller([invalid, corrected])

        def parse(value):
            if value["fix"] == 0:
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="invalid_value",
                            message="fix is invalid",
                            paths=("fix",),
                        )
                    ]
                )
            if len(value["rows"]) > 1:
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="research_state_item_over_limit",
                            message=(
                                "combined ResearchState array count exceeds the "
                                "effective limit; minimum_removed_items=1 "
                                'must_reduce_any_of_paths=["rows"]'
                            ),
                            paths=("rows",),
                            repair_context={
                                "minimum_removed_items": 1,
                                "must_reduce_any_of_paths": ["rows"],
                                "required_compaction_remove_paths": ["rows[1]"],
                            },
                        )
                    ]
                )
            if value["rows"] != ["original"]:
                raise ValidationError(
                    "compaction must remove rows[1] while preserving rows[0]"
                )
            return value

        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={}, parser=parse,
            allow_outcomes=False, enforce_scoped_correction=True,
            exact_compaction_scope=True, stable_correction_prefix=True,
        )
        self.assertEqual(value, {"fix": 1, "rows": ["original"]})
        self.assertEqual(usage.llm_calls, 2)

    def test_validator_add_repair_authorizes_only_bounded_append(self) -> None:
        invalid = {
            "supporting_evidence": [
                {
                    "claim": "Revenue was $42 million.",
                    "exact_text": "Revenue was $4 million.",
                }
            ]
        }
        bounded_append = {
            "supporting_evidence": [
                invalid["supporting_evidence"][0],
                {
                    "claim": "Revenue was $42 million.",
                    "exact_text": "Growth reached $42 million.",
                },
            ]
        }
        unbounded_append = {
            "supporting_evidence": [
                invalid["supporting_evidence"][0],
                {
                    "claim": "Revenue was $42 million.",
                    "exact_text": "Growth reached $42 million.",
                },
                {
                    "claim": "Revenue was $42 million.",
                    "exact_text": "Scale reached $42 million.",
                },
            ]
        }

        def parse(value):
            refs = value["supporting_evidence"]
            supported = {
                ref["claim"] for ref in refs if "42" in ref["exact_text"]
            }
            if any(
                "42" in ref["claim"] and ref["claim"] not in supported
                for ref in refs
            ):
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="claim_quantity_not_supported",
                            message="claim cites an unsupported quantity",
                            paths=("supporting_evidence[0].claim",),
                            allowed_repairs=("replace", "remove", "add"),
                            repair_context={
                                "missing_quantity_literals": ["42"],
                                "same_claim_evidence_paths": [
                                    "supporting_evidence[0].claim"
                                ],
                            },
                        )
                    ]
                )
            return value

        caller = ScriptedRoleCaller([invalid, bounded_append])
        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={}, parser=parse,
            allow_outcomes=False, enforce_scoped_correction=True,
            exact_compaction_scope=True, stable_correction_prefix=True,
        )
        self.assertEqual(value, bounded_append)
        self.assertEqual(usage.llm_calls, 2)

        caller = ScriptedRoleCaller([invalid, unbounded_append])
        with self.assertRaises(CandidateExecutionRejected):
            evolution_runtime_module._complete_parsed_role(
                caller, stage="research_controller_reflect",
                system_prompt="Return the fixed contract.", payload={},
                parser=parse, allow_outcomes=False,
                enforce_scoped_correction=True, exact_compaction_scope=True,
                stable_correction_prefix=True,
            )

    def test_v119_duplicate_need_transition_accepts_targeted_occurrence(self) -> None:
        from types import SimpleNamespace

        from stock_opportunity_agent.research.evolution_research_validation import (
            _targeted_answer_need_transition_errors,
        )

        residual = (
            "Property openings, licensing decisions, and regulatory milestones "
            "disclosed by 2025-07-31 that could materially change Wynn's "
            "earnings trajectory."
        )
        catalyst = (
            "What scheduled catalysts, property openings, licensing decisions, "
            "refinancing events, or regulatory milestones were disclosed by "
            "2025-07-31 that could materially change Wynn's earnings trajectory "
            "within the six-month horizon?"
        )
        prior = SimpleNamespace(next_information_needs=[
            "Latest quarterly figures?", "Forward guidance?", catalyst, catalyst,
            "10-Q debt contingencies?", "Analyst revisions?",
        ])
        returned = SimpleNamespace(next_information_needs=[
            "Latest quarterly figures?", "Forward guidance?", residual, catalyst,
            "10-Q debt contingencies?", "Analyst revisions?",
        ])
        selection = SimpleNamespace(
            reason_code="answer_need",
            signal_ref="financing_listing_action:v2",
            target_need_indices=[2],
            answer_scope="partial",
            residual_need=residual,
        )
        errors = _targeted_answer_need_transition_errors(
            prior,
            returned,
            (selection,),
            {"financing_listing_action:v2"},
            {"financing_listing_action:v2"},
            need_dispositions=({"need_index": 2, "answer_scope": "partial",
                "residual_need": residual, "evidence_refs": [{"signal_ref": "financing_listing_action:v2",
                "evidence_group": "supporting", "evidence_index": 0}]},),
            evaluation_context={"prediction_time": "2025-07-31T00:00:00+00:00"},
        )
        # The targeted occurrence at prior index 2 became the exact residual
        # while the untargeted duplicate at prior index 3 is preserved
        # byte-for-byte: this raw V119 transition is correct, not invalid.
        self.assertEqual(errors, [])

    def test_need_transition_feedback_targets_returned_path_not_prior_index(self) -> None:
        from types import SimpleNamespace

        from stock_opportunity_agent.research.evolution_research_validation import (
            _need_transition_validation_issue,
            _targeted_answer_need_transition_errors,
        )

        residual = (
            "Property openings and regulatory milestones disclosed by "
            "2025-07-31 that could materially change Wynn's earnings "
            "trajectory."
        )
        catalyst = (
            "What scheduled catalysts, property openings, licensing "
            "decisions, refinancing events, or regulatory milestones were "
            "disclosed by 2025-07-31 that could materially change Wynn's "
            "earnings trajectory within the six-month horizon?"
        )
        prior = SimpleNamespace(next_information_needs=[
            "Latest quarterly figures?", catalyst, "Forward guidance?",
        ])
        returned = SimpleNamespace(next_information_needs=[
            "Latest quarterly figures?", "Forward guidance?", catalyst,
        ])
        selection = SimpleNamespace(
            reason_code="answer_need",
            signal_ref="financing_listing_action:v2",
            target_need_indices=[1],
            answer_scope="partial",
            residual_need=residual,
        )
        errors = _targeted_answer_need_transition_errors(
            prior,
            returned,
            (selection,),
            {"financing_listing_action:v2"},
            {"financing_listing_action:v2"},
            need_dispositions=({"need_index": 1, "answer_scope": "partial",
                "residual_need": residual, "evidence_refs": [{"signal_ref": "financing_listing_action:v2",
                "evidence_group": "supporting", "evidence_index": 0}]},),
            evaluation_context={"prediction_time": "2025-07-31T00:00:00+00:00"},
        )
        self.assertEqual(len(errors), 1)
        error = errors[0]
        self.assertEqual(error["returned_path"], "next_information_needs[2]")
        self.assertEqual(error["prior_state_path"], "next_information_needs[1]")
        self.assertNotIn("path", error)
        issue = _need_transition_validation_issue(error, returned)
        self.assertEqual(issue.paths, ("next_information_needs[2]",))
        self.assertIn("'returned_path': 'next_information_needs[2]'", issue.message)
        self.assertNotIn("'path':", issue.message)
        self.assertTrue(issue.repair_context["write_scope_complete"])
        self.assertEqual(
            issue.repair_context["returned_path"], "next_information_needs[2]"
        )

    def test_need_transition_multiplicity_preserves_occurrence_counts(self) -> None:
        from types import SimpleNamespace

        from stock_opportunity_agent.research.evolution_research_validation import (
            _targeted_answer_need_transition_errors,
        )

        context = {"prediction_time": "2025-07-31T00:00:00+00:00"}

        def transition(prior_needs, returned_needs, selection, actual=()):
            return _targeted_answer_need_transition_errors(
                SimpleNamespace(next_information_needs=prior_needs),
                SimpleNamespace(next_information_needs=returned_needs),
                (selection,),
                {"financing_listing_action:v2"},
                {"financing_listing_action:v2"},
                need_dispositions=actual,
                evaluation_context=context,
            )

        adopted = SimpleNamespace(
            reason_code="answer_need",
            signal_ref="financing_listing_action:v2",
            target_need_indices=[9],
            answer_scope="full",
            residual_need="",
        )
        # One returned occurrence cannot satisfy two preserved duplicates.
        errors = transition(["Catalyst?", "Catalyst?"], ["Catalyst?"], adopted)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["required_action"], "restore_exactly")

        targeted_full = SimpleNamespace(
            reason_code="answer_need",
            signal_ref="financing_listing_action:v2",
            target_need_indices=[1],
            answer_scope="full",
            residual_need="",
        )
        actual_full = ({"need_index": 1, "answer_scope": "full", "residual_need": None,
            "evidence_refs": [{"signal_ref": "financing_listing_action:v2",
                "evidence_group": "supporting", "evidence_index": 0}]},)
        # A retained untargeted duplicate is not the target: removing only
        # the targeted occurrence is accepted.
        self.assertEqual(
            transition(["Catalyst?", "Catalyst?"], ["Catalyst?"], targeted_full, actual_full),
            [],
        )
        # But retaining both occurrences leaves surplus targeted content.
        errors = transition(["Catalyst?", "Catalyst?"], ["Catalyst?", "Catalyst?"], targeted_full, actual_full)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["required_action"], "remove_exact_target")
        self.assertEqual(errors[0]["returned_path"], "next_information_needs[1]")

        first = SimpleNamespace(
            reason_code="answer_need",
            signal_ref="financing_listing_action:v2",
            target_need_indices=[0],
            answer_scope="partial",
            residual_need="First residual by 2025-07-31.",
        )
        prior = ["First need?", "Keep.", "Second need?", "Keep too."]
        actual_partial = ({"need_index": 0, "answer_scope": "partial",
            "residual_need": "First residual by 2025-07-31.", "evidence_refs": [
                {"signal_ref": "financing_listing_action:v2", "evidence_group": "supporting", "evidence_index": 0}]},)
        self.assertEqual(
            transition(
                prior,
                ["First residual by 2025-07-31.", "Keep.",
                 "Second need?", "Keep too."],
                first,
                actual_partial,
            ),
            [],
        )
        errors = transition(prior, prior, first, actual_partial)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["prior_state_path"], "next_information_needs[0]")
        # Multiple targeted residuals each carry their own obligation.
        shared = SimpleNamespace(
            reason_code="answer_need",
            signal_ref="financing_listing_action:v2",
            target_need_indices=[0, 2],
            answer_scope="partial",
            residual_need="Shared residual by 2025-07-31.",
        )
        actual_shared = tuple({"need_index": index, "answer_scope": "partial",
            "residual_need": "Shared residual by 2025-07-31.", "evidence_refs": [
                {"signal_ref": "financing_listing_action:v2", "evidence_group": "supporting", "evidence_index": 0}]}
            for index in (0, 2))
        errors = transition(prior, prior, shared, actual_shared)
        self.assertEqual(len(errors), 2)
        self.assertTrue(
            all(
                error["required_action"] == "replace_with_exact_residual"
                for error in errors
            )
        )

    def test_authorized_returned_need_repair_projects_with_unrelated_preserved(self) -> None:
        needs = [
            "Latest quarterly figures?", "Forward guidance?", residual := (
                "Property openings and regulatory milestones by 2025-07-31."
            ), "Catalyst duplicate need.", "10-Q debt contingencies?",
            "Analyst revisions?",
        ]
        removal = evolution_runtime_module._project_scoped_correction(
            {
                "next_information_needs": list(needs),
                "hypotheses": ["Hypothesis."],
                "decision": "continue",
            },
            {
                "next_information_needs": [
                    needs[0], needs[1], residual, needs[4], needs[5],
                ],
                "hypotheses": ["Hypothesis."],
                "decision": "continue",
            },
            ["next_information_needs[3]"],
            # A whole-member path alone authorizes replacement, not deletion:
            # the need-transition validator's removal allowance must be
            # stated explicitly for a direct projection call.
            member_removal_allowances={"next_information_needs": {3}},
        )
        self.assertEqual(
            removal[0]["next_information_needs"],
            [needs[0], needs[1], residual, needs[4], needs[5]],
        )
        self.assertEqual(removal[0]["hypotheses"], ["Hypothesis."])
        self.assertEqual(removal[0]["decision"], "continue")
        replacement = evolution_runtime_module._project_scoped_correction(
            {
                "next_information_needs": list(needs),
                "hypotheses": ["Hypothesis."],
                "decision": "continue",
            },
            {
                "next_information_needs": [
                    needs[0], needs[1], residual, residual, needs[4], needs[5],
                ],
                "hypotheses": ["Hypothesis."],
                "decision": "continue",
            },
            ["next_information_needs[3]"],
        )
        self.assertEqual(
            replacement[0]["next_information_needs"],
            [needs[0], needs[1], residual, residual, needs[4], needs[5]],
        )
        self.assertEqual(replacement[0]["hypotheses"], ["Hypothesis."])

    def test_content_anchored_reconciliation_restores_unmentioned_beliefs(self) -> None:
        beliefs = [f"Belief {index}." for index in range(8)]
        corrected = [beliefs[0], beliefs[1], beliefs[3], beliefs[7], beliefs[6]]
        projected = evolution_runtime_module._project_scoped_correction(
            {"current_beliefs": list(beliefs), "decision": "continue"},
            {"current_beliefs": list(corrected), "decision": "continue"},
            ["current_beliefs[2]", "current_beliefs[4]"],
            member_removal_allowances={"current_beliefs": {2, 4}},
        )
        self.assertEqual(
            projected[0]["current_beliefs"],
            [beliefs[0], beliefs[1], beliefs[3], beliefs[5], beliefs[6], beliefs[7]],
        )
        self.assertEqual(projected[0]["decision"], "continue")

        replaced = evolution_runtime_module._project_scoped_correction(
            {"current_beliefs": list(beliefs), "decision": "continue"},
            {
                "current_beliefs": [
                    beliefs[0], beliefs[1], "Replacement belief.",
                    beliefs[3], beliefs[7], beliefs[6],
                ],
                "decision": "continue",
            },
            ["current_beliefs[2]", "current_beliefs[4]"],
            member_removal_allowances={"current_beliefs": {2, 4}},
        )
        self.assertEqual(
            replaced[0]["current_beliefs"],
            [
                beliefs[0], beliefs[1], "Replacement belief.", beliefs[3],
                beliefs[5], beliefs[6], beliefs[7],
            ],
        )

    def test_content_anchored_reconciliation_fails_closed(self) -> None:
        # Duplicate content cannot anchor a unique mapping once the ordered
        # membership check has already rejected the edit.
        self.assertIsNone(evolution_runtime_module._project_scoped_correction(
            {"current_beliefs": ["Dup.", "Invalid 42.", "Dup.", "Tail."]},
            {"current_beliefs": ["Tail.", "Dup.", "Dup."]},
            ["current_beliefs[1]"],
        ))
        # An insertion beyond the add budget has no authorized slot.
        self.assertIsNone(evolution_runtime_module._project_scoped_correction(
            {"current_beliefs": ["Keep.", "Invalid 42.", "Sibling."]},
            {
                "current_beliefs": [
                    "Sibling.", "Keep.", "Replacement.", "Extra.",
                ],
            },
            ["current_beliefs[1]"],
        ))
        # A vanished authorized member without removal authority is rejected.
        self.assertIsNone(evolution_runtime_module._project_scoped_correction(
            {"current_beliefs": ["Keep.", "Invalid 42.", "Sibling."]},
            {"current_beliefs": ["Sibling.", "Keep."]},
            ["current_beliefs[1]"],
            member_removal_allowances={"current_beliefs": set()},
        ))
        # An unauthorized deletion is undone, never accepted: the missing
        # sibling returns byte-for-byte while the authorized slot may carry
        # the model's replacement.
        projected = evolution_runtime_module._project_scoped_correction(
            {"current_beliefs": ["Keep.", "Invalid 42.", "Sibling."]},
            {"current_beliefs": ["Keep.", "Rewritten."]},
            ["current_beliefs[1]"],
        )
        self.assertEqual(
            projected[0]["current_beliefs"], ["Keep.", "Rewritten.", "Sibling."]
        )

    def test_drifted_whole_member_correction_reconciles_to_authorized_slots(self) -> None:
        invalid = {
            "current_beliefs": [
                "Belief zero.", "Belief one.",
                "Unsupported numeric belief 5.9 ounces.", "Belief three.",
                "Unsupported belief 500 meters.", "Belief five.",
                "Belief six.", "Belief seven.",
            ],
            "decision": "continue",
        }
        corrected = {
            "current_beliefs": [
                "Belief zero.", "Belief one.", "Belief three.",
                "Belief seven.", "Belief six.",
            ],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        def parse(value):
            if any(
                "Unsupported" in belief for belief in value["current_beliefs"]
            ):
                raise StructuredValidationError([ValidationIssue(
                    code="assertion_without_support",
                    message="quantitative beliefs must copy evidence claims",
                    paths=("current_beliefs[2]", "current_beliefs[4]"),
                    allowed_repairs=("replace", "remove"),
                )])
            return value

        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={},
            parser=parse, allow_outcomes=False, enforce_scoped_correction=True,
            exact_compaction_scope=True, stable_correction_prefix=True,
        )
        self.assertEqual(value["current_beliefs"], [
            "Belief zero.", "Belief one.", "Belief three.", "Belief five.",
            "Belief six.", "Belief seven.",
        ])
        self.assertEqual(value["decision"], "continue")
        self.assertEqual(usage.llm_calls, 2)

    def test_need_fallback_transitions_exactly_one_duplicate_occurrence(self) -> None:
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_need_transition_fallback,
        )

        original = {"next_information_needs": ["Catalyst?", "Catalyst?", "Sibling?"]}
        remove = StructuredValidationError([ValidationIssue(
            code="research_need_transition_invalid", message="target retained",
            paths=("next_information_needs[1]",),
            repair_context={"prior_need": "Catalyst?",
                            "required_action": "remove_exact_target"},
        )])
        value, _ = _research_need_transition_fallback(original, remove)
        self.assertEqual(value["next_information_needs"], ["Catalyst?", "Sibling?"])
        replace = StructuredValidationError([ValidationIssue(
            code="research_need_transition_invalid", message="target retained",
            paths=("next_information_needs[0]",),
            repair_context={"prior_need": "Catalyst?",
                            "returned_path": "next_information_needs[0]",
                            "returned_need": "Catalyst?",
                            "required_action": "replace_with_exact_residual",
                            "required_need": "Residual by 2025-07-31."},
        )])
        value, _ = _research_need_transition_fallback(
            {"next_information_needs": ["Catalyst?", "Catalyst?"]}, replace
        )
        self.assertEqual(
            value["next_information_needs"],
            ["Residual by 2025-07-31.", "Catalyst?"],
        )

    def test_scoped_correction_guard_blocks_unauthorized_member_deletion(self) -> None:
        # A provided-but-empty allowance mapping authorizes no whole-member
        # removal at all, so the demonstrated unsafe projection is gone.
        self.assertIsNone(evolution_runtime_module._project_scoped_correction(
            {"rows": ["invalid", "keep1", "keep2"]},
            {"rows": ["keep2"]},
            ["rows[0]"],
            member_removal_allowances={},
        ))
        # Two authorized slots between anchors plus one novel replacement is
        # ambiguous: the first-slot guess must be rejected.
        self.assertIsNone(evolution_runtime_module._project_scoped_correction(
            {"rows": ["anchor a.", "invalid one.", "invalid two.", "anchor d."]},
            {"rows": ["anchor a.", "Replacement."]},
            ["rows[1]", "rows[2]"],
            member_removal_allowances={"rows": {1, 2}},
        ))

        invalid = {"rows": ["invalid", "keep1", "keep2"], "decision": "continue"}
        dropped = {"rows": ["keep2"], "decision": "continue"}
        caller = ScriptedRoleCaller([invalid, dropped])

        def parse(value):
            if "invalid" in value["rows"]:
                raise StructuredValidationError([ValidationIssue(
                    code="row_invalid", message="rows[0] is invalid",
                    paths=("rows[0]",), allowed_repairs=("replace",),
                )])
            return value

        # replace-only authority: dropping rows[0] entirely must be blocked
        # by the scope guard, not silently accepted as a list rewrite.
        with self.assertRaises(CandidateExecutionRejected):
            evolution_runtime_module._complete_parsed_role(
                caller, stage="research_controller_reflect",
                system_prompt="Return the fixed contract.", payload={},
                parser=parse, allow_outcomes=False,
                enforce_scoped_correction=True, exact_compaction_scope=True,
                stable_correction_prefix=True,
            )
        replaced = {"rows": ["replaced", "keep1", "keep2"], "decision": "continue"}
        caller = ScriptedRoleCaller([invalid, replaced])
        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={},
            parser=parse, allow_outcomes=False,
            enforce_scoped_correction=True, exact_compaction_scope=True,
            stable_correction_prefix=True,
        )
        self.assertEqual(value, replaced)
        self.assertEqual(usage.llm_calls, 2)

    def test_replace_only_member_path_never_deletes_or_splits(self) -> None:
        # The independent counterexample: original-order pure deletion kept
        # every sibling in place, so only the raw drift checker's operation
        # authority can block it. Replace-only authority must also reject
        # splitting one member into several rows and unauthorized additions.
        invalid = {"rows": ["invalid", "keep1", "keep2"], "decision": "continue"}

        def parse(value):
            if "invalid" in value["rows"]:
                raise StructuredValidationError([ValidationIssue(
                    code="row_invalid", message="rows[0] is invalid",
                    paths=("rows[0]",), allowed_repairs=("replace",),
                )])
            return value

        for label, corrected in (
            (
                "pure deletion with all siblings preserved",
                {"rows": ["keep1", "keep2"], "decision": "continue"},
            ),
            (
                "splitting one member into several rows",
                {
                    "rows": ["first half", "second half", "keep1", "keep2"],
                    "decision": "continue",
                },
            ),
            (
                "addition without add authority",
                {
                    "rows": ["replaced", "extra", "keep1", "keep2"],
                    "decision": "continue",
                },
            ),
        ):
            with self.subTest(membership_change=label):
                caller = ScriptedRoleCaller([invalid, corrected])
                with self.assertRaises(CandidateExecutionRejected):
                    evolution_runtime_module._complete_parsed_role(
                        caller, stage="research_controller_reflect",
                        system_prompt="Return the fixed contract.", payload={},
                        parser=parse, allow_outcomes=False,
                        enforce_scoped_correction=True,
                        exact_compaction_scope=True,
                        stable_correction_prefix=True,
                    )
                self.assertEqual(len(caller.calls), 2)
                feedback = caller.calls[1]["payload"]["validation_feedback"]
                self.assertEqual(feedback["required_change_paths"], ["rows[0]"])
                self.assertEqual(
                    feedback["obligations"][0]["allowed_repairs"], ["replace"]
                )

        with self.subTest(membership_change="authorized replacement accepted"):
            replaced = {
                "rows": ["replaced", "keep1", "keep2"],
                "decision": "continue",
            }
            caller = ScriptedRoleCaller([invalid, replaced])
            value, usage = evolution_runtime_module._complete_parsed_role(
                caller, stage="research_controller_reflect",
                system_prompt="Return the fixed contract.", payload={},
                parser=parse, allow_outcomes=False,
                enforce_scoped_correction=True, exact_compaction_scope=True,
                stable_correction_prefix=True,
            )
            self.assertEqual(value, replaced)
            self.assertEqual(usage.llm_calls, 2)

    def test_explicit_member_removal_and_bounded_add_stay_authorized(self) -> None:
        invalid = {"rows": ["invalid", "keep1", "keep2"], "decision": "continue"}

        def removal_parse(value):
            if "invalid" in value["rows"]:
                raise StructuredValidationError([ValidationIssue(
                    code="row_invalid", message="rows[0] is invalid",
                    paths=("rows[0]",), allowed_repairs=("replace", "remove"),
                )])
            return value

        removed = {"rows": ["keep1", "keep2"], "decision": "continue"}
        caller = ScriptedRoleCaller([invalid, removed])
        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={},
            parser=removal_parse, allow_outcomes=False,
            enforce_scoped_correction=True, exact_compaction_scope=True,
            stable_correction_prefix=True,
        )
        self.assertEqual(value, removed)
        self.assertEqual(usage.llm_calls, 2)

        def add_parse(value):
            if "invalid" in value["rows"]:
                raise StructuredValidationError([ValidationIssue(
                    code="row_invalid", message="rows[0] is invalid",
                    paths=("rows[0]",),
                    allowed_repairs=("replace", "remove", "add"),
                    repair_context={
                        "missing_quantity_literals": ["42", "7"],
                        "same_claim_evidence_paths": ["rows[0]"],
                    },
                )])
            return value

        bounded_add = {
            "rows": ["replaced", "extra 42", "extra 7", "keep1", "keep2"],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([invalid, bounded_add])
        value, usage = evolution_runtime_module._complete_parsed_role(
            caller, stage="research_controller_reflect",
            system_prompt="Return the fixed contract.", payload={},
            parser=add_parse, allow_outcomes=False,
            enforce_scoped_correction=True, exact_compaction_scope=True,
            stable_correction_prefix=True,
        )
        self.assertEqual(value, bounded_add)
        self.assertEqual(usage.llm_calls, 2)

        beyond_budget = {
            "rows": [
                "replaced", "extra 42", "extra 7", "one extra too many",
                "keep1", "keep2",
            ],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([invalid, beyond_budget])
        with self.assertRaises(CandidateExecutionRejected):
            evolution_runtime_module._complete_parsed_role(
                caller, stage="research_controller_reflect",
                system_prompt="Return the fixed contract.", payload={},
                parser=add_parse, allow_outcomes=False,
                enforce_scoped_correction=True, exact_compaction_scope=True,
                stable_correction_prefix=True,
            )


class NeedTransitionDuplicateRestorationTests(TestCase):
    """Occurrence-aware restoration of missing duplicate needs (V121 Bumble)."""

    NEED_A = (
        "What guidance did management disclose by 2025-09-30 for the "
        "remainder of 2025?"
    )
    NEED_B = (
        "What operational updates were disclosed by 2025-09-30 after the "
        "restructuring?"
    )
    NEED_C = "What was the substance of the Q2 miss disclosed by 2025-09-30?"
    NEED_D = (
        "Do recent price patterns through 2025-09-29 confirm or contradict "
        "the stabilization narrative?"
    )
    NEED_E = "What insider share sales were disclosed by 2025-09-30?"
    NARROWED = "What prior guidance figures were disclosed before June 25, 2025?"
    SIGNAL_CLAIM = "price_momentum_126d=0.465116"
    EVALUATION_CONTEXT = {
        "prediction_time": "2025-09-30T00:00:00+00:00",
        "horizon": "six_calendar_months",
        "horizon_end": "2026-03-30",
    }

    def _prior_state(self) -> dict:
        return {
            "contradictions": [],
            "current_beliefs": ["The latest close is 6.3 on 2025-09-29."],
            "decision": "continue",
            "hypotheses": ["The share price will not double within six months."],
            "next_information_needs": [
                self.NEED_A,
                self.NEED_A,
                self.NEED_B,
                self.NEED_C,
                self.NEED_D,
                self.NEED_E,
            ],
            "open_questions": [],
            "resolved_questions": ["The market backbone returned daily closes."],
            "supporting_evidence": [
                {
                    "claim": "The latest close is 6.3 on 2025-09-29.",
                    "exact_text": "adjusted close 6.3 on 2025-09-29",
                    "kind": "basic_info",
                    "projection_id": "projection_need_a",
                }
            ],
        }

    def _batch(self) -> Any:
        result = SimpleNamespace(
            ref="price_momentum_126d:v1",
            signal_id="price_momentum_126d",
            version=1,
            value=SignalValue.POSITIVE,
            confidence=1.0,
            coverage=SignalCoverage.SUFFICIENT,
            interpretation=self.SIGNAL_CLAIM,
            supporting_evidence=[
                SimpleNamespace(exact_span="126-day window", timestamp=None)
            ],
            counter_evidence=[],
        )
        return SimpleNamespace(results=[result])

    def _selections(self) -> tuple[SignalSelectionDecision, ...]:
        return (
            SignalSelectionDecision.from_dict(
                {
                    "signal_ref": "price_momentum_126d:v1",
                    "reason_code": "test_contradiction",
                    "selection_reason": (
                        "Test whether recent price patterns contradict the "
                        "narrative."
                    ),
                    "applicability_hypothesis": (
                        "Price patterns test the stabilization narrative."
                    ),
                    "expected_role": "primary",
                    "context_tags": ["general"],
                    "target_need_indices": [4],
                }
            ),
        )

    def _invalid_output(self) -> dict:
        from copy import deepcopy

        value = deepcopy(self._prior_state())
        value["next_information_needs"] = [
            self.NEED_B,
            self.NEED_C,
            self.NEED_D,
            self.NARROWED,
            self.NEED_A,
        ]
        value["current_beliefs"] = [
            "The latest close is 6.3 on 2025-09-29.",
            self.SIGNAL_CLAIM,
        ]
        value["supporting_evidence"] = [
            {
                "claim": "The latest close is 6.3 on 2025-09-29.",
                "exact_text": "adjusted close 6.3 on 2025-09-29",
                "kind": "basic_info",
                "projection_id": "projection_need_a",
            },
            {
                "kind": "signal",
                "claim": self.SIGNAL_CLAIM,
                "signal_ref": "price_momentum_126d:v1",
                "evidence_group": "supporting",
                "evidence_index": 0,
            },
        ]
        return value

    def _make_parser(self, prior: ResearchState) -> Any:
        from stock_opportunity_agent.research.evolution_research_validation import (
            _normalize_research_state_output,
            _validate_research_state_refs,
        )

        batch = self._batch()
        selections = self._selections()

        def parse(value):
            normalized = _normalize_research_state_output(
                dict(value),
                previous_state=prior,
                evaluation_context=self.EVALUATION_CONTEXT,
            )
            return _validate_research_state_refs(
                ResearchState.from_dict(normalized),
                phase="reflect",
                previous_state=prior,
                batch=batch,
                selections=selections,
                evaluation_context=self.EVALUATION_CONTEXT,
            )

        return parse

    def _run_role(self, caller, prior: ResearchState, fallback=True):
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )

        return evolution_runtime_module._complete_parsed_role(
            caller,
            stage="research_controller_reflect",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=self._make_parser(prior),
            allow_outcomes=False,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            stable_correction_prefix=True,
            final_validation_fallback=(
                _research_state_evidence_grounding_fallback if fallback else None
            ),
        )

    def test_feedback_carries_occurrence_counts_and_restores_multiplicity(self) -> None:
        from copy import deepcopy

        invalid = self._invalid_output()
        caller = ScriptedRoleCaller([invalid, deepcopy(invalid)])
        value, _ = self._run_role(caller, ResearchState.from_dict(self._prior_state()))
        # Runtime-issued exact restores now precede the LLM correction.
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(caller.calls[0]["payload"]["validation_feedback"], None)
        needs = [str(need) for need in value.next_information_needs]
        self.assertEqual(needs[:5], [self.NEED_B, self.NEED_C, self.NEED_D, self.NARROWED, self.NEED_A])
        self.assertEqual(needs.count(self.NEED_A), 2)
        self.assertEqual(needs.count(self.NEED_E), 1)
        self.assertEqual(len(needs), 7)

    def test_drifted_partial_correction_recovers_without_row_replacement(self) -> None:
        # The correction restores the omitted need, reorders the list, and
        # still collapses the duplicate: the scoped projection must not write
        # the prior coordinate over a valid returned row, and the final state
        # must hold both duplicate occurrences plus the restored need.
        invalid = self._invalid_output()
        corrected = {
            **invalid,
            "next_information_needs": [
                self.NEED_A,
                self.NEED_B,
                self.NEED_E,
                self.NEED_C,
                self.NEED_D,
                self.NARROWED,
            ],
        }
        caller = ScriptedRoleCaller([invalid, corrected])
        value, _ = self._run_role(caller, ResearchState.from_dict(self._prior_state()))
        needs = [str(need) for need in value.next_information_needs]
        self.assertEqual(needs.count(self.NEED_A), 2)
        self.assertEqual(needs.count(self.NEED_E), 1)
        self.assertEqual(needs.count(self.NEED_B), 1)
        self.assertEqual(needs[:5], [self.NEED_B, self.NEED_C, self.NEED_D, self.NARROWED, self.NEED_A])

    def test_unrelated_correction_drift_never_replaces_semantic_failure(self) -> None:
        invalid = {
            "rows": [
                {"fix": 0, "keep": "original"},
                {"fix": 2, "keep": "protected"},
            ]
        }
        corrected = {"rows": [{"fix": 2, "keep": "protected"}]}

        def parse(value):
            if any(row["fix"] == 0 for row in value["rows"]):
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="invalid_value",
                            message="rows[0].fix is invalid",
                            paths=("rows[0].fix",),
                            allowed_repairs=("replace",),
                        )
                    ]
                )
            return value

        caller = ScriptedRoleCaller([invalid, corrected])
        with self.assertRaises(CandidateExecutionRejected) as raised:
            evolution_runtime_module._complete_parsed_role(
                caller,
                stage="research_controller_reflect",
                system_prompt="Return the fixed contract.",
                payload={},
                parser=parse,
                allow_outcomes=False,
                enforce_scoped_correction=True,
                exact_compaction_scope=True,
                stable_correction_prefix=True,
            )
        message = str(raised.exception)
        self.assertIn("rows[0].fix is invalid", message)
        self.assertIn("unrelated-correction drift rejected", message)
        self.assertIn("correction changed unrelated valid content", message)

    def test_missing_residual_append_never_consumes_preserved_duplicate(self) -> None:
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_need_transition_fallback,
        )

        original = {
            "next_information_needs": [self.NEED_A, self.NEED_B],
            "supporting_evidence": [],
        }
        fallback = _research_need_transition_fallback(
            original,
            StructuredValidationError(
                [
                    ValidationIssue(
                        code="research_need_transition_invalid",
                        message="target omitted its exact residual",
                        paths=("next_information_needs[2]",),
                        repair_context={
                            "prior_need": self.NEED_A,
                            "required_action": "replace_with_exact_residual",
                            "required_need": self.NARROWED,
                        },
                    )
                ]
            ),
        )
        self.assertIsNotNone(fallback)
        self.assertEqual(
            fallback[0]["next_information_needs"],
            [self.NEED_A, self.NEED_B, self.NARROWED],
        )


class TemporalQuantityAggregatedFeedbackTests(TestCase):
    """Temporal plus numeric defects share one initial feedback (V121 Kinross)."""

    EVALUATION_CONTEXT = {
        "prediction_time": "2025-09-30T00:00:00+00:00",
        "horizon": "six_calendar_months",
        "horizon_end": "2026-03-30",
    }
    BASIC_INFO = {
        "requests": [
            {
                "projections": [
                    {
                        "projection_id": "projection_rev",
                        "exact_text": "Prior year: Revenue was $4 million.",
                    }
                ]
            }
        ]
    }

    def _value(self) -> dict:
        return {
            "contradictions": [],
            "current_beliefs": ["Revenue was $42 million."],
            "decision": "continue",
            "hypotheses": ["Margins may improve within the horizon."],
            "next_information_needs": [
                "What results will the company report after September 2025 in its Q3 filing?",
                "What guidance is visible by 2025-09-30?",
            ],
            "open_questions": [],
            "resolved_questions": [],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": "Revenue was $42 million.",
                    "projection_id": "projection_rev",
                    "exact_text": "Revenue was $4 million.",
                }
            ],
        }

    def _compliant(self) -> dict:
        from copy import deepcopy

        value = deepcopy(self._value())
        value["next_information_needs"] = ["What guidance is visible by 2025-09-30?"]
        # The authorized in-scope repair narrows the claim (and its linked
        # assertion, a permitted dependency); the grounded literal is kept.
        value["supporting_evidence"][0]["claim"] = (
            "Revenue grew in the most recent quarter."
        )
        value["current_beliefs"] = ["Revenue grew in the most recent quarter."]
        return value

    def _emptied(self) -> dict:
        from copy import deepcopy

        value = deepcopy(self._value())
        value["next_information_needs"] = ["What guidance is visible by 2025-09-30?"]
        value["supporting_evidence"] = []
        return value

    def _make_parser(self):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _normalize_research_state_output,
            _validate_research_state_refs,
        )

        def parse(value):
            normalized = _normalize_research_state_output(
                dict(value),
                initialize=True,
                basic_info=self.BASIC_INFO,
                evaluation_context=self.EVALUATION_CONTEXT,
            )
            return _validate_research_state_refs(
                ResearchState.from_dict(normalized),
                phase="initialize",
                basic_info=self.BASIC_INFO,
            )

        return parse

    def test_initial_feedback_aggregates_temporal_and_quantity_issues(self) -> None:
        from stock_opportunity_agent.research.evolution_research_validation import (
            _normalize_research_state_output,
        )

        with self.assertRaises(StructuredValidationError) as raised:
            _normalize_research_state_output(
                dict(self._value()),
                initialize=True,
                basic_info=self.BASIC_INFO,
                evaluation_context=self.EVALUATION_CONTEXT,
            )
        codes = [issue.code for issue in raised.exception.issues]
        self.assertEqual(codes[0], "future_information_unavailable")
        self.assertEqual(
            set(codes),
            {"future_information_unavailable", "claim_quantity_not_supported"},
        )

    def test_compliant_correction_fixes_all_issues_within_budget(self) -> None:
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )

        caller = ScriptedRoleCaller([self._value(), self._compliant()])
        value, usage = evolution_runtime_module._complete_parsed_role(
            caller,
            stage="research_controller_initialize",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=self._make_parser(),
            allow_outcomes=False,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            stable_correction_prefix=True,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )
        self.assertEqual(
            [str(need) for need in value.next_information_needs],
            ["What guidance is visible by 2025-09-30?"],
        )
        self.assertEqual(usage.llm_calls, 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            sorted(
                obligation["issue_code"]
                for obligation in feedback["obligations"]
            ),
            ["future_information_unavailable"],
        )
        self.assertEqual(feedback["invalid_output"]["supporting_evidence"], [])
        self.assertEqual(feedback["invalid_output"]["current_beliefs"], [])

    def test_empty_evidence_never_retains_unsupported_belief(self) -> None:
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )

        caller = ScriptedRoleCaller([self._value(), self._emptied()])
        value, _usage = evolution_runtime_module._complete_parsed_role(
                caller,
                stage="research_controller_initialize",
                system_prompt="Return the fixed contract.",
                payload={},
                parser=self._make_parser(),
                allow_outcomes=False,
                enforce_scoped_correction=True,
                exact_compaction_scope=True,
                stable_correction_prefix=True,
                final_validation_fallback=_research_state_evidence_grounding_fallback,
            )
        self.assertEqual(value.supporting_evidence, ())
        self.assertEqual(value.current_beliefs, ())
        self.assertEqual(value.hypotheses, tuple(self._value()["hypotheses"]))

    def _complete_temporal_correction(self, initial: dict, corrected: dict):
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )

        caller = ScriptedRoleCaller([initial, corrected])
        result = evolution_runtime_module._complete_parsed_role(
            caller,
            stage="research_controller_initialize",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=self._make_parser(),
            allow_outcomes=False,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            stable_correction_prefix=True,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )
        return result, caller

    def _temporal_value(self):
        value = self._compliant()
        claim = "Revenue was $4 million."
        value["supporting_evidence"][0]["claim"] = claim
        value["current_beliefs"] = [claim]
        value["next_information_needs"] = self._value()["next_information_needs"]
        return value

    def test_exhausted_temporal_correction_preserves_valid_state_siblings(self):
        initial = self._temporal_value()
        corrected = self._temporal_value()
        corrected["next_information_needs"][0] = (
            "Which results will the company report after September 2025 in its Q3 filing?"
        )
        (state, usage), caller = self._complete_temporal_correction(
            initial, corrected
        )
        expected = dict(corrected)
        expected["next_information_needs"] = corrected["next_information_needs"][1:]
        self.assertEqual(state.to_dict(), self._make_parser()(expected).to_dict())
        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(
            caller.calls[1]["payload"]["validation_feedback"]["obligations"][0][
                "issue_code"
            ],
            "future_information_unavailable",
        )
        self.assertEqual(initial, self._temporal_value())
        self.assertEqual(len(corrected["next_information_needs"]), 2)

    def test_multiple_temporal_members_use_one_snapshot_without_index_shift(self):
        value = self._temporal_value()
        future_need = value["next_information_needs"][0]
        valid_need = value["next_information_needs"][1]
        value["next_information_needs"] = [future_need, valid_need, future_need]
        value["open_questions"] = [
            "Which realized results will be published in December 2025?",
            "The disclosed commercial opportunity is uncertain.",
        ]
        (state, usage), _caller = self._complete_temporal_correction(value, value)
        expected = dict(value)
        expected["next_information_needs"] = [valid_need]
        expected["open_questions"] = [value["open_questions"][1]]
        self.assertEqual(state.to_dict(), self._make_parser()(expected).to_dict())
        self.assertEqual(usage.llm_calls, 2)

    def test_temporal_isolation_cannot_finalize_an_empty_continuing_frontier(self):
        value = self._temporal_value()
        value["next_information_needs"] = value["next_information_needs"][:1]
        with self.assertRaises(ValidationError) as raised:
            self._complete_temporal_correction(value, value)
        self.assertIn("continuing research requires", str(raised.exception))
        self.assertEqual(value["decision"], "continue")

    def test_temporal_isolation_requires_exact_owner_remove_authority(self):
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )
        from stock_opportunity_agent.models import ValidationIssue

        context = {
            "prediction_time": "2025-09-30",
            "future_source_date_refs": ["Q3"],
            "required_temporal_boundary": "available_by_prediction_time",
        }
        variants = [
            {"paths": ("next_information_needs",)},
            {"paths": ("current_beliefs[0]",)},
            {"allowed_repairs": ("replace",)},
            {"dependent_paths": ("decision",)},
            {"path_policy": "any"},
            {"repair_context": {}},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                fields = {
                    "code": "future_information_unavailable",
                    "message": "Remove the invalid question.",
                    "paths": ("next_information_needs[0]",),
                    "allowed_repairs": ("replace", "remove"),
                    "repair_context": context,
                }
                fields.update(variant)
                self.assertIsNone(
                    _research_state_evidence_grounding_fallback(
                        self._compliant(),
                        StructuredValidationError([ValidationIssue(**fields)]),
                    )
                )

    def test_disclosed_future_schedule_stays_in_the_research_frontier(self):
        value = self._compliant()
        value["next_information_needs"][0] = (
            "What production milestones did the company disclose by 2025-09-30 "
            "for the period through 2026-03-30?"
        )
        parsed = self._make_parser()(value)
        self.assertEqual(parsed.to_dict(), value)

    def test_mixed_quote_and_temporal_failure_preserves_independent_valid_need(self):
        value = self._temporal_value()
        value["supporting_evidence"][0]["exact_text"] = "Revenue was $40 million."
        (state, usage), _caller = self._complete_temporal_correction(value, value)
        self.assertEqual(state.supporting_evidence, ())
        self.assertEqual(state.current_beliefs, ())
        self.assertEqual(state.next_information_needs, (value["next_information_needs"][1],))
        self.assertEqual(state.hypotheses, tuple(value["hypotheses"]))
        self.assertEqual(usage.llm_calls, 2)

    def test_reflect_quarantine_keeps_prior_unresolved_need_and_literal(self):
        from stock_opportunity_agent.research.evolution_output_validation import (
            _research_state_evidence_grounding_fallback,
        )
        from stock_opportunity_agent.research.evolution_research_validation import (
            _normalize_research_state_output,
            _validate_research_state_refs,
        )

        prior_value = self._temporal_value()
        prior_value["next_information_needs"] = prior_value["next_information_needs"][1:]
        prior = self._make_parser()(prior_value)
        value = prior.to_dict()
        value["next_information_needs"].append(self._temporal_value()["next_information_needs"][0])

        def parse(output):
            normalized = _normalize_research_state_output(
                output,
                previous_state=prior,
                evaluation_context=self.EVALUATION_CONTEXT,
            )
            return _validate_research_state_refs(
                ResearchState.from_dict(normalized),
                phase="reflect",
                previous_state=prior,
                evaluation_context=self.EVALUATION_CONTEXT,
            )

        state, usage = evolution_runtime_module._complete_parsed_role(
            ScriptedRoleCaller([value, value]),
            stage="research_controller_reflect",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=parse,
            allow_outcomes=False,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )
        self.assertEqual(state, prior)
        self.assertEqual(usage.llm_calls, 2)


class TemporalSchedulePluralVocabularyTests(TestCase):
    """Plural bounded schedule nouns keep the as-of allowance (V122 MP Materials)."""

    def _refs(self, text: str) -> list:
        from datetime import date

        from stock_opportunity_agent.research.evolution_research_validation import (
            _future_source_date_refs,
        )

        return _future_source_date_refs(
            text,
            date(2025, 3, 31),
            field_name="next_information_needs",
        )

    def test_v122_case12_plural_milestones_need_is_not_future_information(self) -> None:
        need = (
            "What specific magnet-production milestones, volumes, or customer "
            "commitments did MP Materials disclose by 2025-03-31 for the "
            "period through 2025-09-30?"
        )
        self.assertEqual(self._refs(need), [])
        self.assertEqual(self._refs(need.replace("milestones", "milestone")), [])

    def test_plural_schedule_vocab_variants_share_the_singular_allowance(self) -> None:
        nouns = (
            "milestone",
            "milestones",
            "timeline",
            "timelines",
            "schedule",
            "schedules",
            "forecast",
            "forecasts",
            "target",
            "targets",
            "goal",
            "goals",
            "date",
            "dates",
        )
        for noun in nouns:
            with self.subTest(noun=noun):
                need = (
                    f"What specific production {noun} did the company disclose "
                    "by 2025-03-31 for the period through 2025-09-30?"
                )
                self.assertEqual(self._refs(need), [])

    def test_realized_results_and_actuals_still_reject_in_plural(self) -> None:
        for noun in ("results", "actuals"):
            with self.subTest(noun=noun):
                need = (
                    f"What {noun} did the company report by 2025-03-31 for the "
                    "period through 2025-09-30?"
                )
                self.assertEqual(self._refs(need), ["2025-09-30"])

    def test_missing_or_late_asof_bound_still_rejects_plural_schedules(self) -> None:
        unbounded = (
            "What specific milestones will the company disclose through "
            "2025-09-30?"
        )
        self.assertEqual(self._refs(unbounded), ["2025-09-30"])
        late_bound = (
            "What specific milestones did the company disclose by 2025-06-30 "
            "for the period through 2025-09-30?"
        )
        self.assertEqual(self._refs(late_bound), ["2025-06-30", "2025-09-30"])

    def test_mixed_past_asof_future_forecast_pairs(self) -> None:
        positive = (
            "Which disclosed capacity targets and delivery schedules had the "
            "company committed to as of 2025-03-31 for the quarters ending "
            "through 2025-09-30?"
        )
        self.assertEqual(self._refs(positive), [])
        negative = (
            "Which realized volumes and actuals had the company achieved as "
            "of 2025-03-31 for the period through 2025-09-30?"
        )
        self.assertEqual(self._refs(negative), ["2025-09-30"])


class PriorBoundAndProjectedExpectationTests(TestCase):
    """Round-24: equivalent bounded forecast language (V124 Kinross)."""

    PREDICTION = date(2025, 9, 30)

    def _refs(self, text: str) -> list:
        from stock_opportunity_agent.research.evolution_research_validation import (
            _future_source_date_refs,
        )

        return _future_source_date_refs(
            text, self.PREDICTION, field_name="next_information_needs"
        )

    def test_v124_raw3_need1_before_prediction_time_guidance_passes(self):
        need = (
            "What forward guidance for full-year 2025 and 2026 production, "
            "cost of sales, and capital expenditures did Kinross provide in "
            "its Q2 2025 earnings call or subsequent filings available "
            "before the prediction time, and did it revise prior guidance?"
        )
        self.assertEqual(self._refs(need), [])
        self.assertEqual(
            self._refs(need.replace("before", "prior to")), []
        )

    def test_symbolic_and_explicit_before_bounds_pass(self):
        symbolic = (
            "What cost and capital expenditure guidance for 2026 had "
            "Kinross disclosed prior to the prediction time?"
        )
        self.assertEqual(self._refs(symbolic), [])
        explicit_prior_to = (
            "What capital expenditure guidance did Kinross provide prior "
            "to September 30, 2025 for its 2026 production plans?"
        )
        self.assertEqual(self._refs(explicit_prior_to), [])
        explicit_before = (
            "Which disclosed production targets and delivery schedules "
            "for 2026 were available before September 30, 2025?"
        )
        self.assertEqual(self._refs(explicit_before), [])

    def test_v124_raw5_need3_projected_reserve_support_passes(self):
        need = (
            "What proven and probable reserve and measured and indicated "
            "resource quantities, by asset, had Kinross disclosed as of "
            "the prediction time to support its projected annual "
            "attributable gold equivalent production of 2.0 million oz "
            "between 2025 and 2027?"
        )
        self.assertEqual(self._refs(need), [])
        self.assertEqual(self._refs(need.replace("projected", "expected")), [])
        self.assertEqual(self._refs(need.replace("projected", "anticipated")), [])
        self.assertEqual(
            self._refs(
                "What proven and probable reserves support the disclosed "
                "projections for 2027 production as of the prediction time?"
            ),
            [],
        )

    def test_before_or_prior_to_cutoff_after_prediction_still_rejects(self):
        late_before = (
            "What forward guidance for 2026 production did Kinross "
            "provide before December 31, 2025?"
        )
        self.assertTrue(self._refs(late_before))
        late_prior_to = (
            "What 2026 production guidance did Kinross provide prior to "
            "March 2026?"
        )
        self.assertTrue(self._refs(late_prior_to))

    def test_open_ended_after_window_still_rejects(self):
        need = "What production updates will Kinross publish after March 2026?"
        self.assertTrue(self._refs(need))

    def test_projected_realized_results_and_unbounded_projections_reject(self):
        realized = (
            "What projected 2027 results had Kinross reported as of the "
            "prediction time?"
        )
        self.assertEqual(self._refs(realized), ["2027"])
        actuals = (
            "What projected actuals for 2026 were available before the "
            "prediction time?"
        )
        self.assertEqual(self._refs(actuals), ["2026"])
        unbounded = (
            "What is management's projection for 2027 attributable "
            "production?"
        )
        self.assertEqual(self._refs(unbounded), ["2027"])

    def test_before_bound_parent_lends_clause_and_guidance_framing(self):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _bounded_residual_need,
        )

        parent = (
            "What forward production and capital expenditure guidance did "
            "Kinross provide before the prediction time for 2026?"
        )
        residual = (
            "Specific disclosed production and capital expenditure figures "
            "for 2026 are not fully covered."
        )
        restored = _bounded_residual_need(residual, parent, self.PREDICTION)
        self.assertIsNotNone(restored)
        self.assertIn("before the prediction time", restored)
        self.assertIn("guidance", restored)
        self.assertEqual(self._refs(restored), [])


class OwnershipScopeLocalNegationTests(TestCase):
    """Round-26: locally negated first-party ownership phrases (V125)."""

    NEGATED_DESCRIPTION = (
        "Collect recent third-party news coverage scoped to the target "
        "company_id on customers, financing, orders, regulation, and product "
        "changes that may shift expectations; treat these source types as "
        "third-party reporting, not as the issuer's own disclosure."
    )

    def _plan(
        self,
        *,
        description="Collect target-company-scoped third-party news.",
        source_types=("company_news",),
        query="",
        h_init=None,
        h_reflect=None,
        h_analyse=None,
    ):
        base = default_information_plan()
        proto = base.basic_info_policy.requests[0]
        request = replace(
            proto,
            description=description,
            source_types=tuple(source_types),
            query=query or None,
        )
        return replace(
            base,
            basic_info_policy=replace(
                base.basic_info_policy, requests=(request,)
            ),
            initial_research_skill=h_init or base.initial_research_skill,
            reflection_skill=h_reflect or base.reflection_skill,
            analysis_prompt=h_analyse or base.analysis_prompt,
        )

    def _validate(self, plan):
        from stock_opportunity_agent.research.evolution_output_validation import (
            _validate_proposed_request_scope,
        )

        return _validate_proposed_request_scope(plan)

    def test_v125_negated_news_descriptions_pass(self):
        cases = (
            ("actual1 wire text", self.NEGATED_DESCRIPTION),
            (
                "raw2 strengthened never",
                self.NEGATED_DESCRIPTION.replace(
                    "not as the issuer's own disclosure",
                    "never as the issuer's own disclosure",
                ),
            ),
            (
                "confirmed minimal probe",
                "Collect target-company-scoped third-party news; treat it "
                "as third-party reporting, not as the issuer's own "
                "disclosure.",
            ),
            (
                "do-not-treat prohibition",
                "Do not treat company_news as the target company's own "
                "announcements for this request.",
            ),
            (
                "must-not-description prohibition",
                "Coverage must not be described as the issuer's own news.",
            ),
        )
        for label, description in cases:
            with self.subTest(form=label):
                self._validate(self._plan(description=description))

    def test_affirmative_ownership_with_news_source_still_rejected(self):
        cases = (
            (
                "plain own disclosures",
                "Collect the company's own disclosures on orders.",
            ),
            (
                "unrelated negation in earlier clause",
                "Do not use forward-looking filings; collect the issuer's "
                "own disclosures available now.",
            ),
            (
                "not only but also",
                "Include not only third-party reporting but also the "
                "company's own disclosures.",
            ),
            (
                "negated then affirmative in one field",
                "Treat the coverage as third-party reporting, not as the "
                "issuer's own disclosure, and also collect the company's "
                "own filings.",
            ),
        )
        for label, description in cases:
            with self.subTest(form=label):
                with self.assertRaises(StructuredValidationError) as raised:
                    self._validate(self._plan(description=description))
                issue = raised.exception.issues[0]
                self.assertEqual(issue.code, "source_ownership_not_guaranteed")
                self.assertEqual(issue.paths, ("B.requests[0].description",))

    def test_news_verification_reference_needs_separate_first_party_source(self):
        for connector in ("against", "with", "using"):
            with self.subTest(connector=connector):
                description = (
                    "Retrieve target-company-scoped news as third-party reporting; "
                    f"verify any material claim {connector} the issuer's own filings "
                    "before weighting it."
                )
                plan = self._plan(description=description)
                with self.assertRaises(StructuredValidationError):
                    self._validate(plan)
                filing_request = replace(plan.basic_info_policy.requests[0],
                    request_id="first_party", source_types=("filing",),
                    description="Read the target issuer's own filings.")
                supported = replace(plan, basic_info_policy=replace(
                    plan.basic_info_policy, requests=plan.basic_info_policy.requests + (filing_request,)))
                self._validate(supported)

    def test_verification_reference_cannot_hide_another_ownership_claim(self):
        cases = (
            "Collect the issuer's own disclosures; verify news against the issuer's own filings.",
            "Verify news and collect material facts against the issuer's own filings.",
            "Verify news; rely on the issuer's own filings.",
        )
        for description in cases:
            with self.subTest(description=description):
                plan = self._plan(description=description)
                filing_request = replace(plan.basic_info_policy.requests[0],
                    request_id="first_party", source_types=("filing",),
                    description="Read the target issuer's own filings.")
                plan = replace(plan, basic_info_policy=replace(
                    plan.basic_info_policy, requests=plan.basic_info_policy.requests + (filing_request,)))
                with self.assertRaises(StructuredValidationError):
                    self._validate(plan)

    def test_immediate_instead_or_rather_contrast_negates_only_that_occurrence(self):
        for contrast in ("rather than", "instead of"):
            with self.subTest(contrast=contrast):
                text = f"Attribute coverage to third-party reporting {contrast} the issuer's own disclosure."
                self._validate(self._plan(description=text))
                with self.assertRaises(StructuredValidationError):
                    self._validate(self._plan(description=text + " Collect the issuer's own filings."))
                with self.assertRaisesRegex(ValidationError, "cross-issuer"):
                    self._validate(self._plan(description=(
                        f"Collect competitor actions {contrast} the target company's own disclosures.")))

    def test_query_field_checked_per_occurrence(self):
        flagged = self._plan(
            description="Collect third-party news about financing.",
            query="the issuer's own filings",
        )
        with self.assertRaises(StructuredValidationError) as raised:
            self._validate(flagged)
        self.assertEqual(
            raised.exception.issues[0].paths, ("B.requests[0].query",)
        )

        self._validate(
            self._plan(
                description="Collect third-party news about financing.",
                query=(
                    "Coverage framed as third-party reporting, not as the "
                    "issuer's own filings."
                ),
            )
        )

    def test_skill_ownership_guard_accepts_negation_rejects_affirmative(self):
        negated = (
            "Form hypotheses from news coverage and treat every news item "
            "as third-party reporting, never as the company's own "
            "disclosures; list unresolved information needs."
        )
        self._validate(self._plan(h_init=negated))

        for field, text in (
            (
                "H_reflect",
                "Update beliefs from evidence and rely on the issuer's own "
                "filings; decide whether to continue or finalize next needs.",
            ),
            (
                "H_analyse",
                "Organize evidence from the company's own news and weigh "
                "counter-evidence risks.",
            ),
        ):
            with self.subTest(field=field):
                with self.assertRaises(StructuredValidationError) as raised:
                    self._validate(self._plan(**{field.lower(): text}))
                self.assertEqual(raised.exception.issues[0].paths, (field,))

    def test_cross_issuer_negated_scope_does_not_authorize(self):
        plan = self._plan(
            description=(
                "Collect competitor financing actions from recent news; "
                "treat the coverage as third-party reporting, not as the "
                "target company's own disclosures."
            )
        )
        with self.assertRaises(ValidationError) as raised:
            self._validate(plan)
        self.assertIn("cross-issuer", str(raised.exception))

    def test_cross_issuer_affirmative_scope_still_authorizes(self):
        self._validate(
            self._plan(
                description=(
                    "Collect target-company-scoped news mentioning "
                    "competitors and peer actions."
                )
            )
        )

    def test_v145_basic_info_menu_rejects_free_text_query_and_foreign_families(
        self,
    ):
        from stock_opportunity_agent.research.evolution_output_validation import (
            _validate_plan_for_proposer_context,
        )
        from stock_opportunity_agent.research.evolution_core import (
            BasicInfoPolicy,
        )

        def plan_with(requests):
            return InformationPlan(
                plan_id="menu_fixture",
                parent_ids=(),
                basic_info_policy=BasicInfoPolicy(
                    requests=tuple(RawInfoRequest(**row) for row in requests)
                ),
                initial_research_skill=(
                    "Form a hypothesis and list unresolved information needs."
                ),
                reflection_skill=(
                    "Track support and contradiction, then continue for the "
                    "next need or finalize."
                ),
                analysis_prompt="Weigh supporting and counter evidence.",
            )

        base = {
            "request_id": "scoped_news",
            "description": "Recent company news.",
            "source_types": ["news"],
            "lookback_days": 180,
            "max_documents": 5,
        }
        market = {
            "request_id": "recent_market_backbone",
            "description": "Point-in-time price and volume.",
            "source_types": ["market_data"],
            "lookback_days": 45,
            "max_documents": 1,
        }
        # The menu-compliant composition passes.
        _validate_plan_for_proposer_context(
            plan_with([base, market]), available_source_types=("news", "market_data")
        )
        # A free-text query is not expressible at the orientation stage.
        with_query = dict(base, query="guidance backlog analyst target")
        with self.assertRaises(StructuredValidationError) as caught:
            _validate_plan_for_proposer_context(
                plan_with([with_query, market]),
                available_source_types=("news", "market_data"),
            )
        codes = [issue.code for issue in caught.exception.issues]
        self.assertIn("basic_info_query_not_expressible", codes)
        self.assertEqual(
            caught.exception.issues[0].paths, ("B.requests[0].query",)
        )
        # A source family outside the closed menu is rejected with its path.
        foreign = dict(base, source_types=["social_media"])
        with self.assertRaises(StructuredValidationError) as caught:
            _validate_plan_for_proposer_context(
                plan_with([foreign, market]),
                available_source_types=("social_media", "market_data"),
            )
        codes = [issue.code for issue in caught.exception.issues]
        self.assertIn("basic_info_family_outside_menu", codes)
        # Mixed families obey the strictest matched lookback bound.
        mixed = {
            "request_id": "bridge",
            "description": "Bridge view.",
            "source_types": ["earnings_call", "filing", "financials"],
            "lookback_days": 365,
            "max_documents": 3,
        }
        _validate_plan_for_proposer_context(
            plan_with([mixed, market]),
            available_source_types=(
                "earnings_call", "filing", "financials", "market_data",
            ),
        )
        overreached = dict(mixed, lookback_days=730)
        with self.assertRaises(StructuredValidationError) as caught:
            _validate_plan_for_proposer_context(
                plan_with([overreached, market]),
                available_source_types=(
                    "earnings_call", "filing", "financials", "market_data",
                ),
            )
        codes = [issue.code for issue in caught.exception.issues]
        self.assertIn("basic_info_lookback_out_of_bounds", codes)
