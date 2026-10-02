"""Identity rejection is quarantined before per-Signal validation and correction."""

import copy
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.research.evolution_transport import IdentityOutputRejected, _CaseIdentityProjection
from stock_opportunity_agent.signal_library import LLMSignalBatchInput, SignalSpec, SignalExecutionType, SignalExecutionStatus
from tests.test_same_request_guard import _client


def spec(name):
    return SignalSpec(signal_id=name, version=1, category="catalysts",
                      description="Measure disclosed events.", execution_type=SignalExecutionType.LLM,
                      source_types=("filing",), skill_file="event.md")


def row(item, summary="No visible evidence."):
    return {"signal_ref": item.ref, "result": {
        "signal_id": item.signal_id, "version": item.version,
        "state": {"value": "unavailable", "confidence": 0.0},
        "interpretation": {"summary": summary},
        "evidence": {"supporting": [], "counter": []}, "status": {"coverage": "unavailable"}}}


class IdentityOutputIsolationTests(TestCase):
    def test_quarantine_paths_restores_supplied_tokens_without_mutating_original(self):
        projection = _CaseIdentityProjection(("Acme Corporation", "ACME"), "issuer", "ACME")
        _view, inverse = projection.project({"quote": "Acme Corporation"})
        value = {"results": [{"signal_ref": "event:v1", "result": {
            "quote": "[ANON_ID_0000]", "summary": "Acme Corporation did this.",
            "unknown": "[ANON_ID_9999]"}}], "number": 1203}
        original = copy.deepcopy(value)
        safe, paths = projection.quarantine_output(value, inverse)
        self.assertEqual(paths, ("results[0].result.summary", "results[0].result.unknown"))
        self.assertEqual(safe["results"][0]["result"], {
            "quote": "Acme Corporation", "summary": None, "unknown": None})
        self.assertEqual(safe["number"], 1203)
        self.assertEqual(value, original)
        for bad_key in ("Acme Corporation", "[ANON_ID_9999]"):
            safe, paths = projection.quarantine_output({"outer": {bad_key: "x"}}, inverse)
            self.assertEqual((safe, paths), ({"outer": None}, ("outer",)))

    def run_batch(self, responses, documents=()):
        first, second = spec("event_a"), spec("event_b")

        def respond(**kwargs):
            value = responses.pop(0)
            if callable(value):
                value = value(kwargs["payload"])
            return value, AgentUsage(llm_calls=1, tokens=7, cost=0.01), None

        with tempfile.TemporaryDirectory() as directory:
            caller = _client(Path(directory))
            with caller.anonymous_case(aliases=("Acme Corporation", "ACME"), company_id="issuer", ticker="ACME"):
                with patch.object(caller, "_complete_json_request", side_effect=respond) as calls:
                    results, usage = StructuredLLMSignalRunner(caller).execute_many(
                        (LLMSignalBatchInput(first, documents, "Use only visible facts."),
                         LLMSignalBatchInput(second, documents, "Use only visible facts.")),
                        datetime(2025, 1, 1, tzinfo=timezone.utc))
                    kwargs = [call.kwargs for call in calls.call_args_list]
        return first, second, results, usage, kwargs

    def test_correct_sibling_is_retained_and_only_identity_failed_signal_is_corrected(self):
        a, b = spec("event_a"), spec("event_b")
        good = row(a)
        first, second, results, usage, calls = self.run_batch([
            {"results": [good, row(b, "Acme Corporation has no visible evidence.")]},
            {"results": [row(b)]}])
        retained = results[first.ref].to_dict()
        retained.pop("execution")
        self.assertEqual(retained, good["result"])
        self.assertEqual(results[second.ref].execution_status, SignalExecutionStatus.DOMAIN_UNAVAILABLE)
        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(usage.tokens, 14)
        self.assertEqual([item["signal_ref"] for item in calls[1]["payload"]["signals"]], [second.ref])
        self.assertNotIn("Acme", json.dumps(calls[1]["payload"]))
        self.assertIn("quarantined paths", calls[1]["payload"]["validation_feedback"][0]["validation_error"])

    def test_available_sibling_retains_literal_evidence_and_full_validation(self):
        a, b = spec("event_a"), spec("event_b")
        when = datetime(2025, 1, 1, tzinfo=timezone.utc)
        document = RawInfoDocument.create(document_id="filing-1", company_id="issuer",
            source_type="filing", published_at=when, available_at=when,
            content="The issuer disclosed a new customer agreement.")

        def initial(payload):
            good = row(a, "A customer agreement was disclosed.")
            good["result"]["state"] = {"value": "positive", "confidence": 0.8}
            good["result"]["status"] = {"coverage": "sufficient"}
            projection_id = payload["signals"][0]["eligible_projection_ids"][0]
            literal = next(item["exact_text"] for item in payload["source_projection"]
                           if item["projection_id"] == projection_id)
            good["result"]["evidence"]["supporting"] = [{
                "projection_id": projection_id, "exact_text": literal}]
            return {"results": [good, row(b, "Acme Corporation is unavailable.")]}

        first, second, results, _usage, calls = self.run_batch(
            [initial, {"results": [row(b)]}], (document,))
        self.assertEqual(results[first.ref].value.value, "positive")
        self.assertEqual(results[first.ref].supporting_evidence[0].exact_span, document.content)
        self.assertEqual([item["signal_ref"] for item in calls[1]["payload"]["signals"]], [second.ref])

    def test_repeated_violation_is_technical_failure_without_losing_correct_sibling(self):
        a, b = spec("event_a"), spec("event_b")
        first, second, results, usage, _calls = self.run_batch([
            {"results": [row(a), row(b, "Acme Corporation has no visible evidence.")]},
            {"results": [row(b, "[ANON_ID_9999]")]}])
        self.assertEqual(results[first.ref].execution_status, SignalExecutionStatus.DOMAIN_UNAVAILABLE)
        self.assertEqual(results[second.ref].execution_status, SignalExecutionStatus.VALIDATION_FAILED)
        self.assertEqual(usage.llm_calls, 2)
        self.assertFalse(results[second.ref].supporting_evidence)

    def test_unassignable_violation_quarantines_all_pending_signals(self):
        a, b = spec("event_a"), spec("event_b")
        first, second, results, _usage, calls = self.run_batch([
            {"results": [row(a), row(b)], "extra": "Acme Corporation"},
            {"results": [row(a), row(b)]}])
        self.assertEqual({item["signal_ref"] for item in calls[1]["payload"]["signals"]}, {first.ref, second.ref})
        self.assertTrue(all(item.execution_status is SignalExecutionStatus.DOMAIN_UNAVAILABLE for item in results.values()))

    def test_transport_still_rejects_identity_for_roles_without_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            caller = _client(Path(directory))
            with caller.anonymous_case(aliases=("Acme Corporation",), company_id="issuer", ticker=""):
                with patch.object(caller, "_complete_json_request", return_value=(
                        {"text": "Acme Corporation"}, AgentUsage(llm_calls=1), None)):
                    with self.assertRaises(IdentityOutputRejected) as rejected:
                        caller.complete_json(stage="blind_predictor_predict", system_prompt="Return JSON.",
                                             payload={}, allow_outcomes=False)
        self.assertEqual(rejected.exception.quarantined_output, {"text": None})
