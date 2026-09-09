"""Structured-correction projection tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403


class ScopedCorrectionProjectionTests(TestCase):
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
