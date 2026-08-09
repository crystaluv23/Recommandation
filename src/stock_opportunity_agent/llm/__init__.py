"""Auto-discovered registry for reusable LLM providers and model aliases."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar, overload

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.llm.agent import (
    AgentModel,
    AgentRequest,
    AgentRunResult,
    AgentTurn,
    AgentUsage,
    DomainTool,
    GenericAgent,
    ToolCall,
    ToolObservation,
)


ProviderFactory = Callable[..., Any]
ModelClientFactory = Callable[["ModelClientSettings"], Any]
T = TypeVar("T", bound=ProviderFactory)
M = TypeVar("M", bound=ModelClientFactory)

_PROVIDER_REGISTRY: dict[str, ProviderFactory] = {}
_MODEL_REGISTRY: dict[str, "RegisteredModel"] = {}
_DISCOVERED = False
_DISCOVERING = False
_MODEL_ROLES = frozenset({"evolution", "judge"})
_PROPOSAL_PROFILES = frozenset(
    {"none", "reviewed_file", "plain_json", "openrouter_fusion"}
)


@dataclass(frozen=True)
class ModelClientSettings:
    """Runtime-only settings passed to a registered model client factory."""

    preview_only: bool = False
    temperature: float = 0.0
    timeout_seconds: float = 90.0
    max_http_attempts: int = 1
    environ: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.temperature <= 1:
            raise ValidationError("model temperature must be between 0 and 1")
        if self.timeout_seconds <= 0:
            raise ValidationError("model timeout_seconds must be positive")
        if self.max_http_attempts < 1:
            raise ValidationError("model max_http_attempts must be positive")


@dataclass(frozen=True)
class RegisteredModel:
    """One stable CLI alias and the factory that constructs its API client."""

    alias: str
    provider: str
    model: str
    roles: tuple[str, ...]
    api_key_env_var: str
    description: str
    client_factory: ModelClientFactory = field(repr=False, compare=False)
    proposal_profile: str = "none"
    provider_route: str | None = None
    web_tools_allowed: bool = False
    default_max_output_tokens: int = 2200
    default_reasoning_effort: str | None = None
    default_input_cost_per_million_tokens: float = 0.0
    default_output_cost_per_million_tokens: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("alias", self.alias),
            ("provider", self.provider),
            ("model", self.model),
            ("description", self.description),
        ):
            if not value.strip():
                raise ValidationError(f"registered model {name} must not be empty")
        if not self.roles or set(self.roles) - _MODEL_ROLES:
            raise ValidationError("registered model roles must use evolution and/or judge")
        if len(set(self.roles)) != len(self.roles):
            raise ValidationError("registered model roles must be unique")
        if self.proposal_profile not in _PROPOSAL_PROFILES:
            raise ValidationError("unsupported registered model proposal profile")
        if "evolution" in self.roles and self.proposal_profile == "none":
            raise ValidationError("evolution model requires a proposal profile")
        if "judge" in self.roles and self.web_tools_allowed:
            raise ValidationError("judge model registration must be no-web")
        if self.default_max_output_tokens < 1:
            raise ValidationError("registered model output-token bound must be positive")
        if (
            self.default_input_cost_per_million_tokens < 0
            or self.default_output_cost_per_million_tokens < 0
        ):
            raise ValidationError("registered model token prices cannot be negative")
        if self.proposal_profile == "plain_json" and (
            self.default_input_cost_per_million_tokens <= 0
            or self.default_output_cost_per_million_tokens <= 0
        ):
            raise ValidationError(
                "plain_json evolution model token prices must be positive"
            )

    @property
    def provider_identity(self) -> str:
        """Return the stable provider identity stored in run artifacts."""

        return (
            f"{self.provider}:{self.provider_route}"
            if self.provider_route
            else self.provider
        )

    def create_client(self, settings: ModelClientSettings) -> Any:
        """Construct this model's provider client without exposing registry internals."""

        return self.client_factory(settings)

    def to_public_dict(self) -> dict[str, Any]:
        """Return secret-free catalog metadata for CLI and run manifests."""

        return {
            "alias": self.alias,
            "provider": self.provider,
            "provider_identity": self.provider_identity,
            "provider_route": self.provider_route,
            "model": self.model,
            "roles": list(self.roles),
            "api_key_env_var": self.api_key_env_var,
            "description": self.description,
            "proposal_profile": self.proposal_profile,
            "web_tools_allowed": self.web_tools_allowed,
            "default_max_output_tokens": self.default_max_output_tokens,
            "default_reasoning_effort": self.default_reasoning_effort,
            "default_input_cost_per_million_tokens": (
                self.default_input_cost_per_million_tokens
            ),
            "default_output_cost_per_million_tokens": (
                self.default_output_cost_per_million_tokens
            ),
        }


