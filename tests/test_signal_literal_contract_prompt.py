"""Production extraction prompts expose unchanged literal and unit contracts."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.signal_library import (
    LLMSignalBatchInput, SignalEvidence, SignalExecutionStatus, SignalExecutionType,
    SignalResult, SignalSpec, SignalValue, validate_signal_result,
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
            self.assertIn("First decide whether", call["system_prompt"])
            self.assertIn("Once the measured-object applicability and all mandatory evidence", call["system_prompt"])
            self.assertIn("readable off-object text", call["system_prompt"])
            self.assertIn("an unrelated third-party action does not establish", call["system_prompt"])
            self.assertIn("skill declares the relevant relationship", call["system_prompt"])
            self.assertNotIn("Return unavailable with no evidence only when", call["system_prompt"])
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

    def validate_quotes(self, quotes, *, phrase="credit facility", value=SignalValue.NEUTRAL,
                        same_document=False, split_groups=False):
        """Exercise the actual owner with independent, source-valid literal spans."""
        spec = replace(self.spec, parameters={"result_required_evidence_phrases": [phrase]})
        if same_document:
            documents = (self.document(" Separate context. ".join(quotes)),)
        else:
            documents = tuple(replace(self.document(text), document_id=f"filing_{i}")
                              for i, text in enumerate(quotes))
        evidence = tuple(SignalEvidence(
            document_id=documents[0 if same_document else i].document_id,
            exact_span=text, timestamp=self.as_of,
        ) for i, text in enumerate(quotes))
        result = SignalResult(
            signal_id=spec.signal_id, version=spec.version, value=value, confidence=.5,
            interpretation="Literal measured-object fixture.",
            supporting_evidence=evidence[:1] if split_groups else (),
            counter_evidence=evidence[1:] if split_groups else evidence,
        )
        validate_signal_result(spec, result, documents, as_of=self.as_of)

    def test_phrase_cannot_cross_documents_citations_or_evidence_groups(self):
        for state in (SignalValue.POSITIVE, SignalValue.NEUTRAL, SignalValue.NEGATIVE):
            for same_document in (False, True):
                for split_groups in (False, True):
                    with self.subTest(state=state, same_document=same_document,
                                      split_groups=split_groups):
                        with self.assertRaisesRegex(ValidationError, "within one exact"):
                            self.validate_quotes(
                                ("The board reviewed credit.", "Facility output is unchanged."),
                                value=state, same_document=same_document,
                                split_groups=split_groups,
                            )

    def test_one_complete_literal_preserves_case_spacing_and_punctuation_rules(self):
        for text in ("The CREDIT facility is unchanged.",
                     "The credit-facility is unchanged.",
                     "The credit\n facility is unchanged."):
            with self.subTest(text=text):
                self.validate_quotes(("Other operations continued.", text), split_groups=True)

    def test_single_word_phrase_still_requires_word_boundaries(self):
        with self.assertRaisesRegex(ValidationError, "result_required_evidence_phrases"):
            self.validate_quotes(("Pipeline capacity expanded.",), phrase="PIPE")
        self.validate_quotes(("The PIPE financing closed.",), phrase="PIPE")

    def test_interpretation_cannot_supply_a_missing_literal_phrase(self):
        with self.assertRaisesRegex(ValidationError, "within one exact"):
            self.validate_quotes(("Revenue increased.",), phrase="measured-object fixture")

    def test_failed_compound_phrase_corrects_only_pending_signal_and_keeps_sibling(self):
        doc = self.document(
            "Background. The board reviewed credit. Facility output is unchanged. "
            "Current guidance is unchanged. Closing context."
        )
        compound = replace(self.spec, signal_id="fixture_financing",
                           parameters={"result_required_evidence_phrases": ["credit facility"]})
        initial = {}

        def answer(call):
            payload = call["payload"]
            projection = payload["source_projection"][0]
            rows = []
            for signal in payload["signals"]:
                spec = self.spec if signal["signal_ref"] == self.spec.ref else compound
                correction = "validation_feedback" in payload
                unavailable = correction and spec == compound
                quotes = ([] if unavailable else ["Current guidance is unchanged."]
                          if spec == self.spec else ["The board reviewed credit.",
                                                    "Facility output is unchanged."])
                row = {"signal_ref": spec.ref, "result": {
                    "signal_id": spec.signal_id, "version": spec.version,
                    "state": {"value": "unavailable" if unavailable else "neutral", "confidence": .5},
                    "interpretation": {"summary": "Fixture measured object."},
                    "evidence": {"supporting": [], "counter": [
                        {"projection_id": projection["projection_id"], "exact_text": quote}
                        for quote in quotes]},
                    "status": {"coverage": "unavailable" if unavailable else "sufficient"},
                }}
                rows.append(row)
                if not correction:
                    initial[spec.ref] = deepcopy(row)
            return {"results": rows}

        caller = PatchCaller(answer, answer)
        results, usage = StructuredLLMSignalRunner(caller).execute_many(
            tuple(LLMSignalBatchInput(spec, (doc,), "Apply the measured-object contract.")
                  for spec in (self.spec, compound)), self.as_of,
        )
        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(results[self.spec.ref].execution_status, SignalExecutionStatus.SUCCESS)
        self.assertEqual(results[compound.ref].execution_status, SignalExecutionStatus.DOMAIN_UNAVAILABLE)
        self.assertEqual(results[self.spec.ref].counter_evidence[0].exact_span,
                         initial[self.spec.ref]["result"]["evidence"]["counter"][0]["exact_text"])
        self.assertEqual([x["signal_ref"] for x in caller.calls[1]["payload"]["signals"]],
                         [compound.ref])
        feedback = caller.calls[1]["payload"]["validation_feedback"][0]
        self.assertIn("within one exact", feedback["validation_error"])
        self.assertIn("within one complete literal", feedback["required_action"])
        self.assertEqual(doc.content_hash, self.document(doc.content).content_hash)

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
