"""Blind LLM analysis for cold-start historical cases."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from stock_opportunity_agent.cases.learning import HistoricalCase
from stock_opportunity_agent.llm.openai import ChatMessage, OpenAIChatClient
from stock_opportunity_agent.models import ResearchPacket, ValidationError


@dataclass(frozen=True)
class BlindCaseAnalysis:
    """LLM analysis of one as-of packet with future labels hidden."""

    case_id: str
    packet_id: str
    as_of_date: str
    surge_candidate: str
    surge_candidate_reason: str
    expectation_gap: str
    pre_surge_signals: tuple[str, ...]
    contrary_evidence: tuple[str, ...]
    catalyst_watch: tuple[str, ...]
    confidence: float
    raw_text: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible analysis record."""

        return {
            "case_id": self.case_id,
            "packet_id": self.packet_id,
            "as_of_date": self.as_of_date,
            "surge_candidate": self.surge_candidate,
            "surge_candidate_reason": self.surge_candidate_reason,
            "expectation_gap": self.expectation_gap,
            "pre_surge_signals": list(self.pre_surge_signals),
            "contrary_evidence": list(self.contrary_evidence),
            "catalyst_watch": list(self.catalyst_watch),
            "confidence": self.confidence,
            "raw_text": self.raw_text,
        }


class BlindCaseResearcher(Protocol):
    """Researcher that analyzes a historical case without seeing its outcome."""

    def analyze(self, case: HistoricalCase) -> BlindCaseAnalysis:
        """Analyze a case using only the packet's as-of data."""


class HeuristicBlindCaseResearcher:
    """Offline deterministic researcher for tests and dry runs."""

    def analyze(self, case: HistoricalCase) -> BlindCaseAnalysis:
        packet = case.packet
        features = {feature.name: feature.value for feature in packet.features}
        signals: list[str] = []
        if _numeric(features.get("financial.revenue_growth_yoy")) >= 0.20:
            signals.append("Revenue growth is already above 20% as of the packet date.")
        if _numeric(features.get("price.return_60d")) >= 0.15:
            signals.append("Price action shows early 60-day confirmation.")
        if case.packet.catalysts:
            signals.append("Known catalysts are visible inside the next review window.")
        contrary = []
        if _numeric(features.get("valuation.pe_ratio")) >= 45:
            contrary.append("Valuation is already stretched.")
        return BlindCaseAnalysis(
            case_id=case.case_id,
            packet_id=packet.packet_id,
            as_of_date=packet.as_of.as_of_date.isoformat(),
            surge_candidate="possible" if signals else "unlikely",
            surge_candidate_reason="Heuristic dry-run judgment from point-in-time structured features only.",
            expectation_gap="Heuristic dry-run analysis; no future label was used.",
            pre_surge_signals=tuple(signals or ["No strong pre-surge signal found in structured features."]),
            contrary_evidence=tuple(contrary or ["No major contrary evidence detected by heuristic researcher."]),
            catalyst_watch=tuple(catalyst.name for catalyst in packet.catalysts),
            confidence=0.35,
            raw_text="heuristic",
        )


class OpenAIBlindCaseResearcher:
    """OpenAI-backed blind as-of-date researcher."""

    def __init__(self, client: OpenAIChatClient, *, mask_identity: bool = True) -> None:
        self.client = client
        self.mask_identity = mask_identity

    def analyze(self, case: HistoricalCase) -> BlindCaseAnalysis:
        """Analyze a historical case with future outcome metadata excluded."""

        packet = case.packet
        response = self.client.complete(
            [
                ChatMessage(
                    "developer",
                    (
                        "You are doing blind historical stock research. Use only the supplied as-of packet. "
                        "Do not assume future outcomes, do not ask why the stock later moved, and do not use "
                        "any data after the packet as_of_date. Web search is disabled for this step. "
                        "Treat any masked identity as intentional. Judge whether the anonymous setup looks "
                        "like a potential 3-6 month surge candidate, but do not infer or mention any hidden "
                        "winner/control/failure group. Return strict JSON."
                    ),
                ),
                ChatMessage("user", _packet_prompt(packet, mask_identity=self.mask_identity)),
            ],
            max_output_tokens=1200,
            response_format={"type": "json_object"},
        )
        return _analysis_from_json(case, response.output_text)


