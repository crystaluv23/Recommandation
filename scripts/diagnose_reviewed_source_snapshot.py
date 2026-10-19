#!/usr/bin/env python3
"""Freeze and consume four reviewed local sources without network or model calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import socket

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import EvidenceResolver, RawInfoRequest
from stock_opportunity_agent.data.reviewed_snapshot import materialize_reviewed_snapshot, open_raw_info_store, ReviewedSourceRejected
from stock_opportunity_agent.models import ValidationError


def _binding(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def restore_inputs(path: Path, expected_hash: str):
    """Restore the exact new narrow input freeze through the production loader."""
    inputs = json.loads(path.read_bytes())
    if canonical_json_hash(inputs) != expected_hash:
        raise ReviewedSourceRejected("narrow source input freeze changed")
    binding = inputs["reviewed_source_snapshot"]
    return open_raw_info_store(binding["root"], reviewed_snapshot=binding)


def diagnose(review_path: Path, output: Path):
    """Preserve four-source scope, actual readiness failure and restored view."""
    if output.exists():
        raise ReviewedSourceRejected("diagnostic output must be new")
    review = json.loads(review_path.read_bytes())
    originals = [_binding(row["original_record"]["path"]) for row in review["records"]]
    binding = materialize_reviewed_snapshot(review_path, output / "snapshot")
    atomic_write_json(output / "snapshot_binding.json", binding)
    inputs = {"schema_version": "narrow-reviewed-source-stage-inputs-v1", "source_review": _binding(review_path),
        "reviewed_source_snapshot": binding, "fixed_source_denominator": len(review["records"]),
        "scope": review["scope"], "full_approved_dataset_freeze": False, "model_calls_authorized": False}
    atomic_write_json(output / "input_manifest.json", inputs)
    input_hash = canonical_json_hash(inputs)
    store = restore_inputs(output / "input_manifest.json", input_hash)
    worker = store.snapshot()
    cutoff = datetime.fromisoformat(review["scope"]["as_of"])
    resolver = EvidenceResolver(worker)
    outcomes = []
    for row in review["records"]:
        if row["verdict"] == "admitted":
            document = store.load(row["document_id"], as_of=cutoff)
            try:
                store.load(document.document_id, as_of=document.available_at - timedelta(seconds=1))
                before_rejected = False
            except ValidationError:
                before_rejected = True
            at = store.load(document.document_id, as_of=document.available_at)
            resolution = resolver.resolve(RawInfoRequest("admitted-" + str(len(outcomes)), "Read scoped SEC filing", ("filing",)),
                company_id=document.company_id, identity={}, as_of=document.available_at)
            resolved_documents = resolver.load_documents(resolution, as_of=document.available_at)
            outcomes.append({"document_id": row["document_id"], "verdict": row["verdict"],
                "before_one_second_rejected": before_rejected, "exact_instant_loaded": at == document,
                "exact_replay_added": store.append(document), "content_hash": document.content_hash,
                "available_at": document.available_at.isoformat(), "resolution": resolution.to_dict(),
                "resolver_original_document_loaded": document in resolved_documents})
        else:
            source_type = "news" if row["verdict"] == "excluded" else "earnings_call"
            resolution = resolver.resolve(RawInfoRequest("review-gap-" + source_type, "Read scoped original source", (source_type,)),
                company_id=row["company_id"], identity={}, as_of=cutoff)
            outcomes.append({"document_id": row["document_id"], "verdict": row["verdict"],
                "resolution": resolution.to_dict(), "is_gap": resolution.gap is not None,
                "negative_company_observation": False})
    bad = RawInfoDocument.from_dict(json.loads(Path(review["records"][2]["original_record"]["path"]).read_bytes()))
    old = EvidenceResolver(RawInfoStore(documents=(bad,))).resolve(
        RawInfoRequest("old-news", "Read original provider summary", ("news",)),
        company_id=bad.company_id, identity={}, as_of=cutoff, include_context=True)
    raw_bad_hash = _binding(review["records"][2]["original_record"]["path"])
    try:
        worker.append(bad)
        append_rejected = False
    except ReviewedSourceRejected:
        append_rejected = True
    # This view has one issuer/two filings, so the unchanged full 48-case
    # production selection must fail readiness rather than shrink its cohort.
    from run_minimal_rounds import prepare
    try:
        prepare(output / "full_preflight", reviewed_source_snapshot=output / "snapshot_binding.json")
        preflight = {"status": "unexpected_full_readiness"}
    except ValidationError as exc:
        preflight = {"status": "full_readiness_rejected", "reason": str(exc),
            "failure_artifact": _binding(output / "full_preflight/preparation_failure.json")}
    result = {"schema_version": "reviewed-source-snapshot-diagnostic-v1", "input_manifest_hash": input_hash,
        "reviewed_source_snapshot": binding, "original_bindings": originals, "outcomes": outcomes,
        "admitted_document_ids": [doc.document_id for doc in store.documents],
        "worker_preserves_review_type": type(worker) is type(store), "excluded_append_rejected": append_rejected,
        "legacy_original_news_resolution": old.to_dict(), "legacy_news_original_binding": raw_bad_hash,
        "legacy_news_temporal_lookup_still_resolves": old.status == "resolved",
        "minimal_full_preflight": preflight, "original_records_unchanged": originals == [_binding(row["original_record"]["path"]) for row in review["records"]],
        "external_api_calls": 0, "new_model_responses": 0, "full_dataset_readiness_proven": False,
        "signal_semantics_or_prediction_quality_proven": False, "engineering_mvp_closed": False,
        "code_bindings": [_binding(Path(__file__)), *[_binding(Path("src/stock_opportunity_agent") / name) for name in (
            "data/reviewed_snapshot.py", "data/resolution.py", "research/evolution_control.py", "research/signal_evolution.py")],
            _binding(Path(__file__).parent / "run_minimal_rounds.py")]}
    result["narrow_boundary_checks_passed"] = (
        len(outcomes) == 4 and len(store.documents) == 2 and result["original_records_unchanged"]
        and result["worker_preserves_review_type"] and append_rejected
        and preflight["status"] == "full_readiness_rejected"
        and all((row["before_one_second_rejected"] and row["exact_instant_loaded"]
                 and not row["exact_replay_added"] and row["resolver_original_document_loaded"])
                if row["verdict"] == "admitted" else row["is_gap"] for row in outcomes))
    atomic_write_json(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network forbidden in reviewed source diagnostic")
    socket.socket = forbidden
    result = diagnose(args.review.resolve(), args.output.resolve())
    print(json.dumps({key: value for key, value in result.items() if key not in {"legacy_original_news_resolution", "outcomes", "original_bindings", "code_bindings"}}, indent=2))


if __name__ == "__main__":
    main()
