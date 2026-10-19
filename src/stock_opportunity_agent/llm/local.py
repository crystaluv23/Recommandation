"""Local model aliases for reviewed-file and deterministic development paths."""

from __future__ import annotations

from typing import Any

from stock_opportunity_agent.llm import ModelClientSettings, register, register_model


@register("local")
def model(*_args: Any, **_kwargs: Any) -> None:
    """Return no API client for local orchestration adapters."""

    return None


@register_model(
    "codex-reviewed-file",
    provider="local",
    model="reviewed-candidate-json",
    roles=("evolution",),
    api_key_env_var="",
    description="Codex/human-reviewed candidate JSON; no provider call.",
    proposal_profile="reviewed_file",
)
def reviewed_file_model(_settings: ModelClientSettings) -> None:
    """Use the existing reviewed candidate-file proposer."""

    return None


@register_model(
    "local-heuristic",
    provider="local",
    model="deterministic-ralph-heuristic",
    roles=("judge",),
    api_key_env_var="",
    description="Network-free deterministic judge for orchestration diagnostics only.",
)
def local_heuristic_model(_settings: ModelClientSettings) -> None:
    """Use the existing deterministic Ralph blind analyzer."""

    return None


@register_model(
    "independent-subagent", provider="local", model="independent-subagent",
    roles=("evolution", "judge"), api_key_env_var="",
    description="Independent role agent through exact local request/response files; no API transport.",
    proposal_profile="independent_agent", default_max_output_tokens=16384,
)
def independent_subagent_model(_settings: ModelClientSettings) -> None:
    """Require explicit LocalRoleExchange injection in StructuredRoleClient."""
    return None
