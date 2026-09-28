"""Offline acceptance over real historical reflection and correction artifacts."""

from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.evolution_core import (
    CandidateExecutionRejected, CaseReflectionEvidence, MagnitudeClass, RuntimeBudgetExceeded,
)
from stock_opportunity_agent.research.evolution_plan_roles import _ReflectionMemoryCaller
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
from tests.scheme_evolution_test_support import make_trajectory

from scripts.replay_incremental_reflection_memory import (
    HistoricalSources,
    V126,
    V138,
    V141,
    deny_network,
    run_replay,
)


class OfflineReplayBoundaryTests(TestCase):
    def test_invalid_and_repeated_memory_reads_preserve_consumed_usage(self) -> None:
        trajectory = make_trajectory("read_boundary", 15.0, True, MagnitudeClass.TWO_TO_THREE)
        index = ReflectionMemoryIndex.from_case_rows([
            CaseReflectionEvidence.from_trajectory(trajectory, case_index=1).to_model_dict(),
        ], owner_ref="offline-plan")
        source_ref = index.source_catalog()[0]["source_ref"]
        scenarios = (
            ("missing", {"read_refs": ["reflection_source:missing"]}, CandidateExecutionRejected),
            ("duplicate", {"read_refs": [source_ref]}, CandidateExecutionRejected),
            ("list_level", {"browse_memory": {"cursor": 0, "level": []}}, CandidateExecutionRejected),
            ("object_level", {"browse_memory": {"cursor": 0, "level": {}}}, CandidateExecutionRejected),
            ("budget", RuntimeBudgetExceeded("scripted budget", AgentUsage(llm_calls=1, tokens=3)), RuntimeBudgetExceeded),
            ("provider", CandidateExecutionRejected("plan_critic", "scripted failure", AgentUsage(llm_calls=1, tokens=3)), CandidateExecutionRejected),
        )
        for name, second, error_class in scenarios:
            with self.subTest(name=name):
                class Caller:
                    def __init__(self):
                        self.calls = []

                    def complete_json(self, **kwargs):
                        self.calls.append(kwargs)
                        if len(self.calls) == 1:
                            return {"read_refs": [source_ref]}, AgentUsage(llm_calls=1, tokens=7)
                        if isinstance(second, Exception):
                            raise second
                        return second, AgentUsage(llm_calls=1, tokens=3)

                caller = Caller()
                wrapped = _ReflectionMemoryCaller(caller, index, role="plan_critic", aliases=())
                with deny_network(), self.assertRaises(error_class) as caught:
                    wrapped.complete_json(
                        stage="plan_critic", payload={}, max_request_tokens=100,
                        system_prompt="Offline source-read boundary test.", allow_outcomes=True,
                    )
                self.assertEqual(caught.exception.usage.llm_calls, 2)
                self.assertEqual(caught.exception.usage.tokens, 10)
                self.assertEqual(caller.calls[1]["max_request_tokens"], 93)
                self.assertEqual(len(caller.calls[1]["payload"]["memory_disclosures"]), 1)
                self.assertEqual(len(wrapped.disclosures), 1)
                if isinstance(caught.exception, CandidateExecutionRejected):
                    self.assertEqual(caught.exception.stage, "plan_critic")

    def test_network_guard_rejects_dns_and_direct_socket_connections(self) -> None:
        with deny_network() as attempts:
            with self.assertRaisesRegex(AssertionError, "network is forbidden"):
                socket.getaddrinfo("provider.example", 443)
            with socket.socket() as connection:
                with self.assertRaisesRegex(AssertionError, "network is forbidden"):
                    connection.connect(("127.0.0.1", 443))
        self.assertEqual(attempts["network_attempts"], 2)

    def test_historical_mutation_is_detected_before_success_is_reported(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "immutable.json"
            path.write_text('{"original": true}', encoding="utf-8")
            sources = HistoricalSources()
            sources.read(path)
            path.write_text('{"original": false}', encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "source was rewritten"):
                sources.verify()


@skipUnless(
    all(path.exists() for path in (V126, V138, V141)),
    "local immutable V126/V138/V141 artifacts are not present",
)
class HistoricalReflectionReplayTests(TestCase):
    def test_production_contract_replay_preserves_real_evidence_without_network(self) -> None:
        result = run_replay()
        self.assertEqual(result["external_model_calls"], 0)
        self.assertEqual(result["network_attempts"], 0)
        self.assertEqual(result["historical_reflections"]["case_count"], 48)
        self.assertFalse(
            result["historical_reflections"]["false_success"]["canonical_binary_correct"]
        )
        self.assertTrue(all(row["unchanged"] for row in result["source_hashes"]))
