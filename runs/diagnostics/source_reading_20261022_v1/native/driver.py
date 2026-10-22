"""Frozen synthetic F5 protocol probe; exact native roles, no external APIs."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import sys

from diagnose_executed_answer_scope import StageContract
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending, _immutable
from stock_opportunity_agent.signal_library import FrozenSignalRegistry, SignalSpec, SignalExecutor, SignalRetrievalPolicy, SignalExecutionType

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]


def deny_network(*args, **kwargs):
    """Refuse source/provider I/O; exact local role exchange needs no socket."""
    raise AssertionError("network forbidden in synthetic F5 stage")


def bindings():
    """Freeze production code and the driver before any independent answer."""
    files = [*sorted((REPO / "src").rglob("*.py")), Path(__file__)]
    return {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def prepare():
    """Freeze eleven eligible sources and a source-only oracle outside requests."""
    cutoff = datetime(2025, 9, 30, tzinfo=timezone.utc)
    quote = "Management raised annual guidance from $100 million to $120 million."
    docs = tuple(RawInfoDocument.create(document_id=f"disclosure-{i:02d}", company_id="probe_subject",
        source_type="filing", published_at=cutoff - timedelta(days=i), available_at=cutoff - timedelta(days=i),
        content=f"Operating disclosure {i:02d}. " +
            (quote if i == 10 else "Routine operating activity continued with no forecast figures in this disclosure.")) for i in range(11))
    spec = SignalSpec(signal_id="guidance_revision", version=1, category="catalysts",
        description="Extract an explicitly disclosed upward or downward annual guidance revision.",
        execution_type=SignalExecutionType.LLM, source_types=("filing",), skill_file="guidance_revision.md",
        retrieval_policy=SignalRetrievalPolicy(query_terms=("guidance",)))
    skill = ("Compare the explicitly disclosed current annual guidance with the previously stated annual guidance. "
        "Positive means an upward revision, negative a downward revision, neutral explicitly unchanged. "
        "Require the literal comparator and amounts; if insufficient use unavailable. Do not infer from a document's date. "
        "Cite the exact complete disclosed sentence.")
    inputs = {"as_of": cutoff.isoformat(), "spec": spec.to_dict(), "skill": skill,
              "documents": [d.to_dict() for d in docs], "explicitly_synthetic": True}
    _immutable(ROOT / "inputs.json", inputs)
    _immutable(ROOT / "oracle.json", {"source_only": True, "signal_ref": spec.ref,
        "value": "positive", "document_id": docs[-1].document_id, "exact_span": quote,
        "content_hash": docs[-1].content_hash, "must_read_initial_rank": 11})
    _immutable(ROOT / "contract.json", {"schema_version": "bounded-source-reading-synthetic-probe-v1",
        "input_hash": canonical_json_hash(inputs), "code": bindings(), "external_llm_api_calls": 0,
        "scope": "one synthetic Signal; protocol and source-reading capability only, no F5 or MVP closure",
        "limits": {"max_structured_corrections": 1, "max_request_tokens": 65536,
                   "max_case_tokens": 131072, "max_local_role_calls": 4}})


def resume():
    """Drive unchanged production executor until pending or a durable result."""
    contract = json.loads((ROOT / "contract.json").read_text())
    inputs = json.loads((ROOT / "inputs.json").read_text())
    if contract["code"] != bindings() or contract["input_hash"] != canonical_json_hash(inputs):
        raise ValidationError("frozen source-reading probe code/input drift")
    exchange = LocalRoleExchange(ROOT / "exchange", max_calls=4)
    caller = StructuredRoleClient(registration=get_model("independent-subagent"), contract=StageContract(contract),
        workspace=ROOT, ledger=ExternalAttemptLedger(ROOT / "unused_external.json", max_attempts=1, max_total_cost=.01),
        allow_external=False, local_role_exchange=exchange, environ={})
    runner = StructuredLLMSignalRunner(caller)
    runner.set_request_token_budget(contract["limits"]["max_case_tokens"])
    spec = SignalSpec.from_dict(inputs["spec"])
    snapshot = FrozenSignalRegistry(version=1, registry_hash=canonical_json_hash(inputs["spec"]),
        specs=(spec,), skills={spec.ref: inputs["skill"]})
    executor = SignalExecutor(snapshot, RawInfoStore(documents=tuple(RawInfoDocument.from_dict(d) for d in inputs["documents"])),
        llm_runner=runner)
    try:
        batch = executor.execute_batch((spec.ref,), company_id="probe_subject", as_of=datetime.fromisoformat(inputs["as_of"]))
    except LocalRoleRequestPending as pending:
        return {"state": "pending", **pending.pending}
    record = {"results": [r.to_dict() for r in batch.results], "usage": asdict(batch.usage),
        "resolutions": [r.to_dict() for r in batch.resolutions],
        "document_fingerprints": {k: list(v) for k, v in batch.document_fingerprints.items()},
        "request_hashes": caller.request_hash_trace}
    _immutable(ROOT / "result.json", record)
    oracle = json.loads((ROOT / "oracle.json").read_text())
    result = batch.results[0]
    passed = (result.value.value == oracle["value"] and result.execution_status.value == "success"
        and any(e.document_id == oracle["document_id"] and e.exact_span == oracle["exact_span"] for e in result.supporting_evidence)
        and [d.document_id for d in batch.resolutions[0].documents] == [oracle["document_id"]])
    _immutable(ROOT / "acceptance.json", {"synthetic_source_oracle_passed": passed,
        "scope": contract["scope"], "actual_receipts": len(list((ROOT / "exchange/receipts").glob("*.json"))),
        "logical_usage": asdict(batch.usage), "external_llm_api_calls": 0})
    return {"state": "completed", "passed": passed, "result_path": str(ROOT / "result.json")}


if __name__ == "__main__":
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    if sys.argv[1:] == ["prepare"]:
        prepare()
        print(json.dumps({"state": "prepared", "root": str(ROOT)}))
    else:
        print(json.dumps(resume(), ensure_ascii=False))
