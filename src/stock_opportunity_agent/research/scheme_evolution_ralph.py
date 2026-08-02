"""Adapters from scheme evolution into the existing Ralph information-plan path."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, is_dataclass, replace
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from stock_opportunity_agent.cases.learning import HistoricalCase
from stock_opportunity_agent.data.documents import DocumentRecord
from stock_opportunity_agent.llm.openai import ChatMessage, OpenAIChatClient
from stock_opportunity_agent.models import EvidenceKind, ValidationError
from stock_opportunity_agent.research.information_plan import (
    PreparedInformationPlanExperiment,
    prepare_information_plan_experiment,
)
from stock_opportunity_agent.research.ralph_loop import (
    BlindSchemePacket,
    HeuristicRalphBlindResearcher,
    InformationScheme,
    _identity_token_pattern,
    _identity_tokens,
)
from stock_opportunity_agent.research.scheme_evolution import (
    BlindSample,
    EvolutionFold,
    MaterializedScheme,
    PredictionRecord,
    SchemeGenome,
    SignalSpec,
    genome_recipe_hash,
)
from stock_opportunity_agent.research.scheme_evolution_records import (
    MetaLesson,
    MutationRequest,
)


_STRICT_PREDICTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "predicted_class",
        "confidence_level",
        "difficulty_level",
        "difficulty_reasons",
        "decisive_signals",
        "conflicting_signals",
        "missing_information",
        "flip_conditions",
        "evidence_source_ids",
    ],
    "properties": {
        "predicted_class": {"type": "string", "enum": ["A", "B", "C"]},
        "confidence_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "difficulty_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "difficulty_reasons": {"type": "array", "items": {"type": "string"}},
        "decisive_signals": {"type": "array", "items": {"type": "string"}},
        "conflicting_signals": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "flip_conditions": {"type": "array", "items": {"type": "string"}},
        "evidence_source_ids": {"type": "array", "items": {"type": "string"}},
    },
}

_FIXED_BLIND_TASK_INSTRUCTIONS = (
    "Use only the supplied anonymous point-in-time packet and materialized signal "
    "definitions. Web tools are disabled. Do not infer identity, historical "
    "validation labels, realized outcomes, future prices, or post-cutoff facts. "
    "Predict the fixed six-month smoothed maximum adjusted-close multiple using "
    "exactly this immutable mapping: class A means below 2.0 and is binary "
    "negative; class B means at least 2.0 and below 3.0 and is binary positive; "
    "class C means at least 3.0 and is binary positive. A negative or unsupported "
    "setup must map to A, never C. Do not output probabilities, scores, or token "
    "likelihoods. Every supporting or contradicting claim must cite at least one "
    "evidence_source_id present in the packet."
)


class GenomeBlindAnalyzer(Protocol):
    """Analyze one existing anonymous Ralph packet under a genome prompt."""

    @property
    def settings_fingerprint(self) -> str:
        """Return a secret-free provider/model/prompt-harness fingerprint."""

    def analyze(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        packet: BlindSchemePacket,
    ) -> dict[str, Any]:
        """Return the strict prediction object plus a ``_metadata`` object."""


class ExternalAttemptLedger:
    """Persist cumulative provider attempts and observed costs across resumes."""

    def __init__(
        self,
        path: str | Path,
        *,
        scope_fingerprint: str,
        authorized_max_attempts: int,
    ) -> None:
        if not scope_fingerprint.strip():
            raise ValidationError("external attempt scope fingerprint must not be empty")
        if authorized_max_attempts < 1:
            raise ValidationError("authorized external attempt count must be positive")
        self.path = Path(path)
        self.scope_fingerprint = scope_fingerprint
        self.authorized_max_attempts = authorized_max_attempts
        if self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._validate(payload)
            previous_max = int(payload["authorized_max_attempts"])
            if authorized_max_attempts < previous_max:
                raise ValidationError(
                    "authorized external attempt count cannot shrink on resume"
                )
            if authorized_max_attempts > previous_max:
                payload["authorization_changes"].append(
                    {
                        "changed_at": datetime.now(timezone.utc).isoformat(),
                        "previous_max_attempts": previous_max,
                        "authorized_max_attempts": authorized_max_attempts,
                    }
                )
                payload["authorized_max_attempts"] = authorized_max_attempts
                _write_json(self.path, payload)
            self._payload = payload
        else:
            self._payload = {
                "schema_version": "scheme-evolution-external-attempt-ledger-v0.1",
                "scope_fingerprint": scope_fingerprint,
                "authorized_max_attempts": authorized_max_attempts,
                "authorization_changes": [],
                "attempts": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_json(self.path, self._payload)

    @property
    def attempt_count(self) -> int:
        """Return every reserved HTTP attempt, including interrupted attempts."""

        return len(self._payload["attempts"])

    @property
    def spent_cost_usd(self) -> float:
        """Return cumulative observed or conservative estimated response cost."""

        return round(
            sum(float(row.get("cost_usd") or 0.0) for row in self._payload["attempts"]),
            8,
        )

    def reserve(
        self,
        *,
        cache_key: str,
        input_hash: str,
        maximum_cost_usd: float,
    ) -> str:
        """Atomically consume one authorized attempt before network access."""

        if maximum_cost_usd < 0:
            raise ValidationError("external attempt maximum cost cannot be negative")
        if self.attempt_count >= self.authorized_max_attempts:
            raise ValidationError("authorized external HTTP attempt budget is exhausted")
        attempt_id = f"attempt-{self.attempt_count + 1:04d}"
        self._payload["attempts"].append(
            {
                "attempt_id": attempt_id,
                "cache_key": cache_key,
                "input_hash": input_hash,
                "status": "started",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "response_id": None,
                "cost_usd": round(float(maximum_cost_usd), 8),
                "cost_observed": False,
                "error_type": None,
                "error_summary": None,
            }
        )
        self._persist()
        return attempt_id

    def finish(
        self,
        attempt_id: str,
        *,
        status: str,
        response_id: str | None = None,
        cost_usd: float | None = None,
        cost_observed: bool = False,
        error: Exception | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Finalize one reserved attempt without deleting failed history."""

        if status not in {"completed", "provider_error", "failed_validation"}:
            raise ValidationError("invalid external attempt status")
        row = next(
            (item for item in self._payload["attempts"] if item["attempt_id"] == attempt_id),
            None,
        )
        if row is None:
            raise ValidationError("external attempt id is not present in the ledger")
        if row["status"] != "started":
            raise ValidationError("external attempt was already finalized")
        row.update(
            {
                "status": status,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "response_id": response_id,
                "cost_usd": (
                    row["cost_usd"]
                    if cost_usd is None
                    else round(float(cost_usd), 8)
                ),
                "cost_observed": bool(cost_observed) if cost_usd is not None else False,
                "error_type": type(error).__name__ if error is not None else None,
                "error_summary": (
                    error_summary[:1000]
                    if error_summary is not None
                    else re.sub(r"\s+", " ", str(error)).strip()[:1000]
                    if error is not None
                    else None
                ),
            }
        )
        self._persist()

    def _persist(self) -> None:
        self._payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(self.path, self._payload)

    def _validate(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            raise ValidationError("external attempt ledger must be a JSON object")
        if payload.get("schema_version") != "scheme-evolution-external-attempt-ledger-v0.1":
            raise ValidationError("unsupported external attempt ledger schema")
        if payload.get("scope_fingerprint") != self.scope_fingerprint:
            raise ValidationError("external attempt ledger scope mismatch")
        if not isinstance(payload.get("attempts"), list):
            raise ValidationError("external attempt ledger attempts must be a list")
        if not isinstance(payload.get("authorization_changes"), list):
            raise ValidationError(
                "external attempt ledger authorization_changes must be a list"
            )
        previous_max = payload.get("authorized_max_attempts")
        if not isinstance(previous_max, int) or isinstance(previous_max, bool):
            raise ValidationError("external attempt ledger maximum must be an integer")
        if len(payload["attempts"]) > previous_max:
            raise ValidationError("external attempt ledger exceeds its authorized maximum")


class HeuristicGenomeBlindAnalyzer:
    """Local diagnostic adapter; never evidence of real information-plan lift."""

    def __init__(self) -> None:
        self._researcher = HeuristicRalphBlindResearcher()

    @property
    def settings_fingerprint(self) -> str:
        return "heuristic-genome-blind-analyzer-v0.1"

    def analyze(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        packet: BlindSchemePacket,
    ) -> dict[str, Any]:
        """Map the existing deterministic Ralph result into the strict contract."""

        del genome, materialized
        analysis = self._researcher.analyze(packet)
        evidence_refs = sorted(_packet_evidence_refs(packet))
        predicted_class = (
            "C"
            if analysis.surge_candidate == "likely" and analysis.confidence >= 0.7
            else "B"
            if analysis.surge_candidate in {"likely", "possible"}
            else "A"
        )
        difficulty_level = (
            "high"
            if analysis.surge_candidate == "insufficient_information"
            else "medium"
            if analysis.confidence < 0.6
            else "low"
        )
        return {
            "predicted_class": predicted_class,
            "confidence_level": _confidence_bucket(analysis.confidence),
            "difficulty_level": difficulty_level,
            "difficulty_reasons": (
                ["insufficient_information"]
                if analysis.surge_candidate == "insufficient_information"
                else []
            ),
            "decisive_signals": list(analysis.pre_surge_signals),
            "conflicting_signals": list(analysis.contrary_evidence),
            "missing_information": list(analysis.missing_context),
            "flip_conditions": [
                "classification changes if missing point-in-time evidence contradicts the current signals"
            ],
            "evidence_source_ids": evidence_refs,
            "_metadata": {
                "provider": "local_heuristic",
                "model": "deterministic_ralph",
                "temperature": 0.0,
                "token_cost_usd": 0.0,
                "latency_ms": 0.0,
                "retry_count": 0,
                "raw_response_location": None,
                "pipeline_diagnostic_only": True,
            },
        }


class OpenRouterFusionSchemeProposer:
    """One-call, cached Fusion proposer for bounded SchemeGenome mutations."""

    _PRICING_SNAPSHOT = {
        "verified_at": "2026-08-02",
        "panel_aliases": {
            "~anthropic/claude-opus-latest": "anthropic/claude-opus-5",
            "~openai/gpt-latest": "openai/gpt-5.6-sol",
            "~google/gemini-pro-latest": "google/gemini-3.1-pro-preview",
        },
        "maximum_input_usd_per_million": 5.0,
        "maximum_output_usd_per_million": 30.0,
        "maximum_web_search_usd": 0.014,
    }

    def __init__(
        self,
        client: OpenAIChatClient,
        cache_dir: str | Path,
        *,
        objective_text: str,
        preset: str = "general-high",
        max_tool_calls: int = 1,
        inner_max_tokens: int = 3000,
        outer_max_tokens: int = 5000,
        max_cost_usd: float = 2.0,
    ) -> None:
        if not objective_text.strip():
            raise ValidationError("Fusion proposal objective must not be empty")
        if max_tool_calls < 1 or inner_max_tokens < 1 or outer_max_tokens < 1:
            raise ValidationError("Fusion proposal bounds must be positive")
        if max_cost_usd <= 0:
            raise ValidationError("Fusion proposal cost cap must be positive")
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.objective_text = objective_text
        self.preset = preset
        self.max_tool_calls = max_tool_calls
        self.inner_max_tokens = inner_max_tokens
        self.outer_max_tokens = outer_max_tokens
        self.max_cost_usd = max_cost_usd
        self.external_call_count = 0
        self.cache_hit_count = 0
        self.spent_cost_usd = 0.0

    @property
    def settings_fingerprint(self) -> str:
        return _hash_json(
            {
                "model": getattr(self.client, "model", "openrouter/fusion"),
                "preset": self.preset,
                "max_tool_calls": self.max_tool_calls,
                "inner_max_tokens": self.inner_max_tokens,
                "outer_max_tokens": self.outer_max_tokens,
                "reasoning": {"effort": "high", "exclude": True},
                "pricing_snapshot": self._PRICING_SNAPSHOT,
            }
        )

    def preview_request(
        self,
        parents: list[SchemeGenome],
        meta_memory: list[MetaLesson],
        mutation_requests: list[MutationRequest],
        count: int,
    ) -> dict[str, Any]:
        """Return exact proposal content and a conservative current-price bound."""

        if count != 1:
            raise ValidationError("bounded Fusion proposer currently requires count=1")
        input_payload = {
            "objective": self.objective_text,
            "candidate_count": count,
            "parents": [parent.to_dict() for parent in parents],
            "aggregate_meta_memory": [
                _sanitized_meta_lesson(lesson) for lesson in meta_memory
            ],
            "mutation_requests": [request.to_dict() for request in mutation_requests],
            "fixed_boundaries": {
                "evaluation_contract_mutable": False,
                "blind_validation_must_be_anonymous": True,
                "blind_validation_web_tools_allowed": False,
                "proposal_only": True,
                "human_review_required": True,
            },
        }
        developer_prompt = (
            "Act as the high-capability proposal layer for a bounded information-scheme "
            "evolution experiment. Use Fusion deliberation to propose exactly one complete "
            "SchemeGenome JSON object derived from an active parent. You may use web research "
            "only for general source-family or research-method ideas; never identify or research "
            "validation companies. Preserve the fixed A/B/C exam, anonymous no-web blind "
            "analysis, output schema, point-in-time cutoffs, and proposal-only boundary. Make "
            "few attributable changes. Return JSON only as {\"candidates\": [<full genome>]}."
        )
        user_prompt = json.dumps(input_payload, indent=2, sort_keys=True)
        messages = [
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ]
        request_hash = _hash_json(
            {
                "messages": messages,
                "settings_fingerprint": self.settings_fingerprint,
            }
        )
        approximate_input_tokens = sum(len(row["content"]) for row in messages) / 4
        panel_and_analyst_calls = 4
        estimated_cost = (
            approximate_input_tokens
            * 10
            * self._PRICING_SNAPSHOT["maximum_input_usd_per_million"]
            / 1_000_000
            + (panel_and_analyst_calls * self.inner_max_tokens + self.outer_max_tokens)
            * self._PRICING_SNAPSHOT["maximum_output_usd_per_million"]
            / 1_000_000
            + panel_and_analyst_calls
            * self.max_tool_calls
            * self._PRICING_SNAPSHOT["maximum_web_search_usd"]
        )
        return {
            "schema_version": "scheme-evolution-fusion-proposal-preview-v0.1",
            "destination": f"{getattr(self.client, 'base_url', 'https://openrouter.ai/api/v1')}/responses",
            "model": getattr(self.client, "model", "openrouter/fusion"),
            "messages": messages,
            "plugins": [
                {
                    "id": "fusion",
                    "preset": self.preset,
                    "max_tool_calls": self.max_tool_calls,
                    "max_completion_tokens": self.inner_max_tokens,
                    "reasoning": {"effort": "high"},
                }
            ],
            "tool_choice": "required",
            "reasoning": {"effort": "high", "exclude": True},
            "max_output_tokens": self.outer_max_tokens,
            "request_hash": request_hash,
            "settings_fingerprint": self.settings_fingerprint,
            "pricing_snapshot": self._PRICING_SNAPSHOT,
            "pricing_snapshot_estimated_cost_usd": estimated_cost,
            "cost_bound_kind": "pricing_snapshot_estimate_not_provider_hard_cap",
            "external_call_performed": False,
        }

    def propose(
        self,
        parents: list[SchemeGenome],
        meta_memory: list[MetaLesson],
        mutation_requests: list[MutationRequest],
        count: int,
    ) -> list[SchemeGenome]:
        """Call Fusion once or reuse its exact cached candidate response."""

        preview = self.preview_request(parents, meta_memory, mutation_requests, count)
        estimated_cost = float(preview["pricing_snapshot_estimated_cost_usd"])
        if estimated_cost > self.max_cost_usd:
            raise ValidationError("Fusion proposal estimate exceeds its configured cost cap")
        cache_path = self.cache_dir / f"{preview['request_hash']}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("settings_fingerprint") != self.settings_fingerprint:
                raise ValidationError("cached Fusion proposal settings mismatch")
            if cached.get("status") != "completed":
                raise ValidationError(
                    "cached Fusion proposal is incomplete or failed; automatic retry is disabled"
                )
            self.cache_hit_count += 1
            return [SchemeGenome.from_dict(row) for row in cached["candidates"]]
        messages = [
            ChatMessage(str(row["role"]), str(row["content"]))
            for row in preview["messages"]
        ]
        self.external_call_count += 1
        response = self.client.complete(
            messages,
            max_output_tokens=self.outer_max_tokens,
            tool_choice="required",
            plugins=preview["plugins"],
            reasoning=preview["reasoning"],
        )
        usage = response.raw.get("usage", {}) if isinstance(response.raw, Mapping) else {}
        actual_cost = _reported_usage_cost(usage)
        self.spent_cost_usd += actual_cost if actual_cost is not None else estimated_cost
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        response_record = {
            "schema_version": "scheme-evolution-fusion-proposal-cache-v0.1",
            "status": "received_pending_validation",
            "request_hash": preview["request_hash"],
            "settings_fingerprint": self.settings_fingerprint,
            "resolved_model": response.model,
            "response_id": response.response_id,
            "response_hash": hashlib.sha256(
                response.output_text.encode("utf-8")
            ).hexdigest(),
            "usage": usage if isinstance(usage, Mapping) else {},
            "reported_cost_usd": actual_cost,
            "pricing_snapshot_estimated_cost_usd": estimated_cost,
            "raw_output": response.output_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(cache_path, response_record)
        try:
            raw_candidates = _parse_fusion_candidates(response.output_text)
            candidates = [SchemeGenome.from_dict(row) for row in raw_candidates]
            if len(candidates) != count:
                raise ValidationError("Fusion proposal returned the wrong candidate count")
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            _write_json(
                cache_path,
                {
                    **response_record,
                    "status": "failed_validation",
                    "validation_error": f"{type(exc).__name__}: {exc}",
                },
            )
            raise
        _write_json(
            cache_path,
            {
                **response_record,
                "status": "completed",
                "candidates": [candidate.to_dict() for candidate in candidates],
            },
        )
        return candidates


class OpenAIGenomeBlindAnalyzer:
    """Strict JSON, cached blind analyzer using the existing provider client."""

    def __init__(
        self,
        client: OpenAIChatClient,
        cache_dir: str | Path,
        *,
        provider: str,
        model: str,
        temperature: float,
        max_attempts: int = 2,
        max_output_tokens: int = 2200,
        reasoning_effort: str | None = None,
        input_cost_per_million_tokens: float = 0.0,
        output_cost_per_million_tokens: float = 0.0,
        max_cost_usd: float | None = None,
        attempt_ledger_path: str | Path | None = None,
        attempt_scope_fingerprint: str | None = None,
        authorized_max_external_attempts: int | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValidationError("max_attempts must be positive")
        if max_output_tokens < 1:
            raise ValidationError("max_output_tokens must be positive")
        if reasoning_effort not in {None, "max", "xhigh", "high", "medium", "low"}:
            raise ValidationError("unsupported reasoning_effort")
        if input_cost_per_million_tokens < 0 or output_cost_per_million_tokens < 0:
            raise ValidationError("token price estimates cannot be negative")
        if max_cost_usd is not None and max_cost_usd < 0:
            raise ValidationError("max_cost_usd cannot be negative")
        ledger_settings = (
            attempt_ledger_path,
            attempt_scope_fingerprint,
            authorized_max_external_attempts,
        )
        if any(value is not None for value in ledger_settings) and not all(
            value is not None for value in ledger_settings
        ):
            raise ValidationError(
                "attempt ledger path, scope, and authorized maximum must be supplied together"
            )
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_attempts = max_attempts
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.input_cost_per_million_tokens = input_cost_per_million_tokens
        self.output_cost_per_million_tokens = output_cost_per_million_tokens
        self.max_cost_usd = max_cost_usd
        self.attempt_ledger = (
            ExternalAttemptLedger(
                attempt_ledger_path,
                scope_fingerprint=str(attempt_scope_fingerprint),
                authorized_max_attempts=int(authorized_max_external_attempts),
            )
            if attempt_ledger_path is not None
            else None
        )
        self.spent_cost_usd = (
            self.attempt_ledger.spent_cost_usd if self.attempt_ledger else 0.0
        )
        self.external_call_count = 0
        self.cache_hit_count = 0

    @property
    def cumulative_external_call_count(self) -> int:
        """Return persisted attempts, or this process's count when no ledger is configured."""

        if self.attempt_ledger is not None:
            return self.attempt_ledger.attempt_count
        return self.external_call_count

    def assert_authorized_capacity(
        self,
        requests: Iterable[Mapping[str, Any]],
    ) -> dict[str, int]:
        """Fail before network access if uncached requests exceed remaining attempts."""

        rows = list(requests)
        if self.attempt_ledger is None:
            return {
                "logical_request_count": len(rows),
                "cached_request_count": 0,
                "outstanding_request_count": len(rows),
                "remaining_authorized_attempts": len(rows),
            }
        cached_count = 0
        for row in rows:
            cache_key = str(row.get("cache_key", ""))
            input_hash = str(row.get("input_hash", ""))
            if not cache_key or not input_hash:
                raise ValidationError("attempt-capacity request is missing cache identity")
            cache_path = self.cache_dir / f"{cache_key}.json"
            if not cache_path.exists():
                continue
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("input_hash") != input_hash:
                raise ValidationError("cached genome blind input hash mismatch")
            if cached.get("settings_fingerprint") != self.settings_fingerprint:
                raise ValidationError("cached genome blind settings mismatch")
            cached_count += 1
        outstanding_count = len(rows) - cached_count
        remaining_attempts = (
            self.attempt_ledger.authorized_max_attempts
            - self.attempt_ledger.attempt_count
        )
        if outstanding_count > remaining_attempts:
            raise ValidationError(
                "uncached blind requests exceed the remaining authorized external HTTP "
                f"attempts: outstanding={outstanding_count} remaining={remaining_attempts}"
            )
        return {
            "logical_request_count": len(rows),
            "cached_request_count": cached_count,
            "outstanding_request_count": outstanding_count,
            "remaining_authorized_attempts": remaining_attempts,
        }

    @property
    def settings_fingerprint(self) -> str:
        return _hash_json(
            {
                "provider": self.provider,
                "model": self.model,
                "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens,
                "reasoning_effort": self.reasoning_effort,
                "top_p": None,
                "seed": None,
                "input_cost_per_million_tokens": self.input_cost_per_million_tokens,
                "output_cost_per_million_tokens": self.output_cost_per_million_tokens,
                "max_cost_usd": self.max_cost_usd,
                "response_schema": _STRICT_PREDICTION_SCHEMA,
            }
        )

    def analyze(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        packet: BlindSchemePacket,
    ) -> dict[str, Any]:
        """Call or reuse the strict, anonymous, no-web prediction request."""

        request = self.preview_request(genome, materialized, packet)
        input_hash = str(request["input_hash"])
        prompt_hash = str(request["prompt_hash"])
        cache_key = str(request["cache_key"])
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("input_hash") != input_hash:
                raise ValidationError("cached genome blind input hash mismatch")
            if cached.get("settings_fingerprint") != self.settings_fingerprint:
                raise ValidationError("cached genome blind settings mismatch")
            if cached.get("prompt_hash") != prompt_hash:
                raise ValidationError("cached genome blind prompt hash mismatch")
            self.cache_hit_count += 1
            cached_metadata = dict(cached.get("request_metadata") or {})
            cached_metadata["cache_hit"] = True
            cached_metadata["external_call_performed"] = False
            return _validate_prediction_output(
                cached.get("prediction"),
                packet,
                metadata=cached_metadata,
            )
        recovered = self._recover_failed_validation_attempt(
            packet=packet,
            cache_key=cache_key,
            input_hash=input_hash,
            prompt_hash=prompt_hash,
            cache_path=cache_path,
        )
        if recovered is not None:
            return recovered
        messages = [
            ChatMessage(str(message["role"]), str(message["content"]))
            for message in request["messages"]
        ]
        maximum_request_cost = float(request["maximum_request_cost_usd"])
        if (
            self.max_cost_usd is not None
            and self.spent_cost_usd + maximum_request_cost > self.max_cost_usd
        ):
            raise ValidationError(
                "next blind request could exceed the configured API cost budget"
            )
        last_error: ValidationError | None = None
        for attempt in range(1, self.max_attempts + 1):
            if (
                attempt > 1
                and self.max_cost_usd is not None
                and self.spent_cost_usd + maximum_request_cost > self.max_cost_usd
            ):
                raise ValidationError(
                    "retry could exceed the configured API cost budget"
                )
            started = time.monotonic()
            ledger_attempt_id = (
                self.attempt_ledger.reserve(
                    cache_key=cache_key,
                    input_hash=input_hash,
                    maximum_cost_usd=maximum_request_cost,
                )
                if self.attempt_ledger is not None
                else None
            )
            self.external_call_count += 1
            try:
                response = self.client.complete(
                    messages,
                    max_output_tokens=int(request["max_output_tokens"]),
                    response_format=request["response_format"],
                    reasoning=(
                        {"effort": self.reasoning_effort, "exclude": True}
                        if self.reasoning_effort
                        else None
                    ),
                )
            except Exception as exc:
                if self.attempt_ledger is not None and ledger_attempt_id is not None:
                    self.attempt_ledger.finish(
                        ledger_attempt_id,
                        status="provider_error",
                        error=exc,
                        error_summary=_secret_safe_error_summary(
                            exc,
                            secrets=(str(getattr(self.client, "api_key", "")),),
                        ),
                    )
                raise
            latency_ms = (time.monotonic() - started) * 1000
            usage = response.raw.get("usage", {}) if isinstance(response.raw, Mapping) else {}
            reported_cost = _reported_usage_cost(usage)
            token_estimated_cost = _estimated_token_cost(
                usage,
                input_cost_per_million_tokens=self.input_cost_per_million_tokens,
                output_cost_per_million_tokens=self.output_cost_per_million_tokens,
            )
            cost_observed = reported_cost is not None or token_estimated_cost > 0
            estimated_cost = (
                reported_cost
                if reported_cost is not None
                else token_estimated_cost
                if token_estimated_cost > 0
                else maximum_request_cost
            )
            self.spent_cost_usd += estimated_cost
            response_hash = hashlib.sha256(
                response.output_text.encode("utf-8")
            ).hexdigest()
            response_audit_id = ledger_attempt_id or (
                "response-"
                + _hash_json(
                    {
                        "response_id": response.response_id,
                        "response_hash": response_hash,
                    }
                )[:16]
            )
            response_audit_path = (
                self.cache_dir
                / "_attempts"
                / cache_key
                / f"{response_audit_id}.json"
            )
            response_audit = {
                "schema_version": "genome-blind-response-attempt-v0.1",
                "status": "received_pending_validation",
                "cache_key": cache_key,
                "input_hash": input_hash,
                "settings_fingerprint": self.settings_fingerprint,
                "prompt_hash": prompt_hash,
                "response_id": response.response_id,
                "response_model": response.model or self.model,
                "response_hash": response_hash,
                "raw_output": response.output_text,
                "usage": usage if isinstance(usage, Mapping) else {},
                "cost_usd": estimated_cost,
                "cost_observed": cost_observed,
                "received_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_json(response_audit_path, response_audit)
            try:
                raw = json.loads(response.output_text)
            except json.JSONDecodeError as exc:
                last_error = ValidationError("genome blind response was not valid JSON")
                _write_json(
                    response_audit_path,
                    {
                        **response_audit,
                        "status": "failed_validation",
                        "validation_error": str(last_error),
                    },
                )
                if self.attempt_ledger is not None and ledger_attempt_id is not None:
                    self.attempt_ledger.finish(
                        ledger_attempt_id,
                        status="failed_validation",
                        response_id=response.response_id,
                        cost_usd=estimated_cost,
                        cost_observed=cost_observed,
                        error=last_error,
                    )
                if attempt >= self.max_attempts:
                    raise last_error from exc
                continue
            metadata = {
                "provider": self.provider,
                "model": response.model or self.model,
                "temperature": self.temperature,
                "top_p": None,
                "seed": None,
                "system_prompt_hash": prompt_hash,
                "input_hash": input_hash,
                "response_hash": response_hash,
                "request_timestamp": datetime.now(timezone.utc).isoformat(),
                "token_usage": usage if isinstance(usage, Mapping) else {},
                "estimated_cost_usd": estimated_cost,
                "token_cost_usd": estimated_cost,
                "latency_ms": round(latency_ms, 4),
                "retry_count": attempt - 1,
                "raw_response_location": str(response_audit_path),
                "pipeline_diagnostic_only": False,
                "cache_hit": False,
                "external_call_performed": True,
            }
            try:
                validated = _validate_prediction_output(
                    raw,
                    packet,
                    metadata=metadata,
                )
            except ValidationError as exc:
                last_error = exc
                _write_json(
                    response_audit_path,
                    {
                        **response_audit,
                        "status": "failed_validation",
                        "validation_error": str(exc),
                    },
                )
                if self.attempt_ledger is not None and ledger_attempt_id is not None:
                    self.attempt_ledger.finish(
                        ledger_attempt_id,
                        status="failed_validation",
                        response_id=response.response_id,
                        cost_usd=estimated_cost,
                        cost_observed=cost_observed,
                        error=exc,
                    )
                if attempt >= self.max_attempts:
                    raise
                continue
            _write_json(
                response_audit_path,
                {
                    **response_audit,
                    "status": "validated",
                    "validation_error": None,
                },
            )
            if self.attempt_ledger is not None and ledger_attempt_id is not None:
                self.attempt_ledger.finish(
                    ledger_attempt_id,
                    status="completed",
                    response_id=response.response_id,
                    cost_usd=estimated_cost,
                    cost_observed=cost_observed,
                )
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            _write_json(
                cache_path,
                {
                    "schema_version": "genome-blind-analysis-cache-v0.1",
                    "input_hash": input_hash,
                    "settings_fingerprint": self.settings_fingerprint,
                    "prompt_hash": prompt_hash,
                    "response_id": response.response_id,
                    "response_hash": response_hash,
                    "raw_output": response.output_text,
                    "usage": usage if isinstance(usage, Mapping) else {},
                    "response_audit_path": str(response_audit_path),
                    "prediction": {
                        key: value
                        for key, value in validated.items()
                        if key != "_metadata"
                    },
                    "request_metadata": metadata,
                },
            )
            return validated
        raise last_error or ValidationError("genome blind analysis failed")

    def _recover_failed_validation_attempt(
        self,
        *,
        packet: BlindSchemePacket,
        cache_key: str,
        input_hash: str,
        prompt_hash: str,
        cache_path: Path,
    ) -> dict[str, Any] | None:
        """Revalidate a paid exact response before considering another HTTP call."""

        attempt_dir = self.cache_dir / "_attempts" / cache_key
        if not attempt_dir.exists():
            return None
        for audit_path in sorted(attempt_dir.glob("*.json"), reverse=True):
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            if audit.get("status") != "failed_validation":
                continue
            if audit.get("input_hash") != input_hash:
                continue
            if audit.get("settings_fingerprint") != self.settings_fingerprint:
                continue
            if audit.get("prompt_hash") != prompt_hash:
                continue
            raw_output = audit.get("raw_output")
            if not isinstance(raw_output, str):
                continue
            try:
                raw = json.loads(raw_output)
            except json.JSONDecodeError:
                continue
            usage = audit.get("usage")
            usage = dict(usage) if isinstance(usage, Mapping) else {}
            estimated_cost = float(audit.get("cost_usd", 0.0))
            metadata = {
                "provider": self.provider,
                "model": str(audit.get("response_model") or self.model),
                "temperature": self.temperature,
                "top_p": None,
                "seed": None,
                "system_prompt_hash": prompt_hash,
                "input_hash": input_hash,
                "response_hash": str(audit.get("response_hash", "")),
                "request_timestamp": str(audit.get("received_at", "")),
                "token_usage": usage,
                "estimated_cost_usd": estimated_cost,
                "token_cost_usd": estimated_cost,
                "latency_ms": 0.0,
                "retry_count": 0,
                "raw_response_location": str(audit_path),
                "pipeline_diagnostic_only": False,
                "cache_hit": True,
                "external_call_performed": False,
                "revalidated_from_attempt_audit": True,
            }
            try:
                validated = _validate_prediction_output(raw, packet, metadata=metadata)
            except ValidationError:
                continue
            _write_json(
                audit_path,
                {
                    **audit,
                    "status": "validated",
                    "validation_error": None,
                    "prior_validation_error": audit.get("validation_error"),
                    "revalidated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            _write_json(
                cache_path,
                {
                    "schema_version": "genome-blind-analysis-cache-v0.1",
                    "input_hash": input_hash,
                    "settings_fingerprint": self.settings_fingerprint,
                    "prompt_hash": prompt_hash,
                    "response_id": audit.get("response_id"),
                    "response_hash": audit.get("response_hash"),
                    "raw_output": raw_output,
                    "usage": usage,
                    "response_audit_path": str(audit_path),
                    "prediction": {
                        key: value for key, value in validated.items() if key != "_metadata"
                    },
                    "request_metadata": metadata,
                },
            )
            self.cache_hit_count += 1
            return validated
        return None

    def preview_request(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        packet: BlindSchemePacket,
    ) -> dict[str, Any]:
        """Return the secret-free request content without calling the provider."""

        input_payload = {
            "packet": packet.to_prompt_dict(),
            "materialized_signals": [
                signal.to_dict() for signal in materialized.retained_signals
            ],
        }
        input_hash = _hash_json(input_payload)
        developer_prompt = (
            genome.blind_analysis_prompt.template
            + "\n"
            + _FIXED_BLIND_TASK_INSTRUCTIONS
        )
        prompt_hash = hashlib.sha256(developer_prompt.encode("utf-8")).hexdigest()
        cache_key = _hash_json(
            {
                "input_hash": input_hash,
                "prompt_hash": prompt_hash,
                "settings": self.settings_fingerprint,
            }
        )
        user_prompt = json.dumps(input_payload, indent=2, sort_keys=True)
        maximum_request_cost = (
            (len(developer_prompt) + len(user_prompt)) / 4
            * self.input_cost_per_million_tokens
            / 1_000_000
            + self.max_output_tokens
            * self.output_cost_per_million_tokens
            / 1_000_000
        )
        provider_routing = None
        if hasattr(self.client, "provider_only"):
            provider_routing = {
                "only": list(getattr(self.client, "provider_only")),
                "require_parameters": bool(
                    getattr(self.client, "provider_require_parameters")
                ),
                "allow_fallbacks": bool(
                    getattr(self.client, "provider_allow_fallbacks")
                ),
            }
        base_url = getattr(self.client, "base_url", None)
        return {
            "schema_version": "scheme-evolution-blind-request-preview-v0.1",
            "destination": f"{base_url}/responses" if base_url else None,
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "reasoning": (
                {"effort": self.reasoning_effort, "exclude": True}
                if self.reasoning_effort
                else None
            ),
            "provider_routing": provider_routing,
            "messages": [
                {"role": "developer", "content": developer_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "input_payload": input_payload,
            "input_hash": input_hash,
            "prompt_hash": prompt_hash,
            "settings_fingerprint": self.settings_fingerprint,
            "cache_key": cache_key,
            "max_output_tokens": self.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "name": "scheme_prediction",
                "strict": True,
                "schema": _STRICT_PREDICTION_SCHEMA,
            },
            "maximum_request_cost_usd": maximum_request_cost,
            "external_call_performed": False,
        }


class RalphInformationPlanFoldEvaluator:
    """Materialize genomes with current Ralph facts and render current packets."""

    def __init__(
        self,
        *,
        cases: Iterable[HistoricalCase],
        documents_by_symbol: Mapping[str, Iterable[DocumentRecord]],
        base_scheme: InformationScheme,
        analyzer: GenomeBlindAnalyzer,
        artifact_dir: str | Path | None = None,
    ) -> None:
        self.cases_by_id = {case.case_id: case for case in cases}
        self.documents_by_symbol = {
            symbol.upper(): tuple(documents)
            for symbol, documents in documents_by_symbol.items()
        }
        self.base_scheme = base_scheme
        self.analyzer = analyzer
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else None
        self._prepared: dict[str, PreparedInformationPlanExperiment] = {}
        self._evaluator_fingerprint = _hash_json(
            {
                "adapter": "ralph-information-plan-fold-evaluator-v0.1",
                "analyzer": self.analyzer.settings_fingerprint,
                "base_scheme": self.base_scheme.to_dict(),
                "case_hashes": {
                    case_id: _hash_json(case)
                    for case_id, case in sorted(self.cases_by_id.items())
                },
                "document_hashes": {
                    symbol: [_hash_json(document) for document in documents]
                    for symbol, documents in sorted(self.documents_by_symbol.items())
                },
            }
        )

    @property
    def evaluator_fingerprint(self) -> str:
        return self._evaluator_fingerprint

    def materialize(self, genome: SchemeGenome, fold: EvolutionFold) -> MaterializedScheme:
        """Use only fold discovery cases and labels to build the concrete plan."""

        discovery = [self._case(sample.sample_id) for sample in fold.discovery_samples]
        admission = [self._case(sample.sample_id) for sample in fold.admission_samples]
        scheme = _scheme_for_genome(self.base_scheme, genome)
        documents = _documents_for_genome(self.documents_by_symbol, genome)
        prepared = prepare_information_plan_experiment(
            discovery,
            admission,
            active_scheme=scheme,
            run_id=f"{genome.genome_id}:{fold.fold_id}",
            context_budget=int(genome.complexity_budget["max_context_tokens"]),
            families=tuple(genome.metadata.get("information_families", ())),
            documents_by_symbol=documents,
        )
        input_hash = _hash_json(
            {
                "genome_recipe": genome_recipe_hash(genome),
                "fold_id": fold.fold_id,
                "discovery": [
                    {
                        "sample_id": sample.sample_id,
                        "realized_max_multiple": sample.realized_max_multiple,
                        "true_class": sample.true_class,
                        "is_surge": sample.is_surge,
                    }
                    for sample in fold.discovery_samples
                ],
                "source_pool": prepared.source_pool_by_case,
            }
        )
        retained, rejected = _retained_seed_signals(
            genome.seed_signal_specs,
            prepared,
        )
        output_hash = _hash_json(
            {
                "plan": prepared.plan.to_dict(),
                "retained_signals": [signal.to_dict() for signal in retained],
                "rejected_signals": rejected,
            }
        )
        materialized = MaterializedScheme(
            materialized_scheme_id=f"{genome.genome_id}:{fold.fold_id}:{output_hash[:12]}",
            genome_id=genome.genome_id,
            fold_id=fold.fold_id,
            discovered_signals=[],
            retained_signals=retained,
            rejected_signals=rejected,
            materialization_inputs_hash=input_hash,
            output_hash=output_hash,
        )
        if self.artifact_dir is not None:
            _write_materialization_preflight(
                self.artifact_dir,
                genome=genome,
                materialized=materialized,
                prepared=prepared,
                selected_cases=discovery + admission,
            )
        self._prepared[materialized.materialized_scheme_id] = prepared
        return materialized

    def restore(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        fold: EvolutionFold,
    ) -> None:
        """Rebuild transient packets while reusing the persisted frozen signals."""

        discovery = [self._case(sample.sample_id) for sample in fold.discovery_samples]
        admission = [self._case(sample.sample_id) for sample in fold.admission_samples]
        scheme = _scheme_for_genome(self.base_scheme, genome)
        documents = _documents_for_genome(self.documents_by_symbol, genome)
        prepared = prepare_information_plan_experiment(
            discovery,
            admission,
            active_scheme=scheme,
            run_id=f"{genome.genome_id}:{fold.fold_id}",
            context_budget=int(genome.complexity_budget["max_context_tokens"]),
            families=tuple(genome.metadata.get("information_families", ())),
            documents_by_symbol=documents,
        )
        retained, rejected = _retained_seed_signals(genome.seed_signal_specs, prepared)
        expected_output_hash = _hash_json(
            {
                "plan": prepared.plan.to_dict(),
                "retained_signals": [signal.to_dict() for signal in retained],
                "rejected_signals": rejected,
            }
        )
        if expected_output_hash != materialized.output_hash:
            raise ValidationError("restored Ralph materialization differs from frozen signals")
        self._prepared[materialized.materialized_scheme_id] = prepared

    def predict(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        sample: BlindSample,
    ) -> PredictionRecord:
        """Analyze the current organized packet and return the evolution record."""

        prepared = self._prepared.get(materialized.materialized_scheme_id)
        if prepared is None:
            raise ValidationError("materialized Ralph scheme is not available in this evaluator")
        try:
            index = prepared.holdout_case_ids.index(sample.sample_id)
        except ValueError as exc:
            raise ValidationError("blind sample is not in the materialized admission fold") from exc
        packet = prepared.organized_packets[index]
        output = self.analyzer.analyze(genome, materialized, packet)
        metadata = dict(output.get("_metadata", {}))
        data_cost = sum(source.estimated_cost_usd for source in genome.data_source_specs)
        metadata["data_cost_usd"] = data_cost
        return PredictionRecord(
            genome_id=genome.genome_id,
            materialized_scheme_id=materialized.materialized_scheme_id,
            fold_id=materialized.fold_id,
            sample_id=sample.sample_id,
            prediction_time=sample.prediction_time,
            predicted_class=str(output["predicted_class"]),
            is_surge=str(output["predicted_class"]) in {"B", "C"},
            confidence_level=str(output["confidence_level"]),
            difficulty_level=str(output["difficulty_level"]),
            difficulty_reasons=list(output["difficulty_reasons"]),
            decisive_signals=list(output["decisive_signals"]),
            conflicting_signals=list(output["conflicting_signals"]),
            missing_information=list(output["missing_information"]),
            flip_conditions=list(output["flip_conditions"]),
            evidence_source_ids=list(output["evidence_source_ids"]),
            model_metadata=metadata,
            input_hash="pending-engine-hash",
            raw_response_location=metadata.get("raw_response_location"),
        )

    def extract(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        sample: BlindSample,
    ) -> dict[str, Any]:
        """Expose the exact label-free organized packet and frozen signal set."""

        del genome
        prepared = self._prepared.get(materialized.materialized_scheme_id)
        if prepared is None:
            raise ValidationError("materialized Ralph scheme is not available in this evaluator")
        try:
            index = prepared.holdout_case_ids.index(sample.sample_id)
        except ValueError as exc:
            raise ValidationError("blind sample is not in the materialized admission fold") from exc
        packet = prepared.organized_packets[index]
        return {
            "sample_id": sample.sample_id,
            "anonymous_packet": packet.to_prompt_dict(),
            "frozen_signals": [
                signal.to_dict() for signal in materialized.retained_signals
            ],
        }

    def preview_request(
        self,
        genome: SchemeGenome,
        materialized: MaterializedScheme,
        sample: BlindSample,
    ) -> dict[str, Any]:
        """Build the exact provider request preview for one blind sample."""

        prepared = self._prepared.get(materialized.materialized_scheme_id)
        if prepared is None:
            raise ValidationError("materialized Ralph scheme is not available in this evaluator")
        try:
            index = prepared.holdout_case_ids.index(sample.sample_id)
        except ValueError as exc:
            raise ValidationError("blind sample is not in the materialized admission fold") from exc
        if not isinstance(self.analyzer, OpenAIGenomeBlindAnalyzer):
            raise ValidationError("request preview requires the strict external analyzer")
        return self.analyzer.preview_request(
            genome,
            materialized,
            prepared.organized_packets[index],
        )

    def _case(self, sample_id: str) -> HistoricalCase:
        try:
            return self.cases_by_id[sample_id]
        except KeyError as exc:
            raise ValidationError(f"evolution sample has no Ralph case: {sample_id}") from exc


def _validate_prediction_output(
    raw: Any,
    packet: BlindSchemePacket,
    *,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValidationError("genome blind prediction must be a JSON object")
    required = _STRICT_PREDICTION_SCHEMA["required"]
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValidationError(f"genome blind prediction missing fields: {missing}")
    extras = sorted(set(raw) - set(required))
    if extras:
        raise ValidationError(f"genome blind prediction has unexpected fields: {extras}")
    if raw["predicted_class"] not in {"A", "B", "C"}:
        raise ValidationError("predicted_class must be A, B, or C")
    if raw["confidence_level"] not in {"low", "medium", "high"}:
        raise ValidationError("invalid confidence_level")
    if raw["difficulty_level"] not in {"low", "medium", "high"}:
        raise ValidationError("invalid difficulty_level")
    for key in (
        "difficulty_reasons",
        "decisive_signals",
        "conflicting_signals",
        "missing_information",
        "flip_conditions",
        "evidence_source_ids",
    ):
        if not isinstance(raw[key], list) or not all(
            isinstance(value, str) and value.strip() for value in raw[key]
        ):
            raise ValidationError(f"{key} must be a list of non-empty strings")
    allowed_refs = _packet_evidence_refs(packet)
    unknown_refs = sorted(set(raw["evidence_source_ids"]) - allowed_refs)
    if unknown_refs:
        raise ValidationError(f"prediction cited evidence refs outside the packet: {unknown_refs}")
    claims = list(raw["decisive_signals"]) + list(raw["conflicting_signals"])
    if claims and not raw["evidence_source_ids"]:
        raise ValidationError("supporting or contradicting claims require packet evidence refs")
    return {
        key: raw[key]
        for key in required
    } | {"_metadata": dict(metadata or {})}


def _scheme_for_genome(base: InformationScheme, genome: SchemeGenome) -> InformationScheme:
    requested_order = list(genome.metadata.get("section_order", ()))
    order = {name: index + 1 for index, name in enumerate(requested_order)}
    sections = tuple(
        replace(
            section,
            priority=order.get(section.name, len(order) + section.priority),
        )
        for section in base.sections
    )
    return replace(
        base,
        scheme_id=genome.genome_id,
        version=f"{genome.genome_id}-g{genome.generation}",
        sections=sections,
        total_token_budget=int(genome.complexity_budget["max_context_tokens"]),
        proposal_status="proposal_only_pending_review",
    )


def _documents_for_genome(
    documents_by_symbol: Mapping[str, tuple[DocumentRecord, ...]],
    genome: SchemeGenome,
) -> dict[str, tuple[DocumentRecord, ...]]:
    allowed_kinds: set[EvidenceKind] = set()
    for source in genome.data_source_specs:
        text = f"{source.source_id} {source.source_family}".lower()
        if "filing" in text or "sec" in text:
            allowed_kinds.add(EvidenceKind.FILING)
        if "news" in text:
            allowed_kinds.add(EvidenceKind.NEWS)
        if "transcript" in text:
            allowed_kinds.add(EvidenceKind.TRANSCRIPT)
        if "theme" in text or "industry" in text:
            allowed_kinds.add(EvidenceKind.THEME_CONTEXT)
        if "research" in text:
            allowed_kinds.add(EvidenceKind.RESEARCH_REPORT)
    if not allowed_kinds:
        raise ValidationError("genome source specs do not map to current document kinds")
    return {
        symbol: tuple(document for document in documents if document.kind in allowed_kinds)
        for symbol, documents in documents_by_symbol.items()
    }


def _retained_seed_signals(
    signals: Iterable[SignalSpec],
    prepared: PreparedInformationPlanExperiment,
) -> tuple[list[SignalSpec], list[dict[str, str]]]:
    available_source_families = {
        family
        for documents in prepared.source_documents_by_case.values()
        for document in documents
        for family in _source_aliases(document)
    }
    retained: list[SignalSpec] = []
    rejected: list[dict[str, str]] = []
    for signal in signals:
        required = {value.lower() for value in signal.required_sources}
        if required & available_source_families:
            retained.append(signal)
        else:
            rejected.append(
                {
                    "signal_id": signal.signal_id,
                    "reason": "none of the signal's required source aliases exist in this fold",
                }
            )
    return retained, rejected


def _source_aliases(document: DocumentRecord) -> set[str]:
    aliases = {document.kind.value, document.source_id.lower()}
    if document.kind is EvidenceKind.FILING:
        aliases.update({"sec_filings", "sec_submissions", "primary_filings"})
    elif document.kind is EvidenceKind.NEWS:
        aliases.update({"provider_company_news", "company_news"})
    return aliases


def _packet_evidence_refs(packet: BlindSchemePacket) -> set[str]:
    refs: set[str] = set()
    for section in packet.sections:
        for item in section.items:
            for key in ("evidence_ref", "source_id", "fact_id", "fact_ref"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    refs.add(value)
            lineage = item.get("derived_from_fact_refs")
            if isinstance(lineage, list):
                refs.update(
                    value for value in lineage if isinstance(value, str) and value
                )
    return refs


def _sanitized_meta_lesson(lesson: MetaLesson) -> dict[str, Any]:
    evidence = dict(lesson.evidence)
    evidence.pop("examples", None)
    return {
        "observation": lesson.observation,
        "evidence": evidence,
        "diagnosed_issue": lesson.diagnosed_issue,
        "tested_change": lesson.tested_change,
        "metric_delta": lesson.metric_delta,
        "status": lesson.status,
        "confidence": lesson.confidence,
        "suggested_mutation_operators": [
            operator.value for operator in lesson.suggested_mutation_operators
        ],
    }


def _parse_fusion_candidates(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValidationError("Fusion proposal did not contain a JSON object")
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValidationError("Fusion proposal was not valid JSON") from exc
    rows = payload.get("candidates") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValidationError("Fusion proposal must contain a candidates list")
    return [dict(row) for row in rows]


def _reported_usage_cost(usage: Any) -> float | None:
    if not isinstance(usage, Mapping):
        return None
    for key in ("cost", "total_cost", "cost_usd"):
        value = usage.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            return float(value)
    return None


def _write_materialization_preflight(
    root: Path,
    *,
    genome: SchemeGenome,
    materialized: MaterializedScheme,
    prepared: PreparedInformationPlanExperiment,
    selected_cases: Iterable[HistoricalCase],
) -> None:
    case_list = list(selected_cases)
    case_by_id = {case.case_id: case for case in case_list}
    identity_terms_by_case = {
        case.case_id: _identity_tokens(case.packet) for case in case_list
    }
    packet_records = []
    finding_count = 0
    for packet in prepared.organized_packets:
        payload = packet.to_prompt_dict()
        source_case = case_by_id.get(packet.source_case_id)
        if source_case is None:
            raise ValidationError("materialized packet has no matching selected case")
        own_identity_terms = identity_terms_by_case[source_case.case_id]
        cross_identity_terms = (
            token
            for case_id, terms in identity_terms_by_case.items()
            if case_id != source_case.case_id
            for token in terms
        )
        identity_findings = _packet_identity_findings(
            packet,
            own_identity_terms=own_identity_terms,
            cross_identity_terms=cross_identity_terms,
        )
        forbidden_keys = sorted(
            _nested_keys(payload)
            & {
                "label",
                "outcome",
                "outcome_return",
                "forward_return",
                "ticker",
                "company_name",
            }
        )
        finding_count += len(identity_findings) + len(forbidden_keys)
        packet_records.append(
            {
                "anonymous_case_id": packet.anonymous_case_id,
                "packet_hash": _hash_json(payload),
                "identity_findings": identity_findings[:10],
                "forbidden_keys": forbidden_keys,
                "packet": payload,
            }
        )
    base = root / _hash_json(
        {
            "materialized_scheme_id": materialized.materialized_scheme_id,
            "output_hash": materialized.output_hash,
        }
    )
    _write_json(
        base / "materialization_preflight.json",
        {
            "schema_version": "scheme-evolution-materialization-preflight-v0.1",
            "genome_id": genome.genome_id,
            "fold_id": materialized.fold_id,
            "materialized_scheme_id": materialized.materialized_scheme_id,
            "materialized_scheme": materialized.to_dict(),
            "packet_count": len(packet_records),
            "finding_count": finding_count,
            "passed": finding_count == 0,
            "external_call_performed": False,
            "artifact_phase": "before_blind_analysis",
            "packets": packet_records,
        },
    )
    if finding_count:
        raise ValidationError("materialized evolution packets failed identity/label preflight")


def _packet_identity_findings(
    packet: BlindSchemePacket,
    *,
    own_identity_terms: Iterable[str],
    cross_identity_terms: Iterable[str],
) -> list[str]:
    """Find identity text only in sample-varying evidence, not fixed instructions."""

    serialized = json.dumps(
        [list(section.items) for section in packet.sections],
        sort_keys=True,
    )
    findings: set[str] = set()
    for token in own_identity_terms:
        if not token:
            continue
        flags = 0 if len(token) < 3 and token.isupper() else re.IGNORECASE
        if re.search(_identity_token_pattern(token), serialized, flags=flags):
            findings.add(token)
    for token in cross_identity_terms:
        if token and len(token) >= 3 and re.search(
            _identity_token_pattern(token),
            serialized,
            flags=re.IGNORECASE,
        ):
            findings.add(token)
    return sorted(findings, key=len, reverse=True)


def _nested_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.add(str(key).lower())
            keys.update(_nested_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_nested_keys(item))
    return keys


def _confidence_bucket(confidence: float) -> str:
    return "high" if confidence >= 0.75 else "medium" if confidence >= 0.5 else "low"


def _secret_safe_error_summary(
    error: Exception,
    *,
    secrets: Iterable[str] = (),
) -> str:
    """Bound provider errors while redacting credentials and account identifiers."""

    summary = re.sub(r"\s+", " ", str(error)).strip()
    for secret in secrets:
        if secret:
            summary = summary.replace(secret, "[REDACTED_SECRET]")
    summary = re.sub(
        r'(?i)("?(?:api[_-]?key|authorization|access[_-]?token|user_id)"?\s*[:=]\s*)'
        r'("?)[^",}\s]+\2',
        r'\1"[REDACTED_SECRET]"',
        summary,
    )
    return summary[:1000]


def _estimated_token_cost(
    usage: Any,
    *,
    input_cost_per_million_tokens: float,
    output_cost_per_million_tokens: float,
) -> float:
    if not isinstance(usage, Mapping):
        return 0.0
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
    if not isinstance(input_tokens, (int, float)) or isinstance(input_tokens, bool):
        input_tokens = 0
    if not isinstance(output_tokens, (int, float)) or isinstance(output_tokens, bool):
        output_tokens = 0
    return round(
        float(input_tokens) * input_cost_per_million_tokens / 1_000_000
        + float(output_tokens) * output_cost_per_million_tokens / 1_000_000,
        8,
    )


def _hash_json(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError(f"cannot serialize {type(value).__name__} for a stable hash")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
