"""Qualify fixed retained anchor prices and consume the new reviewed view."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import socket
from types import SimpleNamespace

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import DataAcquisitionPolicy
from stock_opportunity_agent.data.reviewed_snapshot import (
    _read_bound, _verify_market_document, materialize_reviewed_snapshot,
    open_raw_info_store, ReviewedSourceRejected,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.basic_info_orientation import compile_basic_info_requests
from stock_opportunity_agent.research.evolution_control import _build_evidence_resolver
from stock_opportunity_agent.research.evolution_core import (
    default_information_plan, project_basic_info_bundle, _prediction_baseline_from_market_documents,
)

REPO = Path(__file__).resolve().parents[1]


def _read(path):
    return json.loads(Path(path).read_bytes())


def _binding(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _completed_proofs(inventory_path, proof_root):
    if __package__:
        from scripts.collect_reviewed_market_proofs import _requests
    else:
        from collect_reviewed_market_proofs import _requests
    requests, _count = _requests(inventory_path)
    plan, attempts, results = (_read(proof_root / name) for name in ("plan.json", "attempts.json", "results.json"))
    ids = {row["proof_id"] for row in requests}
    if (plan["inventory"] != _binding(inventory_path) or plan["requests"] != requests
            or len(attempts) != 30 or {row["proof_id"] for row in attempts} != ids
            or any(row["state"] != "received" for row in attempts)
            or len(results) != 30 or {row["name"] for row in results} != ids):
        raise ReviewedSourceRejected("collection is not the exact terminal 30-proof plan")
    if _binding(plan["script"]["path"]) != plan["script"]:
        raise ReviewedSourceRejected("frozen collector script binding differs")
    by_id = {row["name"]: row for row in results}
    for request in requests:
        receipt = by_id[request["proof_id"]]
        if (receipt["endpoint"] != request["endpoint"] or receipt["query"] != request["query"]
                or receipt["raw_response"] != receipt["name"] + ".response.json"
                or receipt["http_status"] != 200 or receipt["provider_status"] != "OK"
                or receipt["next_page_present"] is not False):
            raise ReviewedSourceRejected("terminal proof receipt identity differs")
        _read_bound({"path": str(proof_root / receipt["raw_response"]), "sha256": receipt["sha256"]})
    return by_id


def _candidate(case, source, receipts, proof_root):
    document = RawInfoDocument.from_dict(_read_bound(source["original_record"])[1])
    issuer_id, split_id = case["proof_request_ids"]
    issuer = _read(proof_root / receipts[issuer_id]["raw_response"])["results"]
    record_binding = _binding(proof_root / "results.json")
    row = {"document_id": document.document_id, "company_id": document.company_id,
        "content_hash": document.content_hash, "original_record": source["original_record"],
        "verdict": "unknown", "reason": "Native retained market proof verification pending.",
        "reviewed_available_at": document.available_at.isoformat(),
        "proof_profile": "massive_daily_no_post_cutoff_split_v1", "proofs": [
            {"kind": "massive_daily_origin", "artifact": source["cache"],
             "provider_retrieved_at": source["cache_retrieved_at"],
             "normalization_retrieved_at": source["normalization_retrieved_at_utc"]},
            {"kind": "massive_historical_issuer",
             "artifact": _binding(proof_root / receipts[issuer_id]["raw_response"]),
             "request_record": record_binding, "entry_name": issuer_id,
             "expected_identity": {"ticker": case["ticker"], "cik": case["company_id"].removeprefix("cik_"),
                 "market": "stocks", "locale": "us", "primary_exchange": issuer.get("primary_exchange"),
                 "type": "CS", "currency_name": "usd"}},
            {"kind": "massive_no_post_cutoff_splits",
             "artifact": _binding(proof_root / receipts[split_id]["raw_response"]),
             "request_record": record_binding, "entry_name": split_id}]}
    try:
        proofs = {proof["kind"]: (proof, _read_bound(proof["artifact"])[1]) for proof in row["proofs"]}
        _verify_market_document(document, row, proofs, datetime.fromisoformat(case["prediction_time"]))
    except (ReviewedSourceRejected, ValidationError, ValueError, KeyError, TypeError) as error:
        row["reason"] = "Native market proof rejected: " + str(error)
    else:
        row.update(verdict="admitted", reason="Native complete production reconstruction, historical issuer and all-type split proof passed at the original case cutoff; no predictive effect claim.")
    return row


def _literal_check(baseline, expected):
    return (baseline.get("status") == "available"
        and baseline["trading_dates"] == expected["literal_baseline_dates"]
        and math.isclose(baseline["mean_adjusted_close"], expected["independent_mean"], rel_tol=0, abs_tol=1e-12)
        and math.isclose(baseline["recent_close"], expected["latest_close"], rel_tol=0, abs_tol=1e-12)
        and math.isclose(baseline["doubling_threshold"], 2 * expected["independent_mean"], rel_tol=0, abs_tol=1e-12))


def diagnose(inventory_path, proof_root, review_path, output):
    """Author one new review and consume native market products without labels."""
    inventory_path, proof_root, review_path, output = map(lambda p: Path(p).resolve(),
        (inventory_path, proof_root, review_path, output))
    if output.exists() or review_path.exists():
        raise ReviewedSourceRejected("diagnostic review and output must be new")
    receipts = _completed_proofs(inventory_path, proof_root)
    inventory = _read(inventory_path)
    base_path = Path(inventory["excluded_already_qualified_case"]["existing_review"]["path"])
    base_review = _read(base_path)
    literal_path, origin_path = (inventory_path.parent / name for name in
        ("baseline-literal-expectations.json", "origin-reconstruction.json"))
    literals = _read(literal_path)
    if (len(inventory["cases"]) != 15 or sum(len(case["documents"]) for case in inventory["cases"]) != 16
            or [case["case_id"] for case in literals["cases"]] != [case["case_id"] for case in inventory["cases"]]):
        raise ReviewedSourceRejected("fixed 15-case/16-original expectation scope differs")
    old_input = REPO / "runs/diagnostics/reviewed_market_snapshot_20261019_v4/input_manifest.json"
    old_binding = _read(old_input)["reviewed_source_snapshot"]
    old_files = [_binding(path) for path in sorted(Path(old_binding["root"]).rglob("*")) if path.is_file()]
    review = deepcopy(base_review)
    review.pop("manifest_hash", None)
    review["scope"].update(company_ids=sorted(set(review["scope"]["company_ids"]) |
        {case["company_id"] for case in inventory["cases"]}), purpose="Fixed 15-case/16-original retained anchor market qualification and native consumers; not full readiness.")
    rows = [_candidate(case, source, receipts, proof_root)
            for case in inventory["cases"] for source in case["documents"]]
    review["records"].extend(rows)
    review["readonly_data_requests_for_retained_proofs"] = base_review["readonly_data_requests_for_retained_proofs"] + 30
    review["manifest_hash"] = canonical_json_hash(review)
    atomic_write_json(review_path, review)
    binding = materialize_reviewed_snapshot(review_path, output / "snapshot")
    original_bindings = [row["original_record"] for row in review["records"]]
    inputs = {"schema_version": "fixed-anchor-market-consumers-v1", "fixed_case_denominator": 15,
        "candidate_document_denominator": 16, "source_review": _binding(review_path),
        "reviewed_source_snapshot": binding, "inventory": _binding(inventory_path),
        "collection_plan": _binding(proof_root / "plan.json"), "final_results": _binding(proof_root / "results.json"),
        "final_attempts": _binding(proof_root / "attempts.json"), "origin_reconstruction": _binding(origin_path),
        "baseline_literal_expectations": _binding(literal_path), "original_bindings": original_bindings,
        "raw_response_bindings": [_binding(proof_root / row["raw_response"]) for row in receipts.values()],
        "code_bindings": [_binding(Path(__file__)), *[_binding(REPO / "src/stock_opportunity_agent" / name) for name in
            ("data/reviewed_snapshot.py", "data/raw_info.py", "data/resolution.py", "data/acquisition.py",
             "data/sources/massive.py", "research/evolution_core.py", "research/evolution_control.py",
             "research/basic_info_orientation.py")]], "labels_loaded": False, "full_prepare_executed": False,
        "model_calls_authorized": False, "acquisition_allowed": False}
    atomic_write_json(output / "input_manifest.json", inputs)
    input_hash = canonical_json_hash(inputs)
    frozen_binding = _read(output / "input_manifest.json")["reviewed_source_snapshot"]
    store = open_raw_info_store(frozen_binding["root"], reviewed_snapshot=frozen_binding)
    worker = store.snapshot()
    resolver = _build_evidence_resolver(output / "runtime", worker,
        contract=SimpleNamespace(data_acquisition=DataAcquisitionPolicy()), allow_data_external=False, environ={}, cycle_id=1)
    outcomes = []
    for case, expected in zip(inventory["cases"], literals["cases"], strict=True):
        cutoff = datetime.fromisoformat(case["prediction_time"])
        bundle = resolver.resolve_basic_info(compile_basic_info_requests(default_information_plan().basic_info_policy),
            company_id=case["company_id"], identity={"ticker": case["ticker"]}, as_of=cutoff)
        model, lineage = project_basic_info_bundle(bundle)
        market_results = [result for result in bundle.requests if "market_data" in result.request.source_types]
        documents = tuple(document for result in market_results
            for document in resolver.load_documents(result, as_of=cutoff))
        baseline = _prediction_baseline_from_market_documents(documents, cutoff)
        admitted = [row for row in rows if row["company_id"] == case["company_id"] and row["verdict"] == "admitted"]
        boundary_checks = []
        for row in admitted:
            document = store.load(row["document_id"], as_of=cutoff)
            try:
                store.load(document.document_id, as_of=document.available_at - timedelta(seconds=1))
                before_rejected = False
            except ValidationError:
                before_rejected = True
            boundary_checks.append({"document_id": document.document_id,
                "complete_original_equal": document.to_dict() == _read(row["original_record"]["path"]),
                "before_available_rejected": before_rejected,
                "exact_available_load_equal": store.load(document.document_id, as_of=document.available_at) == document})
        outcome = {"case_id": case["case_id"], "candidate_documents": len(case["documents"]),
            "admitted_documents": len(admitted), "baseline": baseline,
            "consumer_source_ids": [document.document_id for document in documents],
            "all_admitted_market_documents_consumed": {document.document_id for document in documents} == {row["document_id"] for row in admitted},
            "market_request_resolved": any(result.status == "resolved" for result in market_results),
            "literal_matches": [{"document_id": item["document_id"], "matches": _literal_check(baseline, item)}
                for item in expected["original_literal_expectations"]], "source_boundary_checks": boundary_checks}
        outcome["passed"] = (len(admitted) == len(case["documents"]) and outcome["all_admitted_market_documents_consumed"]
            and outcome["market_request_resolved"] and all(item["matches"] for item in outcome["literal_matches"])
            and all(check["complete_original_equal"] and check["before_available_rejected"] and check["exact_available_load_equal"] for check in boundary_checks))
        atomic_write_json(output / "cases" / (case["case_id"] + ".json"),
            {"case": case, "outcome": outcome, "basic_info_bundle": bundle.to_dict(), "model_context": model, "lineage": lineage})
        outcomes.append(outcome)
        print(case["case_id"] + ": " + ("passed" if outcome["passed"] else "unresolved"), flush=True)
    if canonical_json_hash(_read(output / "input_manifest.json")) != input_hash:
        raise ReviewedSourceRejected("diagnostic input freeze changed")
    for bound in [*inputs["original_bindings"], *inputs["raw_response_bindings"], *inputs["code_bindings"],
            inputs["source_review"], inputs["inventory"], inputs["final_results"], inputs["final_attempts"],
            inputs["collection_plan"], inputs["origin_reconstruction"], inputs["baseline_literal_expectations"]]:
        if _binding(bound["path"]) != bound:
            raise ReviewedSourceRejected("diagnostic bound input changed")
    restored_binding = _read(output / "input_manifest.json")["reviewed_source_snapshot"]
    restored = open_raw_info_store(restored_binding["root"], reviewed_snapshot=restored_binding)
    old_equal = old_files == [_binding(path) for path in sorted(Path(old_binding["root"]).rglob("*")) if path.is_file()]
    result = {"schema_version": "fixed-anchor-market-qualification-result-v1", "input_manifest_hash": input_hash,
        "fixed_case_denominator": 15, "candidate_document_denominator": 16, "old_review_row_count": 5,
        "old_rows_preserved_verbatim": review["records"][:5] == base_review["records"],
        "candidate_verdicts": [{"document_id": row["document_id"], "verdict": row["verdict"], "reason": row["reason"]} for row in rows],
        "new_admitted_document_count": sum(row["verdict"] == "admitted" for row in rows),
        "reviewed_total_document_count": len(store.documents), "consumer_cases_passed": sum(row["passed"] for row in outcomes),
        "outcomes": outcomes, "restored_typed_store_equal": type(restored) is type(store) is type(worker) and restored.documents == store.documents,
        "old_reviewed_view_unchanged": old_equal, "originals_and_inputs_unchanged": True,
        "readonly_data_requests": 0, "external_llm_calls": 0, "labels_loaded": False,
        "full_prepare_executed": False, "full_dataset_readiness_proven": False, "engineering_mvp_closed": False,
        "limitations": ["No new narrative qualification or role execution; 15-case market consumers only.",
            "Source admission and arithmetic do not establish prediction gain, full readiness or Fast/Slow completion."]}
    atomic_write_json(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--proofs", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network forbidden in anchor market diagnostic")
    socket.socket = forbidden
    result = diagnose(args.inventory, args.proofs, args.review, args.output)
    print(json.dumps({key: value for key, value in result.items() if key not in ("outcomes", "candidate_verdicts")}, indent=2))
