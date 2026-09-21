"""Chain-scoped same-request correction guard (defect #11, action-plan B2 gate)."""

import json
import tempfile
import unittest
from pathlib import Path

from tests.evolution_runtime_test_support import *  # noqa: F403

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_output_validation import (
    _complete_parsed_role,
)
from stock_opportunity_agent.research.scheme_evolution import (
    CandidateExecutionRejected,
)


def _client(root: Path, *, events: list | None = None):
    return StructuredRoleClient(
        registration=get_model("deepseek-v4-flash"),
        contract=make_contract(),
        workspace=root,
        ledger=ExternalAttemptLedger(
            root / "attempts.json", max_attempts=10, max_total_cost=10
        ),
        allow_external=False,
        environ={},
        on_progress=(lambda event: events.append(event)) if events is not None else None,
    )


_KWARGS = {
    "system_prompt": "Return JSON.",
    "payload": {"fact": "anonymous"},
    "allow_outcomes": False,
    "max_output_tokens": 8000,
}


class SameRequestGuardSemanticsTest(unittest.TestCase):
    """The three request-identity semantics from the action plan's B2 gate."""

    def test_identical_request_inside_one_chain_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            events: list = []
            client = _client(Path(directory), events=events)
            with client.correction_chain(stage="blind_predictor_predict"):
                with self.assertRaises(ExternalRequestPending):
                    client.complete_json(stage="blind_predictor_predict", **_KWARGS)
                with self.assertRaises(CandidateExecutionRejected) as rejected:
                    client.complete_json(stage="blind_predictor_predict", **_KWARGS)
            self.assertIn("no-progress", str(rejected.exception))
            self.assertTrue(
                any(
                    event.get("event_type") == "correction_no_progress_blocked"
                    for event in events
                )
            )

    def test_correction_stage_repeat_is_blocked_and_base_is_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            with client.correction_chain(stage="blind_predictor_predict"):
                with self.assertRaises(ExternalRequestPending):
                    client.complete_json(
                        stage="blind_predictor_predict_correction", **_KWARGS
                    )
                # A repeated correction request is the no-progress dead loop.
                with self.assertRaises(CandidateExecutionRejected):
                    client.complete_json(
                        stage="blind_predictor_predict_correction", **_KWARGS
                    )
            # The initial stage embeds a different stage name in the request,
            # so a base-stage repeat is its own deduplication domain.
            with client.correction_chain(stage="blind_predictor_predict"):
                with self.assertRaises(ExternalRequestPending):
                    client.complete_json(stage="blind_predictor_predict", **_KWARGS)
                with self.assertRaises(CandidateExecutionRejected):
                    client.complete_json(stage="blind_predictor_predict", **_KWARGS)

    def test_outside_chain_and_across_chains_keeps_cache_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            # No chain: repeated identical requests are ordinary pending calls
            # (a supervisor retry re-runs the initial attempt in a fresh chain).
            for _ in range(2):
                with self.assertRaises(ExternalRequestPending):
                    client.complete_json(stage="blind_predictor_predict", **_KWARGS)
            # A second, independent chain may legally issue the same request:
            # different role/plan/candidate sharing one cached response.
            with client.correction_chain(stage="blind_predictor_predict"):
                with self.assertRaises(ExternalRequestPending):
                    client.complete_json(stage="blind_predictor_predict", **_KWARGS)
            with client.correction_chain(stage="signal_mining_hypotheses"):
                with self.assertRaises(ExternalRequestPending):
                    client.complete_json(stage="blind_predictor_predict", **_KWARGS)

    def test_guard_fires_before_cache_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            request_path = None
            with self.assertRaises(ExternalRequestPending) as pending:
                client.complete_json(stage="h3_compare", **_KWARGS)
            request_path = Path(pending.exception.request_path)
            request_hash = json.loads(request_path.read_text())["request_hash"]
            client.cache.store(
                request_hash,
                {
                    "json_output": {"fact": "cached"},
                    "usage": {
                        "llm_calls": 1,
                        "tokens": 1,
                        "cost": 0.0,
                        "http_attempts": 1,
                    },
                },
            )
            with client.correction_chain(stage="h3_compare"):
                # First occurrence in this chain may consume the cached entry.
                outside = client.complete_json(stage="h3_compare", **_KWARGS)
                self.assertEqual(outside[0], {"fact": "cached"})
                # The repeat must fail closed before the cache could replay it.
                with self.assertRaises(CandidateExecutionRejected):
                    client.complete_json(stage="h3_compare", **_KWARGS)

    def test_chain_scopes_do_not_leak_across_threads(self):
        import threading

        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            result: dict[str, BaseException | None] = {}

            def worker():
                try:
                    with client.correction_chain(stage="shared_stage"):
                        with self.assertRaises(ExternalRequestPending):
                            client.complete_json(stage="shared_stage", **_KWARGS)
                    # The main thread's open chain must not leak into this
                    # thread: this different-stage call is not blocked by it.
                    with self.assertRaises(ExternalRequestPending):
                        client.complete_json(stage="main_stage", **_KWARGS)
                    result["worker"] = None
                except BaseException as exc:  # noqa: BLE001
                    result["worker"] = exc

            with client.correction_chain(stage="main_stage"):
                with self.assertRaises(ExternalRequestPending):
                    client.complete_json(stage="main_stage", **_KWARGS)
                thread = threading.Thread(target=worker)
                thread.start()
                thread.join()
                # The main thread's chain must still block its own repeat.
                with self.assertRaises(CandidateExecutionRejected):
                    client.complete_json(stage="main_stage", **_KWARGS)
            self.assertIsNone(result.get("worker"))


