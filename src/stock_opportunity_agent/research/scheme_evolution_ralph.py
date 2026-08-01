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
        input_cost_per_million_tokens: float = 0.0,
        output_cost_per_million_tokens: float = 0.0,
        max_cost_usd: float | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValidationError("max_attempts must be positive")
        if input_cost_per_million_tokens < 0 or output_cost_per_million_tokens < 0:
            raise ValidationError("token price estimates cannot be negative")
        if max_cost_usd is not None and max_cost_usd < 0:
            raise ValidationError("max_cost_usd cannot be negative")
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_attempts = max_attempts
        self.input_cost_per_million_tokens = input_cost_per_million_tokens
        self.output_cost_per_million_tokens = output_cost_per_million_tokens
        self.max_cost_usd = max_cost_usd
        self.spent_cost_usd = 0.0
        self.external_call_count = 0
        self.cache_hit_count = 0

    @property
    def settings_fingerprint(self) -> str:
        return _hash_json(
            {
                "provider": self.provider,
                "model": self.model,
                "temperature": self.temperature,
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

        packet_payload = packet.to_prompt_dict()
        input_payload = {
            "packet": packet_payload,
            "materialized_signals": [
                signal.to_dict() for signal in materialized.retained_signals
            ],
        }
        input_hash = _hash_json(input_payload)
        cache_key = _hash_json(
            {
                "input_hash": input_hash,
                "prompt_hash": genome.blind_analysis_prompt.content_hash,
                "settings": self.settings_fingerprint,
            }
        )
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("input_hash") != input_hash:
                raise ValidationError("cached genome blind input hash mismatch")
            if cached.get("settings_fingerprint") != self.settings_fingerprint:
                raise ValidationError("cached genome blind settings mismatch")
            self.cache_hit_count += 1
            cached_metadata = dict(cached.get("request_metadata") or {})
            cached_metadata["cache_hit"] = True
            cached_metadata["external_call_performed"] = False
            return _validate_prediction_output(
                cached.get("prediction"),
                packet,
                metadata=cached_metadata,
            )
        developer_prompt = (
            genome.blind_analysis_prompt.template
            + "\nUse only the supplied anonymous point-in-time packet and "
            "materialized signal definitions. Web tools are disabled. Do not "
            "infer identity, labels, forward returns, or post-cutoff facts. "
            "Return only class A, B, or C for the fixed six-month maximum-multiple "
            "task. Do not output probabilities, scores, or token likelihoods. "
            "Every supporting or contradicting claim must cite at least one "
            "evidence_source_id present in the packet."
        )
        user_prompt = json.dumps(input_payload, indent=2, sort_keys=True)
        maximum_request_cost = (
            (len(developer_prompt) + len(user_prompt)) / 4
            * self.input_cost_per_million_tokens
            / 1_000_000
            + 2200 * self.output_cost_per_million_tokens / 1_000_000
        )
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
            self.external_call_count += 1
            response = self.client.complete(
                [
                    ChatMessage("developer", developer_prompt),
                    ChatMessage("user", user_prompt),
                ],
                max_output_tokens=2200,
                response_format={
                    "type": "json_schema",
                    "name": "scheme_prediction",
                    "strict": True,
                    "schema": _STRICT_PREDICTION_SCHEMA,
                },
            )
            latency_ms = (time.monotonic() - started) * 1000
            usage = response.raw.get("usage", {}) if isinstance(response.raw, Mapping) else {}
            estimated_cost = _estimated_token_cost(
                usage,
                input_cost_per_million_tokens=self.input_cost_per_million_tokens,
                output_cost_per_million_tokens=self.output_cost_per_million_tokens,
            )
            if estimated_cost <= 0:
                estimated_cost = maximum_request_cost
            self.spent_cost_usd += estimated_cost
            try:
                raw = json.loads(response.output_text)
            except json.JSONDecodeError as exc:
                last_error = ValidationError("genome blind response was not valid JSON")
                if attempt >= self.max_attempts:
                    raise last_error from exc
                continue
            metadata = {
                "provider": self.provider,
                "model": response.model or self.model,
                "temperature": self.temperature,
                "top_p": None,
                "seed": None,
                "system_prompt_hash": genome.blind_analysis_prompt.content_hash,
                "input_hash": input_hash,
                "response_hash": hashlib.sha256(
                    response.output_text.encode("utf-8")
                ).hexdigest(),
                "request_timestamp": datetime.now(timezone.utc).isoformat(),
                "token_usage": usage if isinstance(usage, Mapping) else {},
                "estimated_cost_usd": estimated_cost,
                "token_cost_usd": estimated_cost,
                "latency_ms": round(latency_ms, 4),
                "retry_count": attempt - 1,
                "raw_response_location": str(cache_path),
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
                if attempt >= self.max_attempts:
                    raise
                continue
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            _write_json(
                cache_path,
                {
                    "schema_version": "genome-blind-analysis-cache-v0.1",
                    "input_hash": input_hash,
                    "settings_fingerprint": self.settings_fingerprint,
                    "prompt_hash": genome.blind_analysis_prompt.content_hash,
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
            for key in ("evidence_ref", "source_id", "fact_id"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    refs.add(value)
    return refs


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
