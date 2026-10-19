"""Qualify three retained periodic bodies and inspect fixed input-only consumers."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import ssl  # Initialize socket subclasses before the network tripwire.
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

import diagnose_reviewed_anchor_financial_snapshot as financial
import run_minimal_rounds
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore, content_sha256
from stock_opportunity_agent.data.resolution import DataAcquisitionPolicy
from stock_opportunity_agent.data.reviewed_snapshot import (
    ReviewedSourceRejected, _verify_sec_response_document, materialize_reviewed_snapshot,
    open_raw_info_store,
)
from stock_opportunity_agent.data.sources.core import decode_response_text
from stock_opportunity_agent.research.basic_info_orientation import compile_basic_info_requests
from stock_opportunity_agent.research.evolution_control import _build_evidence_resolver
from stock_opportunity_agent.research.evolution_core import default_information_plan, project_basic_info_bundle
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.signal_library import SignalExecutor


REPO = Path(__file__).resolve().parents[1]
PERIODIC = REPO / "runs/diagnostics/periodic_source_qualification_20261020_v1"
FINANCIAL = financial.DEFAULT_OUTPUT
DEFAULT_OUTPUT = REPO / "runs/diagnostics/reviewed_periodic_operating_snapshot_20261020_v1/stage"
OWNING_SPEC = REPO / "spec/scripts/diagnose_reviewed_periodic_operating_snapshot.md"
KGC_ROOT = REPO / "runs/cold_start/evolution/deepseek-v4-flash-signal-wildcard-20260822-v1/cache/data/sec_edgar/filing_documents/744c3170d6b993beaf24d546.json"
MS_ROOT = REPO / "runs/cold_start/evolution/information-evolution-mvp-20260911-v20-repair-acceptance/cache/data/sec_edgar/filing_documents/da30b1fbd4806f31edbe7d99.json"
MS_ARCHIVE = MS_ROOT.with_name("522cb1b7491aeb9c9be2a9ab.json")
_binding, _read, _tree = financial._binding, financial._read, financial._tree
_check_bindings = financial._check_bindings
FIXED_AUTHORITIES = {
    FINANCIAL / "plan.json": "09fed612e6e46dc2f36ebe3e8acd6d4a994aa7ad44382447efb08bc52e78a179",
    FINANCIAL / "input_manifest.json": "807fb3dcc990f34822adf79b64c07f50c407c659367dc9b43be68793413df465",
    FINANCIAL / "result.json": "7d9853d178b029fa0ef6b663d14d3837948f16a56a99a1fe1afb778ad1e3be94",
    FINANCIAL / "source-review.json": "faadfd5370718cc9f311d29184f2c14f65a2b5c698e292b1fdee9fed3bc01067",
    FINANCIAL / "snapshot/reviewed_snapshot.json": "51b26fdaa2c6575e9ff3f8b8a727181a5be679eff2a8ac0e426adc3599a8d4b9",
    FINANCIAL.parent / "independent/final-source-review.json": "792be7ca36e8c3898343330a9a45a07861b74c7860e802e9b0bb5e48a01e99b7",
    financial.DEFAULT_INVENTORY: financial.INVENTORY_SHA,
    PERIODIC / "primary-content-review.json": "0eda73af9ac47e2cdc88a115e506b1460fd603606b60af6918ca410068fdc853",
    PERIODIC / "annual-exhibit-content-review.json": "2a87c5a656bd035ac800a958d389ccc826fac94f1b5779bed5dff0f45d504618",
    PERIODIC / "ms-annual-clock-review.json": "2e3b3236087315163cbfea622f1c17313f35178a7b2b655434e6b15283a37bc3",
}


@contextmanager
def _source_only():
    def forbidden(*_args, **_kwargs):
        raise ReviewedSourceRejected("forbidden network/model/label/apply/fullprepare operation")
    with ExitStack() as stack:
        for target, name in ((socket, "socket"), (socket, "create_connection"),
                             (LabelStore, "load"), (LabelStore, "ground_truth"),
                             (run_minimal_rounds, "prepare")):
            stack.enter_context(patch.object(target, name, forbidden))
        for name in ("complete_json", "complete_json_with_token_scores", "complete_binary_token_with_scores"):
            stack.enter_context(patch.object(StructuredRoleClient, name, forbidden))
        stack.enter_context(patch.object(SignalExecutor, "execute_batch", forbidden))
        yield


def _receipt_entry(version, name):
    path = PERIODIC / version / "results.json"
    matches = [row for row in _read(path)["requests"] if row["name"] == name]
    if len(matches) != 1:
        raise ReviewedSourceRejected("exact retained response is missing or ambiguous")
    return path, matches[0]


def _response(version, name):
    path, entry = _receipt_entry(version, name)
    raw = _binding(entry["raw_response"])
    if raw["sha256"] != entry["raw_sha256"]:
        raise ReviewedSourceRejected("retained raw response hash differs")
    encodings = [v for k, v in entry["response_headers"].items() if k.casefold() == "content-encoding"]
    if len(encodings) > 1:
        raise ReviewedSourceRejected("ambiguous content encoding")
    content = decode_response_text(Path(raw["path"]).read_bytes(), encodings[0] if encodings else None)
    return content, {"artifact": _binding(path), "entry_name": name,
        "raw_response": raw, "endpoint": entry["url"], "expected_content_hash": content_sha256(content)}


def _candidates():
    parent_content, parent_proof = _response("fetch-v1", "kgc-fy2024-40f-primary")
    del parent_content
    definitions = [
        ("KGC_AIF", "0000701818", "0001104659-25-028819", "40-F", "2025-03-27",
         "2025-03-27T20:55:21+00:00", "kgc-20241231x40f.htm", KGC_ROOT,
         "fetch-v3", "kgc-fy2024-99_1-annual_information_form", "99.1", "kgc-20241231xex99d1.htm"),
        ("KGC_MDA", "0000701818", "0001104659-25-028819", "40-F", "2025-03-27",
         "2025-03-27T20:55:21+00:00", "kgc-20241231x40f.htm", KGC_ROOT,
         "fetch-v3", "kgc-fy2024-99_2-annual_management_discussion", "99.2", "kgc-20241231xex99d2.htm"),
        ("MS_Q1", "0000895421", "0000895421-25-000343", "10-Q", "2025-05-05",
         "2025-05-05T20:13:06+00:00", "ms-20250331.htm", MS_ROOT,
         "fetch-v1", "ms-q12025-10q-primary", None, None),
    ]
    rows = []
    for name, cik, accession, form, filed, accepted, primary, root, version, entry, code, filename in definitions:
        content, body = _response(version, entry)
        exhibit = filename is not None
        role = "incorporated_exhibit" if exhibit else "primary"
        body.update(kind="sec_static_archive_body_response", document_role=role)
        metadata = {"source_url": body["endpoint"], "accession_number": accession,
                    "form": form, "provider": "sec_edgar", "cik": cik}
        document_id = "sec:cik_" + cik + ":" + accession.replace("-", "")
        proofs = [{"kind": "sec_submissions_root", "artifact": _binding(root), "issuer_cik": cik,
            "accession_number": accession, "form": form, "primary_document": primary,
            "filing_date": filed, "accepted_at": accepted}]
        if exhibit:
            body.update(exhibit_document=filename, exhibit_type=code)
            proofs.append({**parent_proof, "kind": "sec_parent_primary_response", "document_role": "primary"})
            metadata.update(parent_form=form, parent_primary_document=primary,
                exhibit_document=filename, document_role=role, exhibit_type=code)
            document_id = "sec-exhibit:cik_" + cik + ":" + accession.replace("-", "") + ":" + filename
        else:
            proofs.append({"kind": "sec_submissions_linked_archive", "artifact": _binding(MS_ARCHIVE),
                           "filename": "CIK0000895421-submissions-003.json"})
        proofs.append(body)
        document = RawInfoDocument.create(document_id=document_id, company_id="cik_" + cik,
            source_type="filing", published_at=datetime.fromisoformat(accepted),
            available_at=datetime.fromisoformat(accepted), content=content, metadata=metadata)
        rows.append({"candidate": name, "document": document.to_dict(), "proofs": proofs,
            "proof_profile": "sec_filing_exhibit_response_v1" if exhibit else "sec_filing_response_acceptance_v1",
            "content_scope": "whole annual AIF" if name == "KGC_AIF" else
                "whole annual MD&A; audited FS99.3 remains unfetched" if exhibit else "whole Q1 interim report",
            "semantic_review": _binding(PERIODIC / ("annual-exhibit-content-review.json" if exhibit else "primary-content-review.json"))})
    return rows


def _qualify(candidates, cases):
    payload_memo, raw_memo = {}, {}
    for candidate in candidates:
        if candidate["proof_profile"] not in {"sec_filing_response_acceptance_v1", "sec_filing_exhibit_response_v1"}:
            raise ReviewedSourceRejected("unsupported periodic proof profile")
        document = RawInfoDocument.from_dict(candidate["document"])
        matches = [case for case in cases if case["company_id"] == document.company_id]
        if len(matches) != 1:
            raise ReviewedSourceRejected("periodic candidate has no unique original case")
        kinds = [proof["kind"] for proof in candidate["proofs"]]
        if len(kinds) != len(set(kinds)):
            raise ReviewedSourceRejected("duplicate periodic proof kind")
        proofs = {proof["kind"]: (proof, financial._read_bound(proof["artifact"])[1])
                  for proof in candidate["proofs"]}
        _verify_sec_response_document(document, {"reviewed_available_at": document.available_at.isoformat()},
            proofs, datetime.fromisoformat(matches[0]["cutoff"]), payload_memo, raw_memo,
            exhibit=candidate["proof_profile"] == "sec_filing_exhibit_response_v1")


def _data_bindings(review, inputs, old_plan):
    bindings = [review["oracle_identity"], *old_plan["source_bindings"], *inputs["normalizations"]]
    for row in review["records"]:
        bindings.append(row["original_record"])
        bindings.extend(proof["artifact"] for proof in row["proofs"])
    for normalization in inputs["normalizations"]:
        value = _read(normalization["path"])
        bindings.extend([value["source_cache"], value["raw_response"]])
    return sorted({item["path"]: item for item in bindings}.values(), key=lambda item: item["path"])


def _code_bindings():
    specs = [OWNING_SPEC, financial.OWNING_SPEC, *financial.SOURCE_SPECS,
        REPO / "spec/src/stock_opportunity_agent/data/reviewed_sec_response_profile.md",
        REPO / "spec/src/stock_opportunity_agent/research/basic_info_orientation.md",
        REPO / "spec/src/stock_opportunity_agent/signal_library.md"]
    return [_binding(path) for path in [Path(__file__), Path(financial.__file__),
        REPO / "scripts/run_minimal_rounds.py", *specs,
        *sorted((REPO / "src/stock_opportunity_agent").rglob("*.py"))]]


def prepare(output):
    """Freeze new local candidates and proofs without opening the global store."""
    with _source_only():
        return _prepare(Path(output).resolve())


def _prepare(output):
    if output.exists():
        raise ReviewedSourceRejected("periodic diagnostic output must be new")
    authorities = [{"path": str(path.resolve()), "sha256": sha} for path, sha in FIXED_AUTHORITIES.items()]
    _check_bindings(authorities)
    inputs = _read(FINANCIAL / "input_manifest.json")
    old_plan = _read(FINANCIAL / "plan.json")
    review = _read(inputs["source_review"]["path"])
    if (canonical_json_hash({k: v for k, v in old_plan.items() if k != "plan_hash"}) != old_plan["plan_hash"]
            or canonical_json_hash({k: v for k, v in review.items() if k != "manifest_hash"}) != review["manifest_hash"]):
        raise ReviewedSourceRejected("historical financial plan/review identity differs")
    oracle_root = Path(review["oracle_identity"]["path"]).resolve().parent
    if output.is_relative_to(oracle_root) or oracle_root.is_relative_to(output):
        raise ReviewedSourceRejected("new diagnostic must be outside actual oracle")
    cases = _read(old_plan["inventory"]["path"])["cases"]
    if len(cases) != 15 or len({row["case_id"] for row in cases}) != 15 or len(review["records"]) != 655:
        raise ReviewedSourceRejected("fixed 15 cases / 655 old review records differ")
    if {verdict: sum(row["verdict"] == verdict for row in review["records"])
            for verdict in ("admitted", "excluded", "unknown")} != {"admitted": 650, "excluded": 1, "unknown": 4}:
        raise ReviewedSourceRejected("old admitted/excluded/unknown dispositions differ")
    snapshot_rows = _read(Path(inputs["reviewed_source_snapshot"]["root"]) / "reviewed_snapshot.json")
    if len(snapshot_rows["documents"]) != 650:
        raise ReviewedSourceRejected("old 650 admitted documents differ")
    data_bindings = _data_bindings(review, inputs, old_plan)
    _check_bindings(data_bindings + [inputs["source_review"], inputs["plan"], old_plan["inventory"],
        old_plan["registry_source_inputs"], *old_plan["registry_bindings"]])
    candidates = _candidates()
    try:
        _qualify(candidates, cases)
    except Exception as exc:
        atomic_write_json(output / "candidate-failure.json", {"status": "unknown_profile_rejected",
            "error_type": type(exc).__name__, "error": str(exc), "global_appends": 0})
        raise
    candidate_bindings = []
    for candidate in candidates:
        path = output / "candidates" / (candidate["candidate"] + ".json")
        atomic_write_json(path, candidate)
        candidate_bindings.append(_binding(path))
    plan = {"schema_version": "fixed-periodic-operating-plan-v1", "cases": cases,
        "fixed_authorities": authorities,
        "fixed_case_denominator": 15, "signal_ref_denominator": 18, "resolution_denominator": 270,
        "old_source_review": inputs["source_review"], "oracle_identity": review["oracle_identity"],
        "old_financial_tree": _tree(FINANCIAL), "old_source_bindings": data_bindings,
        "source_bindings": [_binding(path) for path in [KGC_ROOT, MS_ROOT, MS_ARCHIVE,
            PERIODIC / "inventory.json", PERIODIC / "proposal.json", PERIODIC / "annual-pointer.json",
            PERIODIC / "primary-content-review.json", PERIODIC / "annual-exhibit-content-review.json",
            PERIODIC / "ms-annual-clock-review.json"]] +
            [binding for version in ("fetch-v1", "fetch-v2", "fetch-v3") for binding in _tree(PERIODIC / version)],
        "candidates": candidate_bindings, "candidate_denominator": len(candidates),
        "old_admitted_document_count": 650, "old_review_row_count": 655,
        "registry_source_inputs": old_plan["registry_source_inputs"],
        "registry_bindings": old_plan["registry_bindings"], "registry_version": old_plan["registry_version"],
        "registry_hash": old_plan["registry_hash"], "registry_refs": old_plan["registry_refs"],
        "excluded_unresolved": [{"candidate": "MS_FY2024_annual", "verdict": "unknown",
            "reason": "Whole body substantive; API/header acceptance time conflict unresolved; not an append candidate.",
            "clock_review": _binding(PERIODIC / "ms-annual-clock-review.json")}],
        "code_bindings": _code_bindings(), "network_allowed": False, "model_allowed": False,
        "labels_allowed": False, "signal_apply_allowed": False, "full_prepare_allowed": False}
    plan["plan_hash"] = canonical_json_hash(plan)
    atomic_write_json(output / "plan.json", plan)
    return plan


def _verify_plan(output):
    plan = _read(output / "plan.json")
    if canonical_json_hash({k: v for k, v in plan.items() if k != "plan_hash"}) != plan["plan_hash"]:
        raise ReviewedSourceRejected("new periodic plan hash differs")
    if (plan["schema_version"] != "fixed-periodic-operating-plan-v1"
            or (plan["fixed_case_denominator"], plan["signal_ref_denominator"], plan["resolution_denominator"],
                plan["candidate_denominator"], plan["old_admitted_document_count"], plan["old_review_row_count"]) != (15, 18, 270, 3, 650, 655)
            or any(plan[key] is not False for key in ("network_allowed", "model_allowed", "labels_allowed",
                                                    "signal_apply_allowed", "full_prepare_allowed"))):
        raise ReviewedSourceRejected("periodic scope or forbidden operation differs")
    for name in ("fixed_authorities", "old_financial_tree", "old_source_bindings", "source_bindings", "candidates", "registry_bindings", "code_bindings"):
        _check_bindings(plan[name])
    _check_bindings([plan["old_source_review"], plan["oracle_identity"], plan["registry_source_inputs"]])
    if _tree(FINANCIAL) != plan["old_financial_tree"]:
        raise ReviewedSourceRejected("old completed financial artifact inventory differs")
    return plan


def execute(output):
    """Execute a separately reviewed freeze once, with source-only tripwires."""
    with _source_only():
        return _execute(Path(output).resolve())


def _execute(output):
    plan = _verify_plan(output)
    with (output / "execution-start.json").open("x", encoding="utf-8") as handle:
        json.dump({"plan_hash": plan["plan_hash"], "started_at": datetime.now(timezone.utc).isoformat()}, handle)
        handle.flush()
        import os
        os.fsync(handle.fileno())
    candidates = [_read(binding["path"]) for binding in plan["candidates"]]
    _qualify(candidates, plan["cases"])
    _verify_plan(output)
    oracle_root = Path(plan["oracle_identity"]["path"]).parent
    started = monotonic()
    before = _tree(oracle_root)
    atomic_write_json(output / "global-originals-before.json", before)
    timings = {"hash_global_seconds": monotonic() - started}
    started = monotonic()
    store = RawInfoStore(root=oracle_root)
    timings["global_store_initial_load_seconds"] = monotonic() - started
    old_review = _read(plan["old_source_review"]["path"])
    receipts, new_rows, expected_paths = [], [], []
    started = monotonic()
    for candidate in candidates:
        document = RawInfoDocument.from_dict(candidate["document"])
        inserted = store.append(document)
        financial._require_same_record(store.load(document.document_id), document)
        original = _binding(oracle_root / document.source_type / document.company_id / (document.document_id + ".json"))
        receipt = {"candidate": candidate["candidate"], "document_id": document.document_id,
            "append_returned_true": inserted, "complete_canonical_load_equal": True, "original_record": original}
        atomic_write_json(output / "append-receipts" / (candidate["candidate"] + ".json"), receipt)
        receipts.append(receipt)
        expected_paths.append(original["path"])
        new_rows.append({"document_id": document.document_id, "company_id": document.company_id,
            "content_hash": document.content_hash, "original_record": original, "verdict": "admitted",
            "reviewed_available_at": document.available_at.isoformat(), "proof_profile": candidate["proof_profile"],
            "content_scope": candidate["content_scope"], "semantic_review": candidate["semantic_review"],
            "reason": "Whole retained body independently reviewed; exact native SEC response proof; external references remain incomplete.",
            "proofs": candidate["proofs"]})
        print(candidate["candidate"] + ": native append and full canonical load verified", flush=True)
    timings["append_and_load_seconds"] = monotonic() - started
    additions = financial._check_global(before, oracle_root, expected_paths)
    atomic_write_json(output / "append-inventory.json", {"receipts": receipts, "global_new_files": additions})
    review = deepcopy(old_review)
    review.pop("manifest_hash", None)
    review["records"].extend(new_rows)
    review["status"] = "reviewed_periodic_operating_sources"
    review["original_oracle_writes"] = sum(row["append_returned_true"] for row in receipts)
    review["scope"]["purpose"] = "Fixed15 cases: unchanged financial review plus whole KGC AIF/MD&A and MS Q1; input-only qualification."
    review["manifest_hash"] = canonical_json_hash(review)
    review_path = output / "source-review.json"
    atomic_write_json(review_path, review)
    started = monotonic()
    view = materialize_reviewed_snapshot(review_path, output / "snapshot")
    reviewed = open_raw_info_store(view["root"], reviewed_snapshot=view)
    worker = reviewed.snapshot()
    timings["materialize_load_worker_seconds"] = monotonic() - started
    snapshot = financial._registry(plan["registry_source_inputs"]["path"], output)
    if snapshot.registry_hash != plan["registry_hash"] or [spec.ref for spec in snapshot.specs] != plan["registry_refs"]:
        raise ReviewedSourceRejected("exact v12 definition authority differs")
    resolver = _build_evidence_resolver(output / "runtime", worker,
        contract=SimpleNamespace(data_acquisition=DataAcquisitionPolicy()), allow_data_external=False, environ={}, cycle_id=1)
    executor = SignalExecutor(snapshot, worker, resolver=resolver)
    summaries = []
    started = monotonic()
    for case in plan["cases"]:
        cutoff = datetime.fromisoformat(case["cutoff"])
        identity = {"ticker": case["ticker"], "cik": case["company_id"].removeprefix("cik_")}
        bundle = resolver.resolve_basic_info(compile_basic_info_requests(default_information_plan().basic_info_policy),
            company_id=case["company_id"], identity=identity, as_of=cutoff)
        model, lineage = project_basic_info_bundle(bundle)
        resolutions = executor.prepare_inputs(tuple(plan["registry_refs"]), company_id=case["company_id"], as_of=cutoff, identity=identity)
        ready = sum(item.status == "resolved" for item in resolutions)
        summary = {"case_id": case["case_id"], "resolved_signal_inputs": ready, "signal_ref_denominator": 18,
            "resolved_fraction": ready / 18, "meets_existing_0_8_signal_input_fraction": ready / 18 >= 0.8}
        atomic_write_json(output / "cases" / (case["case_id"] + ".json"), {"case": case, "summary": summary,
            "basic_info_bundle": bundle.to_dict(), "basic_info_model": model, "basic_info_lineage": lineage,
            "exact_signal_input_resolutions": [{"signal_ref": ref, "resolution": resolution.to_dict()}
                for ref, resolution in zip(plan["registry_refs"], resolutions, strict=True)]})
        summaries.append(summary)
        print(case["ticker"] + ": default BasicInfo projected; exact-v12 inputs " + str(ready) + "/18", flush=True)
    timings["input_only_consumers_seconds"] = monotonic() - started
    inputs = {"schema_version": "fixed-periodic-operating-inputs-v1", "plan": _binding(output / "plan.json"),
        "source_review": _binding(review_path), "reviewed_source_snapshot": view,
        "new_originals": [row["original_record"] for row in new_rows], "old_source_review": plan["old_source_review"],
        "registry_version": snapshot.version, "registry_hash": snapshot.registry_hash, "registry_refs": plan["registry_refs"],
        "fixed_case_denominator": 15, "fixed_resolution_denominator": 270, "excluded_unresolved": plan["excluded_unresolved"]}
    atomic_write_json(output / "input_manifest.json", inputs)
    input_hash = canonical_json_hash(inputs)
    restored = open_raw_info_store(view["root"], reviewed_snapshot=_read(output / "input_manifest.json")["reviewed_source_snapshot"])
    if (not financial._same_document_set(restored.documents, reviewed.documents)
            or not financial._same_document_set(worker.documents, reviewed.documents)
            or type(restored) is not type(worker)
            or canonical_json_hash(_read(output / "input_manifest.json")) != input_hash):
        raise ReviewedSourceRejected("whole reviewed worker/restart/input differs")
    _verify_plan(output)
    _check_bindings(inputs["new_originals"])
    additions = financial._check_global(before, oracle_root, expected_paths)
    preserved = canonical_json_hash(review["records"][:len(old_review["records"])]) == canonical_json_hash(old_review["records"])
    if not preserved:
        raise ReviewedSourceRejected("old review dispositions differ")
    result = {"schema_version": "fixed-periodic-operating-result-v1", "plan_hash": plan["plan_hash"],
        "input_manifest_hash": input_hash, "fixed_case_denominator": 15, "fixed_resolution_denominator": 270,
        "new_product_count": len(new_rows), "newly_appended_products": sum(item["append_returned_true"] for item in receipts),
        "exact_replayed_products": sum(not item["append_returned_true"] for item in receipts),
        "review_record_count": len(review["records"]), "admitted_document_count": len(reviewed.documents),
        "old_review_655rows_preserved": preserved, "old_global_files_unchanged": True,
        "typed_view_worker_restart_equal": True, "global_new_files": additions, "cases": summaries,
        "cases_meeting_existing_0_8": sum(item["meets_existing_0_8_signal_input_fraction"] for item in summaries),
        "timings": timings, "network_requests": 0, "external_llm_calls": 0, "labels_loaded": False,
        "signal_apply_executed": False, "full_prepare_executed": False, "full48_readiness_proven": False,
        "engineering_mvp_closed": False, "excluded_unresolved": plan["excluded_unresolved"],
        "limitations": ["Whole originals are not necessarily wholly model-visible; actual default projections remain bounded.",
            "KGC audited FS99.3 and incorporated external references are not all retrieved or reviewed.",
            "MS annual API/header time conflict remains unresolved and excluded.",
            "Resolved input status proves neither Signal measurement nor model behavior or prediction benefit."]}
    atomic_write_json(output / "result.json", result)
    return result


def main():
    """Prepare a new freeze or execute that separately reviewed source-only plan."""
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = prepare(args.output) if args.prepare else execute(args.output)
    print(json.dumps({key: result[key] for key in ("schema_version", "plan_hash") if key in result}, indent=2))


if __name__ == "__main__":
    main()
