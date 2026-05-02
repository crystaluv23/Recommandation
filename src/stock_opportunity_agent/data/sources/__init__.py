"""Registry for external data-source providers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, overload

from stock_opportunity_agent.models import ValidationError


SourceFactory = Callable[..., Any]
T = TypeVar("T", bound=SourceFactory)

_REGISTRY: dict[str, SourceFactory] = {}


@overload
def register(source: T, /) -> T:
    ...


@overload
def register(name: str, /) -> Callable[[T], T]:
    ...


def register(source: T | str, /) -> T | Callable[[T], T]:
    """Register a data-source factory.

    The decorator supports both ``@register`` and ``@register("sec_edgar")``.
    """

    if isinstance(source, str):
        name = source

        def decorator(func: T) -> T:
            _add(name, func)
            return func

        return decorator

    _add(source.__name__, source)
    return source


def get(name: str) -> SourceFactory:
    """Return a registered data-source factory by name."""

    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise ValidationError(f"unknown data source provider: {name}") from exc


def create(name: str, *args: Any, **kwargs: Any) -> Any:
    """Create a data-source provider through the registered factory."""

    return get(name)(*args, **kwargs)


def registered() -> tuple[str, ...]:
    """Return registered source names."""

    return tuple(sorted(_REGISTRY))


def _add(name: str, source: SourceFactory) -> None:
    if not name.strip():
        raise ValidationError("source name must not be empty")
    if name in _REGISTRY:
        raise ValidationError(f"data source provider already registered: {name}")
    _REGISTRY[name] = source


from stock_opportunity_agent.data.sources import alpha_vantage as _alpha_vantage  # noqa: E402,F401
from stock_opportunity_agent.data.sources import sec_edgar as _sec_edgar  # noqa: E402,F401