class SameRequestGuardWiringTest(unittest.TestCase):
    def test_parsed_role_opens_chain_when_caller_supports_it(self):
        entered: list[str] = []
        exited: list[str] = []

        class ChainCaller(ScriptedRoleCaller):
            def correction_chain(self, *, stage: str):
                import contextlib

                @contextlib.contextmanager
                def _chain():
                    entered.append(stage)
                    try:
                        yield
                    finally:
                        exited.append(stage)

                return _chain()

        valid = {
            "prediction_outcome": {"correct": True},
            "decision_drivers": ["A specific supplied reason."],
            "why_prediction_failed": [],
            "misleading_signals": [],
            "ignored_evidence": [],
            "missing_information": [],
            "plan_issues": [],
        }
        caller = ChainCaller([dict(valid)])
        _complete_parsed_role(
            caller,
            stage="blind_predictor_posthoc_reflect",
            system_prompt="reflect",
            payload={"summary": "context"},
            parser=lambda value: value,
            allow_outcomes=True,
        )
        self.assertEqual(
            entered, ["blind_predictor_posthoc_reflect"]
        )
        self.assertEqual(
            exited, ["blind_predictor_posthoc_reflect"]
        )

    def test_parsed_role_without_chain_support_is_unchanged(self):
        valid = {
            "prediction_outcome": {"correct": False},
            "decision_drivers": [],
            "why_prediction_failed": ["One concrete attribution."],
            "misleading_signals": [],
            "ignored_evidence": [],
            "missing_information": [],
            "plan_issues": [],
        }
        caller = ScriptedRoleCaller([dict(valid)])
        value, _usage = _complete_parsed_role(
            caller,
            stage="blind_predictor_posthoc_reflect",
            system_prompt="reflect",
            payload={"summary": "context"},
            parser=lambda item: item,
            allow_outcomes=True,
        )
        self.assertEqual(value["why_prediction_failed"], ["One concrete attribution."])

    def test_proposer_wraps_attempts_in_a_chain(self):
        import inspect

        from stock_opportunity_agent.research.evolution_plan_roles import (
            LLMInformationPlanProposer,
        )

        source = inspect.getsource(LLMInformationPlanProposer)
        self.assertIn('chain(stage="information_plan_propose")', source)


if __name__ == "__main__":
    unittest.main()
