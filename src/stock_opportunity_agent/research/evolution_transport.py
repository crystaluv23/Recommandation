"""Transport layer for the bounded evolution runtime."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol
from stock_opportunity_agent.artifacts import (
    atomic_write_json as _atomic_write_json,
    canonical_json_hash as _canonical_hash,
)
from stock_opportunity_agent.llm import ModelClientSettings, RegisteredModel, get_model
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.llm.openai import ChatMessage, PreparedJsonRequest
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution import (
    CandidateExecutionRejected,
    EvolutionControlFlow,
    ProgressCallback,
    RuntimeBudgetExceeded,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stock_opportunity_agent.research.evolution_control import (
        EvolutionRunContract,
    )


_FORBIDDEN_OUTCOME_KEYS = frozenset(
    {
        "ground_truth",
        "outcome",
        "outcome_label",
        "label",
        "is_surge",
        "magnitude_class",
        "realized_return",
        "realized_max_multiple",
        "future_price",
        "future_return",
        "post_outcome",
    }
)


def current_code_revision(project_root: str | Path) -> str:
    """Return HEAD only when tracked/runtime source state is reproducible."""

    root = Path(project_root)
    tracked = subprocess.run(
        ["git", "diff", "--quiet", "--", "src", "scripts", "configs"],
        cwd=root,
        check=False,
    )
    if tracked.returncode != 0:
        raise ValidationError("freeze-run requires committed tracked project changes")
    staged = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--quiet",
            "--",
            "src",
            "scripts",
            "configs",
        ],
        cwd=root,
        check=False,
    )
    if staged.returncode != 0:
        raise ValidationError("freeze-run requires committed staged project changes")
    untracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "src",
            "scripts",
            "configs",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    if untracked.stdout.strip():
        raise ValidationError("freeze-run requires committed runtime source files")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def public_model_contract(
    role_aliases: Mapping[str, str], *, environ: Mapping[str, str] | None = None
) -> dict[str, dict[str, Any]]:
    """Resolve registered models and record only public metadata/key presence."""

    env = os.environ if environ is None else environ
    result: dict[str, dict[str, Any]] = {}
    for role, alias in role_aliases.items():
        registry_role = "evolution" if role in {"proposer", "mining", "update"} else "judge"
        registration = get_model(alias, role=registry_role)
        metadata = registration.to_public_dict()
        metadata["api_key_available"] = bool(env.get(registration.api_key_env_var))
        result[str(role)] = metadata
    return result


class ExternalRequestPending(EvolutionControlFlow):
    """Raised after a no-network preflight has persisted one exact request."""

    def __init__(self, request_hash: str, request_path: Path) -> None:
        super().__init__(f"external request requires approval: {request_hash}")
        self.request_hash = request_hash
        self.request_path = request_path


class ExternalExecutionPaused(EvolutionControlFlow):
    """Control-plane pause that must never become candidate diagnostics."""

    def __init__(self, status: str, message: str) -> None:
        self.status = str(status)
        self.message = str(message)
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "reason": self.message,
            "error_type": type(self).__name__,
        }


class ExternalExecutionNotReady(ExternalExecutionPaused):
    """The frozen external boundary is not ready or not acknowledged."""


class ExternalBudgetExhausted(ExternalExecutionPaused):
    """The frozen attempt or cumulative cost ceiling cannot admit a request."""


class StructuredOutputInvalid(ValidationError):
    """A paid provider response was not exactly one JSON object."""

    def __init__(
        self,
        message: str,
        raw_output: str,
        usage: AgentUsage,
        *,
        output_tokens: int | None = None,
        output_token_limit: int | None = None,
    ) -> None:
        self.raw_output = str(raw_output)
        self.usage = usage
        self.output_tokens = output_tokens
        self.output_token_limit = output_token_limit
        super().__init__(message)


class ExactResponseCache:
    """Exact response reuse keyed only by canonical request hash."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self, request_hash: str) -> dict[str, Any] | None:
        path = self.root / f"{request_hash}.json"
        return _read_json(path) if path.exists() else None

    def store(self, request_hash: str, response: Mapping[str, Any]) -> None:
        _write_or_verify_json(
            self.root / f"{request_hash}.json",
            {"request_hash": request_hash, **dict(response)},
        )


class _TicketLock:
    """Minimal FIFO ticket lock for fair ledger admission."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._condition = threading.Condition(self._guard)
        self._next_ticket = 0
        self._serving = 0

    def __enter__(self) -> "_TicketLock":
        with self._condition:
            ticket = self._next_ticket
            self._next_ticket += 1
            while ticket != self._serving:
                self._condition.wait()
            return self

    def __exit__(self, *exc_info: object) -> None:
        with self._condition:
            self._serving += 1
            self._condition.notify_all()


class _InFlightEntry:
    """One physical external call that concurrent waiters may share."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.error: BaseException | None = None


class InFlightRequestCoordinator:
    """Leader/waiter sharing of identical concurrent external requests.

    The leader executes the physical call; waiters block boundedly and then
    read the shared cached response with zero usage, so one logical request
    pays once. Leader failure wakes waiters to take over as a new leader;
    waiting never hangs indefinitely.
    """

    def __init__(self, *, wait_timeout_seconds: float = 600.0) -> None:
        self.wait_timeout_seconds = wait_timeout_seconds
        self._guard = threading.Lock()
        self._entries: dict[str, _InFlightEntry] = {}

    def share(self, request_hash: str, execute, on_shared=None):
        while True:
            with self._guard:
                entry = self._entries.get(request_hash)
                if entry is None:
                    entry = _InFlightEntry()
                    self._entries[request_hash] = entry
                    leader = True
                else:
                    leader = False
            if leader:
                try:
                    return execute()
                finally:
                    entry.done.set()
                    with self._guard:
                        if self._entries.get(request_hash) is entry:
                            del self._entries[request_hash]
            if not entry.done.wait(timeout=self.wait_timeout_seconds):
                raise ValidationError(
                    "in-flight request wait exceeded its bound: " + request_hash
                )
            if entry.error is None and on_shared is not None:
                shared = on_shared()
                if shared is not None:
                    return shared
            # The leader failed or stored nothing: take over as a new leader.


