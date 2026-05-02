"""Validated configuration records and loader for agent runs."""

from __future__ import annotations

import json
import os
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping, TypeVar, Union, get_args, get_origin, get_type_hints

from stock_opportunity_agent.models import ValidationError


T = TypeVar("T")


@dataclass(frozen=True)
class UniverseConfig:
    """Universe filters for the MVP US-listed common stock screen."""

    country: str = "US"
    security_types: tuple[str, ...] = ("common_stock",)
    min_market_cap_usd: float = 5_000_000_000
    min_average_daily_dollar_volume: float = 25_000_000
    priority_sectors: tuple[str, ...] = (
        "Semiconductors",
        "AI Infrastructure",
        "Power Equipment",
        "Cooling",
        "Software",
        "Industrials",
        "Defense",
    )

    def __post_init__(self) -> None:
        _require_non_empty(self.country, "country")
        _require_positive(self.min_market_cap_usd, "min_market_cap_usd")
        _require_positive(self.min_average_daily_dollar_volume, "min_average_daily_dollar_volume")
        if not self.security_types:
            raise ValidationError("security_types must not be empty")


@dataclass(frozen=True)
class DataSourceConfig:
    """Data source adapter names and optional environment variable references."""

    price_source: str = "alpha_vantage"
    fundamentals_source: str = "sec_edgar"
    document_source: str = "sec_edgar"
    sec_user_agent: str = "stock-opportunity-agent/0.1 contact@example.com"
    alpha_vantage_api_key_env_var: str = "ALPHA_VANTAGE_API_KEY"
    credential_env_vars: tuple[str, ...] = ("ALPHA_VANTAGE_API_KEY",)

    def __post_init__(self) -> None:
        for name in (
            "price_source",
            "fundamentals_source",
            "document_source",
            "sec_user_agent",
            "alpha_vantage_api_key_env_var",
        ):
            _require_non_empty(getattr(self, name), name)

    def public_dict(self) -> dict[str, Any]:
        """Return config fields safe for run records and reports."""

        return {
            "price_source": self.price_source,
            "fundamentals_source": self.fundamentals_source,
            "document_source": self.document_source,
            "sec_user_agent": self.sec_user_agent,
            "alpha_vantage_api_key_env_var": self.alpha_vantage_api_key_env_var,
            "credential_env_vars": tuple(self.credential_env_vars),
        }


@dataclass(frozen=True)
class StorageConfig:
    """Local storage locations for data, memory, and reports."""

    root_dir: str = ".agent_state"
    sqlite_path: str = ".agent_state/agent.sqlite"
    parquet_dir: str = ".agent_state/parquet"
    reports_dir: str = "reports"

    def __post_init__(self) -> None:
        for field in fields(self):
            _require_non_empty(getattr(self, field.name), field.name)


@dataclass(frozen=True)
class ScoringConfig:
    """Conservative score thresholds used by early pipeline modules."""

    scoring_version: str = "scoring-v0.1"
    min_score_for_watchlist: float = 0.55
    min_score_for_action_candidate: float = 0.75
    max_extreme_valuation_risk: float = 0.85

    def __post_init__(self) -> None:
        _require_non_empty(self.scoring_version, "scoring_version")
        _require_unit_interval(self.min_score_for_watchlist, "min_score_for_watchlist")
        _require_unit_interval(self.min_score_for_action_candidate, "min_score_for_action_candidate")
        _require_unit_interval(self.max_extreme_valuation_risk, "max_extreme_valuation_risk")
        if self.min_score_for_action_candidate < self.min_score_for_watchlist:
            raise ValidationError("action candidate threshold cannot be below watchlist threshold")


@dataclass(frozen=True)
class PromptConfig:
    """Prompt and model version identifiers used in auditable artifacts."""

    prompt_version: str = "prompt-v0.1"
    model_version: str = "gpt-5.4-mini"
    openai_api_key_env_var: str = "OPENAI_API_KEY"
    openai_base_url: str = "https://api.openai.com/v1"
    research_temperature: float = 0.2

    def __post_init__(self) -> None:
        _require_non_empty(self.prompt_version, "prompt_version")
        _require_non_empty(self.model_version, "model_version")
        _require_non_empty(self.openai_api_key_env_var, "openai_api_key_env_var")
        _require_non_empty(self.openai_base_url, "openai_base_url")
        _require_unit_interval(self.research_temperature, "research_temperature")


@dataclass(frozen=True)
class PipelineConfig:
    """Operational cadence and output sizing."""

    daily_enabled: bool = True
    weekly_watchlist_size: int = 20
    review_windows_days: tuple[int, ...] = (30, 90, 180)
    data_pipeline_version: str = "data-pipeline-v0.1"

    def __post_init__(self) -> None:
        if self.weekly_watchlist_size < 1:
            raise ValidationError("weekly_watchlist_size must be at least 1")
        if not self.review_windows_days:
            raise ValidationError("review_windows_days must not be empty")
        for days in self.review_windows_days:
            if days < 1:
                raise ValidationError("review windows must be positive")
        _require_non_empty(self.data_pipeline_version, "data_pipeline_version")


