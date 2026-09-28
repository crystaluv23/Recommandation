"""Zero-network tests for the parallel Jev routing and prediction path."""

from __future__ import annotations

from unittest import TestCase

from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.llm.openrouter_jev import (
    JevChoiceAnswer,
    JevDecisionResponse,
    OpenRouterJevClient,
    RecordedJevDecisionClient,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    BlindPrediction,
    GroundTruth,
    SignalSelectionDecision,
    jev_decision_feedback,
)
from stock_opportunity_agent.research.evolution_jev_roles import (
    JevBlindPredictor,
    JevSignalRetrievalAgent,
)
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    SignalExecutionType,
    SignalSpec,
)
from tests.evolution_runtime_test_support import ScriptedRoleCaller


class _RecordingTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, headers, payload):
        self.calls.append((url, dict(headers), dict(payload)))
        return self.response


class _ScriptedRoleCaller(ScriptedRoleCaller):
    def complete_json(self, **kwargs):
        output, _ = super().complete_json(**kwargs)
        return output, AgentUsage(llm_calls=1, tokens=7, cost=0.01)


def _choice(choice, probabilities, confidence=0.9):
    return JevChoiceAnswer(
        choice=choice,
        probabilities=probabilities,
        confidence=confidence,
    )


def _response(response_id, answers):
    return JevDecisionResponse(
        response_id=response_id,
        model="typesafe/jev-1.13-20260917",
        provider="TypeSafe",
        answers=answers,
        usage=AgentUsage(llm_calls=1, tokens=20, cost=0.0001),
    )


class OpenRouterJevClientTests(TestCase):
    def test_decisions_request_and_response_are_typed_without_exposing_key(self):
        transport = _RecordingTransport(
            {
                "answers": {
                    "intent": {
                        "type": "choice",
                        "choice": "a",
                        "probabilities": {"a": 0.8, "b": 0.2},
                        "confidence": 0.8,
                    }
                },
                "model": "typesafe/jev-1.13-20260917",
                "provider": "TypeSafe",
                "usage": {"inputTokens": 10, "outputTokens": 2, "cost": 0.001},
            }
        )
        client = OpenRouterJevClient("secret-value", transport=transport)
        prepared = client.prepare_request(
            state={"record": "fixture"},
            questions={
                "intent": {
                    "type": "choice",
                    "instructions": "Choose one.",
                    "criteria": {"a": "A", "b": "B"},
                }
            },
        )
        self.assertEqual(prepared.url, "https://openrouter.ai/api/alpha/decisions")
        self.assertNotIn("secret-value", prepared.body.decode("utf-8"))

        response = client.decide(
            state={"record": "fixture"},
            questions=prepared.payload["questions"],
        )
        self.assertTrue(response.response_id.startswith("jev-"))
        self.assertEqual(response.answers["intent"].probabilities["a"], 0.8)
        self.assertEqual(response.usage.tokens, 12)

    def test_invalid_probability_distribution_fails_closed(self):
        with self.assertRaisesRegex(ValidationError, "sum within 0.05"):
            _choice("a", {"a": 0.8, "b": 0.8})

    def test_provider_rounded_probability_distribution_is_normalized(self):
        answer = _choice("a", {"a": 0.66, "b": 0.33})
        self.assertAlmostEqual(sum(answer.probabilities.values()), 1.0)
        self.assertAlmostEqual(answer.probabilities["a"], 2 / 3)