class ExternalAttemptLedger:
    """Durable fail-closed reservation of attempts and conservative cost.

    Finalized attempts count their settled ``actual_cost``; in-flight attempts
    hold their full reservation until they finalize, so transient retries never
    permanently consume ceiling headroom the run did not actually spend.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_attempts: int,
        max_total_cost: float,
    ) -> None:
        if max_attempts < 1 or max_total_cost <= 0:
            raise ValidationError("ledger ceilings must be positive")
        self.path = Path(path)
        self.max_attempts = max_attempts
        self.max_total_cost = max_total_cost
        self._admission_lock = _TicketLock()
        self._write_lock = threading.RLock()
        if not self.path.exists():
            _atomic_write_json(
                self.path,
                {
                    "schema_version": "evolution-attempt-ledger-v1",
                    "max_attempts": max_attempts,
                    "max_total_cost": max_total_cost,
                    "attempts": [],
                },
            )
        else:
            data = _read_json(self.path)
            if (
                int(data.get("max_attempts", 0)) != max_attempts
                or float(data.get("max_total_cost", 0.0)) != max_total_cost
            ):
                raise ValidationError("attempt ledger ceilings conflict with frozen run")

    def reserve(self, request_hash: str, *, reserved_cost: float) -> int:
        if reserved_cost <= 0:
            raise ValidationError("reserved request cost must be positive")
        with self._admission_lock:
            return self._reserve_locked(request_hash, reserved_cost=reserved_cost)

    def _reserve_locked(self, request_hash: str, *, reserved_cost: float) -> int:
        with self._write_lock:
            return self._reserve_unlocked(request_hash, reserved_cost=reserved_cost)

    def _reserve_unlocked(self, request_hash: str, *, reserved_cost: float) -> int:
        data = _read_json(self.path)
        attempts = list(data.get("attempts", ()))
        if len(attempts) >= self.max_attempts:
            raise ExternalBudgetExhausted(
                "external_attempt_ceiling_exhausted",
                "external attempt ceiling exhausted",
            )
        committed_cost = sum(
            (
                float(item.get("actual_cost", 0.0))
                if item.get("status") in {"completed", "failed", "interrupted"}
                else float(item.get("reserved_cost", 0.0))
            )
            for item in attempts
        )
        if committed_cost + reserved_cost > self.max_total_cost + 1e-12:
            raise ExternalBudgetExhausted(
                "external_cost_ceiling_exhausted",
                "external cumulative cost ceiling would be exceeded",
            )
        attempt_id = len(attempts) + 1
        attempts.append(
            {
                "attempt_id": attempt_id,
                "request_hash": request_hash,
                "reserved_cost": reserved_cost,
                "status": "in_progress",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        data["attempts"] = attempts
        _atomic_write_json(self.path, data)
        return attempt_id

    def reconcile_interrupted(self) -> int:
        """Settle inherited in-flight rows before a resumed executor starts.

        The caller owns the workspace execution lock and invokes this exactly
        once before constructing role clients or workers. A request killed
        between send and response has unknown provider outcome, so its full
        conservative reservation remains charged rather than being silently
        released or retried.
        """

        with self._admission_lock:
            with self._write_lock:
                data = _read_json(self.path)
                attempts = list(data.get("attempts", ()))
                reconciled = 0
                finished_at = datetime.now(timezone.utc).isoformat()
                for attempt in attempts:
                    if attempt.get("status") != "in_progress":
                        continue
                    attempt["status"] = "interrupted"
                    attempt["actual_cost"] = float(
                        attempt.get("reserved_cost", 0.0)
                    )
                    attempt["finished_at"] = finished_at
                    attempt["error_type"] = "InterruptedExternalAttempt"
                    attempt["error_message"] = (
                        "request outcome was uncertain when the previous "
                        "executor stopped"
                    )
                    reconciled += 1
                if reconciled:
                    data["attempts"] = attempts
                    _atomic_write_json(self.path, data)
                return reconciled

    def finalize(
        self,
        attempt_id: int,
        *,
        status: str,
        actual_cost: float,
        response_hash: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if status not in {"completed", "failed"} or actual_cost < 0:
            raise ValidationError("invalid attempt completion")
        with self._write_lock:
            return self._finalize_locked(
                attempt_id,
                status=status,
                actual_cost=actual_cost,
                response_hash=response_hash,
                error_type=error_type,
                error_message=error_message,
            )

    def _finalize_locked(
        self,
        attempt_id: int,
        *,
        status: str,
        actual_cost: float,
        response_hash: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        data = _read_json(self.path)
        attempts = list(data.get("attempts", ()))
        try:
            attempt = attempts[attempt_id - 1]
        except IndexError as exc:
            raise ValidationError("unknown external attempt id") from exc
        if attempt.get("attempt_id") != attempt_id or attempt.get("status") != "in_progress":
            raise ValidationError("external attempt is not pending")
        attempt["status"] = status
        attempt["actual_cost"] = actual_cost
        attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
        if response_hash is not None:
            attempt["response_hash"] = response_hash
        if error_type is not None:
            attempt["error_type"] = error_type
        if error_message is not None:
            attempt["error_message"] = error_message[:500]
        data["attempts"] = attempts
        _atomic_write_json(self.path, data)

    @property
    def summary(self) -> dict[str, Any]:
        data = _read_json(self.path)
        attempts = list(data.get("attempts", ()))
        return {
            "attempt_count": len(attempts),
            "in_progress": sum(item.get("status") == "in_progress" for item in attempts),
            "interrupted": sum(item.get("status") == "interrupted" for item in attempts),
            "reserved_cost": sum(float(item.get("reserved_cost", 0.0)) for item in attempts),
            "actual_cost": sum(float(item.get("actual_cost", 0.0)) for item in attempts),
        }


@dataclass(frozen=True)
class DecisionTokenScores:
    """Provider-derived confidence for one binary JSON decision token."""

    yes_token_probability: float
    no_token_probability: float
    decision_margin: float

    def __post_init__(self) -> None:
        for name in (
            "yes_token_probability",
            "no_token_probability",
            "decision_margin",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0 <= float(value) <= 1
            ):
                raise ValidationError(f"{name} must be finite and in [0, 1]")

    def to_dict(self) -> dict[str, float]:
        return {
            "yes_token_probability": float(self.yes_token_probability),
            "no_token_probability": float(self.no_token_probability),
            "decision_margin": float(self.decision_margin),
        }


def _decision_token_scores_from_cache(
    cached: Mapping[str, Any],
) -> DecisionTokenScores | None:
    value = cached.get("decision_token_scores")
    if not isinstance(value, Mapping):
        return None
    try:
        return DecisionTokenScores(
            yes_token_probability=float(value["yes_token_probability"]),
            no_token_probability=float(value["no_token_probability"]),
            decision_margin=float(value["decision_margin"]),
        )
    except (KeyError, TypeError, ValueError, ValidationError):
        return None


def _normalized_binary_token(token: Any, choices: tuple[str, str]) -> str | None:
    if not isinstance(token, str):
        return None
    words = re.findall(r"[A-Za-z]+", token.upper())
    matches = [choice for choice in choices if choice.upper() in words]
    return matches[0] if len(matches) == 1 else None


def _provider_logprob_entries(raw: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Read documented Chat or compatible Responses token-logprob shapes."""

    choices = raw.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        logprobs = choices[0].get("logprobs")
        if isinstance(logprobs, Mapping) and isinstance(logprobs.get("content"), list):
            return tuple(
                item for item in logprobs["content"] if isinstance(item, Mapping)
            )
    output = raw.get("output")
    if isinstance(output, list):
        entries: list[Mapping[str, Any]] = []
        for message in output:
            if not isinstance(message, Mapping) or not isinstance(
                message.get("content"), list
            ):
                continue
            for content in message["content"]:
                if not isinstance(content, Mapping) or not isinstance(
                    content.get("logprobs"), list
                ):
                    continue
                entries.extend(
                    item
                    for item in content["logprobs"]
                    if isinstance(item, Mapping)
                )
        return tuple(entries)
    return ()