def _packet_prompt(packet: ResearchPacket, *, mask_identity: bool = True) -> str:
    identity_tokens = _identity_tokens(packet)
    company = packet.company.to_dict()
    features = [feature.to_dict() for feature in packet.features]
    evidence = [item.to_dict() for item in packet.evidence]
    catalysts = [catalyst.to_dict() for catalyst in packet.catalysts]
    if mask_identity:
        company = {
            **company,
            "ticker": {
                **company["ticker"],
                "symbol": "MASKED",
                "company_name": "MASKED",
                "figi": None,
            },
            }
        features = [_masked_source_fields(feature) for feature in features]
        evidence = [_masked_source_fields(item) for item in evidence]
        catalysts = [
            {
                **_mask_identity_in_value(catalyst, identity_tokens),
                "evidence": [_masked_source_fields(item) for item in catalyst["evidence"]],
            }
            for catalyst in catalysts
        ]
        features = _mask_identity_in_value(features, identity_tokens)
        evidence = _mask_identity_in_value(evidence, identity_tokens)
        catalysts = _mask_identity_in_value(catalysts, identity_tokens)
    packet_data = {
        "packet_id": "MASKED" if mask_identity else packet.packet_id,
        "as_of_date": packet.as_of.as_of_date.isoformat(),
        "identity_masked": mask_identity,
        "company": company,
        "features": features,
        "evidence": evidence,
        "catalysts": catalysts,
        "required_json_schema": {
            "surge_candidate": "likely | possible | unlikely | insufficient_information",
            "surge_candidate_reason": "string",
            "expectation_gap": "string",
            "pre_surge_signals": ["string"],
            "contrary_evidence": ["string"],
            "catalyst_watch": ["string"],
            "confidence": "number between 0 and 1",
        },
    }
    return json.dumps(packet_data, indent=2, sort_keys=True)


def _masked_source_fields(record: dict[str, Any]) -> dict[str, Any]:
    masked = dict(record)
    if "source_id" in masked:
        masked["source_id"] = "MASKED"
    if "source_url" in masked:
        masked["source_url"] = None
    return masked


def _identity_tokens(packet: ResearchPacket) -> tuple[str, ...]:
    ticker = packet.company.ticker
    tokens = [ticker.symbol, ticker.company_name or ""]
    company = ticker.company_name or ""
    for suffix in (" Incorporated", " Inc.", " Inc", " Corporation", " Corp.", " Corp", " Ltd.", " Ltd", " PLC"):
        if company.endswith(suffix):
            tokens.append(company[: -len(suffix)])
    return tuple(sorted({token for token in tokens if token and token.strip()}, key=len, reverse=True))


def _mask_identity_in_value(value: Any, tokens: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        masked = value
        for token in tokens:
            masked = re.sub(re.escape(token), "MASKED", masked, flags=re.IGNORECASE)
        return masked
    if isinstance(value, list):
        return [_mask_identity_in_value(item, tokens) for item in value]
    if isinstance(value, tuple):
        return tuple(_mask_identity_in_value(item, tokens) for item in value)
    if isinstance(value, dict):
        return {key: _mask_identity_in_value(item, tokens) for key, item in value.items()}
    return value


def _analysis_from_json(case: HistoricalCase, text: str) -> BlindCaseAnalysis:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("blind case analysis was not valid JSON") from exc
    return BlindCaseAnalysis(
        case_id=case.case_id,
        packet_id=case.packet.packet_id,
        as_of_date=case.packet.as_of.as_of_date.isoformat(),
        surge_candidate=_string(data, "surge_candidate"),
        surge_candidate_reason=_string(data, "surge_candidate_reason"),
        expectation_gap=_string(data, "expectation_gap"),
        pre_surge_signals=tuple(_string_list(data, "pre_surge_signals")),
        contrary_evidence=tuple(_string_list(data, "contrary_evidence")),
        catalyst_watch=tuple(_string_list(data, "catalyst_watch")),
        confidence=_confidence(data.get("confidence")),
        raw_text=text,
    )


def _string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"blind case analysis missing {key}")
    return value


def _string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"blind case analysis {key} must be a non-empty string list")
    return value


def _confidence(value: Any) -> float:
    if not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValidationError("blind case confidence must be between 0 and 1")
    return float(value)


def _numeric(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0
