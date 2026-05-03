"""LLM-assisted retrospective inflection discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from stock_opportunity_agent.cases.inflections import (
    InflectionCandidate,
    detect_price_inflections,
    fallback_inflection_from_case,
)
from stock_opportunity_agent.cases.learning import HistoricalCase
from stock_opportunity_agent.data.sources.core import PriceBar
from stock_opportunity_agent.llm.openai import ChatMessage, OpenAIChatClient
from stock_opportunity_agent.models import ValidationError


@dataclass(frozen=True)
class InflectionResearchResult:
    """Retrospective inflection-discovery output for one case."""

    case_id: str
    symbol: str
    candidates: tuple[InflectionCandidate, ...]
    web_enabled: bool
    raw_text: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible result."""

        return {
            "case_id": self.case_id,
            "symbol": self.symbol,
            "web_enabled": self.web_enabled,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "raw_text": self.raw_text,
        }


class InflectionResearcher(Protocol):
    """Researcher that may use retrospective data to locate surge inflections."""

    def discover(self, case: HistoricalCase) -> InflectionResearchResult:
        """Find candidate surge inflection points for a case."""


class HeuristicInflectionResearcher:
    """Offline fallback inflection researcher."""

    def discover(self, case: HistoricalCase) -> InflectionResearchResult:
        symbol = case.packet.company.ticker.symbol
        candidate = fallback_inflection_from_case(symbol, case.outcome_start_date)
        return InflectionResearchResult(
            case_id=case.case_id,
            symbol=symbol,
            candidates=(candidate,),
            web_enabled=False,
            raw_text="heuristic fallback",
        )


class FactorInflectionResearcher:
    """Factor-based inflection researcher using price and volume bars."""

    def __init__(self, bars_by_symbol: dict[str, tuple[PriceBar, ...]], *, min_forward_return: float = 0.80) -> None:
        self.bars_by_symbol = {symbol.upper(): bars for symbol, bars in bars_by_symbol.items()}
        self.min_forward_return = min_forward_return

    def discover(self, case: HistoricalCase) -> InflectionResearchResult:
        """Find inflection candidates from price/volume bars."""

        symbol = case.packet.company.ticker.symbol
        bars = self.bars_by_symbol.get(symbol.upper(), ())
        candidates = detect_price_inflections(
            symbol,
            bars,
            window_start=case.packet.as_of.as_of_date,
            window_end=case.outcome_end_date,
            min_forward_return=self.min_forward_return,
        )
        if not candidates:
            candidates = (
                fallback_inflection_from_case(
                    symbol,
                    case.outcome_start_date,
                    explanation="Fallback uses the case outcome start because no qualifying price/volume inflection was found.",
                    evidence=("Price/volume scan ran but found no candidate above the threshold.",),
                ),
            )
        return InflectionResearchResult(
            case_id=case.case_id,
            symbol=symbol,
            candidates=candidates,
            web_enabled=False,
            raw_text="factor price-volume scan",
        )


class CompositeInflectionResearcher:
    """Run multiple inflection researchers and merge their candidates."""

    def __init__(self, researchers: tuple[InflectionResearcher, ...]) -> None:
        if not researchers:
            raise ValidationError("composite inflection researcher requires at least one researcher")
        self.researchers = researchers

    def discover(self, case: HistoricalCase) -> InflectionResearchResult:
        """Return merged candidates from all configured researchers."""

        results = [researcher.discover(case) for researcher in self.researchers]
        candidates = tuple(
            sorted(
                (candidate for result in results for candidate in result.candidates),
                key=lambda candidate: (-candidate.score, candidate.inflection_date, candidate.method),
            )
        )
        return InflectionResearchResult(
            case_id=case.case_id,
            symbol=case.packet.company.ticker.symbol,
            candidates=candidates,
            web_enabled=any(result.web_enabled for result in results),
            raw_text="\n\n".join(result.raw_text for result in results),
        )


class OpenAIWebInflectionResearcher:
    """OpenAI researcher for retrospective inflection discovery with web search enabled."""

    def __init__(self, client: OpenAIChatClient) -> None:
        self.client = client

    def discover(self, case: HistoricalCase) -> InflectionResearchResult:
        """Use web search to identify public narrative and event inflection points."""

        symbol = case.packet.company.ticker.symbol
        response = self.client.complete(
            [
                ChatMessage(
                    "developer",
                    (
                        "You are doing retrospective inflection discovery for historical case setup. "
                        "You may use web search to identify public events, earnings, customer orders, "
                        "analyst upgrades, and narrative shifts that likely marked the start of a major "
                        "stock repricing. Return strict JSON only."
                    ),
                ),
                ChatMessage(
                    "user",
                    json.dumps(
                        {
                            "symbol": symbol,
                            "company_name": case.packet.company.ticker.company_name,
                            "sector": case.packet.company.sector,
                            "industry": case.packet.company.industry,
                            "case_as_of_date": case.packet.as_of.as_of_date.isoformat(),
                            "outcome_start_date": case.outcome_start_date.isoformat(),
                            "outcome_end_date": case.outcome_end_date.isoformat(),
                            "required_json_schema": {
                                "candidates": [
                                    {
                                        "inflection_date": "YYYY-MM-DD",
                                        "score": "number between 0 and 1",
                                        "explanation": "string",
                                        "evidence": ["string"],
                                    }
                                ]
                            },
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                ),
            ],
            max_output_tokens=1200,
            response_format={"type": "json_object"},
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
        )
        return _result_from_json(case, response.output_text)


def _result_from_json(case: HistoricalCase, text: str) -> InflectionResearchResult:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("inflection discovery response was not valid JSON") from exc
    raw_candidates = data.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValidationError("inflection discovery requires candidates")
    symbol = case.packet.company.ticker.symbol
    candidates = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            raise ValidationError("inflection candidate must be an object")
        candidates.append(
            InflectionCandidate(
                symbol=symbol,
                inflection_date=_date_from_string(item.get("inflection_date")),
                method="openai_web_search",
                score=_score(item.get("score")),
                explanation=_string(item.get("explanation"), "explanation"),
                evidence=tuple(_string_list(item.get("evidence"), "evidence")),
            )
        )
    return InflectionResearchResult(
        case_id=case.case_id,
        symbol=symbol,
        candidates=tuple(candidates),
        web_enabled=True,
        raw_text=text,
    )


def _date_from_string(value: Any):
    from datetime import date

    if not isinstance(value, str):
        raise ValidationError("inflection_date must be a string")
    return date.fromisoformat(value)


def _score(value: Any) -> float:
    if not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValidationError("inflection score must be between 0 and 1")
    return float(value)


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string")
    return value


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"{name} must be a non-empty string list")
    return value