def _extract_decision_token_scores(
    raw: Mapping[str, Any],
    *,
    parsed: Mapping[str, Any],
    decision_field: str,
    decision_tokens: tuple[str, str],
) -> DecisionTokenScores | None:
    """Extract raw YES/NO probabilities and pairwise YES probability if complete."""

    chosen = parsed.get(decision_field)
    if not isinstance(chosen, str) or chosen not in decision_tokens:
        return None
    entries = _provider_logprob_entries(raw)
    for entry in entries:
        if _normalized_binary_token(entry.get("token"), decision_tokens) != chosen:
            continue
        exact_logprobs: dict[str, list[float]] = {
            token: [] for token in decision_tokens
        }
        compatible_logprobs: dict[str, list[float]] = {
            token: [] for token in decision_tokens
        }

        def collect(candidate: Mapping[str, Any]) -> None:
            raw_token = candidate.get("token")
            token = _normalized_binary_token(raw_token, decision_tokens)
            if token is None:
                return
            try:
                value = float(candidate["logprob"])
            except (KeyError, TypeError, ValueError):
                return
            compatible_logprobs[token].append(value)
            if raw_token == token:
                exact_logprobs[token].append(value)

        collect(entry)
        alternatives = entry.get("top_logprobs")
        if not isinstance(alternatives, list):
            continue
        for alternative in alternatives:
            if isinstance(alternative, Mapping):
                collect(alternative)
        yes_token, no_token = decision_tokens
        logprobs: dict[str, float] = {}
        for token in decision_tokens:
            candidates = exact_logprobs[token] or compatible_logprobs[token]
            if not candidates:
                return None
            logprobs[token] = max(candidates)
        if yes_token not in logprobs or no_token not in logprobs:
            return None
        if any(
            not math.isfinite(value) or value <= -1000.0
            for value in logprobs.values()
        ):
            return None
        yes_probability = math.exp(logprobs[yes_token])
        no_probability = math.exp(logprobs[no_token])
        difference = logprobs[yes_token] - logprobs[no_token]
        pairwise_yes = (
            1.0 / (1.0 + math.exp(-difference))
            if difference >= 0
            else math.exp(difference) / (1.0 + math.exp(difference))
        )
        if not 0 <= yes_probability <= 1 or not 0 <= no_probability <= 1:
            return None
        return DecisionTokenScores(yes_probability, no_probability, pairwise_yes)
    return None