@dataclass(frozen=True)
class MetaLearningPolicy:
    """Approval rules for framework changes proposed by meta-learning."""

    low_risk_auto_approval: bool = False
    medium_risk_requires_human: bool = True
    high_risk_requires_human: bool = True
    signal_version: str = "signals-v0.1"

    def __post_init__(self) -> None:
        _require_non_empty(self.signal_version, "signal_version")
        if not self.medium_risk_requires_human or not self.high_risk_requires_human:
            raise ValidationError("medium and high risk meta-learning changes require human approval")


@dataclass(frozen=True)
class AgentConfig:
    """Top-level validated configuration used to stamp each agent run."""

    config_version: str = "config-v0.1"
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    data_sources: DataSourceConfig = field(default_factory=DataSourceConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    prompts: PromptConfig = field(default_factory=PromptConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    meta_learning: MetaLearningPolicy = field(default_factory=MetaLearningPolicy)

    def __post_init__(self) -> None:
        _require_non_empty(self.config_version, "config_version")

    def public_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible config record with no secret values."""

        return _to_public_dict(self)


def load_config(path: str | Path | None = None, environ: Mapping[str, str] | None = None) -> AgentConfig:
    """Load validated config from defaults, an optional JSON file, and env overrides.

    Environment overrides currently cover run identity, storage roots, API key
    variable names, and SEC user-agent:
    ``SOA_CONFIG_VERSION``, ``SOA_STORAGE_ROOT_DIR``, ``SOA_REPORTS_DIR``,
    ``SOA_OPENAI_API_KEY_ENV_VAR``, ``SOA_ALPHA_VANTAGE_API_KEY_ENV_VAR``,
    and ``SOA_SEC_USER_AGENT``.
    """

    data: dict[str, Any] = {}
    if path is not None:
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValidationError("config file must contain a JSON object")
        data = loaded

    env = os.environ if environ is None else environ
    data = _merge_dicts(data, _env_overrides(env))
    return _build_dataclass(AgentConfig, data)


def _build_dataclass(cls: type[T], data: Mapping[str, Any]) -> T:
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    allowed = {field.name for field in fields(cls)}
    unknown = set(data) - allowed
    if unknown:
        raise ValidationError(f"unknown config fields for {cls.__name__}: {sorted(unknown)}")

    for field in fields(cls):
        if field.name in data:
            kwargs[field.name] = _coerce_config_value(data[field.name], hints[field.name])
        elif field.default is not MISSING:
            continue
        elif field.default_factory is not MISSING:
            continue
        else:
            raise ValidationError(f"{cls.__name__}.{field.name} is required")
    return cls(**kwargs)


def _coerce_config_value(value: Any, annotation: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Union:
        non_none = [arg for arg in args if arg is not type(None)]
        if value is None:
            return None
        if len(non_none) == 1:
            return _coerce_config_value(value, non_none[0])
    if origin is tuple:
        return tuple(_coerce_config_value(item, args[0]) for item in value)
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, Mapping):
            raise ValidationError(f"{annotation.__name__} config must be an object")
        return _build_dataclass(annotation, value)
    return value


def _merge_dicts(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _env_overrides(environ: Mapping[str, str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if "SOA_CONFIG_VERSION" in environ:
        overrides["config_version"] = environ["SOA_CONFIG_VERSION"]
    storage: dict[str, Any] = {}
    if "SOA_STORAGE_ROOT_DIR" in environ:
        storage["root_dir"] = environ["SOA_STORAGE_ROOT_DIR"]
    if "SOA_REPORTS_DIR" in environ:
        storage["reports_dir"] = environ["SOA_REPORTS_DIR"]
    if storage:
        overrides["storage"] = storage
    prompts: dict[str, Any] = {}
    if "SOA_OPENAI_API_KEY_ENV_VAR" in environ:
        prompts["openai_api_key_env_var"] = environ["SOA_OPENAI_API_KEY_ENV_VAR"]
    if prompts:
        overrides["prompts"] = prompts
    data_sources: dict[str, Any] = {}
    if "SOA_ALPHA_VANTAGE_API_KEY_ENV_VAR" in environ:
        data_sources["alpha_vantage_api_key_env_var"] = environ["SOA_ALPHA_VANTAGE_API_KEY_ENV_VAR"]
    if "SOA_SEC_USER_AGENT" in environ:
        data_sources["sec_user_agent"] = environ["SOA_SEC_USER_AGENT"]
    if data_sources:
        overrides["data_sources"] = data_sources
    return overrides


def _to_public_dict(value: Any) -> Any:
    if isinstance(value, DataSourceConfig):
        return value.public_dict()
    if is_dataclass(value):
        return {field.name: _to_public_dict(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return tuple(_to_public_dict(item) for item in value)
    if isinstance(value, list):
        return [_to_public_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_public_dict(item) for key, item in value.items()}
    return value


def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValidationError(f"{name} must not be empty")


def _require_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValidationError(f"{name} must be positive")


def _require_unit_interval(value: float, name: str) -> None:
    if not 0 <= value <= 1:
        raise ValidationError(f"{name} must be between 0 and 1")
