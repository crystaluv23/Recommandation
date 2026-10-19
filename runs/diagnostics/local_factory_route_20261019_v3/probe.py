"""Diagnose production local/Jev routing without answers or network access.

Run with PYTHONPATH=src using the project-compatible Python. This uses a
synthetic contract/input and a temporary clean Git identity solely to enter
the real contract builder despite unrelated current checkout changes. It
does not qualify a dataset or run an evaluation cycle. No answer is authored.
"""
from __future__ import annotations

import hashlib
import json
import platform
import socket
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.llm.openai import UrllibTransport
from stock_opportunity_agent.research import evolution_control as control
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending
from stock_opportunity_agent.research.scheme_evolution import PlanEvaluationConfig


class BoundaryReached(RuntimeError):
    """Deny a provider constructor or transport before any external action."""


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
if (OUT / "result.json").exists():
    raise RuntimeError("preserve existing diagnostic result; copy probe to a fresh root")
paths = [
    "src/stock_opportunity_agent/research/evolution_control.py",
    "src/stock_opportunity_agent/research/evolution_transport.py",
    "src/stock_opportunity_agent/research/evolution_jev_roles.py",
    "src/stock_opportunity_agent/research/evolution_plan_roles.py",
    "src/stock_opportunity_agent/research/local_role_exchange.py",
    "src/stock_opportunity_agent/llm/openrouter_jev.py",
    "src/stock_opportunity_agent/llm/local.py",
    "scripts/evolve_information_schemes.py",
]
result = {"schema_version": "local-factory-route-diagnostic-v1",
          "production_code_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
          "python_runtime": platform.python_version(), "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
          "synthetic_inputs": True, "model_answers_created": 0,
          "http_transmissions": 0, "socket_connection_attempts": 0, "cases": []}


def record(name, operation):
    try:
        value = operation()
        result["cases"].append({"name": name, "status": "returned", "value": value})
    except Exception as exc:
        result["cases"].append({"name": name, "status": "raised", "type": type(exc).__name__, "message": str(exc)})


def deny_socket(*args, **kwargs):
    result["socket_connection_attempts"] += 1
    raise BoundaryReached("socket denied before connection")


limits = {"plan_rounds_per_signal_cycle": 1, "candidates_per_round": 1,
          "max_parallel_plans": 1, "top_k": 3, "random_k": 2,
          "similarity_threshold": 0.9, "parent_selection_seed": 42,
          "plan_proposal_temperature": 1.0, "judge_temperature": 0.0,
          "max_signal_rounds": 5, "max_signal_calls": 20, "max_llm_calls": 40,
          "max_signals_per_round": 4, "max_llm_signals_per_round": 2,
          "basic_info_context_chars": 32000, "signal_batch_context_chars": 32000,
          "predictor_context_bytes": 24000, "posthoc_context_chars": 24000,
          "meta_context_chars": 48000, "role_output_tokens": control.ROLE_OUTPUT_TOKEN_LIMITS,
          "finalization_token_reserve": 36000,
          "max_tokens": 120000, "max_case_cost": 5.0, "max_agent_steps": 20,
          "evaluation": PlanEvaluationConfig().to_dict(), "max_local_role_calls": 4}

