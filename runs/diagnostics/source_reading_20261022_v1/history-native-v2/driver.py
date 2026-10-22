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
    target_tag = "NetCashProvidedByUsedInOperatingActivities"
    records = [{"taxonomy": "us-gaap", "tag": target_tag, "unit": "USD", "value": value,
        "start": f"{year}-01-01", "end": f"{year}-06-30"}
        for year, value in ((2024,120),(2023,100),(2022,80),(2021,70))]
    required_rows = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in records[2:]]
    quote = required_rows[0]
    docs = []
    for i in range(11):
        rows = records if i == 10 else [{**records[0], "tag": "OtherFinancialConcept"}]
        payload = {"schema_version": "sec-company-facts-document-v1", "filing_date": "2024-08-01",
            "facts": rows, "document_title": f"Financial disclosure {i:02d}", "note": "operating cash flow 2022 2021 " * (10 if i < 10 else 1)}
        docs.append(RawInfoDocument.create(document_id=f"disclosure-{i:02d}", company_id="probe_subject",
            source_type="sec_company_facts", published_at=cutoff-timedelta(days=i), available_at=cutoff-timedelta(days=i),
            content=json.dumps(payload, sort_keys=True, separators=(",", ":"))))
    docs = tuple(docs)
    spec = SignalSpec(signal_id="historical_cash_flow_change", version=1, category="financial",
        description="Compare disclosed six-month operating cash flow in 2022 with the matching six months in 2021.",
        execution_type=SignalExecutionType.LLM, source_types=("financials",), skill_file="historical_cash_flow_change.md",
        retrieval_policy=SignalRetrievalPolicy(query_terms=("operating cash flow 2022 2021",)))
    skill = ("Use NetCashProvidedByUsedInOperatingActivities for the six months ending June 30, 2022 and June 30, 2021. "
        "Positive means the disclosed 2022 value exceeds 2021, negative means below, neutral means equal. "
        "Require both literal rows, matching USD unit and six-month periods, and reject conflicts as unavailable. "
        "Do not substitute the latest or nearest recent reporting year. Cite both complete raw fact records.")
    inputs = {"as_of": cutoff.isoformat(), "spec": spec.to_dict(), "skill": skill,
              "documents": [d.to_dict() for d in docs], "explicitly_synthetic": True}
    snapshot = FrozenSignalRegistry(version=1, registry_hash=canonical_json_hash(spec.to_dict()),
        specs=(spec,), skills={spec.ref: skill})
    check = SignalExecutor(snapshot, RawInfoStore(documents=docs))
    resolution = check.prepare_inputs((spec.ref,), company_id="probe_subject", as_of=cutoff)[0]
    selected = [d.document_id for d in resolution.documents]
    if docs[-1].document_id in selected or len(selected) != 10:
        raise ValidationError("synthetic rank-eleven precondition failed")
    _immutable(ROOT / "preflight.json", {"initial_selected_ids": selected,
        "outside_initial_selection": docs[-1].document_id, "eligible_documents": 11})
    _immutable(ROOT / "inputs.json", inputs)
    _immutable(ROOT / "oracle.json", {"source_only": True, "signal_ref": spec.ref,
        "value": "positive", "document_id": docs[-1].document_id, "exact_span": quote,
        "content_hash": docs[-1].content_hash, "must_read_initial_rank": 11, "required_rows": required_rows, "required_periods": ["2022-06-30", "2021-06-30"]})
    _immutable(ROOT / "contract.json", {"schema_version": "bounded-source-reading-synthetic-probe-v1",
        "input_hash": canonical_json_hash(inputs), "code": bindings(), "external_llm_api_calls": 0,
        "scope": "one synthetic historical-period Signal; bounded reading only, no actual-source or MVP closure",
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
        and all(any(e.document_id == oracle["document_id"] and e.exact_span == row for e in result.supporting_evidence) for row in oracle["required_rows"])
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