_WIRE_AUDITED_PROVIDERS = frozenset({"deepseek", "openai", "openrouter"})


def _prepare_wire_record(
    client: Any,
    messages: list[ChatMessage],
    kwargs: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Build one secret-free exact provider body when the client supports it."""

    prepare = getattr(client, "prepare_request", None)
    if not callable(prepare):
        return None
    prepared = prepare(messages, **dict(kwargs))
    if not isinstance(prepared, PreparedJsonRequest):
        raise ValidationError("provider prepare_request returned an invalid value")
    body = prepared.body
    return {
        "url": prepared.url,
        "body_utf8": body.decode("utf-8"),
        "body_bytes": len(body),
        "body_sha256": prepared.body_sha256,
    }


class StructuredRoleClient:
    """Registered JSON role client guarded by request disclosure/cache/ledger."""

    def __init__(
        self,
        *,
        registration: RegisteredModel,
        contract: EvolutionRunContract,
        workspace: str | Path,
        ledger: ExternalAttemptLedger,
        allow_external: bool = False,
        acknowledged_contract_hash: str | None = None,
        environ: Mapping[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.registration = registration
        self.contract = contract
        self.workspace = Path(workspace)
        self.requests_root = self.workspace / "requests"
        self.requests_root.mkdir(parents=True, exist_ok=True)
        self.cache = ExactResponseCache(self.workspace / "cache" / "responses")
        self.ledger = ledger
        self.allow_external = allow_external
        self.acknowledged_contract_hash = acknowledged_contract_hash
        self.environ = environ
        self.on_progress = on_progress
        self.request_hash_trace: list[str] = []
        self.max_structured_corrections = int(
            contract.limits.get("max_structured_corrections", 1)
        )
        # Thread-local so bounded parallel workers never mix their chains.
        self._chain_state = threading.local()
        self._inflight = InFlightRequestCoordinator()

    @contextmanager
    def correction_chain(self, *, stage: str):
        """Scope no-progress request rejection to one logical correction chain.

        Stages ``X`` and ``X_correction`` belong to the same chain. Inside an
        open chain, a request whose canonical hash was already issued by that
        chain fails closed before cache lookup: the exact-response cache would
        replay the previously rejected response, so the retry can make no
        progress. Requests outside any chain — including supervisor re-runs of
        an initial attempt after a transport failure, and the same request
        issued by a different role, plan, or candidate — are unaffected and
        keep the ordinary cache-hit semantics.
        """

        base_stage = str(stage).removesuffix("_correction")
        stack = getattr(self._chain_state, "stack", None)
        if stack is None:
            stack = []
            self._chain_state.stack = stack
        entry = (base_stage, set())
        stack.append(entry)
        try:
            yield
        finally:
            try:
                stack.remove(entry)
            except ValueError:
                pass

    def _output_limit(self, requested: int | None, *, binary: bool = False) -> int:
        """Use the frozen reasoning headroom in both preview and execution."""

        base = requested or self.registration.default_max_output_tokens
        if binary or self.registration.default_reasoning_effort in {None, "none"}:
            return base
        return base + int(self.contract.limits.get("structured_reasoning_token_reserve", 0))

    def estimate_json_request_tokens(
        self,
        *,
        system_prompt: str,
        payload: Mapping[str, Any],
        allow_outcomes: bool,
        anonymous_aliases: Iterable[str] = (),
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> int:
        """Return the exact conservative byte-plus-output reservation for JSON."""

        _scan_payload(
            payload,
            allow_outcomes=allow_outcomes,
            anonymous_aliases=anonymous_aliases,
        )
        structured_system_prompt = (
            "Return exactly one JSON object and no non-JSON text. " + system_prompt
        )
        output_limit = self._output_limit(max_output_tokens)
        messages = [
            ChatMessage("system", structured_system_prompt),
            ChatMessage(
                "user",
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        ]
        kwargs: dict[str, Any] = {
            "max_output_tokens": output_limit,
            "response_format": {"type": "json_object"},
        }
        if self.registration.default_reasoning_effort:
            kwargs["reasoning"] = {
                "effort": self.registration.default_reasoning_effort
            }
        wire_request = None
        if self.registration.provider in _WIRE_AUDITED_PROVIDERS:
            preview_client = self.registration.create_client(
                ModelClientSettings(
                    preview_only=True,
                    temperature=temperature,
                    max_http_attempts=1,
                    environ=self.environ,
                )
            )
            wire_request = _prepare_wire_record(preview_client, messages, kwargs)
        estimated_input_bytes = (
            int(wire_request["body_bytes"])
            if wire_request is not None
            else len(
                json.dumps(
                    [
                        {"role": message.role, "content": message.content}
                        for message in messages
                    ],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
        )
        return max(1, estimated_input_bytes) + output_limit

    def complete_json(
        self,
        *,
        stage: str,
        system_prompt: str,
        payload: Mapping[str, Any],
        allow_outcomes: bool,
        anonymous_aliases: Iterable[str] = (),
        max_output_tokens: int | None = None,
        max_request_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], AgentUsage]:
        """Return structured JSON without provider token metadata."""

        value, usage, _scores = self._complete_json(
            stage=stage,
            system_prompt=system_prompt,
            payload=payload,
            allow_outcomes=allow_outcomes,
            anonymous_aliases=anonymous_aliases,
            max_output_tokens=max_output_tokens,
            max_request_tokens=max_request_tokens,
            temperature=temperature,
        )
        return value, usage

    def complete_json_with_token_scores(
        self,
        *,
        stage: str,
        system_prompt: str,
        payload: Mapping[str, Any],
        allow_outcomes: bool,
        decision_field: str,
        decision_tokens: tuple[str, str],
        anonymous_aliases: Iterable[str] = (),
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], AgentUsage, "DecisionTokenScores | None"]:
        """Return JSON plus optional provider-derived binary token scores."""

        return self._complete_json(
            stage=stage,
            system_prompt=system_prompt,
            payload=payload,
            allow_outcomes=allow_outcomes,
            anonymous_aliases=anonymous_aliases,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            decision_field=decision_field,
            decision_tokens=decision_tokens,
        )

    def complete_binary_token_with_scores(
        self,
        *,
        stage: str,
        system_prompt: str,
        payload: Mapping[str, Any],
        allow_outcomes: bool,
        decision_field: str,
        decision_tokens: tuple[str, str],
        anonymous_aliases: Iterable[str] = (),
        temperature: float = 1.0,
    ) -> tuple[str, AgentUsage, "DecisionTokenScores | None"]:
        """Return one exact binary token plus optional provider log probabilities."""

        preview_client = self.registration.create_client(
            ModelClientSettings(
                preview_only=True,
                temperature=temperature,
                max_http_attempts=1,
                environ=self.environ,
            )
        )
        if not getattr(preview_client, "supports_token_logprobs", False):
            return "", AgentUsage(), None
        value, usage, scores = self._complete_json(
            stage=stage,
            system_prompt=system_prompt,
            payload=payload,
            allow_outcomes=allow_outcomes,
            anonymous_aliases=anonymous_aliases,
            max_output_tokens=4,
            temperature=temperature,
            decision_field=decision_field,
            decision_tokens=decision_tokens,
            binary_token_output=True,
        )
        return str(value[decision_field]), usage, scores

    def _complete_json(
        self,
        *,
        stage: str,
        system_prompt: str,
        payload: Mapping[str, Any],
        allow_outcomes: bool,
        anonymous_aliases: Iterable[str] = (),
        max_output_tokens: int | None = None,
        max_request_tokens: int | None = None,
        temperature: float = 0.0,
        decision_field: str | None = None,
        decision_tokens: tuple[str, str] | None = None,
        binary_token_output: bool = False,
    ) -> tuple[dict[str, Any], AgentUsage, "DecisionTokenScores | None"]:
        """Persist and validate an exact request, then preview/cache/execute it."""

        if not 0 <= temperature <= 1:
            raise ValidationError("role temperature must be between 0 and 1")
        if (decision_field is None) != (decision_tokens is None):
            raise ValidationError(
                "decision field and decision tokens must be requested together"
            )
        if decision_tokens is not None and (
            len(decision_tokens) != 2
            or len(set(decision_tokens)) != 2
            or any(not token.strip() for token in decision_tokens)
        ):
            raise ValidationError("decision tokens must contain two unique values")
        if binary_token_output and (
            decision_field is None or decision_tokens is None
        ):
            raise ValidationError(
                "binary token output requires a decision field and tokens"
            )
        _scan_payload(
            payload,
            allow_outcomes=allow_outcomes,
            anonymous_aliases=anonymous_aliases,
        )
        structured_system_prompt = (
            system_prompt
            if binary_token_output
            else "Return exactly one JSON object and no non-JSON text. "
            + system_prompt
        )
        output_limit = self._output_limit(max_output_tokens, binary=binary_token_output)
        payload_text = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        messages = [
            ChatMessage("system", structured_system_prompt),
            ChatMessage("user", payload_text),
        ]
        kwargs: dict[str, Any] = {"max_output_tokens": output_limit}
        if not binary_token_output:
            kwargs["response_format"] = {"type": "json_object"}
        if self.registration.default_reasoning_effort:
            kwargs["reasoning"] = {
                "effort": self.registration.default_reasoning_effort
            }

        preview_client = None
        supports_token_logprobs = False
        wire_request = None
        if self.registration.provider in _WIRE_AUDITED_PROVIDERS:
            preview_client = self.registration.create_client(
                ModelClientSettings(
                    preview_only=True,
                    temperature=temperature,
                    max_http_attempts=1,
                    environ=self.environ,
                )
            )
            supports_token_logprobs = bool(
                decision_tokens is not None
                and getattr(preview_client, "supports_token_logprobs", False)
            )
            if supports_token_logprobs:
                kwargs["logprobs"] = True
                kwargs["top_logprobs"] = 20
            wire_request = _prepare_wire_record(preview_client, messages, kwargs)

        request = {
            "schema_version": "evolution-exact-request-v1",
            "contract_hash": self.contract.contract_hash,
            "stage": stage,
            "model": self.registration.to_public_dict(),
            "temperature": temperature,
            "max_http_attempts": 1,
            "max_output_tokens": output_limit,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        }
        if wire_request is not None:
            request["wire_request"] = wire_request
        if binary_token_output:
            request["output_contract"] = {
                "type": "single_binary_token",
                "tokens": list(decision_tokens or ()),
            }
        else:
            request["response_format"] = {"type": "json_object"}
        if decision_tokens is not None:
            request["token_logprobs"] = {
                "decision_field": decision_field,
                "decision_tokens": list(decision_tokens),
                "top_logprobs": 20,
                "required": False,
            }
        request_hash = _canonical_hash(request)
        self.request_hash_trace.append(request_hash)
        chain_stack = getattr(self._chain_state, "stack", None)
        if chain_stack:
            chain_base, chain_hashes = chain_stack[-1]
            if chain_base == stage.removesuffix("_correction"):
                if request_hash in chain_hashes:
                    _emit_runtime_progress(
                        self.on_progress,
                        "correction_no_progress_blocked",
                        stage=stage,
                        model_alias=self.registration.alias,
                        request_hash=request_hash,
                    )
                    raise CandidateExecutionRejected(
                        stage,
                        "no-progress identical correction request "
                        f"{request_hash}: the exact-response cache would "
                        "replay the previously rejected response; change the "
                        "output instead of re-sending it",
                    )
                chain_hashes.add(request_hash)
        request_path = self.requests_root / f"{request_hash}.json"
        _write_or_verify_json(
            request_path,
            {"request_hash": request_hash, "request": request},
        )
        _emit_runtime_progress(
            self.on_progress,
            "request_ready",
            stage=stage,
            model_alias=self.registration.alias,
            request_hash=request_hash,
            request_path=str(request_path),
        )
        cached = self.cache.load(request_hash)
        if cached is not None:
            _emit_runtime_progress(
                self.on_progress,
                "request_cache_hit",
                stage=stage,
                model_alias=self.registration.alias,
                request_hash=request_hash,
            )
            return (
                dict(cached["json_output"]),
                _usage_from_cache(cached),
                _decision_token_scores_from_cache(cached),
            )
        if not self.allow_external:
            _emit_runtime_progress(
                self.on_progress,
                "request_pending_external_approval",
                stage=stage,
                model_alias=self.registration.alias,
                request_hash=request_hash,
                request_path=str(request_path),
            )
            raise ExternalRequestPending(request_hash, request_path)
        if self.acknowledged_contract_hash != self.contract.contract_hash:
            raise ExternalExecutionNotReady(
                "external_acknowledgement_required",
                "external execution requires exact run-contract acknowledgement",
            )
        if not (self.environ or os.environ).get(self.registration.api_key_env_var):
            raise ExternalExecutionNotReady(
                "external_api_key_unavailable",
                "required API key is unavailable: "
                f"{self.registration.api_key_env_var}",
            )

        client = self.registration.create_client(
            ModelClientSettings(
                preview_only=False,
                temperature=temperature,
                max_http_attempts=1,
                environ=self.environ,
            )
        )
        actual_supports_token_logprobs = bool(
            decision_tokens is not None
            and getattr(client, "supports_token_logprobs", False)
        )
        if self.registration.provider not in _WIRE_AUDITED_PROVIDERS:
            supports_token_logprobs = actual_supports_token_logprobs
            if supports_token_logprobs:
                kwargs["logprobs"] = True
                kwargs["top_logprobs"] = 20
        elif actual_supports_token_logprobs != supports_token_logprobs:
            raise ExternalExecutionNotReady(
                "wire_request_drift",
                "provider token-logprob capability changed after request preview",
            )
        if wire_request is not None:
            actual_wire_request = _prepare_wire_record(client, messages, kwargs)
            if actual_wire_request != wire_request:
                raise ExternalExecutionNotReady(
                    "wire_request_drift",
                    "provider request bytes changed after exact request approval",
                )

        estimated_input_bytes = (
            int(wire_request["body_bytes"])
            if wire_request is not None
            else len(
                json.dumps(
                    request["messages"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
        )
        estimated_input_tokens = max(
            1,
            estimated_input_bytes,
        )
        conservative_request_tokens = estimated_input_tokens + output_limit
        if (
            max_request_tokens is not None
            and conservative_request_tokens > max_request_tokens
        ):
            raise RuntimeBudgetExceeded(
                "request token reservation exceeds remaining case budget: "
                f"required={conservative_request_tokens}, remaining={max_request_tokens}"
            )
        reserved_cost = _model_cost(
            self.registration,
            input_tokens=estimated_input_tokens,
            output_tokens=output_limit,
        )
        def _execute_external_attempt():
            # One physical call per identical concurrent request: the leader
            # executes and caches; waiters share the cached response with
            # zero usage so the ledger records the physical call once.
                    attempt_id = self.ledger.reserve(request_hash, reserved_cost=reserved_cost)
                    _emit_runtime_progress(
                        self.on_progress,
                        "external_call_started",
                        stage=stage,
                        model_alias=self.registration.alias,
                        request_hash=request_hash,
                        attempt_id=attempt_id,
                        reserved_cost=reserved_cost,
                    )
                    try:
                        response = client.complete(messages, **kwargs)
                        usage_data = response.raw.get("usage", {})
                        input_tokens = int(
                            usage_data.get(
                                "input_tokens",
                                usage_data.get("prompt_tokens", estimated_input_tokens),
                            )
                        )
                        output_tokens = int(
                            usage_data.get(
                                "output_tokens",
                                usage_data.get("completion_tokens", 0),
                            )
                        )
                        actual_cost = _model_cost(
                            self.registration,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                        )
                        usage = AgentUsage(
                            llm_calls=1,
                            tokens=input_tokens + output_tokens,
                            cost=actual_cost,
                        )
                        provider_usage = _provider_usage_record(
                            usage_data,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost=actual_cost,
                        )
                        structured_output_normalization: dict[str, str] | None = None
                        try:
                            if binary_token_output:
                                if response.output_text not in (decision_tokens or ()):
                                    raise ValidationError(
                                        "provider must return exactly one canonical binary token"
                                    )
                                parsed = {str(decision_field): response.output_text}
                            else:
                                parsed, structured_output_normalization = (
                                    _parse_json_object_envelope(response.output_text)
                                )
                        except (json.JSONDecodeError, ValidationError) as exc:
                            failure_record = {
                                "request_hash": request_hash,
                                "attempt_id": attempt_id,
                                "response_id": response.response_id,
                                "model": response.model,
                                "raw_output": response.output_text,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                                "usage": provider_usage,
                            }
                            failure_path = (
                                self.workspace
                                / "failed_responses"
                                / f"{attempt_id:06d}_{request_hash}.json"
                            )
                            _atomic_write_json(failure_path, failure_record)
                            response_hash = _canonical_hash(failure_record)
                            self.ledger.finalize(
                                attempt_id,
                                status="failed",
                                actual_cost=actual_cost,
                                response_hash=response_hash,
                                error_type=type(exc).__name__,
                                error_message=str(exc),
                            )
                            _emit_runtime_progress(
                                self.on_progress,
                                "external_call_failed",
                                stage=stage,
                                model_alias=self.registration.alias,
                                request_hash=request_hash,
                                attempt_id=attempt_id,
                                error_type=type(exc).__name__,
                                failure_path=str(failure_path),
                            )
                            raise StructuredOutputInvalid(
                                f"provider returned invalid structured output: {exc}",
                                response.output_text,
                                usage,
                                output_tokens=output_tokens,
                                output_token_limit=output_limit,
                            ) from exc
                        scores = (
                            _extract_decision_token_scores(
                                response.raw,
                                parsed=parsed,
                                decision_field=str(decision_field),
                                decision_tokens=decision_tokens,
                            )
                            if supports_token_logprobs and decision_tokens is not None
                            else None
                        )
                        response_record = {
                            "response_id": response.response_id,
                            "model": response.model,
                            "json_output": parsed,
                            "usage": provider_usage,
                        }
                        if structured_output_normalization is not None:
                            response_record["structured_output_normalization"] = (
                                structured_output_normalization
                            )
                        if decision_tokens is not None:
                            response_record["decision_token_scores"] = (
                                scores.to_dict() if scores is not None else None
                            )
                        self.cache.store(request_hash, response_record)
                        response_hash = _canonical_hash(response_record)
                        self.ledger.finalize(
                            attempt_id,
                            status="completed",
                            actual_cost=actual_cost,
                            response_hash=response_hash,
                        )
                        _emit_runtime_progress(
                            self.on_progress,
                            "external_call_completed",
                            stage=stage,
                            model_alias=self.registration.alias,
                            request_hash=request_hash,
                            attempt_id=attempt_id,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            prompt_cache_hit_tokens=provider_usage.get(
                                "prompt_cache_hit_tokens"
                            ),
                            prompt_cache_miss_tokens=provider_usage.get(
                                "prompt_cache_miss_tokens"
                            ),
                            actual_cost=actual_cost,
                        )
                        return parsed, usage, scores
                    except StructuredOutputInvalid:
                        raise
                    except Exception as exc:
                            self.ledger.finalize(
                                attempt_id,
                                status="failed",
                                actual_cost=0.0,
                                error_type=type(exc).__name__,
                                error_message=str(exc),
                            )
                            _emit_runtime_progress(
                                self.on_progress,
                                "external_call_failed",
                                stage=stage,
                                model_alias=self.registration.alias,
                                request_hash=request_hash,
                                attempt_id=attempt_id,
                                error_type=type(exc).__name__,
                                error_message=str(exc)[:500],
                            )
                            raise
        def _shared_cached_result():
            cached = self.cache.load(request_hash)
            if cached is None:
                return None
            return (
                dict(cached["json_output"]),
                AgentUsage(),
                _decision_token_scores_from_cache(cached),
            )

        return self._inflight.share(
            request_hash,
            _execute_external_attempt,
            on_shared=_shared_cached_result,
        )


class JSONRoleCaller(Protocol):
    """Small injectable boundary shared by concrete role adapters and tests."""

    def complete_json(
        self,
        *,
        stage: str,
        system_prompt: str,
        payload: Mapping[str, Any],
        allow_outcomes: bool,
        anonymous_aliases: Iterable[str] = (),
        max_output_tokens: int | None = None,
        max_request_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], AgentUsage]:
        """Return one validated structured role response and usage."""


def _complete_json_with_invalid_value(
    caller: JSONRoleCaller,
    *,
    stage: str,
    system_prompt: str,
    payload: Mapping[str, Any],
    allow_outcomes: bool,
    anonymous_aliases: Iterable[str] = (),
    max_output_tokens: int | None = None,
    max_request_tokens: int | None = None,
    temperature: float = 0.0,
) -> tuple[dict[str, Any], AgentUsage]:
    """Turn malformed provider text into role-level correction input."""

    try:
        kwargs: dict[str, Any] = {
            "stage": stage,
            "system_prompt": system_prompt,
            "payload": payload,
            "allow_outcomes": allow_outcomes,
            "anonymous_aliases": anonymous_aliases,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
        }
        if max_request_tokens is not None:
            kwargs["max_request_tokens"] = max_request_tokens
        return caller.complete_json(**kwargs)
    except StructuredOutputInvalid as exc:
        validation_error = str(exc)
        if (
            exc.output_tokens is not None
            and exc.output_token_limit is not None
            and exc.output_tokens >= exc.output_token_limit
            and exc.raw_output.lstrip().startswith("{")
            and not exc.raw_output.rstrip().endswith("}")
        ):
            validation_error += (
                "; provider output reached max_output_tokens="
                f"{exc.output_token_limit} and ended before one complete JSON object. "
                "Treat this as output-ceiling truncation: return the compact decision "
                "frontier only, obey every field/item/byte ceiling, and do not "
                "enumerate the input projections"
            )
        return (
            {
                "invalid_structured_output": exc.raw_output[:12_000],
                "validation_error": validation_error,
            },
            exc.usage,
        )


def _scan_payload(
    value: Any,
    *,
    allow_outcomes: bool,
    anonymous_aliases: Iterable[str],
    identity_boundary: str = "anonymous request",
) -> None:
    aliases = tuple(
        sorted(
            {str(item).strip() for item in anonymous_aliases if str(item).strip()},
            key=len,
            reverse=True,
        )
    )
    alias_matchers: list[tuple[bool, str, re.Pattern[str]]] = []
    for alias in aliases:
        ticker_like = alias.isalnum() and alias.isupper() and len(alias) <= 5
        if ticker_like and len(alias) <= 2:
            pattern = (
                rf"(?:\${re.escape(alias)}(?![A-Za-z0-9])|"
                rf"(?i:\b(?:ticker|symbol|nasdaq|nyse|amex)\b)"
                rf"\s*(?::|=)?\s*{re.escape(alias)}(?![A-Za-z0-9]))"
            )
        else:
            pattern = (
                rf"(?<![A-Za-z0-9])"
                rf"{re.escape(alias if ticker_like else alias.casefold())}"
                rf"(?![A-Za-z0-9])"
            )
        alias_matchers.append((ticker_like, alias if ticker_like else alias.casefold(), re.compile(pattern)))

    @lru_cache(maxsize=4096)
    def contains_identity(item: str) -> bool:
        casefolded = item.casefold()
        for ticker_like, literal, matcher in alias_matchers:
            text = item if ticker_like else casefolded
            if literal in text and matcher.search(text):
                return True
        return False

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                normalized = _normalize_field(str(key))
                if (
                    not allow_outcomes
                    and _is_outcome_field(normalized)
                    and not _is_source_concept_label(path, normalized)
                ):
                    raise ValidationError(f"outcome field leaked into request: {path}.{key}")
                visit(nested, f"{path}.{key}")
            return
        if isinstance(item, (list, tuple)):
            for index, nested in enumerate(item):
                visit(nested, f"{path}[{index}]")
            return
        if isinstance(item, str):
            if contains_identity(item):
                raise ValidationError(
                    f"identity alias leaked into {identity_boundary}: {path}"
                )

    visit(value, "payload")


def _model_cost(
    registration: RegisteredModel, *, input_tokens: int, output_tokens: int
) -> float:
    return (
        input_tokens * registration.default_input_cost_per_million_tokens
        + output_tokens * registration.default_output_cost_per_million_tokens
    ) / 1_000_000


def _provider_usage_record(
    usage_data: Mapping[str, Any],
    *,
    input_tokens: int,
    output_tokens: int,
    cost: float,
) -> dict[str, int | float]:
    """Keep provider cache observability without weakening conservative cost gates."""

    record: dict[str, int | float] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
    }
    for key in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
        value = usage_data.get(key)
        if type(value) is int and value >= 0:
            record[key] = value
    if "prompt_cache_hit_tokens" not in record:
        details = usage_data.get("input_tokens_details")
        cached_tokens = (
            details.get("cached_tokens") if isinstance(details, Mapping) else None
        )
        if (
            type(cached_tokens) is int
            and 0 <= cached_tokens <= input_tokens
        ):
            record["prompt_cache_hit_tokens"] = cached_tokens
            record["prompt_cache_miss_tokens"] = input_tokens - cached_tokens
    return record


def _usage_from_cache(data: Mapping[str, Any]) -> AgentUsage:
    usage = data.get("usage", {})
    return AgentUsage(
        llm_calls=0,
        tokens=int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
        cost=0.0,
    )


def _parse_json_object_envelope(
    text: str,
) -> tuple[dict[str, Any], dict[str, str] | None]:
    """Parse one object and audit one unambiguous redundant closing brace."""

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    normalization: dict[str, str] | None = None
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as failure:
        try:
            value, end = json.JSONDecoder().raw_decode(stripped)
        except json.JSONDecodeError:
            raise failure
        suffix = stripped[end:].strip()
        if failure.msg != "Extra data" or suffix != "}":
            raise failure
        normalization = {
            "kind": "dropped_one_redundant_trailing_closing_brace",
            "raw_output_sha256": hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest(),
        }
    if not isinstance(value, dict):
        raise ValidationError("structured model response must be a JSON object")
    return value, normalization


def _normalize_field(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _is_outcome_field(normalized: str) -> bool:
    return normalized in _FORBIDDEN_OUTCOME_KEYS or any(
        normalized.startswith(f"{field}_") or normalized.endswith(f"_{field}")
        for field in _FORBIDDEN_OUTCOME_KEYS
    )


def _is_source_concept_label(path: str, normalized: str) -> bool:
    """Return whether one label is source-owned SEC Company Facts semantics."""

    return normalized == "label" and re.search(
        r"\.structured_context\.concepts\[\d+\]$", path
    ) is not None


def _emit_runtime_progress(
    callback: ProgressCallback | None,
    event_type: str,
    **details: Any,
) -> None:
    if callback is not None:
        callback({"event_type": event_type, **details})


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"required local artifact is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"required JSON artifact is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"JSON artifact must contain an object: {path}")
    return value


def _write_or_verify_json(path: Path, value: Mapping[str, Any]) -> None:
    expected = json.loads(json.dumps(dict(value), sort_keys=True))
    if path.exists():
        if _read_json(path) != expected:
            raise ValidationError(f"conflicting immutable evolution artifact: {path}")
        return
    _atomic_write_json(path, expected)