with tempfile.TemporaryDirectory(prefix="local-factory-route-") as directory:
    tmp = Path(directory)
    clean = tmp / "synthetic-clean-project"
    clean.mkdir()
    (clean / "BOUND-SOURCE-HASHES.json").write_text(json.dumps(result["production_code_sha256"], sort_keys=True))
    for args in (["init", "-q"], ["add", "BOUND-SOURCE-HASHES.json"],
                 ["-c", "user.name=Diagnostic", "-c", "user.email=diagnostic@localhost", "commit", "-q", "-m", "Bind diagnostic source identity"]):
        subprocess.run(["git", *args], cwd=clean, check=True, capture_output=True)
    manifest = tmp / "synthetic-approved-manifest.json"
    manifest.write_text(json.dumps({"approval_status": "human_approved", "locked_test_sealed": True,
                                    "diagnostic_only": True}))
    args = dict(run_id="synthetic-local-route-probe", dataset_manifest_path=manifest,
                inventory=None, raw_info_oracle=SimpleNamespace(oracle_id="synthetic-probe-oracle"),
                raw_info_inventory_hash="a" * 64, initial_signal_registry_version=1,
                initial_signal_registry_hash="b" * 64, priors={"diagnostic": "fact-free"},
                role_aliases={"judge": "independent-subagent", "proposer": "independent-subagent"},
                project_root=clean, limits=limits, max_external_attempts=1, max_total_cost=1.0,
                environ={})
    with patch.object(socket.socket, "connect", deny_socket), patch.object(socket, "create_connection", deny_socket):
        ordinary = control.build_run_contract(**args, parallel_jev_decisions=False)
        result["local_contract"] = ordinary.to_dict()
        record("builder_local_plus_jev", lambda: control.build_run_contract(**args, parallel_jev_decisions=True).to_dict())
        # Bypass constructor validation only after serializing a legal local
        # contract, to represent a runtime object mutated by an unsupported caller.
        # This is separate from the real builder admission probe above.
        models = dict(ordinary.models)
        models["jev"] = {"alias": "openrouter-jev", "provider": "openrouter", "model": "typesafe/jev-1.13"}
        record("loaded_contract_local_plus_jev", lambda: control.EvolutionRunContract.from_dict(
            {**ordinary.to_dict(), "parallel_jev_decisions": True, "models": models}).to_dict())
        runtime_bad = replace(ordinary)
        object.__setattr__(runtime_bad, "parallel_jev_decisions", True)
        object.__setattr__(runtime_bad, "models", models)
        record("preflight_mutated_local_plus_jev", lambda: control._validate_cycle_execution_request(runtime_bad, allow_data_external=False))
        client = StructuredRoleClient(registration=get_model("independent-subagent"), contract=ordinary,
                    workspace=tmp / "local", ledger=ExternalAttemptLedger(tmp / "local-attempts.json", max_attempts=1, max_total_cost=1),
                    allow_external=False, environ={})
        provider_hits = []

        def provider_sentinel(*_args, **_kwargs):
            provider_hits.append("OpenRouterJevClient.from_environ")
            raise BoundaryReached("external provider construction reached with independent-subagent and allow_external=False")

        with patch.object(control.OpenRouterJevClient, "from_environ", side_effect=provider_sentinel):
            record("runtime_local_flag_false", lambda: [type(v).__name__ for v in control._parallel_decision_roles(client, parallel_jev_decisions=False, environ={})])
            record("runtime_local_flag_true", lambda: [type(v).__name__ for v in control._parallel_decision_roles(client, parallel_jev_decisions=True, environ={})])
        result["provider_constructor_sentinel_hits"] = provider_hits
        record("runtime_local_flag_true_no_key", lambda: [type(v).__name__ for v in control._parallel_decision_roles(client, parallel_jev_decisions=True, environ={})])
        transport_hits = []

        def transport_sentinel(_self, url, headers, payload):
            transport_hits.append({"url": url, "model": payload.get("model"), "questions": list(payload.get("questions", {})),
                                   "authorization_present": "Authorization" in headers})
            raise BoundaryReached("HTTP post_json denied before transmission; placeholder key only")

        with patch.object(UrllibTransport, "post_json", transport_sentinel):
            def actual_predictor_boundary():
                _signal, predictor = control._parallel_decision_roles(client, parallel_jev_decisions=True,
                                        environ={"OPENROUTER_API_KEY": "diagnostic-placeholder-not-a-secret"})
                predictor.predict({"diagnostic_context": "No source facts or outcome labels."})
            record("runtime_local_plus_jev_actual_predictor_transport", actual_predictor_boundary)
        result["http_transport_denials"] = transport_hits
        # Native local handoff positive control: persist only an unanswered
        # fact-free request. Never submit a synthetic or root-authored answer.
        try:
            client.complete_json(stage="factory_route_probe", system_prompt="Return JSON.",
                                 payload={"diagnostic": "No answer should be generated by this probe."}, allow_outcomes=False)
        except LocalRoleRequestPending as exc:
            result["native_local_pending_positive"] = {"exception": type(exc).__name__, "request_hash": exc.pending["request_hash"],
                                                        "receipt_count": len(list((tmp / "local/local_roles/receipts").glob("*.json")))}
        result["external_ledger_summary"] = client.ledger.summary

result["scope"] = "Actual builder/contract parser/preflight/role factory and Jev predictor entry; no complete cycle or source admission."
result["minimal_fix"] = [
    "Reject independent-subagent combined with parallel_jev_decisions in build_run_contract before constructing remote model metadata.",
    "Reject the same combination in contract admission and cycle preflight; retain immutable existing files rather than rewriting them.",
    "Defend _parallel_decision_roles against local registration/exchange before OpenRouterJevClient.from_environ; worker and coordinator share this helper.",
    "Keep flag=false native StructuredRoleClient roles unchanged, and retain remote-only behavior; never invent Jev probabilities or provider logprobs."
]
(OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
print(json.dumps({"result": str(OUT / "result.json"), "cases": result["cases"],
                  "provider_constructor_sentinel_hits": result["provider_constructor_sentinel_hits"],
                  "http_transport_denials": result["http_transport_denials"], "socket_connection_attempts": result["socket_connection_attempts"]}, indent=2))
