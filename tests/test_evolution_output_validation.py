"""Structured-correction projection tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403


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