class JevParallelRoleTests(TestCase):
    def _registry(self):
        specs = (
            SignalSpec(
                signal_id="revenue_growth_yoy",
                version=1,
                category="fundamentals",
                description="Measures year-over-year revenue growth.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                source_types=("sec_companyfacts",),
                function="financial.revenue_growth_yoy",
            ),
            SignalSpec(
                signal_id="price_momentum_126d",
                version=1,
                category="market",
                description="Measures medium-term adjusted-price momentum.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                source_types=("price_daily",),
                function="market.price_momentum_126d",
            ),
        )
        return FrozenSignalRegistry(1, "fixture-registry", specs, {})

    def test_jev_selects_signal_and_persists_probability_feedback(self):
        response = _response(
            "jev-routing-1",
            {
                "signal_000__revenue_growth_yoy:v1": _choice(
                    "need_0",
                    {"need_0": 0.82, "context_only": 0.08, "no_match": 0.10},
                    0.82,
                ),
                "signal_001__price_momentum_126d:v1": _choice(
                    "no_match",
                    {"need_0": 0.12, "context_only": 0.08, "no_match": 0.80},
                    0.80,
                ),
            },
        )
        client = RecordedJevDecisionClient([response])
        result = JevSignalRetrievalAgent(client).select(
            ("What was the latest revenue growth?",),
            self._registry(),
            {},
        )
        self.assertEqual(
            tuple(item.signal_ref for item in result.value),
            ("revenue_growth_yoy:v1",),
        )
        serialized = result.value[0].to_dict()
        self.assertEqual(serialized["jev_decision"]["confidence"], 0.82)
        self.assertEqual(
            serialized["jev_decision"]["probabilities"]["need_0"],
            0.82,
        )
        self.assertEqual(SignalSelectionDecision.from_dict(serialized), result.value[0])
        routing_feedback = result.metadata["jev_routing_decisions"]
        self.assertEqual(len(routing_feedback), 2)
        self.assertEqual(routing_feedback[1]["choice"], "no_match")
        self.assertEqual(routing_feedback[1]["confidence"], 0.80)
        self.assertEqual(len(client.calls), 1)

    def test_jev_prediction_is_immutable_while_llm_explains_and_reflects(self):
        jev = RecordedJevDecisionClient(
            [
                _response(
                    "jev-prediction-1",
                    {
                        "candidate_judgment": _choice(
                            "possible",
                            {
                                "likely": 0.18,
                                "possible": 0.62,
                                "unlikely": 0.12,
                                "insufficient_information": 0.08,
                            },
                            0.62,
                        ),
                    },
                ),
                _response(
                    "jev-magnitude-1",
                    {
                        "magnitude": _choice(
                            "3-10x",
                            {
                                "2-3x": 0.20,
                                "3-10x": 0.70,
                                "10x+": 0.10,
                            },
                            0.70,
                        ),
                    },
                )
            ]
        )
        caller = _ScriptedRoleCaller(
            [
                {
                    "key_reasons": [
                        "The supplied catalyst and growth evidence support a candidate."
                    ],
                    "uncertainties": ["Magnitude remains uncertain."],
                },
                {
                    "prediction_outcome": {"correct": True},
                    "decision_drivers": [
                        "The supplied catalyst supported the saved positive decision."
                    ],
                    "why_prediction_failed": [],
                    "misleading_signals": [],
                    "ignored_evidence": [],
                    "missing_information": [],
                    "plan_issues": [],
                },
            ]
        )
        predictor = JevBlindPredictor(jev, caller)
        prediction_step = predictor.predict(
            {
                "analysis_prompt": (
                    "Do not generate a prediction and require a quantified bridge."
                ),
                "context_contract": {"kind": "presentation metadata"},
                "prediction_baseline": {"status": "available", "value": 10.0},
                "analysis": ["Anonymous point-in-time catalyst evidence."],
            }
        )
        prediction = prediction_step.value
        self.assertEqual(prediction.candidate_judgment.value, "possible")
        self.assertEqual(prediction.magnitude.value, "3-10x")
        self.assertEqual(prediction.session_id, "jev-prediction-1")
        self.assertEqual(len(prediction.jev_decisions), 2)
        self.assertNotIn("revealed_ground_truth", caller.calls[0]["payload"])

        reloaded = BlindPrediction.from_dict(prediction.to_dict())
        self.assertEqual(reloaded, prediction)
        truth = GroundTruth(4.2)
        feedback = jev_decision_feedback(prediction, truth)
        self.assertAlmostEqual(
            feedback["candidate_judgment"][
                "probability_assigned_to_realized_binary"
            ],
            0.80,
        )
        self.assertEqual(
            feedback["magnitude"]["probability_assigned_to_true_magnitude"],
            0.70,
        )
        self.assertEqual(len(jev.calls), 2)
        self.assertEqual(
            jev.calls[1]["state"]["immutable_candidate_judgment"],
            "possible",
        )
        self.assertNotIn(
            "analysis_prompt", jev.calls[0]["state"]["evidence_context"]
        )
        self.assertNotIn(
            "context_contract", jev.calls[0]["state"]["evidence_context"]
        )
        self.assertIn("decision_contract", jev.calls[0]["state"])

        reflection = predictor.reflect(
            {"analysis": ["Anonymous point-in-time catalyst evidence."]},
            prediction,
            truth,
        )
        self.assertTrue(reflection.value.correct)
        self.assertIn("jev_decision_feedback", caller.calls[1]["payload"])
        self.assertEqual(
            caller.calls[1]["payload"]["original_prediction"]["magnitude"],
            "3-10x",
        )

    def test_negative_judgment_skips_magnitude_request(self):
        client = RecordedJevDecisionClient(
            [
                _response(
                    "jev-negative",
                    {
                        "candidate_judgment": _choice(
                            "unlikely",
                            {
                                "likely": 0.05,
                                "possible": 0.10,
                                "unlikely": 0.75,
                                "insufficient_information": 0.10,
                            },
                        ),
                    },
                )
            ]
        )
        caller = _ScriptedRoleCaller(
            [{"key_reasons": ["Evidence is insufficient."], "uncertainties": []}]
        )
        prediction = JevBlindPredictor(client, caller).predict(
            {"analysis": ["fixture"]}
        ).value
        self.assertFalse(prediction.is_surge)
        self.assertIsNone(prediction.magnitude)
        self.assertEqual(len(prediction.jev_decisions), 1)
        self.assertEqual(len(client.calls), 1)
        feedback = jev_decision_feedback(prediction, GroundTruth(1.1))
        self.assertFalse(feedback["magnitude"]["requested"])
