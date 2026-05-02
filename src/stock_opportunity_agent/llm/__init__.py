"""Registry for LLM providers used across the agent."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, overload

from stock_opportunity_agent.models import ValidationError


ProviderFactory = Callable[..., Any]
T = TypeVar("T", bound=ProviderFactory)

_REGISTRY: dict[str, ProviderFactory] = {}


@overload
def register(provider: T, /) -> T:
    ...


@overload
def register(name: str, /) -> Callable[[T], T]:
    ...


def register(provider: T | str, /) -> T | Callable[[T], T]:
    """Register an LLM provider factory.

    The decorator supports both ``@register`` and ``@register("openai")``.
    """

    if isinstance(provider, str):
        name = provider

        def decorator(func: T) -> T:
            _add(name, func)
            return func

        return decorator

    _add(provider.__name__, provider)
    return provider


def get(name: str) -> ProviderFactory:
    """Return a registered LLM provider factory by name."""

    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise ValidationError(f"unknown LLM model provider: {name}") from exc


def create(name: str, *args: Any, **kwargs: Any) -> Any:
    """Create a provider instance through the registered factory."""

    return get(name)(*args, **kwargs)


def registered() -> tuple[str, ...]:
    """Return registered provider names."""

    return tuple(sorted(_REGISTRY))


def _add(name: str, provider: ProviderFactory) -> None:
    if not name.strip():
        raise ValidationError("provider name must not be empty")
    if name in _REGISTRY:
        raise ValidationError(f"LLM model provider already registered: {name}")
    _REGISTRY[name] = provider


from stock_opportunity_agent.llm import openai as _openai  # noqa: E402,F401
