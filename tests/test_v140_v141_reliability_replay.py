"""Zero-network regressions for the V140/V141 reliability findings."""

from unittest import TestCase

from scripts.replay_v140_v141_reliability import run_replay
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import StructuredValidationError, ValidationIssue
from stock_opportunity_agent.research.evolution_core import CandidateExecutionRejected
from stock_opportunity_agent.research.evolution_output_validation import (
    _complete_parsed_role,
    _research_state_evidence_grounding_fallback,
)
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine


class V140V141ReliabilityReplayTests(TestCase):
    def test_persisted_artifacts_replay_without_network(self) -> None:
        result = run_replay()

        self.assertEqual(result["network_calls"], 0)
        self.assertGreater(
            result["jev"]["v141"]["diagnostics"]["direction"]["case_count"],
            0,
        )
        self.assertIn(
            "choice_counts",
            result["jev"]["v141"]["diagnostics"]["magnitude"],
        )
        self.assertTrue(
            result["correction_recovery"]["no_progress_frontier"][
                "typed_state_reload"
            ]
        )
        self.assertTrue(
            result["correction_recovery"]["same_signal_coordinate_frontier"][
                "removed_paths"
            ]
        )
        self.assertEqual(
            result["mixed_modality"]["classification"], "mixed"
        )
        self.assertFalse(result["mixed_modality"]["materialization_allowed"])

        pure_narrative_numeric = {
            "measurement": {
                "observable": "disclosed_contract_count",
                "value_kind": "numeric",
                "normalization": "count qualifying disclosures",
                "predicate": {"modality": "narrative"},
            },
            "evidence_refs": ["event-001", "document-news:case:news:001"],
        }
        self.assertEqual(
            SignalEvolutionEngine._candidate_modality(pure_narrative_numeric),
            "narrative",
        )

    def test_identical_correction_block_enters_deterministic_fallback(self) -> None:
        invalid = {
            "supporting_evidence": [
                {"claim": "Unsupported 42"},
                {"claim": "Grounded sibling"},
            ],
            "current_beliefs": ["Unsupported 42", "Grounded sibling"],
        }
        issue = ValidationIssue(
            code="claim_quantity_not_supported",
            message="Unsupported quantity.",
            paths=("supporting_evidence[0].claim",),
            allowed_repairs=("replace", "remove", "add"),
            dependent_paths=("current_beliefs[0]",),
        )

        class NoProgressCaller:
            max_structured_corrections = 2
            on_progress = None

            def __init__(self) -> None:
                self.calls = 0

            def complete_json(self, **kwargs):
                self.calls += 1
                if self.calls == 3:
                    raise CandidateExecutionRejected(
                        kwargs["stage"],
                        "no-progress identical correction request replay-hash",
                    )
                return dict(invalid), AgentUsage(llm_calls=1)

        def parse(value):
            if any(
                row.get("claim") == "Unsupported 42"
                for row in value.get("supporting_evidence", ())
            ):
                raise StructuredValidationError([issue])
            return value

        caller = NoProgressCaller()
        value, usage = _complete_parsed_role(
            caller,
            stage="research_controller_reflect",
            system_prompt="Return the fixed contract.",
            payload={},
            parser=parse,
            allow_outcomes=False,
            stable_correction_prefix=True,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )

        self.assertEqual(
            value["supporting_evidence"], [{"claim": "Grounded sibling"}]
        )
        self.assertEqual(value["current_beliefs"], ["Grounded sibling"])
        # With the fallback promoted ahead of the LLM round for mechanical
        # quantity failures, the same deterministic outcome is reached on
        # the first answer; the no-progress transport guard scenario the
        # historical replay exercised remains covered by transport tests.
        self.assertEqual(caller.calls, 1)
        self.assertEqual(usage.llm_calls, 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
