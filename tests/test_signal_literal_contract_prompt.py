"""Production extraction prompts expose unchanged literal and unit contracts."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.signal_library import (
    SignalExecutionStatus, SignalExecutionType, SignalSpec, SignalValue,
)
from tests.test_evolution_state_patch import PatchCaller


class SignalLiteralContractPromptTests(TestCase):
    def setUp(self):
        self.as_of = datetime(2025, 7, 31, tzinfo=timezone.utc)
        self.spec = SignalSpec(
            signal_id="fixture_guidance", version=1, category="management",
            description="Compare explicit current and prior guidance.",
            execution_type=SignalExecutionType.LLM, source_types=("filing",),
            skill_file="skill.md", parameters={"result_required_evidence_phrases": ["guidance"]},
        )

    def document(self, text):
        return RawInfoDocument.create(
            document_id="fixture_filing", company_id="opaque_fixture", source_type="filing",
            published_at=self.as_of, available_at=self.as_of, content=text,
        )

    def output(self, call, *, unavailable=False):
        """Script explicit authored output using only the production projection."""
        projection = call["payload"]["source_projection"][0]
        return {"results": [{"signal_ref": self.spec.ref, "result": {
            "signal_id": self.spec.signal_id, "version": self.spec.version,
            "state": {"value": "unavailable" if unavailable else "neutral", "confidence": 0.5},
            "interpretation": {"summary": "Fixture unavailable measured object." if unavailable else "Fixture unchanged guidance."},
            "evidence": {"supporting": [], "counter": [] if unavailable else [{
                "projection_id": projection["projection_id"], "exact_text": projection["exact_text"],
            }]},
            "status": {"coverage": "unavailable" if unavailable else "sufficient"},
        }}]}

    def execute(self, caller, text):
        return StructuredLLMSignalRunner(caller).execute(
            self.spec, (self.document(text),), "Compare explicit guidance.", self.as_of,
        )

    def test_initial_prompt_and_correction_action_have_the_same_mandatory_contract(self):
        initial = []

        def invalid(call):
            value = self.output(call)
            initial.append(deepcopy(value))
            return value

        caller = PatchCaller(invalid, lambda call: self.output(call, unavailable=True))
        result, usage = self.execute(caller, "Revenue grew year over year.")
        self.assertEqual(result.execution_status, SignalExecutionStatus.DOMAIN_UNAVAILABLE)
        self.assertEqual(usage.llm_calls, 2)
        action = caller.calls[1]["payload"]["validation_feedback"][0]["required_action"]
        self.assertIn("only when all mandatory evidence requirements still hold", action)
        self.assertIn("result_required_evidence_phrases", action)
        self.assertIn("unavailable coverage and empty supporting/counter arrays", action)
        self.assertEqual(caller.calls[0]["payload"]["source_projection"], caller.calls[1]["payload"]["source_projection"])
        self.assertEqual(initial[0]["results"][0]["result"]["state"]["value"], "neutral")
        for call in caller.calls:
            self.assertIn("general business commentary cannot replace the measured object", call["system_prompt"])
            self.assertIn("only if it supports the same measured claim", call["system_prompt"])
            self.assertIn("compatible units", call["system_prompt"])
            self.assertIn("conversion must be supported by visible source evidence", call["system_prompt"])

    def test_valid_neutral_measured_object_remains_available(self):
        caller = PatchCaller(self.output)
        result, usage = self.execute(caller, "Current guidance is unchanged from prior guidance.")
        self.assertEqual(result.execution_status, SignalExecutionStatus.SUCCESS)
        self.assertEqual(result.value, SignalValue.NEUTRAL)
        self.assertEqual(len(result.counter_evidence), 1)
        self.assertEqual(usage.llm_calls, 1)

    def test_repeated_missing_required_phrase_still_fails_validation(self):
        caller = PatchCaller(self.output, self.output)
        result, usage = self.execute(caller, "Revenue grew year over year.")
        self.assertEqual(result.execution_status, SignalExecutionStatus.VALIDATION_FAILED)
        self.assertEqual(usage.llm_calls, 2)
        self.assertIn("result_required_evidence_phrases", result.execution_error_message)

    def test_unavailable_with_retained_evidence_is_not_silently_accepted(self):
        def invalid(call):
            value = self.output(call)
            value["results"][0]["result"]["state"]["value"] = "unavailable"
            value["results"][0]["result"]["status"]["coverage"] = "unavailable"
            return value

        caller = PatchCaller(invalid, invalid)
        result, usage = self.execute(caller, "Current guidance is unchanged from prior guidance.")
        self.assertEqual(result.execution_status, SignalExecutionStatus.VALIDATION_FAILED)
        self.assertIn("unavailable signal result cannot carry evidence", result.execution_error_message)
        self.assertEqual(usage.llm_calls, 2)
