"""Independent mixed-role, frozen-load and wrapped-caller negative controls."""
from __future__ import annotations

import copy
import hashlib
import json
import socket
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from stock_opportunity_agent.research import evolution_control as control
from stock_opportunity_agent.research.evolution_transport import public_model_contract

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
target = OUT / "admission-matrix.json"
if target.exists():
    raise RuntimeError("preserve existing diagnostic result")
base = json.loads((OUT / "result.json").read_text())["local_contract"]
remote_models = public_model_contract({"judge": "deepseek-v4-flash", "proposer": "deepseek-v4-flash"}, environ={})
jev = {"alias": "openrouter-jev", "provider": "openrouter", "model": "typesafe/jev-1.13"}
rows = []
socket_hits = []
provider_hits = []


class ProviderBoundary(RuntimeError):
    pass


def deny_socket(*_args, **_kwargs):
    socket_hits.append("denied")
    raise ProviderBoundary("socket denied")


def provider(*_args, **_kwargs):
    provider_hits.append("sentinel")
    raise ProviderBoundary("constructor sentinel; no environment or transport access")


def record(name, fn, expected):
    before = len(provider_hits)
    row = {"name": name, "expected": expected}
    try:
        fn()
        row["actual"] = "returned"
    except Exception as exc:
        row.update(actual=type(exc).__name__, message=str(exc))
    row["provider_constructor_hits"] = len(provider_hits) - before
    row["pass"] = row["actual"] == expected and (row["provider_constructor_hits"] == (1 if expected == "ProviderBoundary" else 0))
    rows.append(row)


with tempfile.TemporaryDirectory(prefix="local-admission-matrix-") as directory, \
     patch.object(socket.socket, "connect", deny_socket), patch.object(socket, "create_connection", deny_socket), \
     patch.object(control.OpenRouterJevClient, "from_environ", side_effect=provider):
    tmp = Path(directory)
    manifest = tmp / "synthetic-manifest.json"
    manifest.write_text(json.dumps({"approval_status": "human_approved", "locked_test_sealed": True, "diagnostic_only": True}))
    for roles in (("judge",), ("proposer",), ("judge", "proposer")):
        value = copy.deepcopy(base)
        value["models"] = copy.deepcopy(remote_models)
        for role in roles:
            value["models"][role] = copy.deepcopy(base["models"][role])
        value["models"]["jev"] = jev
        value["parallel_jev_decisions"] = True
        record("parser_local_" + "+".join(roles), lambda value=value: control.EvolutionRunContract.from_dict(value), "ExternalExecutionNotReady")
        frozen = tmp / ("frozen-" + "+".join(roles) + ".json")
        frozen.write_text(json.dumps({"contract": value, "contract_hash": control._canonical_hash(value)}))
        old_hash = hashlib.sha256(frozen.read_bytes()).hexdigest()
        record("frozen_load_local_" + "+".join(roles), lambda frozen=frozen: control.EvolutionRunContract.load_frozen(frozen), "ExternalExecutionNotReady")
        rows[-1]["frozen_file_unchanged"] = hashlib.sha256(frozen.read_bytes()).hexdigest() == old_hash
        rows[-1]["pass"] &= rows[-1]["frozen_file_unchanged"]
        mutated = control.EvolutionRunContract.from_dict(base)
        object.__setattr__(mutated, "models", value["models"])
        object.__setattr__(mutated, "parallel_jev_decisions", True)
        record("preflight_local_" + "+".join(roles), lambda mutated=mutated: control._validate_cycle_execution_request(mutated, allow_data_external=False), "ExternalExecutionNotReady")
        aliases = {role: metadata["alias"] for role, metadata in value["models"].items() if role != "jev"}
        # True conflicts are rejected before current_code_revision can inspect
        # the intentionally dirty live checkout; no clean-project stand-in.
        record("builder_local_" + "+".join(roles), lambda aliases=aliases: control.build_run_contract(
            run_id="synthetic-mixed-route-probe", dataset_manifest_path=manifest, inventory=None,
            raw_info_oracle=SimpleNamespace(oracle_id=base["raw_info_oracle_id"]),
            raw_info_inventory_hash=base["raw_info_inventory_hash"], initial_signal_registry_version=1,
            initial_signal_registry_hash=base["initial_signal_registry_hash"], priors={"diagnostic": "fact-free"},
            role_aliases=aliases, project_root=ROOT, limits=base["limits"], max_external_attempts=1,
            max_total_cost=1.0, parallel_jev_decisions=True, environ={}), "ExternalExecutionNotReady")
    remote_caller = dict(registration=SimpleNamespace(alias="deepseek-v4-flash", provider="deepseek"),
                         contract=SimpleNamespace(models=remote_models), allow_external=True, local_role_exchange=None)
    variants = {
        "runtime_alias_only": {**remote_caller, "registration": SimpleNamespace(alias="independent-subagent", provider="local")},
        "runtime_exchange_only": {**remote_caller, "local_role_exchange": object()},
        "runtime_contract_proposer_only": {**remote_caller, "contract": SimpleNamespace(models={**remote_models, "proposer": base["models"]["proposer"]})},
        "runtime_remote_explicit_false": {**remote_caller, "allow_external": False},
    }
    for name, attrs in variants.items():
        record(name, lambda attrs=attrs: control._parallel_decision_roles(SimpleNamespace(**attrs), parallel_jev_decisions=True, environ={}), "ExternalExecutionNotReady")
    record("runtime_remote_true_preserved", lambda: control._parallel_decision_roles(SimpleNamespace(**remote_caller), parallel_jev_decisions=True, environ={}), "ProviderBoundary")
    record("runtime_legacy_fake_caller_preserved", lambda: control._parallel_decision_roles(SimpleNamespace(), parallel_jev_decisions=True, environ={}), "ProviderBoundary")

result = {"schema_version": "local-factory-independent-admission-matrix-v1", "synthetic_inputs": True,
          "code_sha256": hashlib.sha256((ROOT / "src/stock_opportunity_agent/research/evolution_control.py").read_bytes()).hexdigest(),
          "cases": rows, "pass_count": sum(r["pass"] for r in rows), "case_count": len(rows),
          "http_transmissions": 0, "socket_connection_attempts": len(socket_hits), "model_answers_created": 0}
target.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
print(json.dumps({key: value for key, value in result.items() if key != "cases"}, indent=2))
assert result["pass_count"] == result["case_count"]
