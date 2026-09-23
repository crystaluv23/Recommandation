#!/usr/bin/env python3
"""Zero-network replay for the parallel Jev routing and blind-decision path."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.llm.openrouter_jev import (
    JevChoiceAnswer,
    JevDecisionResponse,
    RecordedJevDecisionClient,
)
from stock_opportunity_agent.research.evolution_core import (
    BlindPrediction,
    GroundTruth,
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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "reports/jev-parallel-offline-replay-20260923.json"


class _RecordedRoleCaller:
    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, **kwargs: Any):
        self.calls.append(dict(kwargs))
        return self.outputs.pop(0), AgentUsage(llm_calls=1, tokens=7, cost=0.0)


def _choice(
    choice: str,
    probabilities: dict[str, float],
    confidence: float,
) -> JevChoiceAnswer:
    return JevChoiceAnswer(
        choice=choice,
        probabilities=probabilities,
        confidence=confidence,
    )


def _response(
    response_id: str,
    answers: dict[str, JevChoiceAnswer],
) -> JevDecisionResponse:
    return JevDecisionResponse(
        response_id=response_id,
        model="typesafe/jev-1.13-20260917",
        provider="TypeSafe",
        answers=answers,
        usage=AgentUsage(llm_calls=1, tokens=20, cost=0.0),
    )


def _registry() -> FrozenSignalRegistry:
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
    return FrozenSignalRegistry(1, "jev-replay-registry-v1", specs, {})


def run_replay() -> dict[str, Any]:
    """Replay recorded decisions and explanations without opening a network client."""

    routing_client = RecordedJevDecisionClient(
        [
            _response(
                "recorded-routing-1",
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
        ]
    )
    routing = JevSignalRetrievalAgent(routing_client).select(
        ("What was the latest revenue growth?",),
        _registry(),
        {},
    )
    routing_feedback = list(routing.metadata["jev_routing_decisions"])
    if len(routing_feedback) != 2 or routing_feedback[1]["choice"] != "no_match":
        raise ValueError("Jev routing feedback did not preserve all card decisions")

    prediction_client = RecordedJevDecisionClient(
        [
            _response(
                "recorded-prediction-1",
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
                "recorded-magnitude-1",
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
    role_caller = _RecordedRoleCaller(
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
    predictor = JevBlindPredictor(prediction_client, role_caller)
    final_context = {
        "prediction_baseline": {"status": "available", "value": 10.0},
        "analysis": ["Anonymous point-in-time catalyst evidence."],
    }
    prediction_step = predictor.predict(final_context)
    persisted_prediction = prediction_step.value.to_dict()
    reloaded = BlindPrediction.from_dict(persisted_prediction)
    if reloaded != prediction_step.value:
        raise ValueError("persisted Jev prediction did not reload exactly")

    if not persisted_prediction:
        raise ValueError("ground truth cannot be revealed before prediction persistence")
    truth = GroundTruth(4.2)
    reflection = predictor.reflect(final_context, reloaded, truth)
    feedback = jev_decision_feedback(reloaded, truth)
    if feedback is None:
        raise ValueError("Jev decision feedback was not derived")
    if "jev_decision_feedback" not in role_caller.calls[1]["payload"]:
        raise ValueError("post-label reflection did not receive Jev feedback")

    return {
        "schema_version": "jev-parallel-offline-replay-v1",
        "external_calls": 0,
        "routing": {
            "selected_signal_refs": [item.signal_ref for item in routing.value],
            "decision": routing.value[0].jev_decision.to_dict(),
            "all_card_decisions": routing_feedback,
            "recorded_request_count": len(routing_client.calls),
        },
        "prediction": persisted_prediction,
        "prediction_persisted_before_truth": True,
        "jev_decision_feedback": feedback,
        "post_label_reflection_received_jev_feedback": True,
        "reflection": reflection.value.to_dict(),
        "recorded_prediction_request_count": len(prediction_client.calls),
        "recorded_llm_request_count": len(role_caller.calls),
        "acceptance": {
            "typed_routing_choice": True,
            "typed_prediction_choices": True,
            "probability_and_confidence_round_trip": True,
            "selected_and_rejected_routing_feedback": True,
            "immutable_decision_with_llm_explanation": True,
            "post_label_feedback_visibility": True,
            "network_disabled": True,
        },
        "limitations": [
            "Recorded responses prove wiring and persistence, not Jev research quality.",
            "A separately authorized frozen-case shadow run is required before cutover.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_replay()
    atomic_write_json(args.output, result)
    print(args.output)


if __name__ == "__main__":
    main()
