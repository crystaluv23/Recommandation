"""Correction fitting accounts for the full transmitted feedback envelope."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.evolution_core import RuntimeBudgetExceeded
from stock_opportunity_agent.research.evolution_signal_roles import (
    StructuredLLMSignalRunner, _LLM_SIGNAL_BATCH_SYSTEM_PROMPT, _shared_llm_signal_projection,
)
from stock_opportunity_agent.signal_library import (
    LLMSignalBatchInput, SignalExecutionStatus, SignalExecutionType, SignalSpec,
)


class ReservingCaller:
    """Enforce one consistent byte-plus-output reservation before scripted replies."""

    def __init__(self, callback, *, step_tokens=50):
        self.callback = callback
        self.step_tokens = step_tokens
        self.calls = []
        self.estimates = []

    def estimate_json_request_tokens(self, **kwargs):
        self.estimates.append(deepcopy(kwargs))
        return (len(json.dumps(kwargs["payload"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8"))
            + len(kwargs["system_prompt"].encode("utf-8")) + kwargs["max_output_tokens"])

    def complete_json(self, **kwargs):
        reservation = self.estimate_json_request_tokens(**{
            key: kwargs[key] for key in ("system_prompt", "payload", "max_output_tokens")
        })
        if reservation > kwargs["max_request_tokens"]:
            raise RuntimeBudgetExceeded("complete correction envelope exceeds remaining budget")
        self.calls.append(deepcopy(kwargs))
        return self.callback(kwargs), AgentUsage(llm_calls=1, tokens=self.step_tokens)


class SignalCorrectionReservationTests(TestCase):
    def setUp(self):
        self.as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.literal = "Management reaffirmed prior guidance."
        self.document = RawInfoDocument.create(
            document_id="fixture_filing", company_id="opaque_fixture", source_type="filing",
            published_at=self.as_of, available_at=self.as_of,
            content=self.literal + " Routine disclosure about operations." * 1500,
        )
        self.inputs = tuple(LLMSignalBatchInput(SignalSpec(
            signal_id=name, version=1, category="management", description="Measure guidance.",
            execution_type=SignalExecutionType.LLM, source_types=("filing",), skill_file="skill.md",
            parameters={"result_required_evidence_phrases": ["guidance"]},
        ), (self.document,), "Measure guidance.") for name in ("pending", "sibling"))

    def row(self, call, signal, *, invalid=False):
        projection = next(row for row in call["payload"]["source_projection"] if self.literal in row["exact_text"])
        return {"signal_ref": signal["signal_ref"], "result": {
            "signal_id": signal["signal_spec"]["signal_id"], "version": 1,
            "state": {"value": "unavailable" if invalid else "neutral", "confidence": 0.5},
            "interpretation": {"summary": "Fixture unchanged guidance."},
            "evidence": {"supporting": [], "counter": [{
                "projection_id": projection["projection_id"], "exact_text": self.literal,
            }]}, "status": {"coverage": "unavailable" if invalid else "sufficient"},
        }}

    def test_full_correction_fit_preserves_accepted_sibling_and_paid_usage(self):
        def answer(call):
            correcting = "validation_feedback" in call["payload"]
            return {"results": [self.row(call, row,
                invalid=not correcting and row["signal_ref"] == "pending:v1")
                for row in call["payload"]["signals"]]}

        caller = ReservingCaller(answer, step_tokens=800)
        runner = StructuredLLMSignalRunner(caller)
        projections, lineage = _shared_llm_signal_projection(self.inputs)
        initial = runner._batch_payload(self.inputs, projections, lineage, self.as_of, budget_trimmed=False)
        ceiling = caller.estimate_json_request_tokens(
            system_prompt=_LLM_SIGNAL_BATCH_SYSTEM_PROMPT, payload=initial, max_output_tokens=4000,
        ) + 10
        runner.set_request_token_budget(ceiling)
        results, usage = runner.execute_many(self.inputs, self.as_of)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(usage.tokens, 1600)
        self.assertEqual(results["sibling:v1"].execution_status, SignalExecutionStatus.SUCCESS)
        self.assertEqual(results["pending:v1"].execution_status, SignalExecutionStatus.SUCCESS)
        correction = caller.calls[1]
        self.assertEqual(correction["payload"]["batch_signal_refs"], ["pending:v1"])
        self.assertTrue(correction["payload"]["context_contract"]["budget_trimmed"])
        self.assertTrue(correction["payload"]["signals"][0]["eligible_projection_ids"])
        self.assertEqual(len(correction["payload"]["validation_feedback"]), 1)
        self.assertEqual(correction["max_request_tokens"], ceiling - 800)
        unfitted = runner._batch_payload(
            (self.inputs[0],), projections, lineage, self.as_of, budget_trimmed=False,
            validation_feedback=tuple(correction["payload"]["validation_feedback"]),
        )
        without_feedback = {key: value for key, value in unfitted.items() if key != "validation_feedback"}
        self.assertLessEqual(caller.estimate_json_request_tokens(
            system_prompt=_LLM_SIGNAL_BATCH_SYSTEM_PROMPT, payload=without_feedback, max_output_tokens=4000,
        ), correction["max_request_tokens"])
        self.assertGreater(caller.estimate_json_request_tokens(
            system_prompt=_LLM_SIGNAL_BATCH_SYSTEM_PROMPT, payload=unfitted, max_output_tokens=4000,
        ), correction["max_request_tokens"])
        self.assertTrue(any(row["payload"] == correction["payload"] for row in caller.estimates[:-1]))
        self.assertEqual(self.document.content, self.literal + " Routine disclosure about operations." * 1500)

    def test_minimum_correction_that_does_not_fit_remains_budget_blocked(self):
        inputs = (LLMSignalBatchInput(self.inputs[0].spec, (), "Measure guidance."),)

        def invalid(call):
            return {"results": []}

        caller = ReservingCaller(invalid)
        runner = StructuredLLMSignalRunner(caller)
        initial = runner._batch_payload(inputs, [], {}, self.as_of, budget_trimmed=False)
        runner.set_request_token_budget(caller.estimate_json_request_tokens(
            system_prompt=_LLM_SIGNAL_BATCH_SYSTEM_PROMPT, payload=initial, max_output_tokens=4000,
        ) + 10)
        results, usage = runner.execute_many(inputs, self.as_of)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(usage.tokens, 50)
        self.assertEqual(results["pending:v1"].execution_status, SignalExecutionStatus.BUDGET_BLOCKED)
        self.assertIn("exact reservation", results["pending:v1"].execution_error_message)
