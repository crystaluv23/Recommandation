"""Signal Mining, Update, and exploration role-adapter tests."""

from copy import deepcopy

from tests.evolution_runtime_test_support import *  # noqa: F403
from stock_opportunity_agent.research.basic_info_orientation import make_orientation_request
from stock_opportunity_agent.research import (
    evolution_core as core_module,
    evolution_signal_roles as signal_roles_module,
)


class SignalRoleAdapterTests(TestCase):
    def test_reflection_masks_provider_view_without_mutating_feedback(self) -> None:
        case_identity = "cik_0001077183:20250331"
        output = {
            "episode_reflections": [
                {
                    "episode_ref": "episode-c0001-001",
                    "source_refs": ["update-target-001"],
                    "reflection": "The target had no paired effectiveness gain.",
                    "unresolved_questions": [],
                    "kind": "hypothesis",
                    "brief": "Without paired effectiveness gain, retain this counterexample; transfer is untested.",
                }
            ],
            "lesson_additions": [],
        }
        caller = ScriptedRoleCaller([output])
        model = LLMSignalMiningModel(caller)
        aliases = (case_identity, "Target Corporation", "Gain Therapeutics")
        model.set_identity_guard_aliases(aliases)
        payload = {
            "episode_slots": ["episode-c0001-001"],
            "lesson_slots": ["lesson-c0001-001"],
            "feedback_units": [
                {
                    "feedback_ref": "update-target-001",
                    "artifact": {
                        "case_id": case_identity,
                        "case_ids": [case_identity, "another-case", case_identity],
                        "company": "Target Corporation and Gain Therapeutics",
                        "reason": "The target had no paired effectiveness gain.",
                    },
                }
            ],
        }

        step = model.reflect_feedback(payload)

        sent = caller.calls[0]["payload"]
        self.assertNotIn(case_identity, json.dumps(sent))
        self.assertIn("[MASKED_COMPANY]", json.dumps(sent))
        self.assertEqual(caller.calls[0]["anonymous_aliases"], aliases)
        self.assertEqual(len(caller.calls), 1)
        case_refs = sent["feedback_units"][0]["artifact"]["case_ids"]
        self.assertEqual(case_refs[0], case_refs[2])
        self.assertNotEqual(case_refs[0], case_refs[1])
        self.assertEqual(sent["feedback_units"][0]["artifact"]["case_id"], case_refs[0])
        self.assertNotIn("Target Corporation", json.dumps(sent))
        self.assertNotIn("Gain Therapeutics", json.dumps(sent))
        self.assertEqual(sent["feedback_units"][0]["feedback_ref"], "update-target-001")
        self.assertEqual(
            sent["feedback_units"][0]["artifact"]["reason"],
            "The target had no paired effectiveness gain.",
        )
        self.assertEqual(
            payload["feedback_units"][0]["artifact"]["case_id"], case_identity
        )
        self.assertEqual(step.value, output)

    def test_mining_typed_source_read_accepts_only_supplied_opaque_refs(self) -> None:
        caller = ScriptedRoleCaller(
            [{"read_source_refs": ["feedback-2"]}]
        )
        step = LLMSignalMiningModel(caller).request_slow_sources(
            {
                "source_read_contract_version": "slow-source-read-v1",
                "role_scope": "H1",
                "available_sources": [
                    {"ref": "feedback-1", "content_hash": "a"},
                    {"ref": "feedback-2", "content_hash": "b"},
                ],
                "current_view": {"included_refs": ["feedback-1"]},
            }
        )

        self.assertEqual(step.value, ("feedback-2",))
        self.assertEqual(caller.stages, ["slow_source_read"])

    def test_reflection_aggregates_nested_source_ref_failures(self) -> None:
        invalid = {
            "episode_reflections": [
                {
                    "episode_ref": "episode-c0001-001",
                    "source_refs": ["nested-source-a"],
                    "reflection": "The first work completed without a candidate.",
                    "unresolved_questions": [],
                },
                {
                    "episode_ref": "episode-c0001-002",
                    "source_refs": ["nested-source-b"],
                    "reflection": "The second work had a technical failure.",
                    "unresolved_questions": ["Which layer failed?"],
                },
            ],
            "lesson_additions": [
                {
                    "lesson_id": "lesson-c0001-001",
                    "guidance": "Keep technical and research failures separate.",
                    "applicable_scope": "Slow validation",
                    "support_refs": ["nested-source-b"],
                    "counterevidence_refs": [],
                    "limitations": ["Two imported work units only."],
                    "qualifies_refs": [],
                    "challenges_refs": [],
                }
            ],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["episode_reflections"][0]["source_refs"] = ["feedback-1"]
        corrected["episode_reflections"][1]["source_refs"] = ["feedback-2"]
        corrected["lesson_additions"][0]["support_refs"] = ["feedback-2"]
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).reflect_feedback(
            {
                "episode_slots": ["episode-c0001-001", "episode-c0001-002"],
                "lesson_slots": ["lesson-c0001-001"],
                "feedback_units": [
                    {
                        "feedback_ref": "feedback-1",
                        "payload": {"source_refs": ["different-nested-a"]},
                    },
                    {
                        "feedback_ref": "feedback-2",
                        "payload": {"source_refs": ["different-nested-b"]},
                    },
                ],
            }
        )

        self.assertEqual(len(step.value["episode_reflections"]), 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligation_count"], 4)
        self.assertEqual(
            feedback["required_change_paths"],
            [
                "episode_reflections[0]",
                "episode_reflections[1]",
                "episode_reflections",
                "lesson_additions[0].support_refs",
            ],
        )
        self.assertIn("top-level feedback_ref", caller.calls[0]["system_prompt"])

    def test_reflection_corrects_all_omitted_selected_feedback_refs(self) -> None:
        initial = {
            "episode_reflections": [
                {
                    "episode_ref": "episode-c0002-001",
                    "source_refs": ["feedback-1"],
                    "reflection": "The first completed work unit was retained.",
                    "unresolved_questions": [],
                }
            ],
            "lesson_additions": [],
        }
        corrected = {
            "episode_reflections": [
                {
                    "episode_ref": "episode-c0002-001",
                    "source_refs": ["feedback-1", "feedback-2", "feedback-3"],
                    "reflection": "All selected complete work units were retained.",
                    "unresolved_questions": [],
                }
            ],
            "lesson_additions": [],
        }
        from tests.test_evolution_state_patch import PatchCaller, patch
        for output in (initial, corrected):
            output["episode_reflections"][0]["kind"] = "hypothesis"
            output["episode_reflections"][0]["brief"] = output["episode_reflections"][0]["reflection"]

        def correct(request):
            return patch(request["payload"]["output_patch_contract"], {
                "op": "replace", "path": "episode_reflections[0]",
                "value": corrected["episode_reflections"][0],
            })

        caller = PatchCaller(initial, correct)

        step = LLMSignalMiningModel(caller).reflect_feedback(
            {
                "episode_slots": [
                    "episode-c0002-001",
                    "episode-c0002-002",
                    "episode-c0002-003",
                ],
                "lesson_slots": ["lesson-c0002-001"],
                "feedback_units": [
                    {"feedback_ref": f"feedback-{index}", "artifact": {}}
                    for index in range(1, 4)
                ],
            }
        )

        self.assertEqual(step.usage.llm_calls, 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        issue = next(
            item
            for item in feedback["obligations"]
            if item["issue_code"] == "reflection_feedback_coverage_missing"
        )
        self.assertEqual(
            issue["missing_feedback_refs"],
            ["feedback-2", "feedback-3"],
        )
        self.assertEqual(
            set(step.value["episode_reflections"][0]["source_refs"]),
            {"feedback-1", "feedback-2", "feedback-3"},
        )

    def test_reflection_fallback_merges_valid_overflow_episode(self) -> None:
        overflow = {
            "episode_reflections": [
                {
                    "episode_ref": "episode-c0002-001",
                    "source_refs": ["feedback-1"],
                    "reflection": "The first selected work unit was retained.",
                    "unresolved_questions": ["What follows from the first unit?"],
                },
                {
                    "episode_ref": "episode-c0002-002",
                    "source_refs": ["feedback-2"],
                    "reflection": "The omitted selected work unit was also retained.",
                    "unresolved_questions": ["What follows from the omitted unit?"],
                },
            ],
            "lesson_additions": [],
        }
        caller = ScriptedRoleCaller([overflow, overflow, overflow])
        caller.max_structured_corrections = 2

        step = LLMSignalMiningModel(caller).reflect_feedback(
            {
                "episode_slots": ["episode-c0002-001"],
                "lesson_slots": ["lesson-c0002-001"],
                "feedback_units": [
                    {"feedback_ref": "feedback-1", "artifact": {}},
                    {"feedback_ref": "feedback-2", "artifact": {}},
                ],
            }
        )

        self.assertEqual(step.usage.llm_calls, 3)
        self.assertEqual(len(step.value["episode_reflections"]), 1)
        episode = step.value["episode_reflections"][0]
        self.assertEqual(episode["episode_ref"], "episode-c0002-001")
        self.assertEqual(
            episode["source_refs"], ["feedback-1", "feedback-2"]
        )
        self.assertIn("first selected work unit", episode["reflection"])
        self.assertIn("omitted selected work unit", episode["reflection"])
        self.assertEqual(
            episode["unresolved_questions"],
            [
                "What follows from the first unit?",
                "What follows from the omitted unit?",
            ],
        )

    def test_reflection_canonicalizes_uniquely_owned_nested_slow_refs(self) -> None:
        nested_ref = "slow-history:source-old:1:slow_loop_result:summary"
        output = {
            "episode_reflections": [
                {
                    "episode_ref": "episode-c0001-001",
                    "source_refs": [nested_ref],
                    "reflection": "The wrapped prior cycle produced no candidate.",
                    "unresolved_questions": [],
                }
            ],
            "lesson_additions": [
                {
                    "lesson_id": "lesson-c0001-001",
                    "guidance": "Keep a no-candidate outcome distinct from failure.",
                    "applicable_scope": "Slow search summaries",
                    "support_refs": [nested_ref],
                    "counterevidence_refs": [],
                    "limitations": ["One wrapped cycle only."],
                    "qualifies_refs": [],
                    "challenges_refs": [],
                }
            ],
        }
        caller = ScriptedRoleCaller([output])

        step = LLMSignalMiningModel(caller).reflect_feedback(
            {
                "episode_slots": ["episode-c0001-001"],
                "lesson_slots": ["lesson-c0001-001"],
                "feedback_units": [
                    {
                        "feedback_ref": "feedback-wrapper",
                        "artifact": {"source_refs": [nested_ref]},
                    }
                ],
            }
        )

        self.assertEqual(
            step.value["episode_reflections"][0]["source_refs"],
            ["feedback-wrapper"],
        )
        self.assertEqual(
            step.value["lesson_additions"][0]["support_refs"],
            ["feedback-wrapper"],
        )
        self.assertEqual(
            step.metadata["canonicalized_nested_refs"],
            {nested_ref: "feedback-wrapper"},
        )
        self.assertEqual(step.usage.llm_calls, 1)

    def _nested_reference_output(self, nested_ref):
        return {
            "episode_reflections": [{
                "episode_ref": "episode-c0001-001",
                "source_refs": [nested_ref],
                "reflection": "The wrapped work has an unresolved measurement question.",
                "unresolved_questions": ["Does this transfer across independent cases?"],
                "kind": "hypothesis",
                "brief": "Keep this measurement question unresolved; independent transfer is untested.",
            }],
            "lesson_additions": [{
                "lesson_id": "lesson-c0001-001",
                "guidance": "Test transfer across independent cases before claiming benefit.",
                "applicable_scope": "Imported feedback comparisons",
                "support_refs": [nested_ref],
                "counterevidence_refs": [],
                "limitations": ["A comparison does not establish independent benefit."],
                "qualifies_refs": [],
                "challenges_refs": [],
                "kind": "action",
                "brief": "Require independent transfer evidence before claiming benefit from an imported comparison.",
            }],
        }

    def test_nested_reference_ownership_is_structural_across_opaque_namespaces(self):
        variants = [
            ("feedback_ref", "prediction_comparison:opaque"),
            ("observation_ref", "prediction_observation:opaque"),
            ("source_refs", ["source-span-opaque", "source-span-opaque"]),
            ("refs", ["opaque-without-prefix"]),
        ]
        for field, refs in variants:
            with self.subTest(field=field, refs=refs):
                nested_ref = refs[0] if isinstance(refs, list) else refs
                output = self._nested_reference_output(nested_ref)
                original = deepcopy(output)
                payload = {
                    "episode_slots": ["episode-c0001-001"],
                    "lesson_slots": ["lesson-c0001-001"],
                    "feedback_units": [{
                        "feedback_ref": "feedback-owner",
                        "artifact": {"data": {field: refs}},
                    }],
                }
                original_payload = deepcopy(payload)
                step = LLMSignalMiningModel(ScriptedRoleCaller([output])).reflect_feedback(payload)
                self.assertEqual(step.value["episode_reflections"][0]["source_refs"], ["feedback-owner"])
                self.assertEqual(step.value["lesson_additions"][0]["support_refs"], ["feedback-owner"])
                self.assertEqual(step.metadata["canonicalized_nested_refs"], {nested_ref: "feedback-owner"})
                self.assertEqual(step.value["episode_reflections"][0]["reflection"], original["episode_reflections"][0]["reflection"])
                self.assertEqual(output, original)
                self.assertEqual(payload, original_payload)
                self.assertEqual(step.usage.llm_calls, 1)

    def test_nested_ref_mentioned_only_as_prose_or_owned_by_two_units_is_not_mapped(self):
        nested_ref = "prediction_comparison:opaque"
        variants = [
            [{"feedback_ref": "feedback-owner", "artifact": {"reason": nested_ref}}],
            [
                {"feedback_ref": "feedback-one", "artifact": {"feedback_ref": nested_ref}},
                {"feedback_ref": "feedback-two", "artifact": {"feedback_ref": nested_ref}},
            ],
        ]
        for units in variants:
            with self.subTest(units=units):
                output = self._nested_reference_output(nested_ref)
                caller = ScriptedRoleCaller([deepcopy(output), deepcopy(output)])
                with self.assertRaises(ValidationError):
                    LLMSignalMiningModel(caller).reflect_feedback({
                        "episode_slots": ["episode-c0001-001", "episode-c0001-002"],
                        "lesson_slots": ["lesson-c0001-001"],
                        "feedback_units": units,
                    })

    def test_update_role_retains_initial_and_correction_request_refs(self) -> None:
        class TracedCaller(ScriptedRoleCaller):
            def __init__(self, outputs):
                super().__init__(outputs)
                self.request_hash_trace = []

            def complete_json(self, **kwargs):
                self.request_hash_trace.append(
                    f"request-{len(self.request_hash_trace) + 1}"
                )
                return super().complete_json(**kwargs)

        invalid = {
            "signal_ref": "cash_reserves:v1",
            "disposition": "defer",
            "problem_type": "insufficient_sample",
            "rationale": [],
            "case_diagnostics": [],
            "changed_paths": [],
            "candidate": None,
        }
        corrected = {**invalid, "rationale": ["Need more distinct observations."]}
        step = LLMSignalUpdateModel(TracedCaller([invalid, corrected])).update(
            {
                "update_contract_version": "signal-update-decision-v2",
                "target": {"signal_ref": "cash_reserves:v1"},
                "induction_cases": [],
            }
        )

        self.assertEqual(
            step.metadata["request_refs"], ("request-1", "request-2")
        )

    def test_source_concept_label_is_not_an_outcome_label(self) -> None:
        payload = {
            "cases": [
                {
                    "evidence": [
                        {
                            "structured_context": {
                                "concepts": [
                                    {"label": "Revenue", "unit": "USD"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        evolution_runtime_module._scan_payload(
            payload,
            allow_outcomes=False,
            anonymous_aliases=(),
        )
        evolution_runtime_module._scan_payload(
            {
                "comparison_concepts": [
                    {
                        "taxonomy": "us-gaap",
                        "concept": "Revenue",
                        "source_display_name": "Revenue",
                        "unit": "USD",
                        "case_count": 3,
                    }
                ]
            },
            allow_outcomes=False,
            anonymous_aliases=(),
        )
        with self.assertRaisesRegex(ValidationError, "outcome field leaked"):
            evolution_runtime_module._scan_payload(
                {"cases": [{"label": "surge"}]},
                allow_outcomes=False,
                anonymous_aliases=(),
            )

    def test_update_candidate_uses_staging_checks_inside_correction(self) -> None:
        stable = SignalSpec(
            signal_id="revenue_growth_yoy", version=1, category="financial",
            description="Measure year-over-year revenue growth.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            modality=SignalModality.STRUCTURED,
            source_types=("financials",), function="financial.revenue_growth_yoy",
        )
        candidate = {
            "signal_ref": stable.ref,
            "spec": {
                **stable.to_dict(),
                "version": 2,
                "parameters": {"positive_min": 0.2},
            },
            "tests": [{"name": "retained fixture"}],
        }
        invalid = json.loads(json.dumps(candidate))
        invalid["signal_ref"] = "revenue_growth_yoy:v2"
        response = {
            "signal_ref": stable.ref, "disposition": "update",
            "problem_type": "threshold_calibration", "rationale": ["Test calibration."],
            "case_diagnostics": [], "changed_paths": ["spec.parameters"],
            "candidate": invalid,
        }
        caller = ScriptedRoleCaller([response, {**response, "candidate": candidate}])
        step = LLMSignalUpdateModel(caller).update({
            "update_contract_version": "signal-update-decision-v2",
            "target": {"signal_ref": stable.ref, "stable_spec": stable.to_dict()},
            "induction_cases": [],
        })
        self.assertEqual(step.value.candidate, candidate)
        self.assertEqual(step.usage.llm_calls, 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["required_change_paths"], [])
        self.assertEqual(
            feedback["obligations"][0]["must_change_any_of_paths"],
            ["candidate", "changed_paths"],
        )
        self.assertIn("target signal_ref", feedback["validation_error"])
        parsed, skill, _tests = signal_roles_module.validate_signal_update_candidate(
            stable.ref, candidate, stable,
        )
        self.assertEqual(parsed.version, 2)
        self.assertIsNone(skill)
        changed = json.loads(json.dumps(candidate))
        changed["spec"]["definition"]["description"] = "A different measurement."
        with self.assertRaisesRegex(ValidationError, "preserve description"):
            signal_roles_module.validate_signal_update_candidate(stable.ref, changed, stable)

    def test_update_no_effective_change_can_exit_without_rewriting_case_evidence(self) -> None:
        stable = SignalSpec(signal_id="revenue_growth_yoy", version=1, category="financial",
            description="Measure year-over-year revenue growth.",
            execution_type=SignalExecutionType.DETERMINISTIC, modality=SignalModality.STRUCTURED,
            source_types=("financials",), function="financial.revenue_growth_yoy")
        row = {"case_ref": "update-case-001", "evidence_verdict": "supported",
               "facts": [{"document_ref": "document-01", "exact_span": "Revenue grew 20%."}],
               "evidence_gaps": [], "outcome_relation": "aligned",
               "outcome_explanation": "The source result agrees with the supplied association."}
        invalid = {"signal_ref": stable.ref, "disposition": "update", "problem_type": "threshold_calibration",
                   "rationale": ["Update calibration."], "case_diagnostics": [row],
                   "changed_paths": ["spec.parameters"], "candidate": {"signal_ref": stable.ref,
                       "spec": {**stable.to_dict(), "version": 2}, "tests": [{"name": "unchanged"}]}}
        corrected = {**invalid, "disposition": "no_change", "candidate": None,
                     "changed_paths": [], "rationale": ["No supported mutable change was established."]}
        caller = ScriptedRoleCaller([invalid, corrected])
        result = LLMSignalUpdateModel(caller).update({
            "target": {"signal_ref": stable.ref, "stable_spec": stable.to_dict()},
            "induction_cases": [{"case_ref": row["case_ref"],
                "evidence_observation": {"executed_evidence": [row["facts"][0]]},
                "outcome_relation": {"current_signal_relation": "aligned"}}],
        })
        self.assertEqual(result.value.disposition, "no_change")
        self.assertIsNone(result.value.candidate)
        self.assertEqual(result.value.case_diagnostics, (row,))
        self.assertEqual(result.usage.llm_calls, 2)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligations"][0]["issue_code"], "signal_update_no_effective_change")
        self.assertEqual(feedback["obligations"][0]["must_change_any_of_paths"],
                         ["candidate", "disposition", "rationale"])
        self.assertEqual(feedback["obligations"][0]["permitted_dependency_paths"], ["changed_paths"])
        self.assertIn("never return it unchanged", caller.calls[0]["system_prompt"])
        permissions = caller.calls[1]["payload"]["output_patch_contract"]["allowed_operations"]
        self.assertIn({"op": "remove", "path": "changed_paths[0]", "descendants": False}, permissions)
        self.assertFalse(any(p["op"] == "replace" and p["path"] == "changed_paths" for p in permissions))
        self.assertNotIn("case_diagnostics", str(caller.calls[1]["payload"]["output_patch_contract"]["allowed_operations"]))

    def test_update_program_repairs_changed_paths_before_correction(self) -> None:
        stable = SignalSpec(
            signal_id="revenue_growth_yoy", version=1, category="financial",
            description="Measure year-over-year revenue growth.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            modality=SignalModality.STRUCTURED,
            source_types=("financials",), function="financial.revenue_growth_yoy",
        )
        candidate = {
            "signal_ref": stable.ref,
            "spec": {
                **stable.to_dict(),
                "version": 2,
                "parameters": {"positive_min": 0.2},
            },
            "tests": [{"name": "retained fixture"}],
        }
        response = {
            "signal_ref": stable.ref,
            "disposition": "update",
            "problem_type": "threshold_calibration",
            "rationale": ["Test calibration."],
            "case_diagnostics": [],
            "changed_paths": ["spec.version", "spec.parameters.positive_min"],
            "candidate": candidate,
        }
        corrected = {**response, "changed_paths": ["spec.parameters"]}
        caller = ScriptedRoleCaller([response, corrected])

        step = LLMSignalUpdateModel(caller).update({
            "update_contract_version": "signal-update-decision-v2",
            "target": {"signal_ref": stable.ref, "stable_spec": stable.to_dict()},
            "induction_cases": [],
            "candidate_contract": {
                "changed_paths_allowed": list(
                    signal_roles_module.SIGNAL_UPDATE_MUTABLE_PATHS
                )
            },
        })

        self.assertEqual(step.value.changed_paths, ("spec.parameters",))
        self.assertEqual(step.value.candidate, candidate)
        self.assertEqual(step.usage.llm_calls, 1)
        self.assertEqual(len(caller.calls), 1)
        self.assertIn("changed_paths_allowed", caller.calls[0]["system_prompt"])

    def test_update_program_normalizes_only_effective_changed_paths(self) -> None:
        stable = SignalSpec(
            signal_id="revenue_growth_yoy", version=1, category="financial",
            description="Measure year-over-year revenue growth.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            modality=SignalModality.STRUCTURED,
            source_types=("financials",), function="financial.revenue_growth_yoy",
        )
        candidate = {
            "signal_ref": stable.ref,
            "spec": {
                **stable.to_dict(),
                "version": 2,
                "raw_retrieval": {
                    **stable.to_dict()["raw_retrieval"],
                    "minimum_observations": 2,
                },
            },
            "tests": [{"name": "retained fixture"}],
        }
        response = {
            "signal_ref": stable.ref,
            "disposition": "update",
            "problem_type": "retrieval",
            "rationale": ["Require two source observations."],
            "case_diagnostics": [],
            "changed_paths": [
                "spec.raw_retrieval.minimum_observations",
                "spec.parameters",
            ],
            "candidate": candidate,
        }
        caller = ScriptedRoleCaller([response, response])

        step = LLMSignalUpdateModel(caller).update({
            "update_contract_version": "signal-update-decision-v2",
            "target": {"signal_ref": stable.ref, "stable_spec": stable.to_dict()},
            "induction_cases": [],
        })

        self.assertEqual(step.usage.llm_calls, 1)
        self.assertEqual(
            step.value.changed_paths,
            ("spec.raw_retrieval.minimum_observations",),
        )
        self.assertEqual(step.value.candidate, candidate)

    def test_update_program_normalizes_paths_rejected_by_record_constructor(self) -> None:
        stable = SignalSpec(signal_id="cash_reserves", version=1, category="financial",
            description="Read the latest point-in-time cash balance.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            modality=SignalModality.STRUCTURED, source_types=("financials",),
            function="financial.cash_reserves")
        candidate = {"signal_ref": stable.ref, "spec": {**stable.to_dict(), "version": 2,
            "raw_retrieval": {**stable.to_dict()["raw_retrieval"], "minimum_observations": 2}},
            "skill": None, "tests": [{"name": "immutable fixture"}]}
        for declared in (["spec.parameters", "spec.parameters"], ["", "spec.parameters"]):
            with self.subTest(declared=declared):
                response = {"signal_ref": stable.ref, "disposition": "update",
                    "problem_type": "retrieval", "rationale": ["Require two observations."],
                    "case_diagnostics": [], "changed_paths": declared, "candidate": candidate}
                original = deepcopy(response)
                caller = ScriptedRoleCaller([response])
                model = LLMSignalUpdateModel(caller)
                validated = []
                model.set_candidate_validator(lambda ref, value, paths: validated.append((ref, deepcopy(value), paths)))
                step = model.update({"target": {"signal_ref": stable.ref, "stable_spec": stable.to_dict()},
                    "induction_cases": []})
                self.assertEqual(step.usage.llm_calls, 1)
                self.assertEqual(len(caller.calls), 1)
                self.assertEqual(step.value.changed_paths, ("spec.raw_retrieval.minimum_observations",))
                self.assertEqual(step.value.candidate, candidate)
                self.assertEqual(validated, [(stable.ref, candidate, step.value.changed_paths)])
                self.assertEqual(response, original)
                self.assertEqual(step.value.rationale, tuple(original["rationale"]))

    def test_update_path_normalization_still_rechecks_fixture_failure(self) -> None:
        stable = SignalSpec(signal_id="cash_reserves", version=1, category="financial",
            description="Read the latest point-in-time cash balance.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            modality=SignalModality.STRUCTURED, source_types=("financials",),
            function="financial.cash_reserves")
        candidate = {"signal_ref": stable.ref, "spec": {**stable.to_dict(), "version": 2,
            "raw_retrieval": {**stable.to_dict()["raw_retrieval"], "minimum_observations": 2}},
            "skill": None, "tests": [{"name": "immutable fixture"}]}
        response = {"signal_ref": stable.ref, "disposition": "update", "problem_type": "retrieval",
            "rationale": ["Require two observations."], "case_diagnostics": [],
            "changed_paths": ["spec.parameters", "spec.parameters"], "candidate": candidate}
        caller = ScriptedRoleCaller([response, response, response])
        model = LLMSignalUpdateModel(caller)
        def reject(_ref, _candidate, _paths):
            raise ValidationError("fixture failed: evidence remains unavailable")
        model.set_candidate_validator(reject)
        with self.assertRaises(CandidateExecutionRejected):
            model.update({"target": {"signal_ref": stable.ref, "stable_spec": stable.to_dict()}, "induction_cases": []})
        correction = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("fixture failed", correction["validation_error"])
        self.assertEqual(correction["invalid_output"]["changed_paths"], ["spec.raw_retrieval.minimum_observations"])
        self.assertEqual(correction["invalid_output"]["candidate"], candidate)

    def test_update_candidate_fixture_failure_is_corrected_before_staging(self) -> None:
        stable = SignalSpec(
            signal_id="cash_reserves",
            version=1,
            category="financial",
            description="Read the latest point-in-time cash balance.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            modality=SignalModality.STRUCTURED,
            source_types=("financials",),
            function="financial.cash_reserves",
        )
        fixture = {"name": "cash fixture"}
        bad_candidate = {
            "signal_ref": stable.ref,
            "spec": {
                **stable.to_dict(),
                "version": 2,
                "raw_retrieval": {
                    **stable.to_dict()["raw_retrieval"],
                    "minimum_observations": 2,
                },
            },
            "tests": [fixture],
        }
        good_candidate = json.loads(json.dumps(bad_candidate))
        good_candidate["spec"]["raw_retrieval"]["minimum_observations"] = 1
        response = {
            "signal_ref": stable.ref,
            "disposition": "update",
            "problem_type": "retrieval",
            "rationale": ["Keep the fixture executable."],
            "case_diagnostics": [],
            "changed_paths": ["spec.parameters"],
            "candidate": bad_candidate,
        }
        corrected = {**response, "candidate": good_candidate}
        caller = ScriptedRoleCaller([response, corrected])
        model = LLMSignalUpdateModel(caller)

        def validate_fixture(
            _signal_ref: str,
            candidate: Mapping[str, Any],
            _changed_paths: tuple[str, ...],
        ) -> None:
            minimum = candidate["spec"]["raw_retrieval"]["minimum_observations"]
            if minimum > 1:
                raise ValidationError("fixture 1 would become unavailable")

        model.set_candidate_validator(validate_fixture)
        step = model.update(
            {
                "target": {
                    "signal_ref": stable.ref,
                    "stable_spec": stable.to_dict(),
                },
                "induction_cases": [],
            }
        )

        self.assertEqual(
            step.value.candidate["spec"]["raw_retrieval"]["minimum_observations"],
            1,
        )
        self.assertEqual(caller.calls[1]["payload"]["validation_feedback"]["invalid_output"]["changed_paths"], ["spec.raw_retrieval.minimum_observations"])
        self.assertEqual(
            caller.calls[1]["payload"]["validation_feedback"]["obligations"][0][
                "issue_code"
            ],
            "signal_update_candidate_fixture_invalid",
        )
        self.assertIn("unchanged fixtures", caller.calls[0]["system_prompt"])

    def test_e1_quarantines_invalid_observations_without_losing_valid_siblings(self) -> None:
        literal = "Management reaffirmed revenue guidance."
        valid = {"summary": "Guidance reaffirmed.", "document_ref": "document-01",
                 "exact_span": literal}
        response = {"signatures": [
            {"case_ref": "case-001", "observations": [valid, {**valid, "exact_span": "invented fact"}],
             "evidence_gaps": []},
            {"case_ref": "case-002", "observations": [valid], "evidence_gaps": []},
            {"case_ref": "case-003", "observations": [{**valid, "exact_span": "x"}],
             "evidence_gaps": []},
        ]}
        caller = ScriptedRoleCaller([response, response, response])
        step = LLMSignalMiningModel(caller).extract_exploration({"cases": [
            {"case_ref": f"case-{index:03d}", "evidence": [
                {"document_ref": "document-01", "content_excerpt": literal}
            ]} for index in (1, 2, 3)
        ]})
        self.assertEqual(step.usage.llm_calls, 2)
        self.assertEqual([len(row.observations) for row in step.value], [1, 1, 0])
        self.assertEqual(step.value[1].to_dict(), response["signatures"][1])
        self.assertEqual(set(step.metadata["quarantined_observations"]), {"case-001", "case-003"})
        self.assertIn("does not establish absent", step.value[2].evidence_gaps[0])

    def test_e1_does_not_displace_business_observation_for_recurring_pair(self) -> None:
        first = '{"end":"2025-06-30","val":120}'
        second = '{"end":"2024-06-30","val":100}'
        narrative = "The shareholder agreed to a ten-year share transfer lock-up."
        response = {"signatures": [{"case_ref": "case-001", "observations": [{
            "summary": "The agreement restricts share transfers.",
            "document_ref": "document-01", "exact_span": narrative,
        }], "evidence_gaps": []}]}
        caller = ScriptedRoleCaller([response])
        step = LLMSignalMiningModel(caller).extract_exploration(
            self._recurring_pair_payload(narrative, first, second)
        )
        self.assertEqual(step.usage.llm_calls, 1)
        self.assertEqual(step.value[0].to_dict(), response["signatures"][0])
        self.assertEqual(step.metadata["quarantined_observations"], {})

    def test_e1_selected_financial_fact_keeps_source_bound_companion_for_e2(self) -> None:
        from stock_opportunity_agent.research.signal_evolution import _literal_only_signature_view
        first = '{"end":"2025-06-30","val":120}'
        second = '{"end":"2024-06-30","val":100}'
        payload = self._recurring_pair_payload("Management reaffirmed guidance.", first, second)
        response = {"signatures": [{"case_ref": "case-001", "observations": [{
            "summary": "A selected source financial record.",
            "document_ref": "document-02", "exact_span": first,
        }], "evidence_gaps": []}]}
        caller = ScriptedRoleCaller([response])
        step = LLMSignalMiningModel(caller).extract_exploration(payload)
        self.assertEqual(step.usage.llm_calls, 1)
        self.assertEqual(len(step.value[0].observations), 1)
        view = _literal_only_signature_view(step.value[0], payload["cases"][0])
        self.assertEqual([o["exact_span"] for o in view["observations"]], [first, second])
        self.assertTrue(all("OperatingIncomeLoss" in o["summary"] for o in view["observations"]))
        self.assertTrue(all("unit=USD" in o["summary"] for o in view["observations"]))

    def test_e1_invalid_quote_recovery_does_not_insert_unselected_financial_facts(self) -> None:
        first = '{"end":"2025-06-30","val":120}'
        second = '{"end":"2024-06-30","val":100}'
        narrative = "Management reaffirmed revenue guidance."
        valid = {"summary": "Guidance was reaffirmed.", "document_ref": "document-01", "exact_span": narrative}
        response = {"signatures": [{"case_ref": "case-001", "observations": [
            valid, {"summary": "Invented fact.", "document_ref": "document-02", "exact_span": "Not in the source."},
        ], "evidence_gaps": []}]}
        caller = ScriptedRoleCaller([response, response, response])
        step = LLMSignalMiningModel(caller).extract_exploration(
            self._recurring_pair_payload(narrative, first, second)
        )
        self.assertEqual([o.to_dict() for o in step.value[0].observations], [valid])
        self.assertIn("case-001", step.metadata["quarantined_observations"])
        self.assertIn("technical extraction limitation", step.value[0].evidence_gaps[-1])

    @staticmethod
    def _recurring_pair_payload(
        narrative: str, first: str, second: str,
    ) -> dict[str, object]:
        return {
            "comparison_concepts": [
                {
                    "taxonomy": "us-gaap",
                    "concept": "OperatingIncomeLoss",
                    "source_display_name": "Operating income",
                    "unit": "USD",
                    "case_count": 4,
                }
            ],
            "cases": [
                {
                    "case_ref": "case-001",
                    "evidence": [
                        {
                            "document_ref": "document-01",
                            "content_excerpt": narrative,
                        },
                        {
                            "document_ref": "document-02",
                            "content_excerpt": "",
                            "structured_context": {
                                "concepts": [
                                    {
                                        "taxonomy": "us-gaap",
                                        "concept": "OperatingIncomeLoss",
                                        "label": "Operating income",
                                        "unit": "USD",
                                        "records": [
                                            {
                                                "start": 0,
                                                "end": len(first),
                                                "exact_span": first,
                                            },
                                            {
                                                "start": len(first) + 1,
                                                "end": len(first) + len(second) + 1,
                                                "exact_span": second,
                                            },
                                        ],
                                    }
                                ]
                            },
                        },
                    ],
                }
            ],
        }

    def test_e1_accepts_a_long_complete_source_literal(self) -> None:
        literal = (
            "Management described a complete point in time operating record with "
            "revenue, expenses, cash flow, customer demand, delivery timing, and "
            "the reporting period needed to interpret each stated amount. "
        ) * 2
        response = {
            "signatures": [
                {
                    "case_ref": "case-001",
                    "observations": [
                        {
                            "summary": "The complete operating record was disclosed.",
                            "document_ref": "document-01",
                            "exact_span": literal,
                        }
                    ],
                    "evidence_gaps": [],
                }
            ]
        }
        caller = ScriptedRoleCaller([response])

        step = LLMSignalMiningModel(caller).extract_exploration(
            {
                "cases": [
                    {
                        "case_ref": "case-001",
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": literal,
                            }
                        ],
                    }
                ]
            }
        )

        self.assertGreater(len(literal), 240)
        self.assertEqual(step.value[0].observations[0].exact_span, literal)
        self.assertEqual(step.metadata["quarantined_observations"], {})

    def test_strict_aggregate_aliases_preserve_words_and_reuse_matchers(self) -> None:
        aliases = ("Future Holdings", "Business Systems", "Z", "Q2")
        text = "Future business plans target Gen Z in Q2. Future Holdings disclosed them."
        masked = core_module._mask_identity_values(text, aliases, expand_aliases=False)
        self.assertEqual(
            masked,
            "Future business plans target Gen Z in Q2. [MASKED_COMPANY] disclosed them.",
        )
        core_module._assert_identity_values_masked(masked, aliases, expand_aliases=False)
        evolution_runtime_module._scan_payload(
            masked, allow_outcomes=True, anonymous_aliases=aliases,
        )
        first = core_module._compiled_identity_aliases(aliases, expand_aliases=False)
        self.assertIs(
            first, core_module._compiled_identity_aliases(aliases, expand_aliases=False),
        )
        local = core_module._mask_identity_values("Future announced results.", aliases)
        self.assertIn("[MASKED_COMPANY]", local)

    def test_slow_identity_inventory_masks_distinctive_brands_only(self) -> None:
        cases = (
            SimpleNamespace(
                case_id="brand-one",
                company_id="issuer-one",
                basic_info={
                    "company_name": "Kinross Gold Corporation",
                    "ticker": "KGC",
                },
            ),
            SimpleNamespace(
                case_id="brand-two",
                company_id="issuer-two",
                basic_info={
                    "company_name": "Wynn Resorts Limited",
                    "ticker": "WYNN",
                },
            ),
            SimpleNamespace(
                case_id="ordinary-word",
                company_id="issuer-three",
                basic_info={"company_name": "Future Holdings", "ticker": "FUTR"},
            ),
            SimpleNamespace(
                case_id="suffix-only",
                company_id="issuer-four",
                basic_info={"company_name": "Holdings", "ticker": "HLDG"},
            ),
            SimpleNamespace(
                case_id="protocol-collision",
                company_id="issuer-five",
                basic_info={"company_name": "Ready Capital", "ticker": "RC"},
            ),
        )

        aggregate_guards = core_module._slow_role_identity_guard_inventory(cases)
        guards = core_module._scoped_slow_identity_guard_inventory(cases)
        masked = core_module._mask_identity_values(
            "Kinross and Wynn disclosed results. Future business remains open news.",
            guards,
            expand_aliases=False,
        )

        self.assertNotIn("Kinross", masked)
        self.assertNotIn("Wynn", masked)
        self.assertIn("Future business remains open news", masked)
        self.assertNotIn("Kinross", aggregate_guards)
        self.assertNotIn("Wynn", aggregate_guards)
        self.assertNotIn("Ready", guards)
        core_module._assert_identity_values_masked(
            {"canonical_rule_names": ["all_ready_issuers"]},
            guards,
            expand_aliases=False,
        )

    def test_signal_h1_v3_accepts_structured_no_hypothesis_with_open_demand(
        self,
    ) -> None:
        response = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "insufficient_retrieval_basis",
                "rationale": [
                    "Available source types do not expose the requested measurement."
                ],
                "need_refs": ["need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "repair_dependency",
                    "signal_refs": [],
                    "rationale": ["The requested source capability is unavailable."],
                }
            ],
        }
        caller = ScriptedRoleCaller([response])

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v3",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {
                    "hypothesis_limit": 1,
                    "evidence_lookback_days": 365,
                },
                "available_raw_source_types": ["news"],
                "capability_backlog": {
                    "signal_need_items": [
                        {"need_ref": "need-001", "need": "Estimate changes"}
                    ]
                },
            }
        )

        self.assertEqual(result.value, ())
        self.assertEqual(result.metadata["conclusion"], "no_testable_hypothesis")
        self.assertEqual(result.metadata["reason_code"], "insufficient_retrieval_basis")
        self.assertEqual(caller.stages, ["signal_mining_hypotheses"])

    def test_signal_h1_prompt_anchors_measurements_to_evidence_manifest(self) -> None:
        response = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "insufficient_retrieval_basis",
                "rationale": ["No manifest family supplies the requested input."],
                "need_refs": ["need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "repair_dependency",
                    "signal_refs": [],
                    "rationale": [
                        "Analyst price targets have no in-window source family."
                    ],
                }
            ],
        }
        caller = ScriptedRoleCaller([response])
        manifest = {
            "schema_version": "h1-measurable-evidence-manifest-v1",
            "cohort_case_count": 4,
            "structured_financial_concepts": [
                {
                    "taxonomy": "us-gaap",
                    "concept": "Revenues",
                    "source_display_name": "Revenues",
                    "unit": "USD",
                    "case_count": 4,
                    "cases_with_comparable_records": 3,
                }
            ],
            "pre_cutoff_price_series_cases": 4,
            "narrative_source_families": [
                {"source_type": "8-k", "case_count": 4}
            ],
            "coverage_note": "value-free coverage",
        }

        LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v3",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {
                    "hypothesis_limit": 1,
                    "evidence_lookback_days": 365,
                },
                "available_raw_source_types": ["news"],
                "measurable_evidence_manifest": manifest,
                "capability_backlog": {
                    "signal_need_items": [
                        {"need_ref": "need-001", "need": "Estimate changes"}
                    ]
                },
            }
        )

        system_prompt = str(caller.calls[0]["system_prompt"])
        self.assertIn("measurable_evidence_manifest", system_prompt)
        self.assertIn("latest-plus-comparable record pairs", system_prompt)
        payload = caller.calls[0]["payload"]
        self.assertEqual(
            payload["measurable_evidence_manifest"], manifest
        )

    def test_signal_h1_v3_covers_ordinary_and_fast_need_refs(self) -> None:
        need_refs = ["target_filing_events", "signal:price_momentum_126d:v1"]
        response = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "insufficient_retrieval_basis",
                "rationale": ["The remaining rows are dependency or coverage gaps."],
                "need_refs": ["need-002", "need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-002"],
                    "disposition": "repair_dependency",
                    "signal_refs": [],
                    "rationale": ["The filing provider returned no usable data."],
                },
                {
                    "need_refs": ["need-001"],
                    "disposition": "already_covered",
                    "signal_refs": ["price_momentum_126d:v1"],
                    "rationale": ["The stable Signal already defines the measure."],
                },
            ],
        }
        caller = ScriptedRoleCaller([response])

        result = LLMSignalMiningModel(caller).propose_hypotheses({
            "h1_contract_version": "signal-mining-hypothesis-v3",
            "hypothesis_slots": ["h1-c0001-s01"],
            "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
            "available_raw_source_types": ["8-k", "market_data"],
            "stable_signal_cards": [{"signal_ref": "price_momentum_126d:v1"}],
            "capability_backlog": {
                "items": [{"request_id": "target_filing_events"}],
                "signal_need_items": [
                    {"need_ref": "signal:price_momentum_126d:v1"}
                ],
            },
        })

        self.assertEqual(result.value, ())
        self.assertEqual(
            [
                ref
                for item in result.metadata["need_dispositions"]
                for ref in item["need_refs"]
            ],
            need_refs,
        )
        self.assertIn("items request_id", caller.calls[0]["system_prompt"])
        projected_backlog = caller.calls[0]["payload"]["capability_backlog"]
        self.assertEqual(
            projected_backlog["signal_need_items"][0]["need_ref"], "need-001"
        )
        self.assertEqual(projected_backlog["items"][0]["request_id"], "need-002")

    def test_signal_h1_v3_uses_runtime_identity_and_structured_measurement(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "conclusion": "hypotheses",
                    "hypotheses": [
                        {
                            "proposal_ref": "h1-c0007-s01",
                            "measurement": {
                                "observable": "Customer commitments converted to revenue",
                                "value_kind": "numeric",
                                "normalization": "ratio to opening backlog",
                            },
                            "applicability": {
                                "rule": "all_ready_issuers",
                                "values": [],
                            },
                            "expected_direction": "higher_in_positive",
                            "retrieval_intent": {
                                "source_types": ["10-q"],
                                "query": "contract awards backlog conversion",
                            },
                            "falsifiers": [
                                {
                                    "condition": "The measurement is extracted.",
                                    "expected_observation": (
                                        "The fixed groups overlap or reverse direction."
                                    ),
                                }
                            ],
                            "need_refs": [],
                        }
                    ],
                    "no_hypothesis": None,
                    "need_dispositions": [],
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v3",
                "hypothesis_slots": ["h1-c0007-s01"],
                "limits": {
                    "hypothesis_limit": 1,
                    "evidence_lookback_days": 540,
                },
                "available_raw_source_types": ["10-q"],
            }
        )

        hypothesis = result.value[0]
        self.assertEqual(hypothesis.hypothesis_id, "h1-c0007-s01")
        self.assertEqual(hypothesis.lookback_days, 540)
        self.assertEqual(hypothesis.expected_direction, "higher_in_positive")
        self.assertEqual(hypothesis.measurement["value_kind"], "numeric")
        self.assertNotIn("h1-c0007-s01", hypothesis.query)

    def test_signal_h1_v3_correction_preserves_valid_sibling_by_runtime_id(
        self,
    ) -> None:
        invalid_item = {
            "proposal_ref": "h1-c0008-s01",
            "measurement": {
                "observable": "New customer commitments",
                "value_kind": "numeric",
                "normalization": "ratio to opening backlog",
            },
            "applicability": {"rule": "all_ready_issuers", "values": []},
            "expected_direction": "higher_in_positive",
            "retrieval_intent": {
                "source_types": ["unavailable-source"],
                "query": "new customer commitments",
            },
            "falsifiers": [
                {
                    "condition": "The measurement is extracted.",
                    "expected_observation": "The fixed groups overlap.",
                }
            ],
            "need_refs": [],
        }
        valid_item = {
            "proposal_ref": "h1-c0008-s02",
            "measurement": {
                "observable": "Backlog converted to recognized revenue",
                "value_kind": "numeric",
                "normalization": "ratio to opening backlog",
            },
            "applicability": {"rule": "all_ready_issuers", "values": []},
            "expected_direction": "higher_in_positive",
            "retrieval_intent": {
                "source_types": ["10-q"],
                "query": "backlog revenue conversion",
            },
            "falsifiers": [
                {
                    "condition": "The measurement is extracted.",
                    "expected_observation": "The fixed groups overlap.",
                }
            ],
            "need_refs": [],
        }
        corrected_item = {
            **invalid_item,
            "retrieval_intent": {
                "source_types": ["10-q"],
                "query": "new customer commitments",
            },
        }
        drifted_valid_item = {
            **valid_item,
            "expected_direction": "lower_in_positive",
        }
        caller = ScriptedRoleCaller(
            [
                {
                    "conclusion": "hypotheses",
                    "hypotheses": [invalid_item, valid_item],
                    "no_hypothesis": None,
                    "need_dispositions": [],
                },
                {
                    "conclusion": "hypotheses",
                    "hypotheses": [drifted_valid_item, corrected_item],
                    "no_hypothesis": None,
                    "need_dispositions": [],
                },
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v3",
                "hypothesis_slots": ["h1-c0008-s01", "h1-c0008-s02"],
                "limits": {"hypothesis_limit": 2, "evidence_lookback_days": 365},
                "available_raw_source_types": ["10-q"],
            }
        )

        by_ref = {item.hypothesis_id: item for item in result.value}
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertEqual(
            by_ref["h1-c0008-s01"].source_types,
            ("10-q",),
        )
        self.assertEqual(
            by_ref["h1-c0008-s02"].expected_direction,
            valid_item["expected_direction"],
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligations"][0]["item_id"], "h1-c0008-s01")

    def test_signal_h1_v3_corrects_missing_need_disposition(self) -> None:
        base = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": ["The visible needs do not define another measurement."],
                "need_refs": ["need-001", "need-002"],
            },
        }
        incomplete = {
            **base,
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "already_covered",
                    "signal_refs": ["existing:v1"],
                    "rationale": ["The stable Signal already covers this need."],
                }
            ],
        }
        complete = {
            **base,
            "need_dispositions": [
                *incomplete["need_dispositions"],
                {
                    "need_refs": ["need-002"],
                    "disposition": "not_testable",
                    "signal_refs": [],
                    "rationale": ["The need does not define an observable measure."],
                },
            ],
        }
        caller = ScriptedRoleCaller([incomplete, complete])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v3",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
                "available_raw_source_types": ["news"],
                "stable_signal_cards": [{"signal_ref": "existing:v1"}],
                "capability_backlog": {
                    "signal_need_items": [
                        {"need_ref": "need-a", "need": "Covered need"},
                        {"need_ref": "need-b", "need": "Unmeasurable need"},
                    ]
                },
            }
        )

        self.assertEqual(step.usage.llm_calls, 2)
        self.assertEqual(caller.calls[0]["max_output_tokens"], 8_000)
        self.assertEqual(len(step.metadata["need_dispositions"]), 2)
        self.assertIn(
            "cover every runtime need alias exactly once",
            caller.calls[1]["payload"]["validation_feedback"]["validation_error"],
        )
        self.assertEqual(
            [
                ref
                for item in step.metadata["need_dispositions"]
                for ref in item["need_refs"]
            ],
            ["need-a", "need-b"],
        )

    def test_signal_h1_compacts_large_need_ledger_and_aggregates_repairs(self) -> None:
        original_refs = [f"original-long-need-ref-{index:03d}-{'x' * 40}" for index in range(145)]
        aliases = [f"need-{index:03d}" for index in range(1, 146)]
        malformed = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": ["No candidate was selected."],
                "need_refs": ["need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-001", "need-001", "need-999"],
                    "disposition": "new_measurement",
                    "signal_refs": [],
                    "rationale": ["A measurement direction appears possible."],
                }
            ],
        }
        corrected = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": ["The supplied needs do not define another measure."],
                "need_refs": ["need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": aliases,
                    "disposition": "not_testable",
                    "signal_refs": [],
                    "rationale": ["No distinct point-in-time measurement is defined."],
                }
            ],
        }
        caller = ScriptedRoleCaller([malformed, corrected])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v3",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
                "available_raw_source_types": ["news"],
                "capability_backlog": {
                    "signal_need_items": [
                        {"need_ref": ref, "need": f"Need {index}"}
                        for index, ref in enumerate(original_refs)
                    ]
                },
            }
        )

        sent_refs = [
            item["need_ref"]
            for item in caller.calls[0]["payload"]["capability_backlog"][
                "signal_need_items"
            ]
        ]
        self.assertEqual(sent_refs, aliases)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            {item["issue_code"] for item in feedback["obligations"]},
            {
                "h1_duplicate_need_refs_in_row",
                "h1_need_ledger_coverage_invalid",
                "h1_new_measurement_conclusion_conflict",
                "h1_unknown_need_refs",
            },
        )
        restored_refs = [
            ref
            for item in step.metadata["need_dispositions"]
            for ref in item["need_refs"]
        ]
        self.assertEqual(restored_refs, original_refs)
        self.assertEqual(
            step.metadata["need_ref_aliases"][-1],
            {"alias": "need-145", "need_ref": original_refs[-1]},
        )

    def test_signal_h1_rejects_withheld_case_context_as_empty_reason(self) -> None:
        invalid = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "insufficient_retrieval_basis",
                "rationale": [
                    "No case-level filing text is visible at H1, so no measure can be defined."
                ],
                "need_refs": ["need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "not_testable",
                    "signal_refs": [],
                    "rationale": ["The need cannot be operationalized without case text."],
                }
            ],
        }
        corrected = {
            "conclusion": "hypotheses",
            "hypotheses": [
                {
                    "proposal_ref": "h1-c0001-s01",
                    "measurement": {
                        "observable": "Cash runway in months",
                        "value_kind": "numeric",
                        "normalization": "cash balance divided by quarterly cash burn",
                    },
                    "applicability": {"rule": "all_ready_issuers", "values": []},
                    "expected_direction": "higher_in_positive",
                    "retrieval_intent": {
                        "source_types": ["company_facts"],
                        "query": "cash balance operating cash burn",
                    },
                    "falsifiers": [
                        {
                            "condition": "Cash runway is measured for fixed groups.",
                            "expected_observation": "The groups overlap or reverse direction.",
                        }
                    ],
                    "need_refs": ["need-001"],
                }
            ],
            "no_hypothesis": None,
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "new_measurement",
                    "signal_refs": [],
                    "rationale": ["Cash runway is a reusable point-in-time measurement."],
                }
            ],
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v3",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
                "available_raw_source_types": ["company_facts"],
                "capability_backlog": {
                    "signal_need_items": [
                        {
                            "need_ref": "original-cash-runway-need-ref",
                            "need": "Measure cash runway.",
                        }
                    ]
                },
            }
        )

        self.assertEqual(len(step.value), 1)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            {item["issue_code"] for item in feedback["obligations"]},
            {
                "h1_not_testable_uses_withheld_context",
                "h1_withheld_context_is_not_empty_reason",
            },
        )
        self.assertEqual(
            step.metadata["hypothesis_need_refs"]["h1-c0001-s01"],
            ["original-cash-runway-need-ref"],
        )

    def test_signal_h1_rejects_v55_absent_roster_phrase_with_empty_backlog(
        self,
    ) -> None:
        invalid = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": [
                    "No runtime need_ref was supplied, so the demand ledger is empty.",
                    (
                        "H1 candidate roster and source excerpts are absent, but "
                        "no backlog gap exists to motivate a new measurement."
                    ),
                ],
                "need_refs": [],
            },
            "need_dispositions": [],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["no_hypothesis"]["rationale"] = [
            invalid["no_hypothesis"]["rationale"][0]
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v7",
                "hypothesis_slots": [
                    "h1-c0001-s01",
                    "h1-c0001-s02",
                    "h1-c0001-s03",
                ],
                "limits": {"hypothesis_limit": 3, "evidence_lookback_days": 365},
                "available_raw_source_types": ["financials"],
                "capability_backlog": {"signal_need_items": [], "items": []},
            }
        )

        self.assertEqual(step.value, ())
        self.assertEqual(
            caller.calls[1]["payload"]["validation_feedback"]["obligations"][0][
                "issue_code"
            ],
            "h1_withheld_context_is_not_empty_reason",
        )

    def test_signal_h1_distinguishes_short_term_assets_from_future_outcomes(
        self,
    ) -> None:
        hypothesis = {
            "conclusion": "hypotheses",
            "hypotheses": [
                {
                    "proposal_ref": "h1-c0001-s01",
                    "measurement": {
                        "observable": (
                            "Presence in point-in-time filings of a disclosed "
                            "statement that cash, cash equivalents, and short-term "
                            "investments are sufficient to fund operations for at "
                            "least the next six months."
                        ),
                        "value_kind": "boolean",
                        "normalization": "none",
                    },
                    "applicability": {"rule": "all_ready_issuers", "values": []},
                    "expected_direction": "more_frequent_in_positive",
                    "retrieval_intent": {
                        "source_types": ["filing"],
                        "query": "cash equivalents short-term investments runway",
                    },
                    "falsifiers": [
                        {
                            "condition": (
                                "Point-in-time filings contain no disclosed "
                                "short-term investments or cash-runway statement."
                            ),
                            "expected_observation": (
                                "The boolean is not more frequent in the fixed "
                                "positive group than in the fixed control group."
                            ),
                        }
                    ],
                    "need_refs": ["need-001"],
                }
            ],
            "no_hypothesis": None,
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "new_measurement",
                    "signal_refs": [],
                    "rationale": ["Cash runway is a point-in-time source measure."],
                }
            ],
        }
        payload = {
            "h1_contract_version": "signal-mining-hypothesis-v3",
            "hypothesis_slots": ["h1-c0001-s01"],
            "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
            "available_raw_source_types": ["filing"],
            "capability_backlog": {
                "signal_need_items": [
                    {"need_ref": "cash-runway-need", "need": "Measure runway."}
                ]
            },
        }
        caller = ScriptedRoleCaller([hypothesis])

        step = LLMSignalMiningModel(caller).propose_hypotheses(payload)

        self.assertEqual(len(step.value), 1)
        self.assertEqual(len(caller.calls), 1)

        for observable in (
            "Latest disclosed remaining performance obligations expected to convert "
            "within the next 12 months / trailing twelve-month revenue before prediction time.",
            "Cash / trailing one-year operating burn from filings available before prediction time.",
            "Use a measurement threshold of 2 for trailing three-month order coverage.",
            "Trailing one-year stock returns and price movement before prediction time.",
            "Short-term market reaction within 30 days before the prediction time.",
        ):
            with self.subTest(observable=observable):
                historical = json.loads(json.dumps(hypothesis))
                historical["hypotheses"][0]["measurement"]["observable"] = observable
                parsed = LLMSignalMiningModel(
                    ScriptedRoleCaller([historical])
                ).propose_hypotheses(payload)
                self.assertEqual(len(parsed.value), 1)

        for condition in (
            "All supporting facts are only available after prediction time.",
            "Only post-cutoff sources contain the required measurement.",
            "The evidence was disclosed subsequent to the cutoff.",
        ):
            with self.subTest(condition=condition):
                valid_falsifier = json.loads(json.dumps(hypothesis))
                valid_falsifier["hypotheses"][0]["falsifiers"][0]["condition"] = condition
                parsed = LLMSignalMiningModel(
                    ScriptedRoleCaller([valid_falsifier])
                ).propose_hypotheses(payload)
                self.assertEqual(len(parsed.value), 1)

        for observable in (
            "Change the fixed prediction threshold to 0.8.",
            "Redefine surge labels using a shorter horizon.",
            "Measure realized revenue growth over the next two quarters.",
        ):
            with self.subTest(observable=observable):
                invalid = json.loads(json.dumps(hypothesis))
                invalid["hypotheses"][0]["measurement"]["observable"] = observable
                with self.assertRaisesRegex(ValidationError, "fixed outcome semantics"):
                    LLMSignalMiningModel(
                        ScriptedRoleCaller([invalid, invalid, invalid])
                    ).propose_hypotheses(payload)

        combined = json.loads(json.dumps(hypothesis))
        combined["hypotheses"][0]["measurement"]["observable"] = (
            "Change the fixed prediction threshold to 0.8."
        )
        combined["need_dispositions"][0]["disposition"] = "update_existing"
        combined["need_dispositions"][0]["signal_refs"] = ["unknown:v1"]
        combined_caller = ScriptedRoleCaller([combined, hypothesis])
        self.assertEqual(len(LLMSignalMiningModel(combined_caller).propose_hypotheses(payload).value), 1)
        codes = {
            issue["issue_code"] for issue in combined_caller.calls[1]["payload"][
                "validation_feedback"
            ]["obligations"]
        }
        self.assertIn("h1_fixed_target_redefinition", codes)
        self.assertGreater(len(codes), 1)

        future_outcome = json.loads(json.dumps(hypothesis))
        future_outcome["hypotheses"][0]["measurement"]["observable"] = (
            "Short-term stock returns over the next six months."
        )
        with self.assertRaisesRegex(
            ValidationError,
            "cannot redefine fixed outcome semantics",
        ):
            LLMSignalMiningModel(
                ScriptedRoleCaller([future_outcome, future_outcome, future_outcome])
            ).propose_hypotheses(payload)

    def test_signal_h1_corrects_post_cutoff_source_and_exact_need_union(self) -> None:
        hypothesis = {
            "proposal_ref": "h1-c0001-s01",
            "measurement": {
                "observable": "Financing action after the prediction date",
                "value_kind": "boolean",
                "normalization": "none",
            },
            "applicability": {"rule": "all_ready_issuers", "values": []},
            "expected_direction": "more_frequent_in_positive",
            "retrieval_intent": {
                "source_types": ["filing"],
                "query": "financing action after prediction date",
            },
            "falsifiers": [
                {
                    "condition": "The action is absent after prediction date.",
                    "expected_observation": "The fixed groups overlap.",
                }
            ],
            "need_refs": ["need-001"],
        }
        invalid = {
            "conclusion": "hypotheses",
            "hypotheses": [hypothesis],
            "no_hypothesis": None,
            "need_dispositions": [
                {
                    "need_refs": ["need-001", "need-002"],
                    "disposition": "new_measurement",
                    "signal_refs": [],
                    "rationale": ["A financing measure may be testable."],
                }
            ],
        }
        corrected_hypothesis = json.loads(json.dumps(hypothesis))
        corrected_hypothesis["measurement"]["observable"] = (
            "Financing action disclosed by the prediction date"
        )
        corrected_hypothesis["retrieval_intent"]["query"] = (
            "financing action disclosed by prediction date"
        )
        corrected_hypothesis["falsifiers"][0]["condition"] = (
            "No financing action is disclosed by the prediction date."
        )
        corrected = {
            **invalid,
            "hypotheses": [corrected_hypothesis],
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "new_measurement",
                    "signal_refs": [],
                    "rationale": ["A financing measure is testable."],
                },
                {
                    "need_refs": ["need-002"],
                    "disposition": "not_testable",
                    "signal_refs": [],
                    "rationale": ["This need defines no reusable observation."],
                },
            ],
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v3",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
                "available_raw_source_types": ["filing"],
                "capability_backlog": {
                    "signal_need_items": [
                        {"need_ref": "first-need", "need": "Measure financing."},
                        {"need_ref": "second-need", "need": "Policy-only request."},
                    ]
                },
            }
        )

        self.assertEqual(len(step.value), 1)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        by_code = {item["issue_code"]: item for item in feedback["obligations"]}
        self.assertIn("h1_post_cutoff_source_invalid", by_code)
        mismatch = by_code["h1_hypothesis_need_refs_mismatch"]
        self.assertEqual(
            mismatch["ledger_only_new_measurement_refs"],
            ["need-002"],
        )
        self.assertEqual(
            mismatch["hypothesis_only_need_refs"], []
        )

    def test_signal_h1_v3_oversized_request_is_local_zero_call_failure(self) -> None:
        class OversizedCaller(ScriptedRoleCaller):
            def estimate_json_request_tokens(self, **_kwargs):
                return 20_001

        caller = OversizedCaller([])
        model = LLMSignalMiningModel(caller)
        model.set_request_token_budget(20_000)

        with self.assertRaisesRegex(
            CandidateExecutionRejected, "complete H1 search context"
        ) as raised:
            model.propose_hypotheses(
                {
                    "h1_contract_version": "signal-mining-hypothesis-v3",
                    "hypothesis_slots": ["h1-c0001-s01"],
                    "limits": {
                        "hypothesis_limit": 1,
                        "evidence_lookback_days": 365,
                    },
                    "available_raw_source_types": ["news"],
                    "capability_backlog": {"signal_need_items": []},
                }
            )

        self.assertEqual(caller.calls, [])
        self.assertEqual(raised.exception.usage, AgentUsage())
        self.assertEqual(
            raised.exception.details["failure_kind"], "role_request_too_large"
        )

    def test_signal_h2_enforces_bounded_unpadded_shortlist_and_allows_empty(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "mining_operations",
                            "cases": [
                                {
                                    "case_ref": case_ref,
                                    "profile_evidence": "irrelevant",
                                    "applicability_reason": "irrelevant",
                                }
                                for case_ref in ("case-001", "case-002", "case-003")
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "mining_operations",
                            "cases": [],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "mining_operations"}],
                "case_briefs": [
                    {"case_ref": "case-001"},
                    {"case_ref": "case-002"},
                    {"case_ref": "case-003"},
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["mining_operations"], ())
        self.assertIn("exceeds", validation_error(caller.calls[1]))
        self.assertEqual(
            caller.stages,
            [
                "signal_mining_case_ranking",
                "signal_mining_case_ranking_correction",
            ],
        )

    def test_signal_h2_rejects_empty_when_canonical_visible_rule_matches(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {"hypothesis_id": "broad_estimates", "cases": []}
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "broad_estimates",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "aerospace services",
                                    "applicability_reason": (
                                        "The canonical rule covers every ready issuer."
                                    ),
                                }
                            ],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [
                    {
                        "hypothesis_id": "broad_estimates",
                        "applicability": "all_ready_issuers",
                    }
                ],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "aerospace services",
                    }
                ],
                "rules": {"max_case_refs_per_hypothesis": 1},
            }
        )

        self.assertEqual(result.value["broad_estimates"], ("case-001",))
        self.assertIn(
            "cannot return an empty ranking",
            validation_error(caller.calls[1]),
        )

    def test_signal_h2_rejects_case_outside_canonical_visible_rule(self) -> None:
        def ranking(case_ref: str, evidence: str) -> dict[str, object]:
            return {
                "rankings": [
                    {
                        "hypothesis_id": "exchange_screen",
                        "cases": [
                            {
                                "case_ref": case_ref,
                                "profile_evidence": evidence,
                                "applicability_reason": (
                                    "The visible exchange satisfies the canonical rule."
                                ),
                            }
                        ],
                    }
                ]
            }

        caller = ScriptedRoleCaller(
            [ranking("case-002", "NASDAQ"), ranking("case-001", "NYSE")]
        )
        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [
                    {
                        "hypothesis_id": "exchange_screen",
                        "applicability": "exchange_values:NYSE",
                    }
                ],
                "case_briefs": [
                    {"case_ref": "case-001", "exchange": "NYSE"},
                    {"case_ref": "case-002", "exchange": "NASDAQ"},
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["exchange_screen"], ("case-001",))
        self.assertIn(
            "must satisfy the canonical visible applicability rule",
            validation_error(caller.calls[1]),
        )

    def test_signal_h2_requires_literal_profile_evidence_for_each_case(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "production_guidance",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "operates gold mines",
                                    "applicability_reason": (
                                        "A mine operator can report production guidance."
                                    ),
                                }
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "production_guidance",
                            "cases": [],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "production_guidance"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "Provides aviation repair services.",
                    }
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["production_guidance"], ())
        self.assertIn("exact contiguous span", validation_error(caller.calls[1]))

    def test_signal_h2_rejects_self_disqualifying_reason_with_stable_feedback(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "expanded service offerings",
                                    "applicability_reason": (
                                        "The profile mentions growth, but no analyst "
                                        "estimate data are provided and the evidence is "
                                        "too generic to confirm applicability."
                                    ),
                                }
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "estimate_gap"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "expanded service offerings",
                    }
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["estimate_gap"], ())
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        self.assertIn(
            "cannot disclaim applicability", validation_error(caller.calls[1])
        )
        prompt = str(caller.calls[0]["system_prompt"])
        self.assertIn("1-160 characters", prompt)
        self.assertIn("1-240 characters", prompt)
        self.assertNotIn("project-driven engineering services", prompt)

    def test_signal_h2_aggregates_inference_and_span_errors_without_echo(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "AI platform leadership",
                                    "applicability_reason": (
                                        "AI platform leadership suggests likely analyst "
                                        "coverage."
                                    ),
                                },
                                {
                                    "case_ref": "case-002",
                                    "profile_evidence": "analyst estimates",
                                    "applicability_reason": (
                                        "The profile lacks visible estimates and cannot "
                                        "confirm applicability."
                                    ),
                                },
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [],
                        }
                    ]
                },
            ]
        )
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(("AI",))

        result = model.rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "estimate_gap"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "AI platform leadership",
                    },
                    {
                        "case_ref": "case-002",
                        "business_description": "expanded service offerings",
                    },
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["estimate_gap"], ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        error = feedback["validation_error"]
        self.assertIn("must not infer missing profile facts", error)
        self.assertIn("cannot disclaim applicability", error)
        self.assertIn("exact contiguous span", error)
        self.assertNotIn("identity alias leaked", error)

    def test_identity_guard_requires_context_for_two_character_ticker(self) -> None:
        evolution_runtime_module._scan_payload(
            {"summary": "AI platform leadership"},
            allow_outcomes=True,
            anonymous_aliases=("AI",),
        )

        for value in ("ticker AI", "$AI", "NASDAQ: AI"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValidationError, "identity alias leaked"
            ):
                evolution_runtime_module._scan_payload(
                    {"summary": value},
                    allow_outcomes=True,
                    anonymous_aliases=("AI",),
                )

    def test_short_ticker_masking_and_guard_preserve_ordinary_research_text(self) -> None:
        aliases = ("Z", "Q2", "AI", "Q2 Holdings")
        ordinary = {"summary": "Gen Z engagement and Q2 revenue from AI services."}
        masked = core_module._mask_identity_values(ordinary, aliases)
        self.assertEqual(masked, ordinary)
        evolution_runtime_module._scan_payload(
            masked, allow_outcomes=True, anonymous_aliases=aliases,
        )
        url = "https://example.com/quote/Z"
        with self.assertRaises(ValidationError):
            core_module._assert_identity_values_masked(url, aliases)
        masked_url = core_module._mask_identity_values(url, aliases)
        self.assertIn("[MASKED_COMPANY]", masked_url)
        core_module._assert_identity_values_masked(masked_url, aliases)
        for text in ("$Z", "ticker Z", "NYSE: Z", "$Q2", "symbol AI", "Q2 Holdings"):
            with self.subTest(text=text):
                with self.assertRaises(ValidationError):
                    evolution_runtime_module._scan_payload(
                        text, allow_outcomes=True, anonymous_aliases=aliases,
                    )
                masked = core_module._mask_identity_values(text, aliases)
                self.assertIn("[MASKED_COMPANY]", masked)
                evolution_runtime_module._scan_payload(
                    masked, allow_outcomes=True, anonymous_aliases=aliases,
                )

    def test_signal_h2_malformed_text_feedback_does_not_echo_raw_output(self) -> None:
        class MalformedThenValidCaller(ScriptedRoleCaller):
            def complete_json(self, **kwargs):
                self.stages.append(str(kwargs["stage"]))
                self.calls.append(dict(kwargs))
                if len(self.calls) == 1:
                    raise StructuredOutputInvalid(
                        "provider returned invalid structured output: Extra data",
                        '{"rankings":[]} Vornado Realty Trust',
                        AgentUsage(llm_calls=1, tokens=5, cost=0.01),
                    )
                return self.outputs.pop(0), AgentUsage(
                    llm_calls=1, tokens=5, cost=0.01
                )

        caller = MalformedThenValidCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [],
                        }
                    ]
                }
            ]
        )
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(("Vornado Realty Trust",))

        result = model.rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "estimate_gap"}],
                "case_briefs": [{"case_ref": "case-001"}],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["estimate_gap"], ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        self.assertIn("Extra data", feedback["validation_error"])
        self.assertNotIn("identity alias", feedback["validation_error"])
        self.assertNotIn("Vornado", json.dumps(caller.calls[1]["payload"]))

    def test_signal_h3_repairs_missing_evidence_rejection_to_inconclusive(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "decisions": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "disposition": "rejected",
                            "rationale": [
                                "The packets do not contain analyst estimate data."
                            ],
                            "candidate": None,
                        }
                    ]
                },
                {
                    "decisions": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "disposition": "inconclusive",
                            "rationale": [
                                "The packets do not contain analyst estimate data."
                            ],
                            "candidate": None,
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).contrast(
            {
                "comparisons": [
                    {
                        "hypothesis": {"hypothesis_id": "estimate_gap"},
                        "evidence_packets": [
                            {
                                "packet_ref": "packet-positive",
                                "label": "positive",
                                "query_match_status": "matched",
                            },
                            {
                                "packet_ref": "packet-control",
                                "label": "control",
                                "query_match_status": "matched",
                            },
                        ],
                    }
                ],
                "rules": {
                    "decisions": [
                        "supported",
                        "refine",
                        "rejected",
                        "inconclusive",
                    ]
                },
            }
        )

        self.assertEqual(result.value[0].disposition, "inconclusive")
        self.assertIn(
            "evidence absence must use inconclusive",
            validation_error(caller.calls[1]),
        )
        self.assertEqual(
            result.value[0].sample_basis,
            {
                "positive_refs": ("packet-positive",),
                "control_refs": ("packet-control",),
            },
        )

    def test_signal_h2_trusts_case_local_masking_without_global_alias_rescan(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "operating_profile",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "leases commercial properties",
                                    "applicability_reason": (
                                        "The profile identifies an externally managed REIT."
                                    ),
                                },
                                {
                                    "case_ref": "case-002",
                                    "profile_evidence": "drug candidate",
                                    "applicability_reason": (
                                        "The profile identifies a clinical-stage drug developer."
                                    ),
                                },
                            ],
                        }
                    ]
                }
            ]
        )
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(
            ("Vornado Realty Trust", "VNO", "LX")
        )

        result = model.rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "operating_profile"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": (
                            "The masked target is managed by Vornado Realty Trust "
                            "(NYSE: VNO) and leases commercial properties."
                        ),
                    },
                    {
                        "case_ref": "case-002",
                        "business_description": (
                            "The masked target develops the LX 9211 drug candidate."
                        ),
                    },
                ],
            }
        )

        self.assertEqual(
            result.value["operating_profile"],
            ("case-001", "case-002"),
        )
        self.assertEqual(caller.calls[0]["anonymous_aliases"], ())

    def test_plan_proposer_repairs_malformed_provider_json_once(self) -> None:
        class MalformedThenValidCaller:
            def __init__(self) -> None:
                self.stages: list[str] = []

            def complete_json(self, **kwargs):
                self.stages.append(str(kwargs["stage"]))
                if len(self.stages) == 1:
                    raise StructuredOutputInvalid(
                        "provider returned two JSON objects",
                        '{"B":{}}\n{"extra":true}',
                        AgentUsage(llm_calls=1, tokens=20, cost=0.01),
                    )
                return (
                    {
                        "used_experience_refs": [],
                        "B": {
                            "requests": [
                                dict(make_orientation_request("scoped_news", max_documents=5).to_dict()),
                                dict(make_orientation_request("market_backbone", max_documents=1).to_dict())
                            ]
                        },
                        "H_init": (
                            "Form an initial source-backed hypothesis and list "
                            "unresolved information needs."
                        ),
                        "H_reflect": (
                            "Reflect over all returned Signal evidence, then continue "
                            "for the next need or finalize."
                        ),
                        "H_analyse": (
                            "Organize and weigh supporting and counter evidence while "
                            "preserving uncertainty."
                        ),
                    },
                    AgentUsage(llm_calls=1, tokens=20, cost=0.01),
                )

        caller = MalformedThenValidCaller()
        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=3,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed prior",
        )

        self.assertEqual(plan.plan_id, "plan_r0001_c01")
        self.assertEqual(
            caller.stages,
            ["information_plan_propose", "information_plan_propose_correction"],
        )

    def test_plan_proposer_corrects_missing_market_backbone(self) -> None:
        missing = {
            "used_experience_refs": [],
            "B": {
                "requests": [
                    dict(make_orientation_request("scoped_news", max_documents=5).to_dict())
                ]
            },
            "H_init": (
                "Form an initial source-backed hypothesis and list unresolved "
                "information needs."
            ),
            "H_reflect": (
                "Reflect over all returned Signal evidence, then continue for the "
                "next need or finalize."
            ),
            "H_analyse": (
                "Organize and weigh supporting and counter evidence while preserving "
                "uncertainty."
            ),
        }
        corrected = json.loads(json.dumps(missing))
        corrected["B"]["requests"].append(
            dict(make_orientation_request("market_backbone", max_documents=1).to_dict())
        )
        caller = ScriptedRoleCaller([missing, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(
            plan.basic_info_policy.requests[-1].request_id,
            "orientation.v1.market_backbone",
        )
        self.assertEqual(
            [call["stage"] for call in caller.calls],
            ["information_plan_propose", "information_plan_propose_correction"],
        )
        self.assertIn("market_data", str(caller.calls[0]["system_prompt"]))

    def test_v91_plan_proposer_confines_query_correction_scope(self) -> None:
        invalid = {
            "used_experience_refs": [],
            "B": {
                "requests": [
                    dict(make_orientation_request("scoped_news", max_documents=5).to_dict()),
                    dict(make_orientation_request("market_backbone", max_documents=1).to_dict(), query=7),
                ]
            },
            "H_init": (
                "Form a source-backed commercialization hypothesis and list "
                "unresolved information needs."
            ),
            "H_reflect": (
                "Update beliefs from all Signal evidence, then continue for the "
                "next need or finalize."
            ),
            "H_analyse": (
                "Organize and weigh supporting and counter evidence while exposing "
                "uncertainty."
            ),
        }
        minimally_corrected = json.loads(json.dumps(invalid))
        del minimally_corrected["B"]["requests"][1]["query"]
        drifted = json.loads(json.dumps(minimally_corrected))
        drifted["H_init"] += " Compare management strategy with market signals."

        with self.assertRaisesRegex(
            CandidateProposalRejected,
            "outside typed authority",
        ):
            LLMInformationPlanProposer(
                ScriptedRoleCaller([invalid, drifted])
            ).propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(default_information_plan(),),
                meta_info=(),
                prior="fixed H_P",
            )

        deleted_request = json.loads(json.dumps(invalid))
        deleted_request["B"]["requests"].pop(1)
        with self.assertRaisesRegex(
            CandidateProposalRejected,
            "outside typed authority",
        ):
            LLMInformationPlanProposer(
                ScriptedRoleCaller([invalid, deleted_request])
            ).propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(default_information_plan(),),
                meta_info=(),
                prior="fixed H_P",
            )

        caller = ScriptedRoleCaller([invalid, minimally_corrected])
        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertIsNone(plan.basic_info_policy.requests[1].query)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["obligations"][0]["must_change_paths"],
            ["B.requests[1].query"],
        )
        self.assertIn("preserve every unmentioned", caller.calls[0]["system_prompt"])

    def test_v91_plan_proposer_omits_empty_optional_query_without_call(self) -> None:
        output = {
            "used_experience_refs": [],
            "B": {
                "requests": [
                    dict(make_orientation_request("market_backbone", max_documents=1).to_dict(), query='')
                ]
            },
            "H_init": (
                "Form a source-backed commercialization hypothesis and list "
                "unresolved information needs."
            ),
            "H_reflect": (
                "Update beliefs from all Signal evidence, then continue for the "
                "next need or finalize."
            ),
            "H_analyse": (
                "Organize and weigh supporting and counter evidence while exposing "
                "uncertainty."
            ),
        }
        caller = ScriptedRoleCaller([output])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertIsNone(plan.basic_info_policy.requests[0].query)
        self.assertEqual(caller.stages, ["information_plan_propose"])

    def test_v81_plan_proposer_corrects_cross_issuer_request_scope(self) -> None:
        invalid = {
            "used_experience_refs": [],
            "B": {
                "requests": [
                    make_orientation_request("operating_report").to_dict(),
                    dict(make_orientation_request("market_backbone", max_documents=1).to_dict()),
                    dict(make_orientation_request("scoped_news", max_documents=3).to_dict(), description="Competitor actions that could affect the company's market position."),
                ]
            },
            "H_init": (
                "Form an initial source-backed hypothesis and list unresolved "
                "information needs."
            ),
            "H_reflect": (
                "Reflect over all returned Signal evidence, then continue for the "
                "next need or finalize."
            ),
            "H_analyse": (
                "Organize and weigh supporting and counter evidence while preserving "
                "uncertainty."
            ),
        }
        corrected = json.loads(json.dumps(invalid))
        corrected_request = corrected["B"]["requests"][2]
        corrected_request["description"] = make_orientation_request("scoped_news").description
        caller = ScriptedRoleCaller([invalid, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        error = caller.calls[1]["payload"]["validation_feedback"][
            "validation_error"
        ]
        self.assertIn("B.requests[2].description", error)
        self.assertIn("target-company-scoped Basic Info resolver", error)
        self.assertIn("target company_id", caller.calls[0]["system_prompt"])
        self.assertEqual(
            plan.basic_info_policy.requests[2].description,
            corrected_request["description"],
        )

    def test_plan_skill_validation_rejects_generic_placeholder(self) -> None:
        plan = default_information_plan()
        placeholder = InformationPlan(
            plan_id="placeholder_plan",
            parent_ids=(),
            basic_info_policy=plan.basic_info_policy,
            initial_research_skill="Complete initialization instructions.",
            reflection_skill=plan.reflection_skill,
            analysis_prompt=plan.analysis_prompt,
        )

        with self.assertRaisesRegex(ValidationError, "generic placeholder"):
            evolution_runtime_module._validate_proposed_plan_skills(placeholder)

    def test_default_information_plan_has_compact_market_backbone(self) -> None:
        plan = default_information_plan()
        request = plan.basic_info_policy.requests[-1]

        self.assertEqual(request.source_types, ("market_data",))
        self.assertEqual(request.lookback_days, 45)
        self.assertEqual(request.max_documents, 1)
        model_catalog = set(
            evolution_runtime_module._model_available_source_types(
                ("filing", "financials", "market_data", "news")
            )
        )
        self.assertTrue(
            {
                source_type
                for item in plan.basic_info_policy.requests
                for source_type in item.source_types
            }.issubset(model_catalog)
        )
        self.assertIn("10-k", model_catalog)
        self.assertIn("sec_company_facts", model_catalog)
        self.assertNotIn("earnings_call", model_catalog)

    def test_signal_update_v2_rejects_label_as_fact_and_keeps_source_verdict_first(
        self,
    ) -> None:
        base = {
            "signal_ref": "financing_listing_action:v1",
            "disposition": "defer",
            "problem_type": "routing_applicability_unclear",
            "rationale": ["The source verdict is insufficient for update-case-001."],
            "changed_paths": [],
            "candidate": None,
        }
        invalid = {
            **base,
            "case_diagnostics": [
                {
                    "case_ref": "update-case-001",
                    "evidence_verdict": "supported",
                    "facts": [
                        {
                            "claim": "The positive label proves financing occurred.",
                            "document_ref": "document-01",
                            "exact_span": "positive label",
                        }
                    ],
                    "evidence_gaps": [],
                    "outcome_relation": "aligned",
                    "outcome_explanation": "The supplied label is positive.",
                }
            ],
        }
        corrected = {
            **base,
            "case_diagnostics": [
                {
                    "case_ref": "update-case-001",
                    "evidence_verdict": "insufficient",
                    "facts": [],
                    "evidence_gaps": ["No transaction terms are visible."],
                    "outcome_relation": "not_assessable",
                    "outcome_explanation": (
                        "The outcome cannot establish a missing source fact."
                    ),
                }
            ],
        }
        caller = ScriptedRoleCaller([invalid, corrected])
        payload = {
            "update_contract_version": "signal-update-decision-v2",
            "target": {"signal_ref": base["signal_ref"]},
            "induction_cases": [
                {
                    "case_ref": "update-case-001",
                    "evidence_observation": {
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": (
                                    "The issuer discussed general corporate liquidity."
                                ),
                            }
                        ]
                    },
                    "outcome_relation": {
                        "label": "positive",
                        "current_signal_relation": "not_assessable",
                    },
                }
            ],
        }

        result = LLMSignalUpdateModel(caller).update(payload)

        self.assertEqual(result.value.case_diagnostics, tuple(corrected["case_diagnostics"]))
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertIn("source-cited literal facts", validation_error(caller.calls[1]))
        self.assertIn("label cannot establish", caller.calls[0]["system_prompt"])

    def test_signal_update_preserves_long_source_literals_without_correction(self) -> None:
        literal = "Management reaffirmed the disclosed annual outlook. " * 20
        output = {
            "signal_ref": "guidance_acceleration:v1",
            "disposition": "defer",
            "problem_type": "insufficient_evidence",
            "rationale": ["A reaffirmation alone does not show acceleration."],
            "changed_paths": [],
            "candidate": None,
            "case_diagnostics": [{
                "case_ref": "update-case-001",
                "evidence_verdict": "insufficient",
                "facts": [{"document_ref": "document-01", "exact_span": literal}],
                "evidence_gaps": ["No comparable prior outlook is supplied."],
                "outcome_relation": "not_assessable",
                "outcome_explanation": "No directional result is available.",
            }],
        }
        caller = ScriptedRoleCaller([output])
        payload = {
            "target": {"signal_ref": output["signal_ref"]},
            "induction_cases": [{
                "case_ref": "update-case-001",
                "evidence_observation": {"executed_evidence": [{
                    "document_ref": "document-01", "exact_span": literal,
                }]},
                "outcome_relation": {"current_signal_relation": "not_assessable"},
            }],
        }

        result = LLMSignalUpdateModel(caller).update(payload)

        self.assertEqual(result.value.case_diagnostics, tuple(output["case_diagnostics"]))
        self.assertEqual(result.usage.llm_calls, 1)

    def test_update_compact_source_refs_restore_exact_html_without_clipping(self) -> None:
        literal = '<span style="' + ('padding-left:1px;' * 700) + '">Revenue 72% in 2024.</span>'
        payload = {
            "target": {"signal_ref": "customer_concentration:v1"},
            "induction_cases": [{
                "case_ref": "update-case-001",
                "evidence_observation": {"executed_evidence": [{
                    "document_ref": "document-01", "exact_span": literal,
                }]},
                "outcome_relation": {"current_signal_relation": "not_assessable"},
            }],
        }
        original = deepcopy(payload)
        wire_output = {}

        def response(call):
            source = call["payload"]["induction_cases"][0]["evidence_observation"]["executed_evidence"][0]
            self.assertEqual(source["exact_span"], "Revenue 72% in 2024.")
            self.assertEqual(source["source_span_raw_chars"], len(literal))
            wire_output.update({
                "signal_ref": "customer_concentration:v1", "disposition": "defer",
                "problem_type": "insufficient_evidence", "rationale": ["No comparable period."],
                "changed_paths": [], "candidate": None,
                "case_diagnostics": [{
                    "case_ref": "update-case-001", "evidence_verdict": "insufficient",
                    "facts": [{"document_ref": "document-01", "source_span_ref": source["source_span_ref"]}],
                    "evidence_gaps": ["Only one period is available."],
                    "outcome_relation": "not_assessable", "outcome_explanation": "No result.",
                }],
            })
            return wire_output

        caller = ScriptedRoleCaller([response])
        result = LLMSignalUpdateModel(caller).update(payload)
        self.assertEqual(result.value.case_diagnostics[0]["facts"], [
            {"document_ref": "document-01", "exact_span": literal},
        ])
        self.assertEqual(payload, original)
        self.assertNotIn("exact_span", wire_output["case_diagnostics"][0]["facts"][0])
        self.assertEqual(result.usage.llm_calls, 1)

    def test_update_source_refs_reject_cross_case_document_unknown_and_mixed_forms(self) -> None:
        payload = {
            "target": {"signal_ref": "guidance_acceleration:v1"},
            "induction_cases": [{
                "case_ref": f"update-case-{index:03d}",
                "evidence_observation": {"executed_evidence": [{
                    "document_ref": "document-01", "exact_span": "The outlook is unchanged.",
                }]},
                "outcome_relation": {"current_signal_relation": "not_assessable"},
            } for index in (1, 2)],
        }
        for variant in ("cross_case", "wrong_document", "unknown", "mixed"):
            with self.subTest(variant=variant):
                good = {}

                def first(call):
                    packets = call["payload"]["induction_cases"]
                    rows = [{
                        "case_ref": packet["case_ref"], "evidence_verdict": "insufficient",
                        "facts": [{"document_ref": "document-01", "source_span_ref":
                                   packet["evidence_observation"]["executed_evidence"][0]["source_span_ref"]}],
                        "evidence_gaps": ["No comparable outlook."],
                        "outcome_relation": "not_assessable", "outcome_explanation": "No result.",
                    } for packet in packets]
                    good.update({"signal_ref": "guidance_acceleration:v1", "disposition": "defer",
                                 "problem_type": "insufficient_evidence", "rationale": ["Wait for comparable outlook."],
                                 "changed_paths": [], "candidate": None, "case_diagnostics": rows})
                    bad = deepcopy(good)
                    fact = bad["case_diagnostics"][0]["facts"][0]
                    if variant == "cross_case":
                        fact["source_span_ref"] = rows[1]["facts"][0]["source_span_ref"]
                    elif variant == "wrong_document":
                        fact["document_ref"] = "document-02"
                    elif variant == "unknown":
                        fact["source_span_ref"] = "not-issued"
                    else:
                        fact["exact_span"] = "The outlook is unchanged."
                    return bad

                caller = ScriptedRoleCaller([first, lambda _call: good])
                result = LLMSignalUpdateModel(caller).update(payload)
                self.assertEqual(result.usage.llm_calls, 2)
                self.assertIn("source_span_ref", validation_error(caller.calls[1]))
                self.assertEqual(result.value.case_diagnostics[1]["facts"], [{
                    "document_ref": "document-01", "exact_span": "The outlook is unchanged.",
                }])

    def test_signal_update_v2_adds_missing_case_without_rewriting_valid_sibling(
        self,
    ) -> None:
        base = {
            "signal_ref": "guidance_acceleration:v1",
            "disposition": "defer",
            "problem_type": "insufficient_case_evidence",
            "rationale": ["Both cases require source-grounded observations."],
            "changed_paths": [],
            "candidate": None,
        }
        valid_first = {
            "case_ref": "update-case-001",
            "evidence_verdict": "insufficient",
            "facts": [],
            "evidence_gaps": ["No guidance statement is visible."],
            "outcome_relation": "not_assessable",
            "outcome_explanation": "No source fact can be associated with the label.",
        }
        missing_second = {
            "case_ref": "update-case-002",
            "evidence_verdict": "insufficient",
            "facts": [],
            "evidence_gaps": ["No guidance statement is visible."],
            "outcome_relation": "not_assessable",
            "outcome_explanation": "No source fact can be associated with the label.",
        }
        caller = ScriptedRoleCaller(
            [
                {**base, "case_diagnostics": [valid_first]},
                lambda kwargs: {
                    "base_hash": kwargs["payload"]["output_patch_contract"]["base_hash"],
                    "operations": [{"op": "append", "path": "case_diagnostics", "value": missing_second}],
                },
            ]
        )
        payload = {
            "update_contract_version": "signal-update-decision-v2",
            "target": {"signal_ref": base["signal_ref"]},
            "induction_cases": [
                {
                    "case_ref": case_ref,
                    "evidence_observation": {"evidence": []},
                    "outcome_relation": {
                        "label": label,
                        "current_signal_relation": "not_assessable",
                    },
                }
                for case_ref, label in (
                    ("update-case-001", "positive"),
                    ("update-case-002", "control"),
                )
            ],
        }

        result = LLMSignalUpdateModel(caller).update(payload)

        diagnostics = {
            item["case_ref"]: item for item in result.value.case_diagnostics
        }
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertEqual(
            diagnostics["update-case-001"]["outcome_explanation"],
            valid_first["outcome_explanation"],
        )
        self.assertEqual(diagnostics["update-case-002"], missing_second)

    def test_signal_update_v2_semantic_blind_review_set(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests"
                / "fixtures"
                / "signal_update_semantic_blind_v1.json"
            ).read_text(encoding="utf-8")
        )
        source_one = "Management raised full-year revenue guidance by 8 percent."
        source_two = "Management maintained prior full-year revenue guidance."
        payload = {
            "update_contract_version": "signal-update-decision-v2",
            "target": {"signal_ref": "guidance_acceleration:v1"},
            "induction_cases": [
                {
                    "case_ref": "blind-case-001",
                    "evidence_observation": {
                        "evidence": [
                            {
                                "document_ref": "blind-document-001",
                                "content_excerpt": source_one,
                            }
                        ]
                    },
                    "outcome_relation": {
                        "label": "positive",
                        "current_signal_relation": "aligned",
                    },
                },
                {
                    "case_ref": "blind-case-002",
                    "evidence_observation": {
                        "evidence": [
                            {
                                "document_ref": "blind-document-002",
                                "content_excerpt": source_two,
                            }
                        ]
                    },
                    "outcome_relation": {
                        "label": "control",
                        "current_signal_relation": "misaligned",
                    },
                },
            ],
        }
        valid_first = {
            "case_ref": "blind-case-001",
            "evidence_verdict": "supported",
            "facts": [
                {
                    "document_ref": "blind-document-001",
                    "exact_span": source_one,
                }
            ],
            "evidence_gaps": [],
            "outcome_relation": "aligned",
            "outcome_explanation": "The source verdict precedes association.",
        }
        valid_second = {
            "case_ref": "blind-case-002",
            "evidence_verdict": "supported",
            "facts": [
                {
                    "document_ref": "blind-document-002",
                    "exact_span": source_two,
                }
            ],
            "evidence_gaps": [],
            "outcome_relation": "misaligned",
            "outcome_explanation": "The source verdict precedes association.",
        }
        base = {
            "signal_ref": "guidance_acceleration:v1",
            "disposition": "defer",
            "problem_type": "semantic_review",
            "rationale": ["Review source facts before outcome association."],
            "changed_paths": [],
            "candidate": None,
        }

        for review in fixture["cases"]:
            with self.subTest(review_id=review["review_id"]):
                invalid = {
                    **base,
                    "case_diagnostics": [review["diagnostic"], valid_second],
                }
                corrected = {
                    **base,
                    "case_diagnostics": [valid_first, valid_second],
                }
                caller = ScriptedRoleCaller([invalid, corrected])

                result = LLMSignalUpdateModel(caller).update(payload)

                self.assertEqual(result.usage.llm_calls, 2)
                self.assertEqual(result.value.case_diagnostics[0], valid_first)
                self.assertEqual(result.value.case_diagnostics[1], valid_second)
                issue_codes = {
                    item["issue_code"]
                    for item in caller.calls[1]["payload"]["validation_feedback"][
                        "obligations"
                    ]
                }
                self.assertIn(review["expected_issue_code"], issue_codes)

    def test_routing_rejects_duplicate_refs_and_preserves_valid_siblings(
        self,
    ) -> None:
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance.update(
            {
                "reason_code": "combine_evidence",
                "target_need_indices": [],
                "answer_scope": None,
                "residual_need": None,
            }
        )
        duplicate = json.loads(json.dumps(guidance))
        negative = signal_selection("negative_word_count:v1")["selections"][0]
        negative.update(
            {
                "reason_code": "combine_evidence",
                "target_need_indices": [],
                "answer_scope": None,
                "residual_need": None,
            }
        )
        financing = signal_selection("financing_listing_action:v1")["selections"][0]
        financing.update(
            {
                "reason_code": "combine_evidence",
                "target_need_indices": [],
                "answer_scope": None,
                "residual_need": None,
            }
        )
        drifted_guidance = json.loads(json.dumps(guidance))
        drifted_guidance["selection_reason"] = "Rewritten valid sibling."
        drifted_negative = json.loads(json.dumps(negative))
        drifted_negative["selection_reason"] = "Another rewritten valid sibling."
        caller = ScriptedRoleCaller(
            [
                {"selections": [guidance, duplicate, negative]},
                lambda request: {
                    "base_hash": request["payload"]["output_patch_contract"]["base_hash"],
                    "operations": [
                        {"op": "replace", "path": "selections[0]", "value": drifted_guidance},
                        {"op": "replace", "path": "selections[1]", "value": financing},
                        {"op": "replace", "path": "selections[2]", "value": drifted_negative},
                    ],
                },
                lambda request: {
                    "base_hash": request["payload"]["output_patch_contract"]["base_hash"],
                    "operations": [
                        {"op": "replace", "path": "selections[1]", "value": financing},
                    ],
                },
            ]
        )
        caller.max_structured_corrections = 2

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            result = LLMSignalRetrievalAgent(caller).select(
                ("What source-backed context is available?",),
                registry.freeze(),
                {},
            )

        self.assertEqual(
            tuple(item.signal_ref for item in result.value),
            (
                "guidance_acceleration:v1",
                "financing_listing_action:v1",
                "negative_word_count:v1",
            ),
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["required_change_paths"], ["selections[1]"])
        self.assertEqual(result.value[0].selection_reason, guidance["selection_reason"])
        self.assertEqual(result.value[2].selection_reason, negative["selection_reason"])
        self.assertEqual(feedback["validation_contract"], "structured-validation-v1")
        self.assertIn("duplicates", feedback["validation_error"])
        self.assertEqual(len(caller.calls), 3)
        self.assertIn("outside typed authority", caller.calls[2]["payload"]["patch_validation_error"])

    def test_h3_only_unmatched_comparator_context_forces_inconclusive(self) -> None:
        rejected = {
            "decisions": [
                {
                    "hypothesis_id": "guidance_change",
                    "disposition": "rejected",
                    "rationale": ["The groups directly contradict the hypothesis."],
                    "candidate": None,
                }
            ]
        }
        inconclusive = {
            "decisions": [
                {
                    "hypothesis_id": "guidance_change",
                    "disposition": "inconclusive",
                    "rationale": [
                        "The visible comparator packets are semantically insufficient."
                    ],
                    "candidate": None,
                }
            ]
        }
        caller = ScriptedRoleCaller([rejected, inconclusive])
        model = LLMSignalMiningModel(caller)

        step = model.contrast(
            {
                "comparisons": [
                    {
                        "hypothesis": {"hypothesis_id": "guidance_change"},
                        "evidence_packets": [
                            {
                                "packet_ref": ref,
                                "label": (
                                    "positive" if ref == "packet-a" else "control"
                                ),
                                "query_match_status": "unmatched_comparator_context",
                            }
                            for ref in ("packet-a", "packet-b")
                        ],
                    }
                ],
            }
        )

        self.assertEqual(step.value[0].disposition, "inconclusive")
        self.assertEqual(step.usage.llm_calls, 2)
        self.assertIn(
            "without query-matched positive and control evidence",
            caller.calls[1]["payload"]["validation_error"],
        )

    def test_h3_one_unmatched_group_forces_inconclusive(self) -> None:
        supported = {
            "decisions": [
                {
                    "hypothesis_id": "guidance_change",
                    "disposition": "supported",
                    "rationale": ["Positive cases contain the queried disclosure."],
                    "candidate": None,
                }
            ]
        }
        inconclusive = {
            "decisions": [
                {
                    "hypothesis_id": "guidance_change",
                    "disposition": "inconclusive",
                    "rationale": ["The control evidence does not directly test the query."],
                    "candidate": None,
                }
            ]
        }
        caller = ScriptedRoleCaller([supported, inconclusive])

        step = LLMSignalMiningModel(caller).contrast(
            {
                "comparisons": [
                    {
                        "hypothesis": {"hypothesis_id": "guidance_change"},
                        "evidence_packets": [
                            {
                                "packet_ref": "packet-positive",
                                "label": "positive",
                                "query_match_status": "matched",
                            },
                            {
                                "packet_ref": "packet-control",
                                "label": "control",
                                "query_match_status": "unmatched_comparator_context",
                            },
                        ],
                    }
                ],
            }
        )

        self.assertEqual(step.value[0].disposition, "inconclusive")
        self.assertEqual(step.usage.llm_calls, 2)

    def test_exploration_e1_corrects_a_nonliteral_observation(self) -> None:
        invalid = {
            "signatures": [
                {
                    "case_ref": "case-001",
                    "observations": [
                        {
                            "summary": "Revenue guidance increased.",
                            "document_ref": "document-01",
                            "exact_span": "Management raised revenue guidance.",
                        }
                    ],
                    "evidence_gaps": [],
                }
            ]
        }
        valid = json.loads(json.dumps(invalid))
        valid["signatures"][0]["observations"][0]["exact_span"] = (
            "Management reaffirmed revenue guidance."
        )
        caller = ScriptedRoleCaller([invalid, valid])

        step = LLMSignalMiningModel(caller).extract_exploration(
            {
                "cases": [
                    {
                        "case_ref": "case-001",
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": (
                                    "Management reaffirmed revenue guidance."
                                ),
                            }
                        ],
                    }
                ]
            }
        )

        self.assertEqual(step.usage.llm_calls, 2)
        self.assertEqual(
            step.value[0].observations[0].exact_span,
            "Management reaffirmed revenue guidance.",
        )
        self.assertIn(
            "not a supplied literal",
            caller.calls[1]["payload"]["validation_feedback"]["validation_error"],
        )

    def test_exploration_e1_empty_packet_records_gap_without_invention(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "signatures": [
                        {
                            "case_ref": "case-001",
                            "observations": [],
                            "evidence_gaps": ["No point-in-time excerpt was supplied."],
                        }
                    ]
                }
            ]
        )

        step = LLMSignalMiningModel(caller).extract_exploration(
            {"cases": [{"case_ref": "case-001", "evidence": []}]}
        )

        self.assertEqual(step.usage.llm_calls, 1)
        self.assertEqual(step.value[0].observations, ())
        self.assertTrue(step.value[0].evidence_gaps)

    def test_exploration_e1_repairs_one_reordered_row_and_preserves_sibling(
        self,
    ) -> None:
        first = {
            "case_ref": "case-001",
            "observations": [
                {
                    "summary": "Management reaffirmed guidance.",
                    "document_ref": "document-01",
                    "exact_span": "Management reaffirmed revenue guidance.",
                }
            ],
            "evidence_gaps": [],
        }
        invalid_second = {
            "case_ref": "case-002",
            "observations": [
                {
                    "summary": "A customer order was disclosed.",
                    "document_ref": "document-01",
                    "exact_span": "A fabricated customer order was disclosed.",
                }
            ],
            "evidence_gaps": [],
        }
        repaired_second = json.loads(json.dumps(invalid_second))
        repaired_second["observations"][0]["exact_span"] = (
            "A binding customer order was disclosed."
        )
        drifted_first = json.loads(json.dumps(first))
        drifted_first["observations"][0]["summary"] = "Unrelated rewritten summary."
        caller = ScriptedRoleCaller(
            [
                {"signatures": [first, invalid_second]},
                {"signatures": [repaired_second, drifted_first]},
            ]
        )

        step = LLMSignalMiningModel(caller).extract_exploration(
            {
                "cases": [
                    {
                        "case_ref": "case-001",
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": (
                                    "Management reaffirmed revenue guidance."
                                ),
                            }
                        ],
                    },
                    {
                        "case_ref": "case-002",
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": (
                                    "A binding customer order was disclosed."
                                ),
                            }
                        ],
                    },
                ]
            }
        )

        self.assertEqual(
            [item.case_ref for item in step.value], ["case-001", "case-002"]
        )
        self.assertEqual(
            step.value[0].observations[0].summary,
            "Management reaffirmed guidance.",
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["validation_contract"], "structured-validation-v1"
        )
        self.assertEqual(feedback["obligations"][0]["item_id"], "case-002")

    def test_exploration_e2_treats_exact_spans_as_authoritative(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "decisions": [],
                    "no_candidate": {
                        "reason_code": "no_measurable_pattern",
                        "rationale": ["The literal cohort shows no repeated difference."],
                        "considered_case_refs": ["case-001", "case-002"],
                    },
                }
            ]
        )

        LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {
                        "case_ref": "case-001",
                        "observations": [
                            {
                                "summary": "An overstated interpretation.",
                                "document_ref": "document-01",
                                "exact_span": "Management reaffirmed prior guidance.",
                            }
                        ],
                        "evidence_gaps": [],
                        "label": "positive",
                    },
                    {
                        "case_ref": "case-002",
                        "observations": [
                            {
                                "summary": "Management maintained its prior position.",
                                "document_ref": "document-02",
                                "exact_span": "Management maintained its prior position.",
                            }
                        ],
                        "evidence_gaps": [],
                        "label": "control",
                    }
                ],
                "decision_slots": ["e2-c0001-s01"],
            }
        )

        self.assertIn(
            "Treat each exact_span as authoritative",
            caller.calls[0]["system_prompt"],
        )

    def test_exploration_e2_repairs_legacy_candidate_shape_without_losing_intent(
        self,
    ) -> None:
        candidate = {"spec": {}, "skill": None, "tests": []}
        invalid = {
            "decisions": [
                {
                    "pattern": "Positive cases improve while controls decline.",
                    "signal": {},
                    "summary": "A repeated contrast exists.",
                    "supported_case_refs": ["case-001", "case-002"],
                }
            ],
            "no_candidate": None,
        }
        corrected = {
            "decisions": [
                {
                    "hypothesis_id": "e2-c0001-s01",
                    "disposition": "supported",
                    "rationale": ["The supplied exact spans show a repeated contrast."],
                    "contrast": {
                        "positive_case_refs": ["case-001"],
                        "control_case_refs": ["case-002"],
                        "observable_difference": (
                            "The positive value rises while the control value declines."
                        ),
                    },
                    "candidate": candidate,
                }
            ],
            "no_candidate": None,
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {"case_ref": "case-001", "label": "positive"},
                    {"case_ref": "case-002", "label": "control"},
                ],
                "decision_slots": ["e2-c0001-s01"],
                "rules": {"decisions": ["supported"]},
            }
        )

        self.assertEqual(step.value[0].candidate, candidate)
        self.assertEqual(
            step.value[0].sample_basis,
            {
                "positive_refs": ("case-001",),
                "control_refs": ("case-002",),
            },
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["obligations"][0]["issue_code"],
            "e2_decision_shape_invalid",
        )
        self.assertIn("positive_case_refs", caller.calls[0]["system_prompt"])

    def test_h3_comparison_packets_are_scoped_per_hypothesis(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "decisions": [
                        {
                            "hypothesis_id": "matched",
                            "disposition": "supported",
                            "rationale": ["Both matched groups show the difference."],
                            "candidate": {},
                        },
                        {
                            "hypothesis_id": "unmatched",
                            "disposition": "inconclusive",
                            "rationale": ["Its own packets do not match the query."],
                            "candidate": None,
                        },
                    ]
                }
            ]
        )
        step = LLMSignalMiningModel(caller).contrast(
            {
                "comparisons": [
                    {
                        "hypothesis": {"hypothesis_id": hypothesis_id},
                        "evidence_packets": [
                            {
                                "packet_ref": f"{hypothesis_id}-positive",
                                "label": "positive",
                                "query_match_status": status,
                            },
                            {
                                "packet_ref": f"{hypothesis_id}-control",
                                "label": "control",
                                "query_match_status": status,
                            },
                        ],
                    }
                    for hypothesis_id, status in (
                        ("matched", "matched"),
                        ("unmatched", "unmatched_comparator_context"),
                    )
                ]
            }
        )

        self.assertEqual(step.value[0].disposition, "supported")
        self.assertEqual(step.value[1].disposition, "inconclusive")
        self.assertEqual(
            step.value[0].sample_basis["positive_refs"],
            ("matched-positive",),
        )
        self.assertIn("sibling hypothesis", caller.calls[0]["system_prompt"])

    def test_exploration_e2_empty_requires_exact_considered_refs(self) -> None:
        malformed = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "insufficient_evidence",
                "rationale": ["The visible signatures are not sufficient."],
                "considered_case_refs": ["case-001"],
            },
        }
        corrected = json.loads(json.dumps(malformed))
        corrected["no_candidate"]["considered_case_refs"] = [
            "case-001",
            "case-002",
        ]
        caller = ScriptedRoleCaller([malformed, corrected])

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {"case_ref": "case-001", "label": "positive"},
                    {"case_ref": "case-002", "label": "control"},
                ],
                "rules": {
                    "decisions": [
                        "supported",
                        "refine",
                        "rejected",
                        "inconclusive",
                    ]
                },
            }
        )

        self.assertEqual(step.value, ())
        self.assertEqual(step.usage.llm_calls, 2)
        self.assertEqual(
            step.metadata["no_candidate"]["considered_case_refs"],
            ["case-001", "case-002"],
        )
        self.assertIn(
            "ignore any stronger or different claim",
            caller.calls[0]["system_prompt"],
        )

    def test_exploration_e2_limited_evidence_cannot_claim_no_pattern(self) -> None:
        invalid = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "no_measurable_pattern",
                "rationale": ["No recurring difference is visible."],
                "considered_case_refs": ["case-001", "case-002"],
            },
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["no_candidate"]["reason_code"] = "insufficient_evidence"
        corrected["no_candidate"]["rationale"] = [
            "The bounded evidence is insufficient for a pattern conclusion."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {"case_ref": "case-001", "label": "positive"},
                    {"case_ref": "case-002", "label": "control"},
                ],
                "rules": {"evidence_limited": True},
            }
        )

        self.assertEqual(step.value, ())
        self.assertEqual(
            caller.calls[1]["payload"]["validation_feedback"]["obligations"][0][
                "issue_code"
            ],
            "e2_limited_evidence_overclaims_no_pattern",
        )

    def test_h1_reflection_action_routes_non_signal_work_to_fast(self) -> None:
        invalid = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": ["The need is already covered."],
                "need_refs": ["need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "already_covered",
                    "signal_refs": ["cash_runway:v1"],
                    "rationale": ["A stable card exists."],
                }
            ],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["need_dispositions"][0]["disposition"] = "fast_plan_action"
        corrected["need_dispositions"][0]["signal_refs"] = []
        corrected["need_dispositions"][0]["rationale"] = [
            "This changes Fast retrieval policy rather than defining a factor."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v5",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
                "available_raw_source_types": ["financials"],
                "stable_signal_cards": [{"signal_ref": "cash_runway:v1"}],
                "capability_backlog": {
                    "signal_need_items": [
                        {
                            "need_ref": "reflection-source-ref",
                            "kind": "meta_reflection_action",
                            "need": "Test point-in-time cash runway.",
                        }
                    ]
                },
            }
        )

        self.assertEqual(step.value, ())
        self.assertEqual(
            {
                item["issue_code"]
                for item in caller.calls[1]["payload"]["validation_feedback"][
                    "obligations"
                ]
            },
            {"h1_reflection_action_ignored"},
        )
        self.assertIn(
            "Use fast_plan_action only when the item changes retrieval",
            caller.calls[0]["system_prompt"],
        )
        self.assertEqual(
            step.metadata["need_dispositions"][0]["disposition"],
            "fast_plan_action",
        )

    def test_h1_aggregates_history_refs_in_ledger_and_terminal_reason(self) -> None:
        history_ref = "slow-history:source-example:1:slow_input:feedback-001"
        invalid = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "need_dispositions": [
                {
                    "need_refs": [history_ref],
                    "disposition": "repair_dependency",
                    "signal_refs": [],
                    "rationale": ["The historical work reported a failure."],
                }
            ],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": [
                    "The retrospective record is not a runtime measurement need."
                ],
                "need_refs": [history_ref],
            },
        }
        corrected = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "need_dispositions": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": [
                    "No runtime need_ref was supplied, so the demand ledger is empty."
                ],
                "need_refs": [],
            },
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v7",
                "hypothesis_slots": [
                    "h1-c0001-s01",
                    "h1-c0001-s02",
                    "h1-c0001-s03",
                ],
                "limits": {"hypothesis_limit": 3, "evidence_lookback_days": 365},
                "available_raw_source_types": ["financials"],
                "stable_signal_cards": [],
                "capability_backlog": {"signal_need_items": [], "items": []},
            }
        )

        self.assertEqual(step.value, ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligation_count"], 2)
        self.assertEqual(
            feedback["required_change_paths"],
            ["need_dispositions[0].need_refs", "no_hypothesis"],
        )
        self.assertEqual(
            feedback["obligations"][0]["authorized_member_removals"],
            ["need_dispositions[0]"],
        )
        self.assertEqual(
            feedback["obligations"][0]["allowed_repairs"], ["replace", "remove"]
        )
        self.assertEqual(step.metadata["need_dispositions"], [])

    def test_h1_fast_plan_action_cannot_divert_ordinary_need(self) -> None:
        invalid = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": ["No reusable measurement can be defined."],
                "need_refs": ["need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "fast_plan_action",
                    "signal_refs": [],
                    "rationale": ["Change the next Fast plan."],
                }
            ],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["need_dispositions"][0]["disposition"] = "not_testable"
        corrected["need_dispositions"][0]["rationale"] = [
            "The requested fact is issuer-specific and not reusable."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v5",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
                "available_raw_source_types": ["financials"],
                "stable_signal_cards": [],
                "capability_backlog": {
                    "signal_need_items": [
                        {"need_ref": "ordinary-need", "need": "One issuer fact."}
                    ]
                },
            }
        )

        self.assertEqual(step.value, ())
        obligation = caller.calls[1]["payload"]["validation_feedback"][
            "obligations"
        ][0]
        self.assertEqual(
            obligation["issue_code"], "h1_fast_plan_action_scope_invalid"
        )
        self.assertEqual(
            step.metadata["need_dispositions"][0]["disposition"], "not_testable"
        )

    def test_h1_existing_disposition_requires_exactly_one_signal(self) -> None:
        invalid = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": ["One existing measure covers the need."],
                "need_refs": ["need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "already_covered",
                    "signal_refs": ["cash_runway:v1", "cash_reserves:v1"],
                    "rationale": ["Existing measures are available."],
                }
            ],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["need_dispositions"][0]["signal_refs"] = ["cash_runway:v1"]
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v5",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
                "available_raw_source_types": ["financials"],
                "stable_signal_cards": [
                    {"signal_ref": "cash_runway:v1"},
                    {"signal_ref": "cash_reserves:v1"},
                ],
                "capability_backlog": {
                    "signal_need_items": [
                        {"need_ref": "cash-need", "need": "Measure cash runway."}
                    ]
                },
            }
        )

        self.assertEqual(step.value, ())
        obligation = caller.calls[1]["payload"]["validation_feedback"]["obligations"][0]
        self.assertEqual(obligation["issue_code"], "h1_disposition_signal_refs_invalid")
        self.assertEqual(
            step.metadata["need_dispositions"][0]["signal_refs"],
            ["cash_runway:v1"],
        )

    def test_h1_unmatched_need_cannot_be_silently_marked_covered(self) -> None:
        invalid = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": ["The stable catalog covers the need."],
                "need_refs": ["need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "already_covered",
                    "signal_refs": ["guidance_acceleration:v1"],
                    "rationale": ["A guidance Signal exists."],
                }
            ],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["need_dispositions"][0] = {
            "need_refs": ["need-001"],
            "disposition": "repair_dependency",
            "signal_refs": [],
            "rationale": ["The client-count filing series is unavailable in the supplied news-only source catalog."],
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v7",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
                "available_raw_source_types": ["news"],
                "stable_signal_cards": [
                    {
                        "signal_ref": "guidance_acceleration:v1",
                        "routing_answer_need_phrases": ["guidance"],
                    }
                ],
                "capability_backlog": {
                    "signal_need_items": [
                        {
                            "need_ref": "client-trend",
                            "kind": "unmatched_signal_need",
                            "need": "Measure active client retention trends.",
                        }
                    ]
                },
            }
        )

        obligation = caller.calls[1]["payload"]["validation_feedback"][
            "obligations"
        ][0]
        self.assertEqual(
            obligation["issue_code"],
            "h1_unmatched_need_cannot_be_already_covered",
        )
        self.assertEqual(
            step.metadata["need_dispositions"][0]["disposition"],
            "repair_dependency",
        )

    def test_h1_capacity_deferral_requires_a_full_portfolio(self) -> None:
        full = {
            "conclusion": "hypotheses", "no_hypothesis": None,
            "hypotheses": [{
                "proposal_ref": "h1-c0001-s01",
                "measurement": {"observable": "Cash runway in months", "value_kind": "numeric", "normalization": "cash balance divided by monthly cash burn"},
                "applicability": {"rule": "all_ready_issuers", "values": []},
                "expected_direction": "higher_in_positive",
                "retrieval_intent": {"source_types": ["company_facts"], "query": "cash balance operating cash burn"},
                "falsifiers": [{"condition": "Cash runway is measured for fixed groups.", "expected_observation": "The groups overlap or reverse direction."}],
                "need_refs": ["need-001"],
            }],
            "need_dispositions": [
                {"need_refs": ["need-001"], "disposition": "new_measurement", "signal_refs": [], "rationale": ["Test cash runway as a distinct normalized measurement."]},
                {"need_refs": ["need-002"], "disposition": "deferred_measurement", "signal_refs": [], "rationale": ["The separate operating margin measurement exceeds the one-slot portfolio."]},
            ],
        }
        empty = json.loads(json.dumps(full))
        empty["conclusion"] = "no_testable_hypothesis"
        empty["hypotheses"] = []
        empty["no_hypothesis"] = {"reason_code": "insufficient_retrieval_basis", "rationale": ["All demand is outside this portfolio."], "need_refs": ["need-001", "need-002"]}
        empty["need_dispositions"][0]["disposition"] = "deferred_measurement"
        caller = ScriptedRoleCaller([empty, full])
        step = LLMSignalMiningModel(caller).propose_hypotheses({
            "hypothesis_slots": ["h1-c0001-s01"],
            "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
            "available_raw_source_types": ["company_facts"],
            "stable_signal_cards": [],
            "capability_backlog": {"signal_need_items": [
                {"need_ref": "runway", "kind": "unmatched_signal_need", "need": "Measure cash runway."},
                {"need_ref": "margin", "kind": "unmatched_signal_need", "need": "Measure operating margin."},
            ]},
        })
        self.assertEqual(len(step.value), 1)
        self.assertEqual(
            caller.calls[1]["payload"]["validation_feedback"]["obligations"][0]["issue_code"],
            "h1_capacity_deferral_without_full_portfolio",
        )

    def test_h1_update_existing_requires_basis_for_every_grouped_need(self) -> None:
        invalid = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": ["The needs can be handled outside this portfolio."],
                "need_refs": ["need-001", "need-002"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-001", "need-002"],
                    "disposition": "update_existing",
                    "signal_refs": ["guidance_acceleration:v1"],
                    "rationale": ["Update the guidance Signal."],
                }
            ],
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["need_dispositions"] = [
            {
                "need_refs": ["need-001"],
                "disposition": "update_existing",
                "signal_refs": ["guidance_acceleration:v1"],
                "rationale": ["The need explicitly requests guidance."],
            },
            {
                "need_refs": ["need-002"],
                "disposition": "repair_dependency",
                "signal_refs": [],
                "rationale": ["Client retention needs a client-count filing series absent from the news-only source catalog."],
            },
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v7",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
                "available_raw_source_types": ["news"],
                "stable_signal_cards": [
                    {
                        "signal_ref": "guidance_acceleration:v1",
                        "routing_answer_need_phrases": ["guidance", "outlook"],
                    }
                ],
                "capability_backlog": {
                    "signal_need_items": [
                        {
                            "need_ref": "guidance-need",
                            "kind": "unmatched_signal_need",
                            "need": "Compare current guidance with prior guidance.",
                        },
                        {
                            "need_ref": "retention-need",
                            "kind": "unmatched_signal_need",
                            "need": "Measure active client retention trends.",
                        },
                    ]
                },
            }
        )

        obligation = caller.calls[1]["payload"]["validation_feedback"][
            "obligations"
        ][0]
        self.assertEqual(
            obligation["issue_code"], "h1_update_existing_lacks_explicit_basis"
        )
        self.assertEqual(obligation["source_refs"], ["need-002"])
        self.assertEqual(len(step.metadata["need_dispositions"]), 2)

    def test_h1_final_fallback_removes_only_redundant_singular_signal_ref(
        self,
    ) -> None:
        duplicated = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "no_new_measurable_gap",
                "rationale": ["The exact stable Signal already covers the need."],
                "need_refs": ["need-001"],
            },
            "need_dispositions": [
                {
                    "need_refs": ["need-001"],
                    "disposition": "already_covered",
                    "signal_ref": "cash_reserves:v1",
                    "signal_refs": ["cash_reserves:v1"],
                    "rationale": ["The need already names the stable Signal."],
                }
            ],
        }
        caller = ScriptedRoleCaller([duplicated, duplicated])

        step = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v7",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {"hypothesis_limit": 1, "evidence_lookback_days": 365},
                "available_raw_source_types": ["financials"],
                "stable_signal_cards": [{"signal_ref": "cash_reserves:v1"}],
                "capability_backlog": {
                    "signal_need_items": [
                        {"need_ref": "cash-need", "need": "Cash reserves."}
                    ]
                },
            }
        )

        self.assertEqual(step.usage.llm_calls, 2)
        self.assertNotIn("signal_ref", step.metadata["need_dispositions"][0])
        self.assertEqual(
            step.metadata["need_dispositions"][0]["signal_refs"],
            ["cash_reserves:v1"],
        )

    def test_exploration_e2_corrects_per_case_rejections_to_no_candidate(self) -> None:
        malformed = {
            "decisions": [
                {
                    "case_ref": "case-001",
                    "disposition": "rejected",
                    "hypothesis_id": None,
                    "rationale": ["No recurring difference is visible."],
                    "candidate": None,
                },
                {
                    "case_ref": "case-002",
                    "disposition": "rejected",
                    "hypothesis_id": None,
                    "rationale": ["No recurring difference is visible."],
                    "candidate": None,
                },
            ],
            "no_candidate": None,
        }
        corrected = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "no_measurable_pattern",
                "rationale": ["No recurring cross-case difference is visible."],
                "considered_case_refs": ["case-001", "case-002"],
            },
        }
        caller = ScriptedRoleCaller([malformed, corrected])

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {"case_ref": "case-001", "label": "positive"},
                    {"case_ref": "case-002", "label": "control"},
                ],
                "rules": {
                    "decisions": [
                        "supported",
                        "refine",
                        "rejected",
                        "inconclusive",
                    ]
                },
            }
        )

        self.assertEqual(step.value, ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["obligations"][0]["issue_code"],
            "e2_per_case_rows_not_portfolio_decisions",
        )
        self.assertEqual(
            feedback["required_change_paths"], ["decisions", "no_candidate"]
        )
        self.assertIn("portfolio-level recurring pattern", caller.calls[0]["system_prompt"])

    def test_exploration_e2_rejects_false_unlabeled_case_rationale(self) -> None:
        invalid = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "no_measurable_pattern",
                "rationale": [
                    "The positive, control, and unlabeled cases show no recurring pattern."
                ],
                "considered_case_refs": ["case-001", "case-002"],
            },
        }
        corrected = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "no_measurable_pattern",
                "rationale": [
                    "The positive and control cases show no recurring measurable pattern."
                ],
                "considered_case_refs": ["case-001", "case-002"],
            },
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {"case_ref": "case-001", "label": "positive"},
                    {"case_ref": "case-002", "label": "control"},
                ]
            }
        )

        self.assertEqual(step.value, ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["obligations"][0]["issue_code"],
            "e2_no_candidate_label_inventory_mismatch",
        )

    def test_exploration_e2_rejects_model_authored_group_counts(self) -> None:
        invalid = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "no_measurable_pattern",
                "rationale": [
                    "Three control cases and four positive cases show no pattern."
                ],
                "considered_case_refs": ["case-001", "case-002"],
            },
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["no_candidate"]["rationale"] = [
            "The supplied literal signatures show no recurring measurable contrast."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {"case_ref": "case-001", "label": "positive"},
                    {"case_ref": "case-002", "label": "control"},
                ]
            }
        )

        self.assertEqual(step.value, ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["obligations"][0]["issue_code"],
            "e2_no_candidate_group_count_restatement",
        )

    def test_exploration_e2_rejects_free_text_case_label_reassignment(self) -> None:
        invalid = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "insufficient_evidence",
                "rationale": [
                    (
                        "The labeled positives (case-001, case-002, case-003) "
                        "and controls (case-003, case-004) do not separate."
                    )
                ],
                "considered_case_refs": [
                    "case-001",
                    "case-002",
                    "case-003",
                    "case-004",
                ],
            },
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["no_candidate"]["rationale"] = [
            "The supplied literal signatures show no recurring measurable contrast."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {"case_ref": "case-001", "label": "positive"},
                    {"case_ref": "case-002", "label": "positive"},
                    {"case_ref": "case-003", "label": "control"},
                    {"case_ref": "case-004", "label": "control"},
                ]
            }
        )

        self.assertEqual(step.value, ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["obligations"][0]["issue_code"],
            "e2_free_text_label_assignment_forbidden",
        )
        self.assertEqual(
            step.metadata["no_candidate"]["positive_case_refs"],
            ["case-001", "case-002"],
        )
        self.assertEqual(
            step.metadata["no_candidate"]["control_case_refs"],
            ["case-003", "case-004"],
        )

    def test_exploration_e2_corrects_unsupplied_profile_claim_in_no_candidate(
        self,
    ) -> None:
        invalid = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "no_measurable_pattern",
                "rationale": [
                    "The positive cases are from different sectors and show no pattern."
                ],
                "considered_case_refs": ["case-001", "case-002"],
            },
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["no_candidate"]["rationale"] = [
            "The supplied revenue spans move in opposite directions across labels."
        ]
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {
                        "case_ref": "case-001",
                        "label": "positive",
                        "observations": [
                            {
                                "exact_span": "Revenue increased from 10 to 12.",
                                "summary": "Literal filing excerpt.",
                            }
                        ],
                    },
                    {
                        "case_ref": "case-002",
                        "label": "control",
                        "observations": [
                            {
                                "exact_span": "Revenue increased from 8 to 9.",
                                "summary": "Literal filing excerpt.",
                            }
                        ],
                    },
                ]
            }
        )

        self.assertEqual(step.value, ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        obligation = feedback["obligations"][0]
        self.assertEqual(obligation["issue_code"], "e2_unsupported_profile_claim")
        self.assertEqual(
            obligation["must_change_paths"], ["no_candidate.rationale"]
        )
        self.assertIn("Do not infer issuer-profile", caller.calls[0]["system_prompt"])

    def test_exploration_e2_replays_v52_and_rejects_invented_source_gap(
        self,
    ) -> None:
        invalid = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "insufficient_evidence",
                "rationale": [
                    (
                        "The supplied signatures show no repeated observable "
                        "cross-case difference across the frozen exact spans."
                    ),
                    (
                        "Evidence gaps explicitly note missing full-year "
                        "cash-flow/revenue figures and partial structured contexts, "
                        "preventing a stable cross-case comparison."
                    ),
                ],
                "considered_case_refs": [
                    "case-001",
                    "case-002",
                    "case-003",
                    "case-004",
                ],
            },
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["no_candidate"]["rationale"] = [
            invalid["no_candidate"]["rationale"][0],
            (
                "The supplied observations are insufficient to establish a "
                "recurring portfolio contrast."
            ),
        ]
        caller = ScriptedRoleCaller([invalid, corrected])
        signatures = [
            {
                "case_ref": "case-001",
                "label": "positive",
                "observations": [{"exact_span": "Revenue from customers was 2,040."}],
                "evidence_gaps": [
                    "The excerpt is truncated and does not show the full balance "
                    "sheet, cash flow statement, or liquidity disclosures for the "
                    "period."
                ],
            },
            {
                "case_ref": "case-002",
                "label": "control",
                "observations": [{"exact_span": "Statements are subject to risks."}],
                "evidence_gaps": [
                    "The excerpt is truncated and does not show the complete list "
                    "of risk factors or the specific forward-looking statements "
                    "being qualified."
                ],
            },
            {
                "case_ref": "case-003",
                "label": "positive",
                "observations": [{"exact_span": "We may consider acquisitions."}],
                "evidence_gaps": [
                    "The excerpt is truncated and does not show the full risk factor "
                    "discussion or any specific strategic transactions under "
                    "consideration."
                ],
            },
            {
                "case_ref": "case-004",
                "label": "control",
                "observations": [{"exact_span": "International revenue was 15%."}],
                "evidence_gaps": [
                    "The excerpt is truncated and does not show the full list of "
                    "international risks or the specific financial impact of "
                    "international operations."
                ],
            },
        ]

        step = LLMSignalMiningModel(caller).discover_exploration(
            {"signatures": signatures}
        )

        self.assertEqual(step.value, ())
        obligation = caller.calls[1]["payload"]["validation_feedback"][
            "obligations"
        ][0]
        self.assertEqual(
            obligation["issue_code"], "e2_source_gap_claim_ungrounded"
        )
        self.assertEqual(
            obligation["must_change_paths"], ["no_candidate.rationale"]
        )
        self.assertIn("[case_ref]", caller.calls[0]["system_prompt"])

    def test_exploration_e2_accepts_verbatim_case_scoped_gap_citation(self) -> None:
        gap = "The excerpt is truncated and does not show the full cash flow statement."
        caller = ScriptedRoleCaller(
            [
                {
                    "decisions": [],
                    "no_candidate": {
                        "reason_code": "insufficient_evidence",
                        "rationale": [f"[case-001] {gap}"],
                        "considered_case_refs": ["case-001", "case-002"],
                    },
                }
            ]
        )

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {
                        "case_ref": "case-001",
                        "label": "positive",
                        "evidence_gaps": [gap],
                    },
                    {
                        "case_ref": "case-002",
                        "label": "control",
                        "evidence_gaps": [],
                    },
                ]
            }
        )

        self.assertEqual(step.value, ())
        self.assertEqual(step.usage.llm_calls, 1)

    def test_exploration_e2_allows_observed_theme_absence_between_groups(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "decisions": [],
                    "no_candidate": {
                        "reason_code": "no_measurable_pattern",
                        "rationale": [
                            (
                                "Natural-disaster spans in a control case have "
                                "no counterpart in the positive cases."
                            ),
                            (
                                "That topic is absent from the positive cases and "
                                "does not form a recurring cross-group contrast."
                            ),
                        ],
                        "considered_case_refs": ["case-001", "case-002"],
                    },
                }
            ]
        )

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {
                        "case_ref": "case-001",
                        "label": "positive",
                        "observations": [{"exact_span": "Debt covenants apply."}],
                        "evidence_gaps": [],
                    },
                    {
                        "case_ref": "case-002",
                        "label": "control",
                        "observations": [
                            {"exact_span": "Natural disasters may disrupt operations."}
                        ],
                        "evidence_gaps": [],
                    },
                ]
            }
        )

        self.assertEqual(step.value, ())
        self.assertEqual(step.usage.llm_calls, 1)

    def test_exploration_e2_corrects_unsupplied_profile_claim_in_contrast(
        self,
    ) -> None:
        candidate = {"spec": {}, "skill": None, "tests": []}
        invalid = {
            "decisions": [
                {
                    "hypothesis_id": "e2-c0001-s01",
                    "disposition": "supported",
                    "rationale": ["The supplied literal values differ by label."],
                    "contrast": {
                        "positive_case_refs": ["case-001"],
                        "control_case_refs": ["case-002"],
                        "observable_difference": (
                            "Small-cap positives rise while large-cap controls fall."
                        ),
                    },
                    "candidate": candidate,
                }
            ],
            "no_candidate": None,
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["decisions"][0]["contrast"]["observable_difference"] = (
            "The positive revenue value rises while the control value falls."
        )
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "decision_slots": ["e2-c0001-s01"],
                "signatures": [
                    {
                        "case_ref": "case-001",
                        "label": "positive",
                        "observations": [{"exact_span": "Revenue rose to 12."}],
                    },
                    {
                        "case_ref": "case-002",
                        "label": "control",
                        "observations": [{"exact_span": "Revenue fell to 8."}],
                    },
                ],
            }
        )

        self.assertEqual(len(step.value), 1)
        obligation = caller.calls[1]["payload"]["validation_feedback"][
            "obligations"
        ][0]
        self.assertEqual(obligation["issue_code"], "e2_unsupported_profile_claim")
        self.assertIn(
            "decisions[0].contrast.observable_difference",
            obligation["must_change_paths"],
        )
        self.assertNotIn("decisions[0].rationale", obligation["must_change_paths"])

    def test_exploration_e2_rejects_claim_that_visible_labels_are_hidden(self) -> None:
        invalid = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "insufficient_evidence",
                "rationale": [
                    "The outcome-hidden labels cannot be compared as text."
                ],
                "considered_case_refs": ["case-001", "case-002"],
            },
        }
        corrected = {
            "decisions": [],
            "no_candidate": {
                "reason_code": "insufficient_evidence",
                "rationale": [
                    "The visible positive and control facts are too heterogeneous."
                ],
                "considered_case_refs": ["case-001", "case-002"],
            },
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        step = LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {"case_ref": "case-001", "label": "positive"},
                    {"case_ref": "case-002", "label": "control"},
                ]
            }
        )

        self.assertEqual(step.value, ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["obligations"][0]["issue_code"],
            "e2_no_candidate_label_inventory_mismatch",
        )
        self.assertIn("labels are now visible", caller.calls[0]["system_prompt"])
        self.assertNotIn("model-authored summary", caller.calls[0]["system_prompt"])

    def test_slow_output_contracts_do_not_supply_populated_answers(self) -> None:
        contracts = (
            signal_roles_module._SIGNAL_MINING_HYPOTHESES_V3_OUTPUT,
            signal_roles_module._SIGNAL_MINING_DECISIONS_OUTPUT,
            signal_roles_module._SIGNAL_MINING_SIGNATURES_OUTPUT,
            signal_roles_module._SIGNAL_UPDATE_V2_OUTPUT,
        )
        for contract in contracts:
            with self.subTest(contract=contract):
                self.assertNotIn("example", contract.casefold())
                self.assertNotIn("large_order_confirmation", contract)
                self.assertNotIn("case-001", contract)
                self.assertNotIn("Induction evidence does not isolate", contract)
                self.assertNotIn("An expectation-changing event", contract)
        self.assertIn(
            "boolean, ordinal, numeric, or categorical",
            signal_roles_module._SIGNAL_MINING_HYPOTHESES_V3_OUTPUT,
        )
        self.assertIn(
            "both supplied record exact_spans",
            signal_roles_module._SIGNAL_MINING_SIGNATURES_OUTPUT,
        )
