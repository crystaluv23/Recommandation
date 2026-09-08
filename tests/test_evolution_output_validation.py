"""Structured-correction projection tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403


class ScopedCorrectionProjectionTests(TestCase):
    def test_group_alias_recognition_does_not_relax_membership_guard(self) -> None:
        for label in ("positive", "control"):
            for qualifier in ("Discovery", "fixed Discovery", "fixed"):
                text = f"{label} {qualifier} cases are issuers with high growth"
                self.assertIsNotNone(
                    evolution_runtime_module._H1_GROUP_REDEFINITION_PATTERN.search(text)
                )
        self.assertIsNone(
            evolution_runtime_module._H1_POSITIVE_CASE_PATTERN.search(
                "Positive revenue and negative costs occur in the control cases."
            )
        )

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
