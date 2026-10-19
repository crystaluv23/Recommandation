"""Hash-bound, network-free handoff of production requests to independent agents."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import fcntl
from pathlib import Path
from typing import Any, Mapping

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.scheme_evolution import EvolutionControlFlow


class LocalRoleRequestPending(EvolutionControlFlow):
    """Pause an unanswered local role without creating a research verdict."""

    def __init__(self, pending: Mapping[str, Any]) -> None:
        self.pending = dict(pending)
        super().__init__(json.dumps(self.pending, sort_keys=True))


class LocalRoleBudgetExhausted(EvolutionControlFlow):
    """Stop local dispatch at the frozen ceiling without a research verdict."""


def _immutable(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dict(record), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValidationError(f"local role immutable artifact changed: {path}")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".local-role-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != text:
                raise ValidationError(f"local role immutable artifact changed: {path}")
    finally:
        os.unlink(temporary)


class LocalRoleExchange:
    """Persist exact model inputs and consume independently authored raw outputs.

    Example: catch ``LocalRoleRequestPending``, dispatch its inbox to a fresh
    agent, record the actual agent id with :meth:`submit`, then resume the same
    production operation. No method imports a network client or edits an answer.
    """

    def __init__(self, root: str | Path, *, max_calls: int) -> None:
        if max_calls < 1:
            raise ValidationError("local role max_calls must be positive")
        self.root = Path(root).resolve()
        self.max_calls = max_calls
        _immutable(self.root / "contract.json", {
            "schema_version": "independent-local-role-exchange-v1",
            "max_calls": max_calls, "external_api_calls": 0,
        })

    def receive(self, request: Mapping[str, Any], *, accounting_tokens: int,
                allow_dispatch: bool = True) -> tuple[str, dict[str, Any]]:
        """Dispatch once or return a receipt-verified, byte-exact raw response."""
        digest = canonical_json_hash(request)
        inbox = self.root / "inbox" / f"{digest}.json"
        raw = self.root / "outbox" / f"{digest}.txt"
        receipt_path = self.root / "receipts" / f"{digest}.json"
        record = {
            "schema_version": "independent-local-role-inbox-v1",
            "request_hash": digest, "backend": "independent-subagent",
            "messages": request["messages"],
            "max_output_tokens": request["max_output_tokens"],
            "output_contract": request.get("output_contract", request.get("response_format")),
        }
        with (self.root / ".dispatch.lock").open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                _immutable(self.root / "contract.json", {
                    "schema_version": "independent-local-role-exchange-v1",
                    "max_calls": self.max_calls, "external_api_calls": 0,
                })
                if not inbox.exists():
                    if not allow_dispatch:
                        raise ValidationError("local cache is missing its original inbox")
                    if len(list((self.root / "inbox").glob("*.json"))) >= self.max_calls:
                        raise LocalRoleBudgetExhausted("local role frozen call ceiling exhausted")
                _immutable(inbox, record)
                inbox_bytes = inbox.read_bytes()
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        pending = {"stage": request["stage"], "request_hash": digest,
                   "inbox_path": str(inbox), "outbox_path": str(raw),
                   "inbox_sha256": hashlib.sha256(inbox_bytes).hexdigest()}
        if not receipt_path.exists():
            if not allow_dispatch:
                raise ValidationError("local cache is missing its response receipt")
            raise LocalRoleRequestPending(pending)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        raw_bytes = raw.read_bytes() if raw.is_file() else None
        if (receipt.get("request_hash") != digest or receipt.get("inbox_sha256") != pending["inbox_sha256"]
                or not isinstance(receipt.get("agent_id"), str) or not receipt["agent_id"].strip()
                or raw_bytes is None or receipt.get("raw_output_sha256") != hashlib.sha256(raw_bytes).hexdigest()):
            raise ValidationError("local role response receipt does not bind exact request and raw answer")
        return raw_bytes.decode("utf-8"), {
            **receipt, "accounting_tokens": accounting_tokens,
            "cost": 0.0, "cost_basis": "zero_external_api_cost_internal_unknown",
            "token_usage": None, "internal_agent_cost": None,
        }

    def submit(self, request_hash: str, *, agent_id: str) -> dict[str, Any]:
        """Bind an agent-authored output to its exact inbox without changing it."""
        if len(request_hash) != 64 or any(c not in "0123456789abcdef" for c in request_hash):
            raise ValidationError("invalid local role request hash")
        if not agent_id.strip():
            raise ValidationError("actual independent agent id is required")
        inbox = self.root / "inbox" / f"{request_hash}.json"
        raw = self.root / "outbox" / f"{request_hash}.txt"
        record = json.loads(inbox.read_text(encoding="utf-8"))
        if record.get("request_hash") != request_hash:
            raise ValidationError("local role inbox request identity mismatch")
        receipt = {"request_hash": request_hash, "agent_id": agent_id,
                   "inbox_sha256": hashlib.sha256(inbox.read_bytes()).hexdigest(),
                   "raw_output_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}
        _immutable(self.root / "receipts" / f"{request_hash}.json", receipt)
        return receipt
