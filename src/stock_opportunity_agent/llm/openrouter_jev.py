"""Typed OpenRouter Jev Decisions API boundary."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.llm.openai import (
    HttpTransport,
    PreparedJsonRequest,
    UrllibTransport,
)
from stock_opportunity_agent.models import ValidationError


DEFAULT_JEV_MODEL = "typesafe/jev-1.13"
DEFAULT_JEV_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_OPENROUTER_API_KEY_ENV_VAR = "OPENROUTER_API_KEY"
MAX_PROBABILITY_ROUNDING_DRIFT = 0.05


@dataclass(frozen=True)
class JevChoiceAnswer:
    """One validated closed-choice answer returned by Jev."""

    choice: str
    probabilities: Mapping[str, float]
    confidence: float

    def __post_init__(self) -> None:
        if not self.choice.strip():
            raise ValidationError("Jev choice must not be empty")
        probabilities = {str(key): float(value) for key, value in self.probabilities.items()}
        if self.choice not in probabilities:
            raise ValidationError("Jev choice must be present in probabilities")
        if not probabilities or any(
            not math.isfinite(value) or value < 0 or value > 1
            for value in probabilities.values()
        ):
            raise ValidationError("Jev probabilities must be finite values in [0, 1]")
        probability_sum = sum(probabilities.values())
        if (
            probability_sum <= 0
            or abs(probability_sum - 1.0)
            > MAX_PROBABILITY_ROUNDING_DRIFT + 1e-12
        ):
            raise ValidationError(
                "Jev rounded probabilities must sum within 0.05 of one"
            )
        probabilities = {
            key: value / probability_sum for key, value in probabilities.items()
        }
        confidence = float(self.confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValidationError("Jev confidence must be in [0, 1]")
        object.__setattr__(self, "probabilities", probabilities)
        object.__setattr__(self, "confidence", confidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "choice",
            "choice": self.choice,
            "probabilities": dict(self.probabilities),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JevChoiceAnswer":
        if data.get("type") != "choice":
            raise ValidationError("Jev answer must have type=choice")
        probabilities = data.get("probabilities")
        if not isinstance(probabilities, Mapping):
            raise ValidationError("Jev choice answer requires probabilities")
        return cls(
            choice=str(data.get("choice", "")),
            probabilities={str(key): float(value) for key, value in probabilities.items()},
            confidence=float(data.get("confidence", 0.0)),
        )


@dataclass(frozen=True)
class JevDecisionResponse:
    """One typed Decisions response plus auditable model identity and usage."""

    response_id: str
    model: str
    provider: str
    answers: Mapping[str, JevChoiceAnswer]
    usage: AgentUsage = AgentUsage(llm_calls=1)

    def __post_init__(self) -> None:
        for name in ("response_id", "model", "provider"):
            if not str(getattr(self, name)).strip():
                raise ValidationError(f"Jev response {name} must not be empty")
        answers = {str(key): value for key, value in self.answers.items()}
        if not answers or any(not isinstance(value, JevChoiceAnswer) for value in answers.values()):
            raise ValidationError("Jev response requires typed choice answers")
        object.__setattr__(self, "answers", answers)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JevDecisionResponse":
        answers = data.get("answers")
        if not isinstance(answers, Mapping):
            raise ValidationError("Jev response requires an answers object")
        usage = data.get("usage", {})
        if not isinstance(usage, Mapping):
            raise ValidationError("Jev response usage must be an object")
        response_id = str(data.get("id", data.get("response_id", ""))).strip()
        if not response_id:
            response_id = "jev-" + hashlib.sha256(
                json.dumps(
                    dict(data),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:24]
        return cls(
            response_id=response_id,
            model=str(data.get("model", "")),
            provider=str(data.get("provider", "")),
            answers={
                str(key): JevChoiceAnswer.from_dict(value)
                for key, value in answers.items()
                if isinstance(value, Mapping)
            },
            usage=AgentUsage(
                llm_calls=1,
                tokens=int(usage.get("inputTokens", usage.get("input_tokens", 0)))
                + int(usage.get("outputTokens", usage.get("output_tokens", 0))),
                cost=float(usage.get("cost", 0.0)),
            ),
        )


class JevDecisionClient(Protocol):
    """Injectable boundary shared by live Decisions and zero-network replay."""

    def decide(
        self,
        *,
        state: Mapping[str, Any],
        questions: Mapping[str, Mapping[str, Any]],
    ) -> JevDecisionResponse:
        """Return validated typed answers for the supplied closed questions."""


class OpenRouterJevClient:
    """OpenRouter client for Jev's Decisions endpoint."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_JEV_MODEL,
        endpoint: str = DEFAULT_JEV_URL,
        app_referer: str = "http://localhost",
        app_title: str = "stock-opportunity-agent",
        transport: HttpTransport | None = None,
    ) -> None:
        for name, value in (
            ("api_key", api_key),
            ("model", model),
            ("endpoint", endpoint),
            ("app_referer", app_referer),
            ("app_title", app_title),
        ):
            if not value.strip():
                raise ValidationError(f"OpenRouter Jev {name} must not be empty")
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.app_referer = app_referer
        self.app_title = app_title
        self.transport = transport or UrllibTransport()

    @classmethod
    def from_environ(
        cls,
        environ: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> "OpenRouterJevClient":
        env = os.environ if environ is None else environ
        api_key = env.get(DEFAULT_OPENROUTER_API_KEY_ENV_VAR)
        if not api_key:
            raise ValidationError(f"{DEFAULT_OPENROUTER_API_KEY_ENV_VAR} is not set")
        return cls(api_key, **kwargs)

    def prepare_request(
        self,
        *,
        state: Mapping[str, Any],
        questions: Mapping[str, Mapping[str, Any]],
    ) -> PreparedJsonRequest:
        normalized_questions = _validate_questions(questions)
        if not state:
            raise ValidationError("Jev state must not be empty")
        return PreparedJsonRequest(
            self.endpoint,
            {
                "model": self.model,
                "state": dict(state),
                "questions": normalized_questions,
            },
        )

    def decide(
        self,
        *,
        state: Mapping[str, Any],
        questions: Mapping[str, Mapping[str, Any]],
    ) -> JevDecisionResponse:
        prepared = self.prepare_request(state=state, questions=questions)
        raw = self.transport.post_json(
            prepared.url,
            {
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": self.app_referer,
                "X-Title": self.app_title,
            },
            prepared.payload,
        )
        response = JevDecisionResponse.from_dict(raw)
        missing = set(prepared.payload["questions"]) - set(response.answers)
        unexpected = set(response.answers) - set(prepared.payload["questions"])
        if missing or unexpected:
            raise ValidationError(
                "Jev response question mismatch: "
                f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
            )
        return response


class RecordedJevDecisionClient:
    """FIFO typed responses for deterministic zero-network replay."""

    def __init__(self, responses: Iterable[JevDecisionResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def decide(
        self,
        *,
        state: Mapping[str, Any],
        questions: Mapping[str, Mapping[str, Any]],
    ) -> JevDecisionResponse:
        if not self.responses:
            raise ValidationError("recorded Jev replay has no response remaining")
        normalized_questions = _validate_questions(questions)
        self.calls.append(
            {"state": dict(state), "questions": normalized_questions}
        )
        response = self.responses.pop(0)
        if set(response.answers) != set(normalized_questions):
            raise ValidationError("recorded Jev response does not match replay questions")
        return response


def _validate_questions(
    questions: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not questions:
        raise ValidationError("Jev questions must not be empty")
    normalized: dict[str, dict[str, Any]] = {}
    for question_id, raw in questions.items():
        question = dict(raw)
        if question.get("type") != "choice":
            raise ValidationError("parallel Jev path accepts choice questions only")
        if not str(question.get("instructions", "")).strip():
            raise ValidationError("Jev choice instructions must not be empty")
        criteria = question.get("criteria")
        if not isinstance(criteria, Mapping) or len(criteria) < 2:
            raise ValidationError("Jev choice criteria require at least two options")
        normalized_criteria = {
            str(key): str(value) for key, value in criteria.items()
        }
        if any(not key.strip() or not value.strip() for key, value in normalized_criteria.items()):
            raise ValidationError("Jev choice criteria keys and descriptions must not be empty")
        question["criteria"] = normalized_criteria
        normalized[str(question_id)] = question
    return normalized
