"""Show the intermediate guard rejects a previously supported proposer hybrid."""
import copy
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research import evolution_control as current
from stock_opportunity_agent.research.evolution_transport import public_model_contract

root = Path(__file__).resolve().parents[3]
out = Path(__file__).resolve().parent
path = out / "hybrid-counterexample.json"
if path.exists():
    raise RuntimeError("retain original intermediate failure")
source = subprocess.check_output(["git", "show", "80e1c798890db46e255ee7b82c1d34ee906923e3:src/stock_opportunity_agent/research/evolution_control.py"], cwd=root)
original = types.ModuleType("_original_factory_control_diagnostic")
original.__file__ = str(root / "src/stock_opportunity_agent/research/evolution_control.py")
sys.modules[original.__name__] = original
exec(compile(source, original.__file__, "exec"), original.__dict__)
fixture = json.loads((out / "result.json").read_text())["local_contract"]
fixture["models"]["judge"] = public_model_contract({"judge": "deepseek-v4-flash"}, environ={})["judge"]
fixture["models"]["jev"] = {"alias": "openrouter-jev", "provider": "openrouter", "model": "typesafe/jev-1.13"}
fixture["parallel_jev_decisions"] = True
results = {"fixture": "synthetic remote judge + local proposer, explicit allow_external=True",
           "original_control_sha256": hashlib.sha256(source).hexdigest(),
           "intermediate_control_sha256": hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
           "http_transmissions": 0, "socket_connection_attempts": 0, "model_answers_created": 0,
           "cases": []}


class ProviderBoundary(RuntimeError):
    pass


for name, module in (("original", original), ("intermediate_guard", current)):
    row = {"version": name}
    try:
        contract = module.EvolutionRunContract.from_dict(copy.deepcopy(fixture))
        row["contract_admission"] = "accepted"
    except Exception as exc:
        row.update(contract_admission=type(exc).__name__, admission_message=str(exc))
    caller = SimpleNamespace(registration=get_model("deepseek-v4-flash"),
                             contract=SimpleNamespace(models=fixture["models"]),
                             allow_external=True, local_role_exchange=None)
    hits = []

    def sentinel(*_args, **_kwargs):
        hits.append("provider_constructor")
        raise ProviderBoundary("denied before key access/network")

    with patch.object(module.OpenRouterJevClient, "from_environ", side_effect=sentinel):
        try:
            module._parallel_decision_roles(caller, parallel_jev_decisions=True, environ={})
            row["runtime"] = "returned"
        except Exception as exc:
            row.update(runtime=type(exc).__name__, runtime_message=str(exc))
    row["provider_constructor_hits"] = len(hits)
    results["cases"].append(row)
path.write_text(json.dumps(results, sort_keys=True, indent=2) + "\n")
print(json.dumps(results, indent=2))
