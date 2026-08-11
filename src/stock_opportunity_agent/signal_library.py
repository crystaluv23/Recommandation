"""Versioned deterministic and LLM-driven Signal Registry."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    EvidenceResolver,
    RawInfoRequest,
    RawInfoResolution,
)
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError


_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_:-]*$")
_FORBIDDEN_SOURCE_TYPES = frozenset(
    {"ground_truth", "outcome_label", "future_price", "future_return"}
)


class SignalExecutionType(str, Enum):
    """Supported Signal execution policies."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"


class SignalValue(str, Enum):
    """Low-dimensional canonical state used by statistics."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNAVAILABLE = "unavailable"


class SignalCoverage(str, Enum):
    """Whether available evidence was sufficient for the result."""

    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class EvidencePolicy:
    """Traceability requirements enforced after every Signal execution."""

    require_source: bool = True
    require_timestamp: bool = True
    require_exact_span: bool = True

    def to_dict(self) -> dict[str, bool]:
        return {
            "require_source": self.require_source,
            "require_timestamp": self.require_timestamp,
            "require_exact_span": self.require_exact_span,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidencePolicy":
        return cls(
            require_source=bool(data.get("require_source", True)),
            require_timestamp=bool(data.get("require_timestamp", True)),
            require_exact_span=bool(data.get("require_exact_span", True)),
        )


@dataclass(frozen=True)
class SignalSpec:
    """Immutable schema, execution policy, retrieval policy, and evidence policy."""

    signal_id: str
    version: int
    category: str
    description: str
    execution_type: SignalExecutionType
    source_types: tuple[str, ...]
    evidence_policy: EvidencePolicy = field(default_factory=EvidencePolicy)
    function: str | None = None
    skill_file: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_id(self.signal_id, "signal_id")
        _validate_id(self.category, "category")
        if self.version < 1:
            raise ValidationError("signal version must be positive")
        if not self.description.strip():
            raise ValidationError("signal description must not be empty")
        if not isinstance(self.execution_type, SignalExecutionType):
            object.__setattr__(
                self,
                "execution_type",
                SignalExecutionType(self.execution_type),
            )
        if not self.source_types:
            raise ValidationError("signal requires at least one raw source type")
        for source_type in self.source_types:
            _validate_id(source_type, "source_type")
        if set(self.source_types) & _FORBIDDEN_SOURCE_TYPES:
            raise ValidationError("signal source types cannot contain outcome data")
        if self.execution_type is SignalExecutionType.DETERMINISTIC:
            if not self.function or self.skill_file:
                raise ValidationError(
                    "deterministic signal requires function and cannot use skill_file"
                )
        elif not self.skill_file or self.function:
            raise ValidationError(
                "LLM signal requires skill_file and cannot use deterministic function"
            )
        object.__setattr__(self, "source_types", tuple(self.source_types))
        object.__setattr__(self, "parameters", dict(self.parameters))

    @property
    def ref(self) -> str:
        """Return the stable version reference used in plans and trajectories."""

        return f"{self.signal_id}:v{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "version": self.version,
            "category": self.category,
            "definition": {"description": self.description},
            "schema": {
                "value": {
                    "type": "categorical",
                    "values": [value.value for value in SignalValue],
                },
                "confidence": {"type": "float"},
            },
            "execution": {
                "type": self.execution_type.value,
                **({"function": self.function} if self.function else {}),
                **({"skill_file": self.skill_file} if self.skill_file else {}),
            },
            "raw_retrieval": {"source_types": list(self.source_types)},
            "evidence_policy": self.evidence_policy.to_dict(),
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalSpec":
        execution = dict(data.get("execution", {}))
        schema = dict(data.get("schema", {}))
        value_schema = dict(schema.get("value", {}))
        declared_values = value_schema.get("values")
        expected_values = [value.value for value in SignalValue]
        if declared_values is not None and list(declared_values) != expected_values:
            raise ValidationError("SignalSpec schema must use the canonical state values")
        confidence_schema = dict(schema.get("confidence", {}))
        if confidence_schema and confidence_schema.get("type") != "float":
            raise ValidationError("SignalSpec confidence schema must be float")
        definition = data.get("definition", {})
        description = (
            definition.get("description", "")
            if isinstance(definition, Mapping)
            else str(definition)
        )
        retrieval = dict(data.get("raw_retrieval", {}))
        return cls(
            signal_id=str(data["signal_id"]),
            version=int(data["version"]),
            category=str(data["category"]),
            description=str(description),
            execution_type=SignalExecutionType(str(execution["type"])),
            function=(str(execution["function"]) if execution.get("function") else None),
            skill_file=(
                str(execution["skill_file"]) if execution.get("skill_file") else None
            ),
            source_types=tuple(str(item) for item in retrieval.get("source_types", ())),
            evidence_policy=EvidencePolicy.from_dict(
                dict(data.get("evidence_policy", {}))
            ),
            parameters=dict(data.get("parameters", {})),
        )


@dataclass(frozen=True)
class SignalEvidence:
    """Literal evidence span from one actual point-in-time input document."""

    document_id: str
    exact_span: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.document_id.strip() or not self.exact_span.strip():
            raise ValidationError("signal evidence requires document_id and exact_span")

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "exact_span": self.exact_span,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalEvidence":
        timestamp = data["timestamp"]
        return cls(
            document_id=str(data["document_id"]),
            exact_span=str(data["exact_span"]),
            timestamp=(
                timestamp
                if isinstance(timestamp, datetime)
                else datetime.fromisoformat(str(timestamp))
            ),
        )


@dataclass(frozen=True)
class SignalResult:
    """Canonical state plus rich interpretation and evidence provenance."""

    signal_id: str
    version: int
    value: SignalValue
    confidence: float
    interpretation: str
    supporting_evidence: tuple[SignalEvidence, ...] = ()
    counter_evidence: tuple[SignalEvidence, ...] = ()
    coverage: SignalCoverage = SignalCoverage.SUFFICIENT

    def __post_init__(self) -> None:
        _validate_id(self.signal_id, "signal_id")
        if self.version < 1:
            raise ValidationError("signal result version must be positive")
        if not isinstance(self.value, SignalValue):
            object.__setattr__(self, "value", SignalValue(self.value))
        if not isinstance(self.coverage, SignalCoverage):
            object.__setattr__(self, "coverage", SignalCoverage(self.coverage))
        if not 0 <= self.confidence <= 1:
            raise ValidationError("signal confidence must be between 0 and 1")
        if not self.interpretation.strip():
            raise ValidationError("signal interpretation must not be empty")
        if self.value is SignalValue.UNAVAILABLE:
            if self.coverage is not SignalCoverage.UNAVAILABLE:
                raise ValidationError("unavailable signal requires unavailable coverage")
        elif self.coverage is SignalCoverage.UNAVAILABLE:
            raise ValidationError("available signal cannot use unavailable coverage")
        object.__setattr__(self, "supporting_evidence", tuple(self.supporting_evidence))
        object.__setattr__(self, "counter_evidence", tuple(self.counter_evidence))

    @property
    def ref(self) -> str:
        return f"{self.signal_id}:v{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "version": self.version,
            "state": {"value": self.value.value, "confidence": self.confidence},
            "interpretation": {"summary": self.interpretation},
            "evidence": {
                "supporting": [item.to_dict() for item in self.supporting_evidence],
                "counter": [item.to_dict() for item in self.counter_evidence],
            },
            "status": {"coverage": self.coverage.value},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalResult":
        state = dict(data.get("state", {}))
        interpretation = data.get("interpretation", {})
        evidence = dict(data.get("evidence", {}))
        status = dict(data.get("status", {}))
        return cls(
            signal_id=str(data["signal_id"]),
            version=int(data["version"]),
            value=SignalValue(str(state["value"])),
            confidence=float(state["confidence"]),
            interpretation=(
                str(interpretation.get("summary", ""))
                if isinstance(interpretation, Mapping)
                else str(interpretation)
            ),
            supporting_evidence=tuple(
                SignalEvidence.from_dict(item)
                for item in evidence.get("supporting", ())
            ),
            counter_evidence=tuple(
                SignalEvidence.from_dict(item)
                for item in evidence.get("counter", ())
            ),
            coverage=SignalCoverage(str(status.get("coverage", "sufficient"))),
        )


@dataclass(frozen=True)
class SignalBatchResult:
    """One complete Signal batch returned to whole-batch reflection."""

    results: tuple[SignalResult, ...]
    signal_calls: int
    usage: AgentUsage = field(default_factory=AgentUsage)
    resolutions: tuple[RawInfoResolution, ...] = ()

    def __post_init__(self) -> None:
        if self.signal_calls != len(self.results):
            raise ValidationError("signal_calls must match batch result count")
        object.__setattr__(self, "results", tuple(self.results))
        object.__setattr__(self, "resolutions", tuple(self.resolutions))


@dataclass(frozen=True)
class SignalCard:
    """Compact progressive-disclosure view of one stable Signal."""

    signal_id: str
    version: int
    category: str
    description: str
    execution_type: SignalExecutionType
    positive_surge_rate: float | None

    @property
    def ref(self) -> str:
        return f"{self.signal_id}:v{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "execution_type": self.execution_type.value,
            "positive_surge_rate": self.positive_surge_rate,
        }


@dataclass
class SignalStats:
    """Observed-policy state counts, not causal Signal credit."""

    retrieved: int = 0
    executed: int = 0
    unavailable: int = 0
    states: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            value.value: {"total": 0, "surge": 0}
            for value in SignalValue
        }
    )
    total_tokens: int = 0
    total_cost: float = 0.0
    processed_observation_ids: set[str] = field(default_factory=set)

    def record_retrieval(self) -> None:
        self.retrieved += 1

    def record_result(
        self,
        result: SignalResult,
        *,
        is_surge: bool,
        usage: AgentUsage = AgentUsage(),
    ) -> None:
        self.executed += 1
        if result.value is SignalValue.UNAVAILABLE:
            self.unavailable += 1
        bucket = self.states[result.value.value]
        bucket["total"] += 1
        bucket["surge"] += int(is_surge)
        self.total_tokens += usage.tokens
        self.total_cost += usage.cost

    def record_observation(
        self,
        observation_id: str,
        result: SignalResult,
        *,
        is_surge: bool,
        usage: AgentUsage = AgentUsage(),
    ) -> bool:
        """Record one actual occurrence exactly once across restore/reconcile."""

        if not observation_id.strip():
            raise ValidationError("signal observation_id must not be empty")
        if observation_id in self.processed_observation_ids:
            return False
        self.processed_observation_ids.add(observation_id)
        self.record_retrieval()
        self.record_result(result, is_surge=is_surge, usage=usage)
        return True

    def surge_rate(self, value: SignalValue) -> float | None:
        bucket = self.states[value.value]
        if bucket["total"] == 0:
            return None
        return bucket["surge"] / bucket["total"]

    def to_dict(self) -> dict[str, Any]:
        state_statistics: dict[str, Any] = {}
        for value in SignalValue:
            bucket = self.states[value.value]
            state_statistics[value.value] = {
                **bucket,
                "surge_rate": self.surge_rate(value),
            }
        return {
            "usage": {
                "retrieved": self.retrieved,
                "executed": self.executed,
                "unavailable": self.unavailable,
            },
            "state_statistics": state_statistics,
            "cost": {
                "total_tokens": self.total_tokens,
                "total_cost": self.total_cost,
            },
            "processed_observation_ids": sorted(self.processed_observation_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalStats":
        usage = dict(data.get("usage", {}))
        states = {
            value.value: {
                "total": int(
                    dict(data.get("state_statistics", {}))
                    .get(value.value, {})
                    .get("total", 0)
                ),
                "surge": int(
                    dict(data.get("state_statistics", {}))
                    .get(value.value, {})
                    .get("surge", 0)
                ),
            }
            for value in SignalValue
        }
        cost = dict(data.get("cost", {}))
        return cls(
            retrieved=int(usage.get("retrieved", 0)),
            executed=int(usage.get("executed", 0)),
            unavailable=int(usage.get("unavailable", 0)),
            states=states,
            total_tokens=int(cost.get("total_tokens", 0)),
            total_cost=float(cost.get("total_cost", 0.0)),
            processed_observation_ids={
                str(item) for item in data.get("processed_observation_ids", ())
            },
        )


@dataclass(frozen=True)
class FrozenSignalRegistry:
    """Immutable definitions and skills used throughout one fast-loop group."""

    version: int
    registry_hash: str
    specs: tuple[SignalSpec, ...]
    skills: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "specs", tuple(self.specs))
        object.__setattr__(self, "skills", dict(self.skills))

    def load_spec(self, signal_ref: str) -> SignalSpec:
        for spec in self.specs:
            if spec.ref == signal_ref:
                return spec
        raise ValidationError(f"unknown frozen signal ref: {signal_ref}")


class SignalRegistry:
    """File-backed progressive-disclosure Signal Registry."""

    def __init__(
        self,
        root: str | Path,
        *,
        candidate_root: str | Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.candidate_root = (
            Path(candidate_root)
            if candidate_root is not None
            else self.root.parent / "signals_candidates"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.candidate_root.mkdir(parents=True, exist_ok=True)
        if not self._registry_path.exists():
            _atomic_write_json(self._registry_path, {"version": 1})

    @property
    def version(self) -> int:
        return int(_read_json(self._registry_path).get("version", 1))

    @property
    def _registry_path(self) -> Path:
        return self.root / "registry.json"

    def bump_version(self) -> int:
        """Advance the stable Registry version once after a promotion batch."""

        next_version = self.version + 1
        _atomic_write_json(self._registry_path, {"version": next_version})
        return next_version

    def register_stable(
        self,
        spec: SignalSpec,
        *,
        skill: str | None = None,
        tests: Iterable[Mapping[str, Any]] = (),
    ) -> None:
        """Register one immutable stable version without overwriting history."""

        current = self._latest_spec_or_none(spec.signal_id)
        if current is None and spec.version != 1:
            raise ValidationError("new signal must start at version 1")
        if current is not None and spec.version != current.version + 1:
            raise ValidationError("signal update must create exactly the next version")
        if spec.execution_type is SignalExecutionType.LLM and not (skill or "").strip():
            raise ValidationError("LLM signal requires non-empty skill content")
        if spec.execution_type is SignalExecutionType.DETERMINISTIC and (skill or "").strip():
            raise ValidationError("deterministic signal cannot include LLM skill content")

        signal_dir = self.root / spec.category / spec.signal_id
        version_dir = signal_dir / "versions" / f"v{spec.version}"
        if version_dir.exists():
            raise ValidationError(f"stable signal version already exists: {spec.ref}")
        version_dir.mkdir(parents=True)
        _atomic_write_json(version_dir / "spec.json", spec.to_dict())
        _atomic_write_json(version_dir / "tests.json", {"tests": list(tests)})
        if skill is not None:
            (version_dir / "skill.md").write_text(skill.rstrip() + "\n", encoding="utf-8")
        if not (signal_dir / "stats.json").exists():
            _atomic_write_json(signal_dir / "stats.json", SignalStats().to_dict())
        _atomic_write_json(
            signal_dir / "manifest.json",
            {
                "signal_id": spec.signal_id,
                "category": spec.category,
                "stable_version": spec.version,
            },
        )

    def install_catalog(self, path: str | Path) -> int:
        """Materialize a compact source-controlled seed catalog."""

        catalog = _read_json(Path(path))
        installed = 0
        for item in catalog.get("signals", ()):
            spec = SignalSpec.from_dict(item["spec"])
            if self._latest_spec_or_none(spec.signal_id) is not None:
                continue
            self.register_stable(
                spec,
                skill=item.get("skill"),
                tests=item.get("tests", ()),
            )
            installed += 1
        return installed

    def list_categories(self) -> tuple[str, ...]:
        """Return category names without exposing full Signal specs."""

        return tuple(sorted({card.category for card in self.list_signal_cards()}))

    def list_signal_cards(self, category: str | None = None) -> tuple[SignalCard, ...]:
        """Return compact cards for the current stable versions."""

        cards: list[SignalCard] = []
        for manifest_path in sorted(self.root.glob("*/*/manifest.json")):
            manifest = _read_json(manifest_path)
            if category is not None and manifest["category"] != category:
                continue
            spec = self.load_spec(
                f"{manifest['signal_id']}:v{int(manifest['stable_version'])}"
            )
            stats = self.load_stats(spec.signal_id)
            cards.append(
                SignalCard(
                    signal_id=spec.signal_id,
                    version=spec.version,
                    category=spec.category,
                    description=spec.description,
                    execution_type=spec.execution_type,
                    positive_surge_rate=stats.surge_rate(SignalValue.POSITIVE),
                )
            )
        return tuple(sorted(cards, key=lambda card: (card.category, card.signal_id)))

    def search_signal_cards(self, query: str) -> tuple[SignalCard, ...]:
        """Search compact cards without loading full specs."""

        needle = query.casefold()
        return tuple(
            card
            for card in self.list_signal_cards()
            if needle
            in " ".join((card.signal_id, card.category, card.description)).casefold()
        )

    def load_spec(self, signal_ref: str) -> SignalSpec:
        """Load one exact stable version after progressive disclosure."""

        signal_id, version = _parse_ref(signal_ref)
        manifest_path = self._manifest_for(signal_id)
        manifest = _read_json(manifest_path)
        path = (
            manifest_path.parent
            / "versions"
            / f"v{version}"
            / "spec.json"
        )
        if not path.exists():
            raise ValidationError(f"unknown stable signal ref: {signal_ref}")
        spec = SignalSpec.from_dict(_read_json(path))
        if spec.signal_id != signal_id or spec.version != version:
            raise ValidationError("signal path and spec identity disagree")
        return spec

    def load_skill(self, signal_ref: str) -> str | None:
        spec = self.load_spec(signal_ref)
        if spec.execution_type is SignalExecutionType.DETERMINISTIC:
            return None
        manifest_path = self._manifest_for(spec.signal_id)
        path = manifest_path.parent / "versions" / f"v{spec.version}" / "skill.md"
        if not path.exists():
            raise ValidationError(f"LLM signal skill is missing: {signal_ref}")
        return path.read_text(encoding="utf-8")

    def load_stats(self, signal_id: str) -> SignalStats:
        manifest_path = self._manifest_for(signal_id)
        return SignalStats.from_dict(_read_json(manifest_path.parent / "stats.json"))

    def record_retrieval(self, signal_ref: str) -> None:
        spec = self.load_spec(signal_ref)
        stats = self.load_stats(spec.signal_id)
        stats.record_retrieval()
        self._save_stats(spec.signal_id, stats)

    def record_result(
        self,
        result: SignalResult,
        *,
        is_surge: bool,
        usage: AgentUsage = AgentUsage(),
    ) -> None:
        self.load_spec(result.ref)
        stats = self.load_stats(result.signal_id)
        stats.record_result(result, is_surge=is_surge, usage=usage)
        self._save_stats(result.signal_id, stats)

    def record_observation(
        self,
        observation_id: str,
        result: SignalResult,
        *,
        is_surge: bool,
        usage: AgentUsage = AgentUsage(),
    ) -> bool:
        """Idempotently persist one actual Signal state occurrence."""

        self.load_spec(result.ref)
        stats = self.load_stats(result.signal_id)
        recorded = stats.record_observation(
            observation_id,
            result,
            is_surge=is_surge,
            usage=usage,
        )
        if recorded:
            self._save_stats(result.signal_id, stats)
        return recorded

    def freeze(self) -> FrozenSignalRegistry:
        """Freeze all current stable definitions and LLM skill text."""

        specs = tuple(
            self.load_spec(card.ref) for card in self.list_signal_cards()
        )
        skills = {
            spec.ref: skill
            for spec in specs
            if (skill := self.load_skill(spec.ref)) is not None
        }
        canonical = json.dumps(
            {
                "version": self.version,
                "specs": [spec.to_dict() for spec in specs],
                "skills": skills,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return FrozenSignalRegistry(
            version=self.version,
            registry_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            specs=specs,
            skills=skills,
        )

    def stage_candidate(
        self,
        spec: SignalSpec,
        *,
        skill: str | None = None,
        tests: Iterable[Mapping[str, Any]] = (),
        origin: str,
    ) -> str:
        """Write a candidate outside the stable registry."""

        if not origin.strip():
            raise ValidationError("signal candidate origin is required")
        if spec.execution_type is SignalExecutionType.LLM and not (skill or "").strip():
            raise ValidationError("LLM signal candidate requires skill content")
        if spec.execution_type is SignalExecutionType.DETERMINISTIC and (skill or "").strip():
            raise ValidationError(
                "deterministic signal candidate cannot include LLM skill content"
            )
        materialized_tests = [dict(item) for item in tests]
        version_dir = (
            self.candidate_root
            / spec.category
            / spec.signal_id
            / f"v{spec.version}"
        )
        if version_dir.exists():
            existing = SignalSpec.from_dict(_read_json(version_dir / "spec.json"))
            if existing != spec:
                raise ValidationError(f"conflicting signal candidate: {spec.ref}")
            existing_skill_path = version_dir / "skill.md"
            existing_skill = (
                existing_skill_path.read_text(encoding="utf-8").strip()
                if existing_skill_path.exists()
                else None
            )
            if existing_skill != ((skill or "").strip() or None):
                raise ValidationError(f"conflicting signal candidate skill: {spec.ref}")
            if self.load_candidate_tests(spec.ref) != tuple(materialized_tests):
                raise ValidationError(f"conflicting signal candidate tests: {spec.ref}")
            if _read_json(version_dir / "candidate.json").get("origin") != origin:
                raise ValidationError(f"conflicting signal candidate origin: {spec.ref}")
            return spec.ref
        version_dir.mkdir(parents=True)
        _atomic_write_json(version_dir / "spec.json", spec.to_dict())
        _atomic_write_json(version_dir / "tests.json", {"tests": materialized_tests})
        _atomic_write_json(version_dir / "candidate.json", {"origin": origin})
        if skill is not None:
            (version_dir / "skill.md").write_text(skill.rstrip() + "\n", encoding="utf-8")
        return spec.ref

    def load_candidate(self, signal_ref: str) -> tuple[SignalSpec, str | None]:
        spec_path = self._candidate_spec_path(signal_ref)
        spec = SignalSpec.from_dict(_read_json(spec_path))
        skill_path = spec_path.parent / "skill.md"
        return spec, (
            skill_path.read_text(encoding="utf-8") if skill_path.exists() else None
        )

    def load_candidate_tests(
        self, signal_ref: str
    ) -> tuple[Mapping[str, Any], ...]:
        """Load immutable candidate fixtures used by executable validation."""

        tests = _read_json(
            self._candidate_spec_path(signal_ref).parent / "tests.json"
        ).get("tests", ())
        if not isinstance(tests, list) or any(not isinstance(item, Mapping) for item in tests):
            raise ValidationError(f"candidate tests must be a list of objects: {signal_ref}")
        return tuple(dict(item) for item in tests)

    def candidate_hash(self, signal_ref: str) -> str:
        """Hash the exact staged spec, skill, and executable fixtures."""

        spec, skill = self.load_candidate(signal_ref)
        payload = {
            "spec": spec.to_dict(),
            "skill": (skill.rstrip() if skill is not None else None),
            "tests": list(self.load_candidate_tests(signal_ref)),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def record_candidate_validation(
        self,
        signal_ref: str,
        *,
        candidate_hash: str,
        accepted: bool,
        reasons: Iterable[str],
    ) -> None:
        """Persist the machine result without changing the stable Registry."""

        if candidate_hash != self.candidate_hash(signal_ref):
            raise ValidationError("candidate changed before validation was recorded")
        path = self._candidate_spec_path(signal_ref).parent / "validation.json"
        _write_or_verify_json(
            path,
            {
                "signal_ref": signal_ref,
                "candidate_hash": candidate_hash,
                "accepted": bool(accepted),
                "status": (
                    "validated_pending_human_approval" if accepted else "rejected"
                ),
                "reasons": [str(item) for item in reasons],
            },
        )

    def approve_candidate(
        self,
        signal_ref: str,
        *,
        expected_candidate_hash: str,
        approved_by: str,
    ) -> None:
        """Record explicit human approval for one exact validated candidate."""

        if not approved_by.strip():
            raise ValidationError("signal approval requires reviewer identity")
        current_hash = self.candidate_hash(signal_ref)
        if expected_candidate_hash != current_hash:
            raise ValidationError("approved candidate hash does not match staged content")
        candidate_dir = self._candidate_spec_path(signal_ref).parent
        validation = _read_json(candidate_dir / "validation.json")
        if not validation.get("accepted") or validation.get("candidate_hash") != current_hash:
            raise ValidationError("candidate requires matching successful validation")
        _write_or_verify_json(
            candidate_dir / "approval.json",
            {
                "signal_ref": signal_ref,
                "candidate_hash": current_hash,
                "approved_by": approved_by.strip(),
                "decision": "approve_stable_signal_promotion",
            },
        )

    def promote_candidate(self, signal_ref: str) -> SignalSpec:
        """Promote one exact validated and human-approved immutable version."""

        spec, skill = self.load_candidate(signal_ref)
        candidate_dir = self._candidate_spec_path(signal_ref).parent
        current_hash = self.candidate_hash(signal_ref)
        approval = _read_json(candidate_dir / "approval.json")
        if (
            approval.get("decision") != "approve_stable_signal_promotion"
            or approval.get("candidate_hash") != current_hash
        ):
            raise ValidationError("candidate lacks matching human approval")
        tests_path = next(
            iter(
                self.candidate_root.glob(
                    f"*/{spec.signal_id}/v{spec.version}/tests.json"
                )
            )
        )
        tests = _read_json(tests_path).get("tests", ())
        self.register_stable(spec, skill=skill, tests=tests)
        _atomic_write_json(
            tests_path.parent / "promotion.json",
            {"promoted": True, "stable_registry_version_before_bump": self.version},
        )
        return spec

    def _candidate_spec_path(self, signal_ref: str) -> Path:
        signal_id, version = _parse_ref(signal_ref)
        matches = list(
            self.candidate_root.glob(f"*/{signal_id}/v{version}/spec.json")
        )
        if len(matches) != 1:
            raise ValidationError(f"unknown or ambiguous signal candidate: {signal_ref}")
        return matches[0]

    def latest_spec(self, signal_id: str) -> SignalSpec:
        spec = self._latest_spec_or_none(signal_id)
        if spec is None:
            raise ValidationError(f"unknown signal: {signal_id}")
        return spec

    def _latest_spec_or_none(self, signal_id: str) -> SignalSpec | None:
        try:
            manifest_path = self._manifest_for(signal_id)
        except ValidationError:
            return None
        manifest = _read_json(manifest_path)
        return self.load_spec(
            f"{signal_id}:v{int(manifest['stable_version'])}"
        )

    def _manifest_for(self, signal_id: str) -> Path:
        _validate_id(signal_id, "signal_id")
        matches = list(self.root.glob(f"*/{signal_id}/manifest.json"))
        if len(matches) != 1:
            raise ValidationError(f"unknown or ambiguous signal id: {signal_id}")
        return matches[0]

    def _save_stats(self, signal_id: str, stats: SignalStats) -> None:
        manifest_path = self._manifest_for(signal_id)
        _atomic_write_json(manifest_path.parent / "stats.json", stats.to_dict())


DeterministicSignalFunction = Callable[
    [SignalSpec, tuple[RawInfoDocument, ...], datetime], SignalResult
]


class LLMSignalRunner(Protocol):
    """No-label adapter for one versioned extraction skill."""

    def execute(
        self,
        spec: SignalSpec,
        documents: tuple[RawInfoDocument, ...],
        skill: str,
        as_of: datetime,
    ) -> tuple[SignalResult, AgentUsage]:
        """Return a structured evidence-backed result and usage."""


class SignalExecutor:
    """Execute a selected Signal batch against one frozen Registry snapshot."""

    def __init__(
        self,
        snapshot: FrozenSignalRegistry,
        raw_info_store: RawInfoStore,
        *,
        resolver: EvidenceResolver | None = None,
        deterministic_functions: Mapping[str, DeterministicSignalFunction] | None = None,
        llm_runner: LLMSignalRunner | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.raw_info_store = raw_info_store
        self.resolver = resolver or EvidenceResolver(raw_info_store)
        self.deterministic_functions = {
            **default_deterministic_signal_functions(),
            **dict(deterministic_functions or {}),
        }
        self.llm_runner = llm_runner

    def can_execute(self, spec: SignalSpec, *, skill: str | None = None) -> bool:
        if spec.execution_type is SignalExecutionType.DETERMINISTIC:
            return bool(spec.function in self.deterministic_functions)
        return self.llm_runner is not None and bool((skill or "").strip())

    def execute_batch(
        self,
        signal_refs: Iterable[str],
        *,
        company_id: str,
        as_of: datetime,
        identity: Mapping[str, Any] | None = None,
    ) -> SignalBatchResult:
        """Execute every selected Signal and validate literal evidence."""

        results: list[SignalResult] = []
        resolutions: list[RawInfoResolution] = []
        usage = AgentUsage()
        refs = tuple(signal_refs)
        if len(set(refs)) != len(refs):
            raise ValidationError("signal batch cannot contain duplicate refs")
        for signal_ref in refs:
            spec = self.snapshot.load_spec(signal_ref)
            resolution = self.resolver.resolve(
                RawInfoRequest(
                    request_id=f"signal:{spec.ref}",
                    description=spec.description,
                    source_types=spec.source_types,
                    max_documents=10,
                ),
                company_id=company_id,
                identity=dict(identity or {}),
                as_of=as_of,
            )
            resolutions.append(resolution)
            documents = self.resolver.load_documents(resolution, as_of=as_of)
            if not documents:
                result = SignalResult(
                    signal_id=spec.signal_id,
                    version=spec.version,
                    value=SignalValue.UNAVAILABLE,
                    confidence=0.0,
                    interpretation="No point-in-time source document was available.",
                    coverage=SignalCoverage.UNAVAILABLE,
                )
            elif spec.execution_type is SignalExecutionType.DETERMINISTIC:
                try:
                    function = self.deterministic_functions[str(spec.function)]
                except KeyError as exc:
                    raise ValidationError(
                        f"unregistered deterministic signal function: {spec.function}"
                    ) from exc
                result = function(spec, documents, as_of)
            else:
                if self.llm_runner is None:
                    raise ValidationError("LLM signal runner is not configured")
                skill = self.snapshot.skills.get(spec.ref, "")
                if not skill.strip():
                    raise ValidationError(f"frozen LLM skill is missing: {spec.ref}")
                result, signal_usage = self.llm_runner.execute(
                    spec, documents, skill, as_of
                )
                usage = usage + signal_usage
            validate_signal_result(spec, result, documents, as_of=as_of)
            results.append(result)
        return SignalBatchResult(
            results=tuple(results),
            signal_calls=len(results),
            usage=usage,
            resolutions=tuple(resolutions),
        )


def validate_signal_result(
    spec: SignalSpec,
    result: SignalResult,
    documents: Iterable[RawInfoDocument],
    *,
    as_of: datetime,
) -> None:
    """Fail closed on identity, future time, source, or exact-span mismatch."""

    if result.signal_id != spec.signal_id or result.version != spec.version:
        raise ValidationError("signal result identity does not match SignalSpec")
    if result.value is SignalValue.UNAVAILABLE:
        return
    evidence = result.supporting_evidence + result.counter_evidence
    if spec.evidence_policy.require_source and not evidence:
        raise ValidationError("available signal result requires source evidence")
    documents_by_id = {document.document_id: document for document in documents}
    for item in evidence:
        try:
            document = documents_by_id[item.document_id]
        except KeyError as exc:
            raise ValidationError("signal evidence cites a document outside its inputs") from exc
        if document.available_at > as_of or item.timestamp > as_of:
            raise ValidationError("signal evidence timestamp exceeds prediction time")
        if spec.evidence_policy.require_exact_span and item.exact_span not in document.content:
            raise ValidationError("signal evidence exact span is not in cited document")


def default_deterministic_signal_functions() -> dict[str, DeterministicSignalFunction]:
    """Return executable functions used by the manually seeded v1 Signals."""

    return {
        "financial.revenue_growth_yoy": _metadata_signal("revenue_growth_yoy"),
        "financial.revenue_acceleration": _revenue_acceleration_signal,
        "financial.gross_margin_change": _metadata_signal("gross_margin_change"),
        "market.max_drawdown_1y": _max_drawdown_signal,
        "company.market_cap": _metadata_signal("market_cap"),
        "financial.cash_reserves": _metadata_signal("cash_reserves"),
        "news.negative_word_count": _negative_word_count_signal,
    }


def _metadata_signal(key: str) -> DeterministicSignalFunction:
    def execute(
        spec: SignalSpec,
        documents: tuple[RawInfoDocument, ...],
        as_of: datetime,
    ) -> SignalResult:
        found = _latest_metadata_value(documents, key)
        if found is None:
            return _unavailable_result(spec, f"Raw Info did not contain {key}.")
        value, document = found
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValidationError(f"deterministic metadata {key} must be numeric")
        return _numeric_result(spec, float(value), document, as_of, label=key)

    return execute


def _revenue_acceleration_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    direct = _latest_metadata_value(documents, "revenue_acceleration")
    if direct is not None:
        value, document = direct
        return _numeric_result(
            spec, float(value), document, as_of, label="revenue_acceleration"
        )
    current = _latest_metadata_value(documents, "revenue_growth_yoy")
    previous = _latest_metadata_value(documents, "previous_revenue_growth_yoy")
    if current is None or previous is None:
        return _unavailable_result(spec, "Revenue growth history was incomplete.")
    value = float(current[0]) - float(previous[0])
    return _numeric_result(spec, value, current[1], as_of, label="revenue_acceleration")


def _max_drawdown_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    found = _latest_metadata_value(documents, "prices")
    if found is None:
        return _unavailable_result(spec, "Raw Info did not contain a price series.")
    values, document = found
    if not isinstance(values, list) or not values:
        raise ValidationError("market price metadata must be a non-empty list")
    peak = -math.inf
    drawdown = 0.0
    for raw in values:
        price = float(raw)
        if price <= 0:
            raise ValidationError("market price metadata must be positive")
        peak = max(peak, price)
        drawdown = min(drawdown, (price / peak) - 1)
    return _numeric_result(spec, drawdown, document, as_of, label="max_drawdown_1y")


def _negative_word_count_signal(
    spec: SignalSpec,
    documents: tuple[RawInfoDocument, ...],
    as_of: datetime,
) -> SignalResult:
    """Count configured literal negative terms across complete news documents."""

    raw_terms = spec.parameters.get(
        "terms",
        ("decline", "loss", "risk", "delay", "investigation", "default"),
    )
    if not isinstance(raw_terms, (list, tuple)):
        raise ValidationError("negative word count terms must be a list")
    terms = tuple(str(item).casefold() for item in raw_terms if str(item).strip())
    count = sum(
        document.content.casefold().count(term)
        for document in documents
        for term in terms
    )
    threshold = int(spec.parameters.get("negative_count_min", 1))
    document = documents[0]
    span = document.content[: min(240, len(document.content))]
    return SignalResult(
        signal_id=spec.signal_id,
        version=spec.version,
        value=(SignalValue.NEGATIVE if count >= threshold else SignalValue.NEUTRAL),
        confidence=1.0,
        interpretation=f"negative_word_count={count}",
        supporting_evidence=(
            SignalEvidence(
                document_id=document.document_id,
                exact_span=span,
                timestamp=min(document.available_at, as_of),
            ),
        ),
        coverage=SignalCoverage.SUFFICIENT,
    )


def _numeric_result(
    spec: SignalSpec,
    numeric_value: float,
    document: RawInfoDocument,
    as_of: datetime,
    *,
    label: str,
) -> SignalResult:
    positive_min = float(spec.parameters.get("positive_min", 0.0))
    negative_max = float(spec.parameters.get("negative_max", positive_min))
    if negative_max > positive_min:
        raise ValidationError("negative_max cannot exceed positive_min")
    if numeric_value >= positive_min:
        value = SignalValue.POSITIVE
    elif numeric_value <= negative_max:
        value = SignalValue.NEGATIVE
    else:
        value = SignalValue.NEUTRAL
    span = document.content[: min(240, len(document.content))]
    return SignalResult(
        signal_id=spec.signal_id,
        version=spec.version,
        value=value,
        confidence=1.0,
        interpretation=f"{label}={numeric_value:.6g}",
        supporting_evidence=(
            SignalEvidence(
                document_id=document.document_id,
                exact_span=span,
                timestamp=min(document.available_at, as_of),
            ),
        ),
        coverage=SignalCoverage.SUFFICIENT,
    )


def _unavailable_result(spec: SignalSpec, interpretation: str) -> SignalResult:
    return SignalResult(
        signal_id=spec.signal_id,
        version=spec.version,
        value=SignalValue.UNAVAILABLE,
        confidence=0.0,
        interpretation=interpretation,
        coverage=SignalCoverage.UNAVAILABLE,
    )


def _latest_metadata_value(
    documents: tuple[RawInfoDocument, ...], key: str
) -> tuple[Any, RawInfoDocument] | None:
    for document in reversed(documents):
        if key in document.metadata:
            return document.metadata[key], document
    return None


def _parse_ref(signal_ref: str) -> tuple[str, int]:
    match = re.fullmatch(r"([a-z0-9][a-z0-9_:-]*):v([1-9][0-9]*)", signal_ref)
    if match is None:
        raise ValidationError(f"invalid signal ref: {signal_ref}")
    return match.group(1), int(match.group(2))


def _validate_id(value: str, name: str) -> None:
    if not _SAFE_ID.fullmatch(value):
        raise ValidationError(f"{name} must use lowercase safe identifier characters")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"required JSON artifact is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"JSON artifact must contain an object: {path}")
    return value


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_or_verify_json(path: Path, value: Mapping[str, Any]) -> None:
    """Preserve an immutable governance artifact or verify an exact replay."""

    expected = json.loads(json.dumps(dict(value), sort_keys=True))
    if path.exists():
        if _read_json(path) != expected:
            raise ValidationError(f"conflicting immutable JSON artifact: {path}")
        return
    _atomic_write_json(path, expected)
