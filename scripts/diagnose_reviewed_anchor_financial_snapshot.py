"""Derive fixed SEC facts, qualify a separate view, and prepare exact inputs."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import ssl  # Initialize stdlib socket subclasses before installing the tripwire.
from time import monotonic
from types import SimpleNamespace

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import DataAcquisitionPolicy
from stock_opportunity_agent.data.reviewed_snapshot import (
    ReviewedSourceRejected, _read_bound, _verify_companyfacts_document, materialize_reviewed_snapshot,
    open_raw_info_store,
)
from stock_opportunity_agent.data.sec_company_facts import (
    STANDARD_FORMS, STANDARD_TAXONOMIES, materialize_company_fact_documents,
    validate_company_facts_response,
)
from stock_opportunity_agent.research.evolution_control import _build_evidence_resolver
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry


REPO = Path(__file__).resolve().parents[1]
PROFILE = "sec_companyfacts_filed_next_utc_day_v1"
INVENTORY_SHA = "4da1faff57f64bcb1e5571d3b3b7bd4d006ad8b5ac427da59a76a5b279d63f8b"
DEFAULT_INVENTORY = REPO / "runs/diagnostics/financial_source_qualification_20261020_v1/inventory.json"
DEFAULT_OPERATING_INPUT = REPO / "runs/diagnostics/reviewed_anchor_operating_source_snapshot_20261020_v1/input_manifest.json"
DEFAULT_OUTPUT = REPO / "runs/diagnostics/reviewed_anchor_financial_snapshot_20261020_v1/stage"
OWNING_SPEC = REPO / "spec/scripts/diagnose_reviewed_anchor_financial_snapshot.md"
SOURCE_SPECS = tuple(REPO / "spec/src/stock_opportunity_agent/data" / name for name in
                     ("reviewed_snapshot.md", "reviewed_companyfacts_profile.md", "sec_company_facts.md"))


def _read(path):
    return json.loads(Path(path).read_bytes())


def _binding(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _tree(root):
    return [_binding(path) for path in sorted(Path(root).rglob("*")) if path.is_file()]


def _check_bindings(bindings):
    for binding in bindings:
        if _binding(binding["path"]) != binding:
            raise ReviewedSourceRejected("bound diagnostic input changed: " + binding["path"])


def _require_same_record(actual, expected):
    """Reject JSON type or provenance drift despite Python value equality."""
    if canonical_json_hash(actual.to_dict()) != canonical_json_hash(expected.to_dict()):
        raise ReviewedSourceRejected("append or replay differs from the complete derived product")


def _same_document_set(actual, expected):
    return canonical_json_hash([doc.to_dict() for doc in actual]) == canonical_json_hash(
        [doc.to_dict() for doc in expected])


def _registry(source_input, output):
    source = _read(source_input)
    registry = SignalRegistry(source["registry_root"], candidate_root=output / "unused_candidates")
    snapshot = registry.snapshot_from_refs(source["registry_version"], tuple(source["registry_refs"]))
    if (snapshot.version != 12 or len(snapshot.specs) != 18
            or snapshot.registry_hash != source["registry_hash"]):
        raise ReviewedSourceRejected("exact frozen v12/18-ref definitions differ")
    return snapshot


def prepare(inventory_path, operating_input_path, output):
    """Freeze local inputs only; never construct or append to the global store."""
    inventory_path, operating_input_path, output = (
        Path(value).resolve() for value in (inventory_path, operating_input_path, output))
    if output.exists():
        raise ReviewedSourceRejected("financial diagnostic output must be new")
    inventory_binding = _binding(inventory_path)
    if inventory_binding["sha256"] != INVENTORY_SHA:
        raise ReviewedSourceRejected("fixed financial inventory changed")
    inventory = _read(inventory_path)
    operating = _read(operating_input_path)
    if (len(inventory["cases"]) != 15
            or len({row["case_id"] for row in inventory["cases"]}) != 15
            or inventory["summary"]["original_financial_documents"] != 15
            or inventory["summary"]["original_raw_response_proof_documents"] != 15
            or inventory["summary"]["matching_exact_cache_requests"] != 15):
        raise ReviewedSourceRejected("fixed 15-case/45-source scope differs")
    source_bindings = [case[key]["binding"] for case in inventory["cases"]
                       for key in ("exact_cache", "original_financial", "original_raw_proof")]
    _check_bindings(source_bindings)
    review_binding = operating["source_review"]
    _, review = _read_bound(review_binding)
    oracle_binding = review["oracle_identity"]
    _read_bound(oracle_binding)
    oracle_root = Path(oracle_binding["path"]).resolve().parent
    if output.is_relative_to(oracle_root) or oracle_root.is_relative_to(output):
        raise ReviewedSourceRejected("diagnostic output must be separate from the source oracle")
    _check_bindings([operating["registry_source_inputs"], *operating["registry_bindings"]])
    snapshot = _registry(operating["registry_source_inputs"]["path"], output)
    if (snapshot.registry_hash != operating["registry_hash"]
            or [spec.ref for spec in snapshot.specs] != operating["registry_refs"]):
        raise ReviewedSourceRejected("operating exact-ref authority differs")
    plan = {
        "schema_version": "fixed-anchor-financial-plan-v1",
        "inventory": inventory_binding, "operating_inputs": _binding(operating_input_path),
        "old_source_review": review_binding, "oracle_identity": oracle_binding,
        "source_bindings": source_bindings, "old_view_bindings": _tree(operating["reviewed_source_snapshot"]["root"]),
        "old_readiness_result": _binding(operating_input_path.parent / "result.json"),
        "registry_source_inputs": operating["registry_source_inputs"],
        "registry_bindings": operating["registry_bindings"],
        "registry_version": snapshot.version, "registry_hash": snapshot.registry_hash,
        "registry_refs": [spec.ref for spec in snapshot.specs],
        "code_bindings": [_binding(Path(__file__)), _binding(OWNING_SPEC), *map(_binding, SOURCE_SPECS),
                          *[_binding(path) for path in sorted((REPO / "src/stock_opportunity_agent").rglob("*.py"))]],
        "fixed_case_denominator": 15, "exact_cache_denominator": 15,
        "legacy_aggregate_denominator": 15, "raw_proof_denominator": 15,
        "signal_ref_denominator": 18, "resolution_denominator": 270,
        "proof_profile": PROFILE, "network_allowed": False, "model_allowed": False,
        "labels_allowed": False, "signal_apply_allowed": False, "full_prepare_allowed": False,
    }
    plan["plan_hash"] = canonical_json_hash(plan)
    atomic_write_json(output / "plan.json", plan)
    return plan


def _verify_plan(output):
    plan = _read(output / "plan.json")
    if canonical_json_hash({k: v for k, v in plan.items() if k != "plan_hash"}) != plan["plan_hash"]:
        raise ReviewedSourceRejected("financial diagnostic plan hash differs")
    if (plan.get("schema_version") != "fixed-anchor-financial-plan-v1"
            or plan.get("proof_profile") != PROFILE
            or any(plan.get(key) != count for key, count in
                   (("fixed_case_denominator", 15), ("exact_cache_denominator", 15),
                    ("legacy_aggregate_denominator", 15), ("raw_proof_denominator", 15),
                    ("signal_ref_denominator", 18), ("resolution_denominator", 270)))
            or any(plan.get(key) is not False for key in
                   ("network_allowed", "model_allowed", "labels_allowed", "signal_apply_allowed", "full_prepare_allowed"))
            or plan["inventory"]["sha256"] != INVENTORY_SHA):
        raise ReviewedSourceRejected("financial diagnostic scope or forbidden operation differs")
    _check_bindings([plan[key] for key in ("inventory", "operating_inputs", "old_source_review",
                    "oracle_identity", "old_readiness_result", "registry_source_inputs")])
    for key in ("source_bindings", "old_view_bindings", "registry_bindings", "code_bindings"):
        _check_bindings(plan[key])
    return plan


def _derive(case):
    cache_binding = case["exact_cache"]["binding"]
    raw_binding = case["original_raw_proof"]["binding"]
    _, cache = _read_bound(cache_binding)
    _, raw_record = _read_bound(raw_binding)
    raw = RawInfoDocument.from_dict(raw_record)
    cik = case["company_id"].removeprefix("cik_")
    endpoint = "https://data.sec.gov/api/xbrl/companyfacts/CIK" + cik + ".json"
    if (cache["endpoint"] != endpoint or cache["params"] != [["method", "GET"]]
            or cache["source_key"] != "sec_edgar" or cache["capability"] != "financial_statements"
            or cache["payload_kind"] != "json"
            or raw.source_type != "sec_company_facts_raw_response"
            or raw.company_id != case["company_id"]
            or raw.content != json.dumps(cache["body"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)):
        raise ReviewedSourceRejected("exact Company Facts origin differs")
    validate_company_facts_response(cache["body"], cik)
    cutoff = datetime.fromisoformat(case["cutoff"])
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ReviewedSourceRejected("financial case cutoff must be aware")
    selection = {"period_end_from": date.min.isoformat(),
        "period_end_through": cutoff.astimezone(timezone.utc).date().isoformat(),
        "available_at_through": cutoff.astimezone(timezone.utc).isoformat(),
        "taxonomy_allowlist": list(STANDARD_TAXONOMIES), "form_allowlist": list(STANDARD_FORMS)}
    policy = {"schema_version": "sec-company-facts-acquisition-v1", "selection": selection}
    provenance = {"acquisition_policy_hash": canonical_json_hash(policy), "acquisition_selection": selection}
    item = {"cik": cik, "company_id": case["company_id"], "symbol": case["ticker"], "source_url": endpoint}
    normalized_at = datetime.now(timezone.utc)
    products, stats = materialize_company_fact_documents(cache["body"], item=item,
        selection=selection, provenance=provenance, retrieved_at=normalized_at)
    if not products:
        raise ReviewedSourceRejected("fixed source produced no eligible accession products")
    normalization = {"schema_version": "sec-companyfacts-normalization-v1", "normalizer_profile": PROFILE,
        "source_cache": cache_binding, "raw_response": raw_binding, "item": item,
        "selection": selection, "provenance": provenance, "normalized_at": normalized_at.isoformat(),
        "expected_products": [{"document_id": doc.document_id,
            "canonical_record_hash": canonical_json_hash(doc.to_dict()), "content_hash": doc.content_hash}
            for doc in products]}
    return products, normalization, stats


def _check_global(before, root, expected_new):
    current = {binding["path"]: binding for binding in _tree(root)}
    for binding in before:
        if current.get(binding["path"]) != binding:
            raise ReviewedSourceRejected("pre-existing global source bytes changed")
    additions = set(current) - {binding["path"] for binding in before}
    permitted = set(expected_new) | {str(root / ".raw-info-append.lock")}
    if additions - permitted or set(expected_new) - set(current):
        raise ReviewedSourceRejected("global source additions differ from the append inventory")
    return [current[path] for path in sorted(additions)]


def _financial_row(document, original, normalization, case):
    return {"document_id": document.document_id, "company_id": document.company_id,
        "content_hash": document.content_hash, "original_record": original,
        "verdict": "admitted", "reviewed_available_at": document.available_at.isoformat(),
        "proof_profile": PROFILE,
        "reason": "Exact retained SEC Company Facts reconstruction under filed-next-UTC-day policy; retrospective extraction and primary-filing audit remain disclosed, with no measurement/readiness claim.",
        "proofs": [{"kind": "sec_companyfacts_cache", "artifact": case["exact_cache"]["binding"]},
            {"kind": "sec_companyfacts_raw_response", "artifact": case["original_raw_proof"]["binding"]},
            {"kind": "sec_companyfacts_normalization", "artifact": normalization}]}


def execute(output):
    """Perform the separately frozen append/qualification/input-only diagnostic."""
    output = Path(output).resolve()
    plan = _verify_plan(output)
    if (output / "execution-start.json").exists():
        raise ReviewedSourceRejected("completed or partial financial diagnostic cannot be rerun")
    atomic_write_json(output / "execution-start.json", {"plan_hash": plan["plan_hash"],
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "started"})
    timings = {}
    started = monotonic()
    cases = _read(plan["inventory"]["path"])["cases"]
    oracle_root = Path(plan["oracle_identity"]["path"]).parent
    before = _tree(oracle_root)
    atomic_write_json(output / "global-originals-before.json", before)
    timings["hash_preexisting_global_seconds"] = monotonic() - started
    old_review = _read(plan["old_source_review"]["path"])
    snapshot = _registry(plan["registry_source_inputs"]["path"], output)
    derived = []
    started = monotonic()
    for case in cases:
        products, normalization, stats = _derive(case)
        normalization_path = output / "normalizations" / (case["case_id"] + ".json")
        atomic_write_json(normalization_path, normalization)
        derived.append((case, products, _binding(normalization_path), stats))
    timings["derive_all_products_seconds"] = monotonic() - started
    # Qualify every group with the actual source-profile verifier before the
    # first append. No fake oracle, marker relocation or candidate file is used.
    started = monotonic()
    profile_memo = {}
    for case, products, normalization_binding, _stats in derived:
        proof_rows = [
            {"kind": "sec_companyfacts_cache", "artifact": case["exact_cache"]["binding"]},
            {"kind": "sec_companyfacts_raw_response", "artifact": case["original_raw_proof"]["binding"]},
            {"kind": "sec_companyfacts_normalization", "artifact": normalization_binding},
        ]
        proofs = {proof["kind"]: (proof, _read_bound(proof["artifact"])[1]) for proof in proof_rows}
        cutoff = datetime.fromisoformat(case["cutoff"])
        for document in products:
            _verify_companyfacts_document(document,
                {"reviewed_available_at": document.available_at.isoformat()}, proofs, cutoff, profile_memo)
    timings["preappend_actual_profile_verification_seconds"] = monotonic() - started
    del profile_memo
    started = monotonic()
    global_store = RawInfoStore(root=oracle_root)
    timings["global_store_initial_load_seconds"] = monotonic() - started
    rows, receipts, case_derivations, expected_new = [], [], [], []
    started = monotonic()
    for case, products, normalization_binding, stats in derived:
        for document in products:
            inserted = global_store.append(document)
            _require_same_record(global_store.load(document.document_id), document)
            original = _binding(oracle_root / document.source_type / document.company_id / (document.document_id + ".json"))
            receipt = {"document_id": document.document_id, "case_id": case["case_id"],
                "append_returned_true": inserted, "complete_load_equal": True, "original_record": original}
            atomic_write_json(output / "append-receipts" / (document.document_id + ".json"), receipt)
            receipts.append(receipt)
            expected_new.append(original["path"])
            rows.append(_financial_row(document, original, normalization_binding, case))
        case_derivations.append({"case_id": case["case_id"], "normalization": normalization_binding,
            "source_cache_clock": case["exact_cache"]["cache_retrieved_at"],
            "legacy_normalization_clock": case["exact_cache"]["original_normalization_clock"],
            "product_count": len(products), "normalizer_statistics": stats})
        print(case["ticker"] + ": appended/verified " + str(len(products)) + " accession products", flush=True)
    timings["native_append_and_exact_load_seconds"] = monotonic() - started
    additions = _check_global(before, oracle_root, expected_new)
    atomic_write_json(output / "append-inventory.json", {"case_derivations": case_derivations,
        "receipts": receipts, "global_new_files": additions, "old_global_bytes_unchanged": True})
    review = deepcopy(old_review)
    review.pop("manifest_hash", None)
    review["records"].extend(rows)
    review["status"] = "reviewed_financial_policy_sources"
    review["original_oracle_writes"] = sum(row["append_returned_true"] for row in receipts)
    review["scope"]["purpose"] = "Fixed15 original cases: new filed-policy financial products plus unchanged operating/market source review; exact-v12 input-only readiness."
    review["manifest_hash"] = canonical_json_hash(review)
    review_path = output / "source-review.json"
    atomic_write_json(review_path, review)
    started = monotonic()
    view = materialize_reviewed_snapshot(review_path, output / "snapshot")
    timings["materialize_reviewed_view_seconds"] = monotonic() - started
    inputs = {"schema_version": "fixed-anchor-financial-inputs-v1", "plan": _binding(output / "plan.json"),
        "source_review": _binding(review_path), "reviewed_source_snapshot": view,
        "normalizations": [item[2] for item in derived], "new_originals": [row["original_record"] for row in rows],
        "case_derivations": case_derivations, "fixed_case_denominator": 15,
        "exact_cache_denominator": 15, "legacy_aggregate_denominator": 15, "raw_proof_denominator": 15,
        "new_product_denominator": len(rows), "registry_version": snapshot.version,
        "registry_hash": snapshot.registry_hash, "registry_refs": plan["registry_refs"],
        "labels_loaded": False, "signal_apply_executed": False, "full_prepare_executed": False}
    atomic_write_json(output / "input_manifest.json", inputs)
    input_hash = canonical_json_hash(inputs)
    started = monotonic()
    store = open_raw_info_store(view["root"], reviewed_snapshot=view)
    worker = store.snapshot()
    resolver = _build_evidence_resolver(output / "runtime", worker,
        contract=SimpleNamespace(data_acquisition=DataAcquisitionPolicy()),
        allow_data_external=False, environ={}, cycle_id=1)
    executor = SignalExecutor(snapshot, worker, resolver=resolver)
    summaries = []
    for case in cases:
        cutoff = datetime.fromisoformat(case["cutoff"])
        resolutions = executor.prepare_inputs(tuple(plan["registry_refs"]), company_id=case["company_id"],
            as_of=cutoff, identity={"ticker": case["ticker"], "cik": case["company_id"].removeprefix("cik_")})
        exact = [{"signal_ref": ref, "resolution": resolution.to_dict()}
                 for ref, resolution in zip(plan["registry_refs"], resolutions, strict=True)]
        ready = sum(item.status == "resolved" for item in resolutions)
        summary = {"case_id": case["case_id"], "resolved_signal_inputs": ready, "signal_ref_denominator": 18,
            "resolved_fraction": ready / 18, "meets_existing_0_8_signal_input_fraction": ready / 18 >= 0.8}
        atomic_write_json(output / "cases" / (case["case_id"] + ".json"),
            {"case": case, "summary": summary, "exact_signal_input_resolutions": exact})
        summaries.append(summary)
        print(case["ticker"] + ": exact-v12 inputs " + str(ready) + "/18", flush=True)
    timings["input_only_consumers_seconds"] = monotonic() - started
    restored = open_raw_info_store(view["root"], reviewed_snapshot=_read(output / "input_manifest.json")["reviewed_source_snapshot"])
    if (not _same_document_set(restored.documents, store.documents)
            or not _same_document_set(worker.documents, store.documents)
            or type(restored) is not type(worker)
            or canonical_json_hash(_read(output / "input_manifest.json")) != input_hash):
        raise ReviewedSourceRejected("financial reviewed view/input restore differs")
    _verify_plan(output)
    _check_bindings(inputs["new_originals"] + inputs["normalizations"])
    additions = _check_global(before, oracle_root, expected_new)
    result = {"schema_version": "fixed-anchor-financial-result-v1", "input_manifest_hash": input_hash,
        "fixed_case_denominator": 15, "original_source_denominators": {"caches": 15, "legacy_aggregates": 15, "raw_proofs": 15},
        "new_product_denominator": len(rows), "newly_appended_products": sum(row["append_returned_true"] for row in receipts),
        "exact_replayed_products": sum(not row["append_returned_true"] for row in receipts),
        "all_append_loads_complete_equal": True, "all_old_global_files_unchanged": True,
        "global_new_files": additions, "old_operating_review_rows_preserved_verbatim": canonical_json_hash(review["records"][:len(old_review["records"])]) == canonical_json_hash(old_review["records"]),
        "typed_view_worker_restore_equal": True, "fixed_resolution_denominator": 270,
        "cases_meeting_existing_0_8": sum(row["meets_existing_0_8_signal_input_fraction"] for row in summaries),
        "cases": summaries, "timings": timings, "network_requests": 0, "external_llm_calls": 0,
        "labels_loaded": False, "signal_apply_executed": False, "full_prepare_executed": False,
        "full48_readiness_proven": False, "engineering_mvp_closed": False,
        "limitations": ["Filed-only next-UTC-day policy, not exact SEC acceptance or as-published API vintage.",
            "Retrospective extraction and required primary-filing audit remain disclosed and incomplete.",
            "270 input resolutions do not prove semantic measurement, full coverage, model behavior or prediction benefit."]}
    atomic_write_json(output / "result.json", result)
    return result


def main():
    """Run an explicit preparation or separately approved execution operation."""
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute", action="store_true")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--operating-input", type=Path, default=DEFAULT_OPERATING_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network forbidden in financial source diagnostic")
    socket.socket = forbidden
    result = prepare(args.inventory, args.operating_input, args.output) if args.prepare else execute(args.output)
    print(json.dumps({key: value for key, value in result.items() if key in
        ("schema_version", "plan_hash", "fixed_case_denominator", "new_product_denominator", "cases_meeting_existing_0_8")}, indent=2))


if __name__ == "__main__":
    main()
