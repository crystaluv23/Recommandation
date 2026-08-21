"""Bounded domain-tool agent harness shared by research and evolution tasks."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Mapping, Protocol, TypeVar

from stock_opportunity_agent.models import ValidationError


T = TypeVar("T")


@dataclass(frozen=True)
class AgentUsage:
    """Auditable usage reported by one or more model turns."""

    llm_calls: int = 0
    tokens: int = 0
    cost: float = 0.0

    def __post_init__(self) -> None:
        if self.llm_calls < 0 or self.tokens < 0 or self.cost < 0:
            raise ValidationError("agent usage values cannot be negative")

    def __add__(self, other: "AgentUsage") -> "AgentUsage":
        return AgentUsage(
            llm_calls=self.llm_calls + other.llm_calls,
            tokens=self.tokens + other.tokens,
            cost=self.cost + other.cost,
        )


@dataclass(frozen=True)
class ToolCall:
    """One model-requested domain tool call."""

    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("tool call name must not be empty")
        object.__setattr__(self, "arguments", dict(self.arguments))


@dataclass(frozen=True)
class AgentTurn:
    """One model response containing exactly one action."""

    tool_call: ToolCall | None = None
    final_output: Any | None = None
    usage: AgentUsage = field(default_factory=lambda: AgentUsage(llm_calls=1))

    def __post_init__(self) -> None:
        if (self.tool_call is None) == (self.final_output is None):
            raise ValidationError(
                "agent turn must contain exactly one tool call or final output"
            )


@dataclass(frozen=True)
class ToolObservation:
    """Recorded result from one named domain tool."""

    name: str
    arguments: Mapping[str, Any]
    result: Any


@dataclass(frozen=True)
class AgentRequest:
    """Immutable view supplied to the model for each bounded step."""

    prompt: str
    tool_cards: tuple[Mapping[str, Any], ...]
    workspace: Mapping[str, Any]
    observations: tuple[ToolObservation, ...]


class AgentModel(Protocol):
    """Minimal adapter implemented by deterministic fixtures or LLM clients."""

    def respond(self, request: AgentRequest) -> AgentTurn:
        """Return the next tool call or structured final output."""


@dataclass(frozen=True)
class DomainTool:
    """One explicitly granted domain operation."""

    name: str
    description: str
    function: Callable[..., Any] = field(repr=False, compare=False)
    arguments_schema: Mapping[str, Any] | None = None
    examples: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.description.strip():
            raise ValidationError("domain tool name and description are required")
        if self.name in {"ls", "cat", "rm", "shell", "exec"}:
            raise ValidationError("raw filesystem and shell tools are not allowed")
        if self.arguments_schema is not None:
            object.__setattr__(self, "arguments_schema", dict(self.arguments_schema))
        object.__setattr__(
            self,
            "examples",
            tuple(dict(example) for example in self.examples),
        )

    def card(self) -> Mapping[str, Any]:
        """Return the prompt-safe progressive-disclosure card."""

        card: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "arguments": str(inspect.signature(self.function)),
        }
        card["arguments_schema"] = (
            dict(self.arguments_schema)
            if self.arguments_schema is not None
            else _signature_arguments_schema(self.function)
        )
        if self.examples:
            card["examples"] = [dict(example) for example in self.examples]
        return card


def _signature_arguments_schema(function: Callable[..., Any]) -> dict[str, Any]:
    signature = inspect.signature(function)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in signature.parameters.items():
        annotation = parameter.annotation
        properties[name] = {
            "python_type": (
                "any" if annotation is inspect.Parameter.empty else str(annotation)
            )
        }
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
        else:
            properties[name]["default"] = parameter.default
    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": False,
    }


class AgentRunError(ValidationError):
    """Bounded agent failure carrying the complete tool trajectory."""

    def __init__(
        self,
        message: str,
        *,
        observations: tuple[ToolObservation, ...],
        usage: AgentUsage,
    ) -> None:
        self.observations = tuple(observations)
        self.usage = usage
        super().__init__(message)


@dataclass(frozen=True)
class AgentRunResult(Generic[T]):
    """Validated final value plus complete local tool trajectory."""

    value: T
    observations: tuple[ToolObservation, ...]
    usage: AgentUsage


class GenericAgent:
    """Execute a bounded tool loop without granting arbitrary I/O."""

    def __init__(self, model: AgentModel) -> None:
        self.model = model

    def run(
        self,
        *,
        prompt: str,
        tools: tuple[DomainTool, ...] | list[DomainTool],
        workspace: Mapping[str, Any],
        output_schema: Callable[[Any], T],
        completion_validator: (
            Callable[[T, tuple[ToolObservation, ...]], None] | None
        ) = None,
        max_steps: int,
        max_output_corrections: int = 1,
    ) -> AgentRunResult[T]:
        """Run until structured output or a fixed step limit is reached."""

        if not prompt.strip():
            raise ValidationError("agent prompt must not be empty")
        if max_steps < 1:
            raise ValidationError("agent max_steps must be positive")
        if max_output_corrections < 0:
            raise ValidationError("agent max_output_corrections cannot be negative")
        tool_by_name = {tool.name: tool for tool in tools}
        if len(tool_by_name) != len(tools):
            raise ValidationError("domain tool names must be unique")

        observations: list[ToolObservation] = []
        usage = AgentUsage()
        output_corrections = 0
        cards = tuple(tool.card() for tool in tools)
        safe_workspace = dict(workspace)

        for _ in range(max_steps):
            try:
                turn = self.model.respond(
                    AgentRequest(
                        prompt=prompt,
                        tool_cards=cards,
                        workspace=safe_workspace,
                        observations=tuple(observations),
                    )
                )
            except ValidationError as exc:
                raise AgentRunError(
                    str(exc),
                    observations=tuple(observations),
                    usage=usage,
                ) from exc
            usage = usage + turn.usage
            if turn.final_output is not None:
                try:
                    value = output_schema(turn.final_output)
                    if completion_validator is not None:
                        completion_validator(value, tuple(observations))
                except ValidationError as exc:
                    if output_corrections >= max_output_corrections:
                        raise AgentRunError(
                            "agent final output remained invalid after "
                            f"{max_output_corrections} corrections",
                            observations=tuple(observations),
                            usage=usage,
                        ) from exc
                    output_corrections += 1
                    observations.append(
                        ToolObservation(
                            name="validate_final_output",
                            arguments={"output": turn.final_output},
                            result={
                                "error": "output_validation",
                                "message": str(exc),
                            },
                        )
                    )
                    continue
                return AgentRunResult(
                    value=value,
                    observations=tuple(observations),
                    usage=usage,
                )

            assert turn.tool_call is not None
            try:
                tool = tool_by_name[turn.tool_call.name]
            except KeyError:
                observations.append(
                    ToolObservation(
                        name=turn.tool_call.name,
                        arguments=dict(turn.tool_call.arguments),
                        result={
                            "error": "ungranted_tool",
                            "granted_tools": sorted(tool_by_name),
                        },
                    )
                )
                continue
            arguments = dict(turn.tool_call.arguments)
            try:
                inspect.signature(tool.function).bind(**arguments)
            except TypeError:
                observations.append(
                    ToolObservation(
                        name=tool.name,
                        arguments=arguments,
                        result={
                            "error": "invalid_arguments",
                            "expected": str(inspect.signature(tool.function)),
                        },
                    )
                )
                continue
            try:
                result = tool.function(**arguments)
            except ValidationError as exc:
                observations.append(
                    ToolObservation(
                        name=tool.name,
                        arguments=arguments,
                        result={
                            "error": "tool_validation",
                            "message": str(exc),
                        },
                    )
                )
                continue
            observations.append(
                ToolObservation(
                    name=tool.name,
                    arguments=arguments,
                    result=result,
                )
            )

        last_error = ""
        if observations and isinstance(observations[-1].result, Mapping):
            last_error = str(observations[-1].result.get("error", ""))
        message = "generic agent exhausted max_steps without final output"
        if last_error:
            message += f": {last_error}"
        raise AgentRunError(
            message,
            observations=tuple(observations),
            usage=usage,
        )
