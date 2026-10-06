"""Coverage-preserving diagnostics for mixed Slow reflection sources."""

from copy import deepcopy
from unittest import TestCase

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.cross_round_reflection import prediction_comparisons
from stock_opportunity_agent.research.evolution_signal_roles import LLMSignalMiningModel
from tests.test_cross_round_reflection import observation
from tests.test_evolution_state_patch import PatchCaller, patch


def episode(slot, refs, text="The recorded process outcome has no verified benefit."):
    """Create a sourced fact without adding a causal conclusion."""

    return {
        "episode_ref": slot, "source_refs": list(refs), "reflection": text,
        "brief": text, "kind": "fact", "unresolved_questions": [],
    }


def payload():
    """Supply one paired original and two independent process summaries."""

    pair = prediction_comparisons([observation(), observation(positive=False, context=2)])[0]
    return {
        "episode_slots": ["episode-1", "episode-2", "episode-3"],
        "lesson_slots": [],
        "feedback_units": [
            {"feedback_ref": "comparison", "kind": "prediction_comparison", "artifact": pair},
            {"feedback_ref": "result-summary", "kind": "search_result", "artifact": {}},
            {"feedback_ref": "validation-summary", "kind": "candidate_result", "artifact": {}},
        ],
    }


class SlowReflectionSourcePartitionTests(TestCase):
    def test_full_slots_retain_summaries_without_changing_valid_comparisons(self):
        initial = {
            "episode_reflections": [
                episode("episode-1", ["comparison"]),
                episode("episode-2", ["comparison", "result-summary", "validation-summary"]),
                episode("episode-3", ["comparison"]),
            ],
            "lesson_additions": [],
        }
        original = deepcopy(initial)

        def correct(request):
            issue = request["payload"]["validation_feedback"]["obligations"][0]
            self.assertEqual(issue["issue_code"], "cross_round_mixed_sources")
            self.assertEqual(issue["comparison_feedback_refs"], ["comparison"])
            self.assertEqual(issue["other_feedback_refs"], ["result-summary", "validation-summary"])
            self.assertEqual(issue["feedback_refs_without_other_valid_episode"],
                             ["result-summary", "validation-summary"])
            contract = request["payload"]["output_patch_contract"]
            self.assertEqual(contract["allowed_operations"], [
                {"op": "replace", "path": "episode_reflections[1]", "descendants": True},
            ])
            fixed = deepcopy(initial["episode_reflections"][1])
            fixed["source_refs"] = issue["feedback_refs_without_other_valid_episode"]
            return patch(contract, {"op": "replace", "path": "episode_reflections[1]", "value": fixed})

        caller = PatchCaller(initial, correct)
        caller.max_structured_corrections = 1
        result = LLMSignalMiningModel(caller).reflect_feedback(payload())
        self.assertEqual(result.value["episode_reflections"][0], original["episode_reflections"][0])
        self.assertEqual(result.value["episode_reflections"][2], original["episode_reflections"][2])
        self.assertEqual(result.value["episode_reflections"][1]["reflection"],
                         original["episode_reflections"][1]["reflection"])
        self.assertEqual(initial, original)
        self.assertIn("Lesson citations do not substitute", caller.calls[0]["system_prompt"])

    def test_partition_diagnostics_follow_actual_coverage_and_row_order(self):
        for keep in ("comparison", "result-summary"):
            for reverse in (False, True):
                with self.subTest(keep=keep, reverse=reverse):
                    remaining = "result-summary" if keep == "comparison" else "comparison"
                    rows = [episode("episode-1", [keep]),
                            episode("episode-2", ["comparison", "result-summary"]),
                            episode("episode-3", ["validation-summary"])]
                    if reverse:
                        rows.reverse()
                    mixed_index = next(i for i, row in enumerate(rows) if row["episode_ref"] == "episode-2")
                    initial = {"episode_reflections": rows, "lesson_additions": []}

                    def correct(request):
                        issue = request["payload"]["validation_feedback"]["obligations"][0]
                        self.assertEqual(issue["feedback_refs_without_other_valid_episode"], [remaining])
                        fixed = {**rows[mixed_index], "source_refs": [remaining]}
                        return patch(request["payload"]["output_patch_contract"], {
                            "op": "replace", "path": f"episode_reflections[{mixed_index}]", "value": fixed,
                        })

                    caller = PatchCaller(initial, correct)
                    self.assertEqual(len(LLMSignalMiningModel(caller).reflect_feedback(payload()).value["episode_reflections"]), 3)

    def test_duplicate_comparison_does_not_satisfy_summary_coverage(self):
        initial = {
            "episode_reflections": [episode("episode-1", ["comparison"]),
                                    episode("episode-2", ["comparison", "result-summary", "validation-summary"])],
            "lesson_additions": [],
        }

        def drop_summaries(request):
            return patch(request["payload"]["output_patch_contract"], {
                "op": "replace", "path": "episode_reflections[1]",
                "value": episode("episode-2", ["comparison"]),
            })

        caller = PatchCaller(initial, drop_summaries)
        caller.max_structured_corrections = 1
        with self.assertRaisesRegex(ValidationError, "cover every selected"):
            LLMSignalMiningModel(caller).reflect_feedback(payload())

    def test_invalid_mixed_sibling_cannot_provide_other_valid_coverage(self):
        initial = {"episode_reflections": [
            episode("episode-1", ["comparison", "result-summary"]),
            episode("episode-2", ["comparison", "validation-summary"]),
        ], "lesson_additions": []}

        def inspect_only(request):
            issues = request["payload"]["validation_feedback"]["obligations"]
            for issue in issues:
                self.assertEqual(issue["other_valid_episode_coverage"], {})
                self.assertEqual(set(issue["feedback_refs_without_other_valid_episode"]),
                                 set(initial["episode_reflections"][issue["obligation_index"] - 1]["source_refs"]))
            return patch(request["payload"]["output_patch_contract"])

        caller = PatchCaller(initial, inspect_only)
        caller.max_structured_corrections = 1
        with self.assertRaises(ValidationError):
            LLMSignalMiningModel(caller).reflect_feedback(payload())