@overload
def register(provider: T, /) -> T:
    ...


@overload
def register(name: str, /) -> Callable[[T], T]:
    ...


def register(provider: T | str, /) -> T | Callable[[T], T]:
    """Register an LLM provider factory with ``@register`` or a named form."""

    if isinstance(provider, str):
        name = provider

        def decorator(func: T) -> T:
            _add_provider(name, func)
            return func

        return decorator

    _add_provider(provider.__name__, provider)
    return provider


def register_model(
    alias: str,
    *,
    provider: str,
    model: str,
    roles: tuple[str, ...],
    api_key_env_var: str,
    description: str,
    proposal_profile: str = "none",
    provider_route: str | None = None,
    web_tools_allowed: bool = False,
    default_max_output_tokens: int = 2200,
    default_reasoning_effort: str | None = None,
    default_input_cost_per_million_tokens: float = 0.0,
    default_output_cost_per_million_tokens: float = 0.0,
) -> Callable[[M], M]:
    """Register one auto-discovered CLI model alias in its provider module."""

    def decorator(factory: M) -> M:
        _add_model(
            RegisteredModel(
                alias=alias,
                provider=provider,
                model=model,
                roles=roles,
                api_key_env_var=api_key_env_var,
                description=description,
                proposal_profile=proposal_profile,
                provider_route=provider_route,
                web_tools_allowed=web_tools_allowed,
                default_max_output_tokens=default_max_output_tokens,
                default_reasoning_effort=default_reasoning_effort,
                default_input_cost_per_million_tokens=(
                    default_input_cost_per_million_tokens
                ),
                default_output_cost_per_million_tokens=(
                    default_output_cost_per_million_tokens
                ),
                client_factory=factory,
            )
        )
        return factory

    return decorator


def get(name: str) -> ProviderFactory:
    """Return an auto-discovered LLM provider factory by name."""

    _discover_modules()
    try:
        return _PROVIDER_REGISTRY[name]
    except KeyError as exc:
        raise ValidationError(f"unknown LLM model provider: {name}") from exc


def create(name: str, *args: Any, **kwargs: Any) -> Any:
    """Create a provider instance through the registered factory."""

    return get(name)(*args, **kwargs)


def registered() -> tuple[str, ...]:
    """Return auto-discovered provider names."""

    _discover_modules()
    return tuple(sorted(_PROVIDER_REGISTRY))


def model_catalog(*, role: str | None = None) -> tuple[RegisteredModel, ...]:
    """Return model registrations, optionally restricted to one declared role."""

    _discover_modules()
    if role is not None and role not in _MODEL_ROLES:
        raise ValidationError(f"unknown LLM model role: {role}")
    values = _MODEL_REGISTRY.values()
    return tuple(
        sorted(
            (item for item in values if role is None or role in item.roles),
            key=lambda item: item.alias,
        )
    )


def get_model(alias: str, *, role: str | None = None) -> RegisteredModel:
    """Return one model alias and verify that it supports the requested role."""

    _discover_modules()
    try:
        registered_model = _MODEL_REGISTRY[alias]
    except KeyError as exc:
        available = ", ".join(item.alias for item in model_catalog(role=role))
        raise ValidationError(
            f"unknown LLM model alias {alias!r}; available: {available or 'none'}"
        ) from exc
    if role is not None and role not in registered_model.roles:
        raise ValidationError(
            f"LLM model alias {alias!r} does not support role {role!r}"
        )
    return registered_model


def _add_provider(name: str, provider: ProviderFactory) -> None:
    normalized = name.strip()
    if not normalized:
        raise ValidationError("provider name must not be empty")
    if normalized in _PROVIDER_REGISTRY:
        raise ValidationError(f"LLM model provider already registered: {normalized}")
    _PROVIDER_REGISTRY[normalized] = provider


def _add_model(registered_model: RegisteredModel) -> None:
    if registered_model.provider not in _PROVIDER_REGISTRY:
        raise ValidationError(
            f"model {registered_model.alias!r} references unregistered provider "
            f"{registered_model.provider!r}"
        )
    if registered_model.alias in _MODEL_REGISTRY:
        raise ValidationError(
            f"LLM model alias already registered: {registered_model.alias}"
        )
    _MODEL_REGISTRY[registered_model.alias] = registered_model


def _discover_modules() -> None:
    """Import package modules once so their decorators populate both registries."""

    global _DISCOVERED, _DISCOVERING
    if _DISCOVERED or _DISCOVERING:
        return
    _DISCOVERING = True
    try:
        for module in sorted(pkgutil.iter_modules(__path__), key=lambda row: row.name):
            if module.name.startswith("_"):
                continue
            importlib.import_module(f"{__name__}.{module.name}")
        _DISCOVERED = True
    finally:
        _DISCOVERING = False
