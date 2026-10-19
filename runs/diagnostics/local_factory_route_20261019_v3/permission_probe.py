"""Check the same Jev bypass against an explicit remote transport prohibition."""
from __future__ import annotations

import hashlib
import json
import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research import evolution_control as control
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient, public_model_contract

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
target = OUT / "permission-result.json"
if target.exists():
    raise RuntimeError("preserve existing diagnostic result; use a fresh root")
fixture = json.loads((OUT / "result.json").read_text())["local_contract"]
fixture["models"] = public_model_contract({"judge": "deepseek-v4-flash", "proposer": "deepseek-v4-flash"}, environ={})
contract = control.EvolutionRunContract.from_dict(fixture)
results = {"schema_version": "jev-transport-permission-diagnostic-v1", "synthetic_fixture": True,
           "code_sha256": hashlib.sha256((ROOT / "src/stock_opportunity_agent/research/evolution_control.py").read_bytes()).hexdigest(),
           "http_transmissions": 0, "socket_connection_attempts": 0, "cases": []}


class ProviderBoundary(RuntimeError):
    pass


def deny_socket(*_args, **_kwargs):
    results["socket_connection_attempts"] += 1
    raise ProviderBoundary("socket denied")


with tempfile.TemporaryDirectory(prefix="jev-permission-probe-") as directory:
    for permission in (False, True):
        root = Path(directory) / str(permission)
        client = StructuredRoleClient(registration=get_model("deepseek-v4-flash"), contract=contract, workspace=root,
                   ledger=ExternalAttemptLedger(root / "attempts.json", max_attempts=1, max_total_cost=1),
                   allow_external=permission, environ={})
        hit = []

        def sentinel(*_args, **_kwargs):
            hit.append("OpenRouterJevClient.from_environ")
            raise ProviderBoundary("provider constructor intercepted before environment/key access")

        row = {"registration": "deepseek-v4-flash", "allow_external": permission}
        with patch.object(socket.socket, "connect", deny_socket), patch.object(socket, "create_connection", deny_socket), \
             patch.object(control.OpenRouterJevClient, "from_environ", side_effect=sentinel):
            try:
                pair = control._parallel_decision_roles(client, parallel_jev_decisions=True, environ={})
                row.update(status="returned", classes=[type(v).__name__ for v in pair])
            except Exception as exc:
                row.update(status="raised", error_type=type(exc).__name__, message=str(exc))
        row["provider_constructor_hits"] = hit
        row["external_attempt_count"] = client.ledger.summary["attempt_count"]
        results["cases"].append(row)
target.write_text(json.dumps(results, sort_keys=True, indent=2) + "\n")
print(json.dumps(results, indent=2))
