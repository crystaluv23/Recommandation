"""Per-Signal evidence identity and coverage-preserving overflow partitions."""

from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.llm.openai import OpenAIClientError
from stock_opportunity_agent.research.evolution_core import RuntimeBudgetExceeded
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner, _shared_llm_signal_projection
from stock_opportunity_agent.signal_library import LLMSignalBatchInput, SignalExecutionStatus, SignalExecutionType, SignalRetrievalPolicy, SignalSpec


class SignalViewStabilityTests(TestCase):
    as_of = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def item(self, name, content, *, document_id=None):
        spec = SignalSpec(signal_id=name, version=1, category="catalysts", description=f"Measure {name}.",
            execution_type=SignalExecutionType.LLM, source_types=("filing",), skill_file="skill.md",
            retrieval_policy=SignalRetrievalPolicy(query_terms=(name,)))
        document = RawInfoDocument.create(document_id=document_id or name, company_id="issuer",
            source_type="filing", published_at=self.as_of, available_at=self.as_of, content=content)
        return LLMSignalBatchInput(spec, (document,), f"Measure {name} from literal evidence.")

    def test_peer_selection_does_not_change_own_view_or_citation_scope(self):
        content = "Guidance outlook current prior numerical comparison. " * 900 + "Financing listing offering debt cash liquidity. " * 900
        first = self.item("guidance", content, document_id="shared-filing")
        second = self.item("financing", content, document_id="shared-filing")
        joint, joint_lineage = _shared_llm_signal_projection((first, second))
        runner = StructuredLLMSignalRunner(None)
        payload = runner._batch_payload((first, second), joint, joint_lineage, self.as_of, budget_trimmed=False)
        for item in (first, second):
            single, _lineage = _shared_llm_signal_projection((item,))
            owned = next(row for row in payload["signals"] if row["signal_ref"] == item.spec.ref)
            self.assertEqual(set(owned["eligible_projection_ids"]), {row["projection_id"] for row in single})
        self.assertEqual(_shared_llm_signal_projection((second, first))[0], joint)

    def test_partition_budget_preserves_successful_sibling_and_actual_usage(self):
        inputs = (self.item("guidance", "Guidance disclosure. " * 4000), self.item("financing", "Financing disclosure. " * 4000))
        class Caller:
            calls = 0
            def estimate_json_request_tokens(self, **kwargs):
                return 7000
            def complete_json(self, **kwargs):
                if kwargs["max_request_tokens"] < 7000:
                    raise RuntimeBudgetExceeded("Remaining case budget cannot reserve this request")
                self.calls += 1
                item = kwargs["payload"]["signals"][0]
                return {"results": [{"signal_ref": item["signal_ref"], "result": {
                    "signal_id": item["signal_spec"]["signal_id"], "version": 1,
                    "state": {"value": "unavailable", "confidence": 0}, "interpretation": {"summary": "No supported comparison."},
                    "evidence": {"supporting": [], "counter": []}, "status": {"coverage": "unavailable"}}}]}, AgentUsage(llm_calls=1, tokens=4000)
        caller = Caller()
        runner = StructuredLLMSignalRunner(caller)
        runner.set_request_token_budget(10000)
        results, usage = runner.execute_many(inputs, self.as_of)
        self.assertEqual(caller.calls, 1)
        self.assertEqual((usage.llm_calls, usage.tokens), (1, 4000))
        self.assertEqual(results[inputs[0].spec.ref].execution_status, SignalExecutionStatus.DOMAIN_UNAVAILABLE)
        self.assertEqual(results[inputs[1].spec.ref].execution_status, SignalExecutionStatus.BUDGET_BLOCKED)

    def test_partition_provider_failure_propagates(self):
        inputs = (self.item("guidance", "Guidance disclosure. " * 4000), self.item("financing", "Financing disclosure. " * 4000))
        class Caller:
            calls = 0
            def complete_json(self, **kwargs):
                self.calls += 1
                if self.calls == 2:
                    raise OpenAIClientError("Provider connection failure")
                item = kwargs["payload"]["signals"][0]
                return {"results": [{"signal_ref": item["signal_ref"], "result": {
                    "signal_id": item["signal_spec"]["signal_id"], "version": 1,
                    "state": {"value": "unavailable", "confidence": 0}, "interpretation": {"summary": "No supported comparison."},
                    "evidence": {"supporting": [], "counter": []}, "status": {"coverage": "unavailable"}}}]}, AgentUsage(llm_calls=1, tokens=10)
        caller = Caller()
        with self.assertRaises(OpenAIClientError):
            StructuredLLMSignalRunner(caller).execute_many(inputs, self.as_of)
        self.assertEqual(caller.calls, 2)
